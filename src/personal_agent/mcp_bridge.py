"""Minimal stdio MCP bridge; AgentOS, never the engine, owns tool execution.

The protocol version comes from the mcp-types registry, but that
package's envelope models are deliberately not adopted: JSONRPCRequest
accepts an unknown top-level key and model_dump then drops it, so a
request this bridge rejects would be normalised into a clean-looking
one and forwarded. Envelope validation stays hand-written here.
"""
import argparse
import json
import sys
import time

from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS, LATEST_HANDSHAKE_VERSION

from .agent_runtime import (CLI_LOOKUP_HINT, ENGINE_UNMEDIATED, Capabilities, evidence_summary, lookup_sources,
                            recorded_private_sources, work_source_records)
from .bounded_execution import AgentOSMcpTools, ExecutionError, profile_actions, redact_reason
from .local_tools import LocalTools
from .quickstart_store import QuickStore


def negotiated_protocol_version(offered):
    """Return the handshake revision this bridge will speak with the peer.

    The registry comes from ``mcp_types`` so the supported set tracks the
    official SDK instead of a hand-maintained literal.  ``initialize`` is a
    handshake method, so the counter-offer is the newest *handshake* revision;
    ``LATEST_PROTOCOL_VERSION`` may name a stateless per-request revision this
    bridge does not implement.  An unknown or non-string offer is never echoed.
    """
    if isinstance(offered, str) and offered in HANDSHAKE_PROTOCOL_VERSIONS:
        return offered
    return LATEST_HANDSHAKE_VERSION


def _send(value):
    sys.stdout.write(json.dumps(value, ensure_ascii=False) + "\n"); sys.stdout.flush()


def _provenance(labels):
    """Egress-taint labels handed over by the AgentOS process for this Work.

    The bridge runs as a separate process, so the Work's private-source
    provenance (same-turn sources and conversation history) must be passed
    in explicitly.  Any label -- known or not -- is kept: an unknown label
    still closes public egress, never opens it.
    """
    return {str(label) for label in labels or () if str(label).strip()}


def _work_running(store, job_id):
    """The bridge acts for exactly one Work, and only while it is running.

    Discovery (``tools/list``) grants nothing; every call rechecks that the
    Work named on the command line exists in this owner store and is still
    ``running``.  A finished, interrupted or foreign Work id is refused, so a
    bridge that outlives its turn cannot keep acting for it.
    """
    # Time-of-check bound: the check runs before each call, so a Work that
    # ends *during* a call may still see that one in-flight call finish.  It
    # is bounded by that call's own deadlines (search 15 s, weather 10 s + 15 s,
    # each research page read 12 s) and no further call starts.
    job = store.job(job_id) if isinstance(job_id, str) and job_id else None
    return bool(job) and job.get('status') == 'running'


def _recorded_private_sources(store, job_id, tools=None):
    """Private-source labels this Work already carries in durable state.

    Taint used to live only in one bridge process: a second bridge started for
    the same running Work (a CLI restarting its MCP server) received only the
    argv ``--provenance`` labels and forgot a ``list_notes`` the first one had
    served.  The bridge rehydrates on start and before every call from the
    Work's successful ``tool_events`` (``recorded_private_sources``) and, since
    #605, from the Work's source record written before model use, which also
    carries the history-window sources the Work was shown.  A missing record
    adds nothing here: the host always passes the same labels on argv.
    """
    labels = recorded_private_sources(store, job_id, tools)
    record = work_source_records(store).get(job_id)
    if isinstance(record, list):
        # A CLI's unmediated-read label concerns its *reply* for later Works,
        # not this Work's own inputs (#605 F1).
        labels |= {str(label) for label in record if str(label).strip() and str(label) != ENGINE_UNMEDIATED}
    return labels


def _lookup_sources(store, job_id):
    """The same permitted-text resolver the host uses (#605)."""
    return lambda: lookup_sources(store, job_id)


def _restrictive(store):
    return (store.config('egress_composition', {}) or {}).get('mode') == 'restrictive'


def _lookup_sensitivity(store, job_id):
    """The host's DecisionEngine judgment path (#605 N3), built on first use.

    The bridge has no service of its own, so the first lookup that would send
    words of the owner's current message builds one ``AgentService`` over the
    same store and asks its ``decision_judge`` -- the same route, context
    bounds and audit as the host.  Any failure is an unavailable judgment,
    which ``Capabilities`` answers with its fail-safe policy.
    """
    built = {}

    def judge(message, terms):
        if 'judge' not in built:
            from .quickstart_service import AgentService
            service = AgentService(store)
            service.current_work_id = job_id
            built['judge'] = service.decision_judge
        return built['judge'].lookup_term_sensitivity(message, terms)
    return judge


def serve(data, job_id, provenance=(), judge=None):
    store = QuickStore(data)
    def record(tool, status, detail):
        with store.db() as db:
            db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)', (job_id,tool,status,detail,time.time()))
    # #604: the Work's allowed actions are the bounded CLI profile; names and
    # schemas come from Capabilities.definitions(), never a bridge-local list.
    capabilities = Capabilities(store, None, {}, '', job_id, record, network=LocalTools(), document_access=False,
                                allowed_tools=set(profile_actions(AgentOSMcpTools.PROFILE)),
                                inherited_provenance=_provenance(provenance), lookup_hint=CLI_LOOKUP_HINT,
                                lookup_sources=_lookup_sources(store, job_id), lookup_restrictive=_restrictive(store),
                                lookup_sensitivity=judge or _lookup_sensitivity(store, job_id))
    capabilities.private_provenance.update(_recorded_private_sources(store, job_id, capabilities.tools))
    tools = AgentOSMcpTools(capabilities)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            method, ident = request.get('method'), request.get('id')
            if method == 'initialize':
                params = request.get('params')
                offered = params.get('protocolVersion') if isinstance(params, dict) else None
                result = {'protocolVersion':negotiated_protocol_version(offered),'capabilities':{'tools':{}},'serverInfo':{'name':'agentos','version':'1'}}
            elif method == 'tools/list': result = {'tools': tools.definitions()}
            elif method == 'tools/call':
                params = request.get('params', {}); name = params.get('name')
                # A CLI-chosen name is stored only when it is an offered tool.
                listed = name if isinstance(name, str) and name in capabilities.allowed_tools else 'unlisted'
                try:
                    if not _work_running(store, job_id):
                        raise ExecutionError('이 작업은 더 이상 실행 중이 아니어서 도구를 실행하지 않았습니다.')
                    capabilities.private_provenance.update(_recorded_private_sources(store, job_id, capabilities.tools))
                    value = tools.call(name, params.get('arguments', {}))
                except (ValueError, ExecutionError, TypeError) as exc:
                    # Redacted recovery metadata: the reason, never the arguments.
                    record(listed, 'failed',
                           json.dumps({'scope':'subscription-mcp-bridge','error':redact_reason(str(exc))}, ensure_ascii=False))
                    raise
                # The same redacted Evidence the direct route records
                # (sources, attempted/failed URLs, counts), never the payload.
                host_action = capabilities.tools[name]['host_action']
                record(name, 'succeeded', json.dumps({'scope':'subscription-mcp-bridge','host_action':host_action,
                                                       'evidence':evidence_summary(host_action, value)}, ensure_ascii=False))
                result = {'content':[{'type':'text','text':json.dumps(value, ensure_ascii=False)}]}
            elif method == 'notifications/initialized': continue
            else: raise ExecutionError('Unsupported MCP request.')
            if ident is not None: _send({'jsonrpc':'2.0','id':ident,'result':result})
        except (ValueError, ExecutionError, TypeError) as exc:
            if isinstance(locals().get('request'),dict) and request.get('id') is not None:
                _send({'jsonrpc':'2.0','id':request['id'],'error':{'code':-32602,'message':'AgentOS MCP request rejected.'}})


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--data',required=True); parser.add_argument('--job',required=True)
    parser.add_argument('--provenance',action='append',default=[])
    args=parser.parse_args(); serve(args.data, args.job, args.provenance)

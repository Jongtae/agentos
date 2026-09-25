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

from .agent_runtime import Capabilities
from .bounded_execution import AgentOSMcpTools, ExecutionError
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


def serve(data, job_id, provenance=()):
    store = QuickStore(data)
    def record(tool, status, detail):
        with store.db() as db:
            db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)', (job_id,tool,status,detail,time.time()))
    tools = AgentOSMcpTools(Capabilities(store, None, {}, '', job_id, record, network=LocalTools(), document_access=False,
                                         allowed_tools={'list_notes','save_note','web_search'},
                                         inherited_provenance=_provenance(provenance)))
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
                params = request.get('params', {}); value = tools.call(params.get('name'), params.get('arguments', {}))
                record(params.get('name'), 'succeeded', json.dumps({'scope':'subscription-mcp-bridge'}, ensure_ascii=False))
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

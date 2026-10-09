"""Minimal stdio MCP bridge; AgentOS, never the engine, owns tool execution.

The host-only MCP SDK owns stdio framing and JSON-RPC response correlation.
AgentOS retains handshake negotiation, the supported method/tool profiles,
serialized execution and Work/Grant/secret/effect/Event/Evidence callbacks.
The isolated engine bridge keeps its separate envelope contract.
"""
import argparse
import json
import sys
import time

from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS, LATEST_HANDSHAKE_VERSION

from .agent_runtime import (ENGINE_UNMEDIATED, OWNER_STATE_ACTIONS, TRANSIENT_FAILURE_TEXT,
                            Capabilities, ToolError, WorkBudget, WorkLedger, classify_failure, declared_effect,
                            claim_owner_steers, evidence_summary, lookup_sources, progress_step, worker_result, recorded_private_sources, split_status, work_source_records,
                            work_stop_requested)
from .current_context import redact_known_secrets
from .providers import ProviderError
from .bounded_execution import (AgentOSMcpTools, BOUNDED_PROFILE, HOST_CLI_PROFILES, STRICT_PROFILE, ExecutionError,  # noqa: F401
                                profile_actions, redact_reason, turn_actions)
from .skills import SkillBinding, SkillLibrary
from .cli_browser_relay import (RELAYED_INFORMATION_USE, RELAYED_LOCATION_REQUEST, RELAYED_PREPARATIONS, RELAYED_SETTINGS,
                                RelayClient, unused_browser_factory)
from .context_observations import answerable_work
from .local_tools import LocalTools
from .search_providers import ProviderRegistry
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


class _AllInlineMethods(frozenset):
    """Make every request use the dispatcher's documented inline path.

    The public API accepts a frozenset and checks membership.  AgentOS must
    serialize supported and rejected requests alike: otherwise the SDK cancels
    a final unknown-method task as soon as stdin reaches EOF, before its error
    is written.  The exact SDK pin and contract tests cover this small wildcard
    adaptation until upstream offers an explicit all-inline mode.
    """

    def __contains__(self, value):
        return True


def _serve_stdio(handle):
    """Adapt the exact-pinned SDK's public dispatcher to AgentOS callbacks.

    Imports stay here so importing the host facade does not require the SDK
    in the isolated engine's base package. No SDK Server/session registration
    is used: it would add methods and require a different initialize shape.
    """
    import anyio
    from mcp import MCPError
    from mcp.server.stdio import stdio_server
    from mcp.shared.jsonrpc_dispatcher import JSONRPCDispatcher

    async def on_request(context, method, params):
        if method == 'notifications/initialized':
            # This is notification-only; do not turn a malformed request
            # into a newly supported request method.
            raise MCPError(code=-32601, message='Method not found.')
        try:
            return handle(method, params)
        except _Rejected as exc:
            raise MCPError(**exc.rpc) from None
        except Exception:
            # The dispatcher otherwise logs the exception and sends its text,
            # which can contain owner payloads, destinations or credentials.
            raise MCPError(code=-32602, message='AgentOS MCP request rejected.') from None

    def handle_notification(method, params):
        # The old bridge also executed supported methods without an id.
        # Keep notification work in the read loop so EOF cannot cancel a
        # normalized no-id call before its durable evidence is recorded.
        try:
            handle(method, params)
        except Exception:
            pass

    async def on_notify(context, method, params):
        # Fallback for a future dispatcher that bypasses the interceptor.
        handle_notification(method, params)

    def on_notify_intercept(method, params):
        handle_notification(method, params)
        return True

    async def malformed_input(exc):
        # Invalid wire input has no trusted request id. Drop it without the
        # SDK's default debug log of the parser exception/payload, and never
        # attribute it to a previously consumed request.
        pass

    async def run():
        # In-process callers may inject text streams (including StringIO).
        # Real process stdio uses the SDK's fd claim and UTF-8 wrappers, keeping
        # stray handler/child output off the protocol wire.
        stdin = None if hasattr(sys.stdin, 'buffer') else anyio.wrap_file(sys.stdin)
        stdout = None if hasattr(sys.stdout, 'buffer') else anyio.wrap_file(sys.stdout)
        async with stdio_server(stdin=stdin, stdout=stdout) as (read_stream, write_stream):
            dispatcher = JSONRPCDispatcher(
                read_stream, write_stream,
                inline_methods=_AllInlineMethods(),
                peer_cancel_mode='signal', on_stream_exception=malformed_input,
            )
            # Inline callbacks have no awaits during tool execution. A later
            # call cannot overtake its predecessor or alter shared Work budget
            # and same-tool Event pairing. Owner Stop remains the Work gate.
            await dispatcher.run(on_request, on_notify, on_notify_intercept)

    anyio.run(run)


def _provenance(labels):
    """Private-source labels handed over by the AgentOS process for this Work.

    The bridge runs as a separate process, so the Work's private-source
    provenance (same-turn sources and conversation history) must be passed
    in explicitly.  Any label -- known or not -- is kept.  #826: the labels
    are a record for the Work's information-use audit, not an egress gate.
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
    """The same lookup resolver the host uses (#605): the running-Work binding and the Work's saved values."""
    return lambda: lookup_sources(store, job_id)


def approved_public_pages(store):
    """The owner's current approved public page addresses (#826).

    The exact normalized URLs the owner approved in Settings; read on every
    use, so a revoked approval refuses a later read.  On this route the
    approval is the owner's page grant itself; it is not bound to the
    direct-API model's fingerprint.
    """
    saved = store.config('public_page_sharing', {})
    if not isinstance(saved, dict) or saved.get('approved') is not True:
        return []
    return [url for url in saved.get('urls') or [] if isinstance(url, str)]


#: The Work this bridge serves has ended; a typed tool error, not a protocol one.
WORK_NOT_RUNNING = '이 작업은 더 이상 실행 중이 아니어서 도구를 실행하지 않았습니다.'
#: Returned for an untyped tool failure whose own text is not AgentOS's.
TOOL_FAILED_TEXT = 'AgentOS 도구가 이 요청을 처리하지 못했습니다. 다른 방법을 고르거나 소유자에게 필요한 정보를 물어보세요.'


class _Rejected(ExecutionError):
    """A JSON-RPC protocol error with its own code and fixed message (#607 AX-06)."""
    def __init__(self, code, message):
        super().__init__(message)
        self.rpc = {'code': code, 'message': message}


def tool_error_result(exc, action):
    """An MCP tool-result error carrying #607's typed recovery metadata.

    Normal tool failures are tool results (``isError``), not JSON-RPC protocol
    errors, so the CLI can tell a transient read failure from a denial, a
    setup need, the Work's Stop/deadline or an unknown effect.  The text is
    AgentOS's own: a typed ``ToolError`` or #605 input request verbatim, a fixed
    text otherwise (an exception's own text may quote a URL or credential).
    """
    code, retry, effect = classify_failure(exc, action)
    if code == 'input_required':
        # #605 D2: AgentOS's own fixed texts reach the CLI verbatim.
        text = str(exc)
    elif isinstance(exc, ToolError):
        text = str(exc)
    elif code == 'transient_failure':
        text = TRANSIENT_FAILURE_TEXT
    else:
        text = TOOL_FAILED_TEXT
    typed = {'code': code, 'retry': retry, 'effect': effect}
    if getattr(exc, 'requires', None):
        typed['requires'] = exc.requires
    return {'content': [{'type': 'text', 'text': text}], 'structuredContent': typed, 'isError': True}, typed


def unexpected_error_result(exc, action):
    """The typed tool result of an exception no tool layer maps (#735).

    Its class name only, never its text (it may quote a URL or credential).
    An effect-free read failed with no effect; any other action may have
    acted before it failed, so its effect is unknown and it is never replayed.
    """
    from .agent_runtime import EFFECT_FREE_READS
    read = action in EFFECT_FREE_READS
    typed = {'code': 'tool_failed', 'retry': 'permanent' if read else 'never', 'effect': 'none' if read else 'unknown',
             'exception': type(exc).__name__}
    return {'content': [{'type': 'text', 'text': TOOL_FAILED_TEXT}], 'structuredContent': typed, 'isError': True}, typed


def _with_steer(result, store, job_id, record):
    """#999: an owner message for this running Work rides on the tool result the worker reads next."""
    steer = claim_owner_steers(store, job_id, record)
    if steer and isinstance(result, dict) and isinstance(result.get('content'), list):
        result['content'].append({'type':'text','text':steer})
    return result


#: #1197: Claude Code's permission prompt for the owner's AI connector tools.
#: Listed only with ``--ai-connections``; never pre-approved, so a model call
#: to it is itself a permission prompt, which this tool refuses.
CONNECTOR_PERMISSION = 'connector_permission'
def _permission_text(decision):
    """Exactly one text block, as Claude Code requires of a permission prompt tool (observed, 2.1.280)."""
    return {'content': [{'type': 'text', 'text': json.dumps(decision, ensure_ascii=False)}]}


def serve(data, job_id, provenance=(), native_search=False, profile=BOUNDED_PROFILE, browser_relay=None,
          search_off_reason='', relay_browser=True, skills=(), ai_connections=False):
    """Serve one Work's AgentOS tools over stdio for the route profile the host named (#701).

    ``profile`` is ``trusted-local`` or ``strict-isolated``; anything else
    serves the strict set.  ``browser_relay`` (trusted-local only) is the
    service's relay directory: the browser tools are then listed and every
    browser call is executed by the service (``cli_browser_relay``); without
    it no browser tool is offered.  ``skills`` (trusted-local only, #961) are the
    ``package/name@digest`` refs of the host Work's skill binding; without any
    no skill tool is offered.
    """
    profile = profile if profile in HOST_CLI_PROFILES else STRICT_PROFILE
    relay = RelayClient(browser_relay) if browser_relay and profile == BOUNDED_PROFILE else None
    store = QuickStore(data)
    def record(tool, status, detail):
        with store.db() as db:
            db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)', (job_id,tool,status,detail,time.time()))
    # #604: the Work's allowed actions are the bounded CLI profile; names and
    # schemas come from Capabilities.definitions(), never a bridge-local list.
    # #826: the connected-folder documents and approved public pages the profile offers are
    # read here, within the folder grants (``Capabilities.roots``/``resolve_file``) and
    # the owner's page approval (``approved_public_pages``) the tools check on every call.
    capabilities = Capabilities(store, None, {}, '', job_id, record, network=LocalTools(providers=ProviderRegistry.from_store(store)), document_access=True,
                                public_page_scope=lambda: approved_public_pages(store),
                                # #774: owner-state tools run only in the service; without its relay they are not offered.
                                allowed_tools=(set(turn_actions(profile, native_search and profile == BOUNDED_PROFILE))
                                               - (set() if relay is not None else set(OWNER_STATE_ACTIONS))),
                                # #701: a placeholder that lists the browser tools; their calls go to the service.
                                browser=unused_browser_factory if relay is not None and relay_browser else None,
                                # #774: placeholders that list schedule_preparation and ask_location; their calls go to the service.
                                preparations=RELAYED_PREPARATIONS if relay is not None else None,
                                # ask_location only for a Work from the paired Telegram chat, as on the direct route.
                                location_request=(RELAYED_LOCATION_REQUEST if relay is not None
                                                  and answerable_work(store.job(job_id)) else None),
                                # #814: a placeholder that lists the settings tools; their calls go to the service.
                                settings=RELAYED_SETTINGS if relay is not None else None,
                                # #826: a placeholder that lists information_use; its calls go to the service.
                                information_use=RELAYED_INFORMATION_USE if relay is not None else None,
                                # #961: the exact skill revisions the host bound to this Work, read here from the store.
                                skills=(SkillBinding.from_refs(SkillLibrary(store), skills)
                                        if skills and profile == BOUNDED_PROFILE else None),
                                inherited_provenance=_provenance(provenance),
                                lookup_sources=_lookup_sources(store, job_id),
                                # #607 AX-10: the same durable attempt count and
                                # deadline as the host serving this Work.
                                budget=WorkBudget(stop=lambda: work_stop_requested(store, job_id),
                                                  ledger=WorkLedger(store, job_id)),
                                # #718: the same stored-secret pass as the host, for recorded step text.
                                secret_redactor=lambda text: redact_known_secrets(store, text))
    capabilities.private_provenance.update(_recorded_private_sources(store, job_id, capabilities.tools))
    tools = AgentOSMcpTools(capabilities, native_search=native_search and profile == BOUNDED_PROFILE)
    tools.PROFILE = profile
    tools.relay = relay
    tools.native_search_reason = str(search_off_reason or '')

    def handle(method, params):
        if method == 'initialize':
            offered = params.get('protocolVersion') if isinstance(params, dict) else None
            result = {'protocolVersion':negotiated_protocol_version(offered),'capabilities':{'tools':{}},'serverInfo':{'name':'agentos','version':'1'}}
        elif method == 'tools/list':
            from .agent_runtime import CONNECTOR_PERMISSION_DEFINITION
            from .bounded_execution import mcp_tool
            # Never read-only: a client must not auto-approve a direct call to it (review on #1197).
            extra = [mcp_tool(CONNECTOR_PERMISSION_DEFINITION, 'bounded_write', profile)] if ai_connections and relay else []
            result = {'tools': tools.definitions() + extra}
        elif method == 'tools/call' and ai_connections and relay and (params or {}).get('name') == CONNECTOR_PERMISSION:
            # #1197: the service decides (reads allowed, everything else refused for now)
            # and records the call; nothing here is shown to the model as a tool result.
            arguments = (params or {}).get('arguments') or {}
            try:
                decision = relay.call(CONNECTOR_PERMISSION, {'tool_name': arguments.get('tool_name'),
                                                             'input': arguments.get('input')})
            except Exception:
                decision = None
            if not isinstance(decision, dict) or decision.get('behavior') not in ('allow', 'deny'):
                decision = {'behavior': 'deny', 'message': 'AgentOS could not decide this action, so it was not run.'}
            return _permission_text(decision)
        elif method == 'tools/call':
            params = params or {}; name = params.get('name')
            # A CLI-chosen name is stored only when it is an offered tool.
            listed = name if isinstance(name, str) and name in capabilities.allowed_tools else 'unlisted'
            action = (capabilities.tools.get(listed) or {}).get('host_action') if listed != 'unlisted' else None
            if listed == 'unlisted' or name not in tools._offered():
                record(listed, 'failed', json.dumps({'scope':'subscription-mcp-bridge','code':'unknown_tool','retry':'permanent',
                                                     'effect':'none','error':'Unknown AgentOS MCP tool.'}))
                raise _Rejected(-32602, 'Unknown AgentOS MCP tool.')
            # #787: a browser call's declared effect, recorded on every event of the call.
            declared = {}
            try:
                if not _work_running(store, job_id):
                    raise ToolError(WORK_NOT_RUNNING, 'stopped')
                capabilities.private_provenance.update(_recorded_private_sources(store, job_id, capabilities.tools))
                arguments, status = split_status(params.get('arguments', {}))
                declared = declared_effect(action, arguments)
                if action:
                    # #607: a call is durably in flight before it runs, so a
                    # crash mid-call leaves an attempted (possibly effectful)
                    # action that retry/resume refuse to replay blindly.
                    # #718: with the call's bounded, redacted display step.
                    record(listed, 'running', json.dumps({'scope':'subscription-mcp-bridge','host_action':action,
                                                          'step':progress_step(action, arguments, status, capabilities.judgment_text),
                                                          **declared}, ensure_ascii=False))
                value = tools.call(name, arguments)
            except ExecutionError as exc:
                # Invalid arguments stay a protocol error (MCP: invalid
                # params).  Redacted: the reason, never the arguments.
                record(listed, 'failed',
                       json.dumps({'scope':'subscription-mcp-bridge','code':'invalid_arguments','retry':'permanent','effect':'none',
                                   'error':redact_reason(str(exc))}, ensure_ascii=False))
                raise _Rejected(-32602, 'Invalid AgentOS MCP tool arguments.') from None
            except (ValueError, TypeError, OSError, ProviderError) as exc:
                # #607 AX-06: a normal tool failure is a typed tool result.
                result, typed = tool_error_result(exc, action)
                record(listed, 'failed',
                       json.dumps({'scope':'subscription-mcp-bridge', **({'host_action':action} if action else {}), **typed,
                                   'error':redact_reason(str(exc)), **declared}, ensure_ascii=False))
                _with_steer(result, store, job_id, record)
                return result
            except Exception as exc:
                # #735: any other exception inside one call (an EOFError from a
                # helper process, an HTTP-library error type no layer maps) is a
                # typed failure of that call.  It used to end the bridge
                # process: the CLI saw its MCP connection close mid-call and
                # the Work recorded only a call that never completed.
                result, typed = unexpected_error_result(exc, action)
                record(listed, 'failed',
                       json.dumps({'scope':'subscription-mcp-bridge', **({'host_action':action} if action else {}), **typed,
                                   'error':redact_reason(TOOL_FAILED_TEXT), **declared}, ensure_ascii=False))
                _with_steer(result, store, job_id, record)
                return result
            # The same redacted Evidence the direct route records
            # (sources, attempted/failed URLs, counts), never the payload.
            host_action = capabilities.tools[name]['host_action']
            record(name, 'succeeded', json.dumps({'scope':'subscription-mcp-bridge','host_action':host_action,
                                                   'evidence':evidence_summary(host_action, value), **declared},
                                                  ensure_ascii=False))
            # #836: the worker reads a held memory write as the owner's one-tap ask, nothing more.
            result = {'content':[{'type':'text','text':json.dumps(worker_result(host_action, value), ensure_ascii=False)}]}
            _with_steer(result, store, job_id, record)
        elif method == 'notifications/initialized': return {}
        else: raise _Rejected(-32601, 'Method not found.')
        return result

    _serve_stdio(handle)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--data',required=True); parser.add_argument('--job',required=True)
    parser.add_argument('--provenance',action='append',default=[])
    parser.add_argument('--native-search',action='store_true')
    # #701: the host names the route profile (absent: the historical trusted-local set, as the
    # doctor's probe runs it; unknown: the strict set).  Only a service-created relay, handed to a
    # trusted-local bridge, ever lists a browser tool.
    parser.add_argument('--profile',default=BOUNDED_PROFILE)
    parser.add_argument('--search-off-reason',default='')
    parser.add_argument('--browser-relay',default=None)
    parser.add_argument('--relay-no-browser',action='store_true')
    parser.add_argument('--skill',action='append',default=[])
    parser.add_argument('--ai-connections',action='store_true')
    args=parser.parse_args()
    serve(args.data, args.job, args.provenance, native_search=args.native_search, profile=args.profile,
          browser_relay=args.browser_relay, search_off_reason=args.search_off_reason,
          relay_browser=not args.relay_no_browser, skills=args.skill, ai_connections=args.ai_connections)

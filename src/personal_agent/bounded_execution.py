"""Bounded subscription-engine execution owned by AgentOS.

This module is deliberately independent of the API-key provider path.  An
engine gets a fresh, empty working directory and a small MCP tool catalogue;
it never receives the owner store, a host path, or arbitrary shell access.
"""
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

from .manifests import CONTEXT_GATED_ACTIONS  # noqa: F401 (#627: re-exported for route checks)


MAX_PROMPT_BYTES = 48_000
#: The final answer record of one CLI turn (#736: the record, never the whole stream).
MAX_OUTPUT_BYTES = 96_000
#: #736: a runaway guard on the whole machine-output stream of one CLI turn.  The
#: stream carries every tool result (mediated browser pages included), so it is
#: far larger than the answer; only the final record is bounded by
#: ``MAX_OUTPUT_BYTES``.
MAX_STREAM_BYTES = 8_000_000
FINAL_RECORD_TOO_LARGE = f'엔진의 최종 응답 기록이 안전한 크기 제한({MAX_OUTPUT_BYTES // 1000}KB)을 초과했습니다.'
STREAM_TOO_LARGE = f'엔진 출력 전체가 안전한 크기 제한({MAX_STREAM_BYTES // 1_000_000}MB)을 초과했습니다.'
# One CLI turn may use up to the Work's whole shared budget (agent_runtime
# WORK_DEADLINE_SECONDS); the remaining budget always bounds it (#607 AX-10).
# The earlier fixed 120 s cap (#118) cut off multi-step browser work.
MAX_TIMEOUT_SECONDS = 600
MAX_REASON_CHARS = 300

LOG = logging.getLogger('personal_agent.engine')
ENGINE_NAMES = {'codex': 'Codex', 'claude-code': 'Claude Code'}
_SECRET = re.compile(r'(?i)\bauthorization["\']?\s*[=:]\s*["\']?(?:[a-z]+\s+)?[^\s"\',}]+|\b(?:bearer|basic)\s+\S+|\b(?:sk|pk|rk)-[A-Za-z0-9_-]{8,}|\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{10,}|\bAIza[0-9A-Za-z_-]{30,}|\b\d{6,}:[A-Za-z0-9_-]{30,}|["\']?\b(?:api[_-]?key|access[_-]?token|token|secret|password)["\']?\s*[=:]\s*["\']?[^\s"\',}]+')
_ECHO_WINDOW = 24
_CONTROL = re.compile(r'[\x00-\x1f\x7f]+')
# Hints are keyed by the provider's structured HTTP status, never by guessing
# from free text.  An unknown status keeps only the observed reason.
_STATUS_HINTS = (
    (lambda s: s in (401, 403), 'auth', '엔진 로그인이 만료되었거나 권한이 없습니다. 해당 CLI에서 다시 로그인하세요.'),
    (lambda s: s == 429, 'usage-limit', '사용량 한도에 도달했습니다. 잠시 후 다시 시도하거나 다른 AI 연결을 사용하세요.'),
    (lambda s: 400 <= s < 500, 'request-rejected', '제공자가 요청을 거부했습니다. 엔진의 모델·계정 설정을 확인하세요.'),
    (lambda s: s >= 500, 'provider-error', '제공자 쪽 오류입니다. 잠시 후 다시 시도하세요.'),
)


# -- Worker-visible capability profiles (#604, AX-02/AX-03) -------------------
#
# A profile names *which* AgentOS actions a CLI route may see; it never carries
# a schema.  Every name, description and input schema a CLI receives is derived
# from the one native action source, ``Capabilities.definitions()`` (i.e.
# ``agent_runtime.DEFINITIONS`` resolved through the manifest ``tools``), so
# the direct-API list and the MCP ``tools/list`` cannot drift apart.  The
# independently maintained three-tool list this replaces is gone.
#
# Discovery grants nothing: an offered tool still goes through
# ``Capabilities.execute`` (declared/allowed tool, current package state,
# provenance egress guard, owner-approved page scope, idempotent writes) on
# every call.  An action a profile does not offer has a *declared* reason, so a
# missing binding is reported as a route limit, never as global incapability,
# and an undeclared omission is a diagnosable defect (scripts/agentos_doctor.py).
#
# No profile here unlocks shell, home or network access for the CLI itself:
# these are AgentOS-hosted actions executed by this process under AgentOS
# policy.  The trusted-local sandbox/argv are unchanged (see ``command``);
# strict-isolated (#616) only narrows what the CLI's own tools can read.
_API_BOUND_PAGES = 'owner-page-approval-bound-to-direct-api-model'
_API_BOUND_DOCUMENTS = 'document-sharing-approval-bound-to-direct-api-model'
_CALENDAR = 'calendar-connector-not-bound-to-cli-route'
_MEMORY = 'owner-memory-not-bound-to-cli-route'
_SPECIALISTS = 'specialists-require-direct-api-model'
_ISOLATED = 'isolation-restricted-profile'
#: #656/#701: the owner-logged-in browser profile is served on the host's
#: direct route and, through the AgentOS service (``cli_browser_relay``), on
#: the trusted-local CLI route.  A CLI worker never holds a handle to that
#: session; the strict-isolated and isolated profiles never offer it.
_BROWSER = 'browser-profile-served-on-trusted-local-route-only'
_BROWSER_ACTIONS = ('browser_open', 'browser_read', 'browser_find', 'browser_click', 'browser_type')
#: #659: accepting a preparation needs the host's DecisionEngine and its
#: Telegram acceptance surface, which a CLI bridge process does not hold.
_PREPARATIONS = 'owner-preparations-not-bound-to-cli-route'
#: #774: relayed to the service on the trusted-local route only.
_OWNER_STATE_RELAYED = ('calendar_query', 'calendar_draft_create', 'calendar_draft_update', 'calendar_draft_cancel',
                        'list_memory', 'save_memory', 'schedule_preparation', 'ask_location')
#: #774: the owner's paired Telegram chat is held by the service, reached only through its relay.
_LOCATION = 'owner-telegram-location-request-served-on-trusted-local-route-only'

#: The verified limitation of the trusted-local profile (owner decision on
#: #604).  The CLI's own built-in tools can read local host files that AgentOS
#: never mediates, so those reads carry no AgentOS provenance and the public
#: reads offered here cannot be closed by it.  Observed with a no-model probe of
#: `codex sandbox -P :read-only` (the policy behind `codex exec --sandbox
#: read-only`) on codex-cli 0.153.4: a fake owner store, a home file and the
#: turn directory were readable; network and writes were blocked.  Claude Code
#: is stated per CLI (#623), from no-model process tests of the exact
#: trusted-local argv on 2.1.280 `-p` (tests/test_strict_isolation.py): its
#: permission layer denied the store read, the home `cat`, a Write and
#: WebFetch, and allowed reads of the turn directory (only those paths were
#: probed); only the declared
#: AgentOS bridge tools are pre-approved.  An allow rule in managed settings
#: (loaded regardless of HOME) could widen that - documented, not observed.
#: The owner accepts this trusted-local-worker risk; strict read isolation is
#: #616 AGENCY-ISOLATION-01.
TRUSTED_LOCAL_LIMITATION = ('the CLI may read host files outside AgentOS provenance '
                            '(verified: codex sandbox -P :read-only, codex-cli 0.153.4); '
                            'Codex exec rules in CODEX_HOME, allow and forbidden, are ignored (--ignore-rules); '
                            'Claude Code 2.1.280 -p denied the tested store and home reads, a Write and WebFetch and could '
                            'read its turn directory (observed); managed settings could allow more (documented only)')

#: The verified limitation of the strict-isolated profile (#616).  Observed
#: with no-model process tests that drive the exact argv through a real
#: `codex exec` / `claude -p` against a loopback scripted model, on a fake store
#: and a synthetic, populated CODEX_HOME (tests/test_strict_isolation.py): the
#: CLI was offered no shell, file or image tool, the permissions profile
#: denied the store, home and CODEX_HOME even to a command an "always allow"
#: exec rule would run, and the AgentOS bridge still served its tools.  Not
#: prevented by any override found on Codex 0.153.4: the owner-authored
#: `$CODEX_HOME/AGENTS.override.md` (which takes precedence) or
#: `$CODEX_HOME/AGENTS.md` reaches the model context (untracked by AgentOS
#: provenance).  Codex's `:minimal` baseline keeps OS paths, /tmp and
#: /private/var/tmp readable to a sandboxed command.
STRICT_ISOLATED_LIMITATION = ('the CLI gets no shell, file or image tool and its sandbox denies the owner store and home; '
                              'Codex still loads $CODEX_HOME/AGENTS.override.md or AGENTS.md (owner-authored, not '
                              'tracked by AgentOS) into '
                              'the model context and its sandbox baseline keeps OS paths, /tmp and /private/var/tmp '
                              'readable; qualified only for the tested CLI version, platform and paths')

#: Paths Codex's `:minimal` baseline keeps readable (observed on 0.153.4); the
#: engine runtime root must not be under one for strict isolation.
BASELINE_READABLE_ROOTS = ('/tmp', '/private/tmp', '/var/tmp', '/private/var/tmp')

#: Name of the Codex permissions profile AgentOS defines on the command line.
CODEX_STRICT_PERMISSIONS = 'agentos-strict-isolated'
#: Codex permissions profile (official `[permissions.<name>]` config): the
#: platform `:minimal` set and the turn directory (the workspace root) are
#: read-only; nothing else is readable or writable and the sandboxed commands
#: have no network.  It replaces `--sandbox read-only`: the legacy flag and a
#: permissions profile do not coexist, and with both present Codex applies the
#: legacy read-only policy, which can read the store (observed, 0.153.4).
CODEX_STRICT_TABLE = (f'permissions.{CODEX_STRICT_PERMISSIONS}='
                      '{filesystem={":minimal"="read", ":workspace_roots"={"."="read"}}, network={enabled=false}}')

CLI_PROFILES = {
    'trusted-local': {
        # The subscription CLI route: an owner-trusted local worker.
        'mode': 'bounded-agentos-mcp',
        'trust': 'trusted-local',
        'limitation': TRUSTED_LOCAL_LIMITATION,
        # Public reads the native route has by default, one owner-private read
        # and the explicit note write, all under the unchanged AgentOS guards.
        # #701: the five browser tools, executed by the AgentOS service's own
        # BrowserSession (mediation, payment guard, approvals, budget) and
        # relayed by the bridge; offered only while the profile is available.
        # #774: the owner-state actions (Memory, calendar, preparations, location request) are
        # relayed the same way and run under the service's unchanged gates:
        # #597 memory approval, calendar previews, #659 preparation acceptance.
        'actions': ('bounded_public_research', 'list_notes', 'propose_current_state', 'save_note', 'weather', 'web_search',
                    *_BROWSER_ACTIONS, *_OWNER_STATE_RELAYED),
        # Approvals bound to the direct-API model fingerprint are not carried to
        # another provider: doing so would silently change the data destination.
        'unavailable': {
            'public_page_read': _API_BOUND_PAGES,
            'find_files': _API_BOUND_DOCUMENTS, 'read_file': _API_BOUND_DOCUMENTS, 'list_roots': _API_BOUND_DOCUMENTS,
            'list_agents': _SPECIALISTS, 'delegate_agent': _SPECIALISTS,
        },
        # No AgentOS-mediated live run of this catalog has been observed.
        # Reference versions are the argv shapes recorded from each CLI's own
        # --help (docs/decision-layer.en.md), exercised only by scripted runners.
        'runtimes': {'codex': {'reference_version': '0.153.4', 'live_tested_version': None},
                     'claude-code': {'reference_version': '2.1.280', 'live_tested_version': None}},
    },
    'isolated-agentos-mcp': {
        # Deliberately restricted isolation profile (not a full-profile pass):
        # the sidecar reaches AgentOS only through a single-use, task-bound
        # bearer capability that serves exactly this read.
        'mode': 'isolated-agentos-mcp',
        'trust': 'isolated-restricted',
        'limitation': 'only the argumentless list_notes read is offered',
        'actions': ('list_notes',),
        'unavailable': {action: _ISOLATED for action in (
            'bounded_public_research', 'save_note', 'weather', 'web_search', 'public_page_read',
            'find_files', 'read_file', 'list_roots', 'calendar_query', 'calendar_draft_create',
            'calendar_draft_update', 'calendar_draft_cancel', 'save_memory', 'list_memory',
            'list_agents', 'delegate_agent', 'propose_current_state', 'schedule_preparation', 'ask_location',
            *_BROWSER_ACTIONS)},
        # Pinned in Dockerfile.engine; a test keeps the two in step.
        'runtimes': {'codex': {'pinned_version': '0.153.4', 'live_tested_version': None}},
    },
    'strict-isolated': {
        # #616: the same host CLI and stdio bridge as trusted-local, launched
        # so that the CLI's own tools cannot read the owner store or home.
        # The owner chooses it explicitly and only after a passing no-model
        # qualification; it never replaces trusted-local silently.
        'mode': 'bounded-agentos-mcp',
        'trust': 'strict-isolated',
        'limitation': STRICT_ISOLATED_LIMITATION,
        # The bridge is told its profile (``--profile``, #701): the trusted-local
        # set without the browser tools, which this profile never offers.
        'actions': ('bounded_public_research', 'list_notes', 'propose_current_state', 'save_note', 'weather', 'web_search'),
        'unavailable': {
            'public_page_read': _API_BOUND_PAGES,
            'find_files': _API_BOUND_DOCUMENTS, 'read_file': _API_BOUND_DOCUMENTS, 'list_roots': _API_BOUND_DOCUMENTS,
            'calendar_query': _CALENDAR, 'calendar_draft_create': _CALENDAR,
            'calendar_draft_update': _CALENDAR, 'calendar_draft_cancel': _CALENDAR,
            'save_memory': _MEMORY, 'list_memory': _MEMORY,
            'list_agents': _SPECIALISTS, 'delegate_agent': _SPECIALISTS,
            **{action: _BROWSER for action in _BROWSER_ACTIONS},
            'schedule_preparation': _PREPARATIONS,
            'ask_location': _LOCATION,
        },
        # Only these exact CLI versions passed the process-level tests; any
        # other version is refused until requalified (no silent downgrade).
        'runtimes': {
            'codex': {'tested_versions': ('0.153.4',), 'tested_platforms': ('darwin',), 'live_tested_version': None,
                      'enforcement': f'Codex permissions profile {CODEX_STRICT_PERMISSIONS} (Seatbelt) instead of '
                                     '--sandbox read-only, --ignore-rules, every non-allowlisted feature disabled '
                                     '(verified at qualification), decision-route instruction overrides'},
            'claude-code': {'tested_versions': ('2.1.280',), 'tested_platforms': ('darwin',), 'live_tested_version': None,
                            'enforcement': 'no built-in tools (--tools ""), --restricted, '
                                           'only the offered AgentOS MCP tools allowed'},
        },
    },
}
BOUNDED_PROFILE, ISOLATED_PROFILE, STRICT_PROFILE = 'trusted-local', 'isolated-agentos-mcp', 'strict-isolated'
#: Profiles the owner can choose for the host subscription CLI route.
HOST_CLI_PROFILES = (BOUNDED_PROFILE, STRICT_PROFILE)


def strict_allowed_features():
    """Enabled Codex features the strict Work profile keeps.

    The #580 decision-call allowlist (request/transport behaviour, not tools)
    plus ``unified_exec``, which 0.153.4 still lists as enabled after
    ``--disable`` (docs/decision-layer.en.md).  With ``shell_tool`` disabled
    no command tool is offered at all (observed); the permissions profile
    would still confine one.
    """
    from .decision_adapters import CODEX_ALLOWED_ENABLED_FEATURES
    return frozenset(CODEX_ALLOWED_ENABLED_FEATURES | {'unified_exec'})


def strict_launch_arguments(engine_id, disabled_features=()):
    """CLI arguments that confine one engine under the strict-isolated profile.

    Codex: the permissions profile replaces ``--sandbox read-only`` (never
    both); ``--ignore-rules`` so an "always allow" exec rule in CODEX_HOME
    cannot run a command outside the sandbox (review P1, observed); the
    decision route's official instruction overrides (#580, reused); and one
    ``--disable`` per non-allowlisted feature from the qualification-time plan
    (review P2: browser/computer use, plugins, hooks, image generation, ...).
    An empty plan is refused: it was never verified.
    Claude Code: no built-in tool at all (no Read/Bash/WebFetch/WebSearch/
    Agent), ``--restricted`` so no settings file can re-add one, and only the
    profile's AgentOS MCP tools are pre-approved; without that approval ``-p``
    denies every MCP call (observed, 2.1.280).
    """
    if engine_id == 'codex':
        from .decision_adapters import CODEX_DECISION_CONFIG
        disabled = sorted(set(disabled_features or ()))
        if not disabled or set(disabled) & strict_allowed_features():
            raise ExecutionError('엄격 격리 Codex 기능 목록이 검증되지 않았습니다.', failure_class='isolation-unqualified')
        argv = ['--ignore-rules', '-c', f'default_permissions="{CODEX_STRICT_PERMISSIONS}"', '-c', CODEX_STRICT_TABLE]
        for key, value in CODEX_DECISION_CONFIG:
            argv += ['-c', f'{key}={value}']
        for feature in disabled:
            argv += ['--disable', feature]
        return argv
    if engine_id == 'claude-code':
        return ['--tools', '', '--restricted', *claude_bridge_allowlist(STRICT_PROFILE)]
    raise ExecutionError('지원하는 구독 엔진을 선택하세요.')


#: #709: Codex's per-MCP-server approval mode for the ``agentos`` bridge only.
#: Codex's documented ``mcp_servers.<id>.default_tools_approval_mode``
#: accepts ``auto | prompt | writes | approve`` (0.153.4 rejects any other
#: value at config load: "unknown variant ... expected one of `auto`,
#: `prompt`, `writes`, `approve`").  ``approve`` resolves Codex's own MCP
#: approval prompt for these tools as approved, so Codex's Guardian/auto-review
#: no longer denies an AgentOS bridge call.  The decision stays with AgentOS:
#: every bridge tool runs through ``Capabilities.execute`` (mediation, the
#: payment guard, exact per-step owner approvals, the Work budget).  Other MCP
#: servers do not exist in this turn (``--ignore-user-config``), and shell
#: commands and sandbox escalations keep Codex's own policy.
CODEX_BRIDGE_APPROVAL_MODE = 'approve'


def codex_bridge_approval_argument():
    """The one ``-c`` override that lets AgentOS, not Codex's reviewer, decide bridge tool calls (#709)."""
    return f'mcp_servers.agentos.default_tools_approval_mode="{CODEX_BRIDGE_APPROVAL_MODE}"'


#: #729: Codex's per-MCP-server tool-call timeout key (seconds, an f64).  Verified
#: on codex-cli 0.153.4: the key is in the binary's ``RawMcpServerConfig``
#: field list next to ``startup_timeout_sec`` ("timed out awaiting tools/call
#: after"), and a parse-only ``codex -c mcp_servers.agentos.tool_timeout_sec=300
#: mcp get agentos --json`` with an empty ``CODEX_HOME`` reports
#: ``"tool_timeout_sec": 300.0`` (a string value is refused at config load; an
#: unknown key is ignored silently, so only the reported value proves it).
#: Unset, Codex cancels a bridge call after its own default (60 s), shorter
#: than a bounded research call.
CODEX_TOOL_TIMEOUT_KEY = 'tool_timeout_sec'
#: Added to the longest offered tool's own bound: bridge start-up, the durable
#: event writes and the reply.
BRIDGE_TOOL_MARGIN_SECONDS = 30
#: A bridge action with no bound of its own below: Codex's own default.
DEFAULT_TOOL_SECONDS = 60


def bridge_tool_bound(actions):
    """The longest own bound, in seconds, of the AgentOS bridge ``actions`` one turn offers (#729).

    Each figure is the tool's existing timeout, not a new one: a browser step
    is bounded by the relay's call cap, a bounded research call by one search
    plus its page reads, a search by the slower of a provider search and a
    native search, the weather lookup by its two requests.  A native search
    may send ``NATIVE_MAX_REQUESTS`` sequential requests (the first plus each
    ``pause_turn`` continuation), each capped by ``NATIVE_TIMEOUT_SECONDS``
    (#729 review).
    """
    from .agent_runtime import BROWSER_ACTIONS
    from .cli_browser_relay import CALL_SECONDS
    from .local_tools import MAX_PAGE_SECONDS
    from .research import MAX_RESEARCH_PAGES
    from .search_providers import NATIVE_MAX_REQUESTS, NATIVE_TIMEOUT_SECONDS, SEARCH_TIMEOUT_SECONDS
    search = max(SEARCH_TIMEOUT_SECONDS, NATIVE_MAX_REQUESTS * NATIVE_TIMEOUT_SECONDS)
    own = {'web_search': search, 'bounded_public_research': search + MAX_RESEARCH_PAGES * MAX_PAGE_SECONDS,
           # local_tools.LocalTools.weather: geocoding (10 s) then the forecast (15 s).
           'weather': 10 + 15, 'public_page_read': MAX_PAGE_SECONDS,
           # #774 review: a relayed write asks the Judgment AI (explicit memory / preparation
           # request) before it commits; one decision call is bounded by DEFAULT_TOOL_SECONDS.
           'save_memory': 2 * DEFAULT_TOOL_SECONDS, 'schedule_preparation': 2 * DEFAULT_TOOL_SECONDS}
    bounds = [CALL_SECONDS if action in BROWSER_ACTIONS else own.get(action, DEFAULT_TOOL_SECONDS)
              for action in actions or ()]
    return max(bounds, default=DEFAULT_TOOL_SECONDS)


def bridge_tool_timeout(actions, turn_seconds):
    """The ``agentos`` server's tool-call timeout: the longest offered bound plus a margin,
    never beyond the turn's own time (the Work's remaining budget, capped)."""
    return max(1, min(int(turn_seconds), bridge_tool_bound(actions) + BRIDGE_TOOL_MARGIN_SECONDS))


def codex_bridge_timeout_argument(seconds):
    """The one ``-c`` override of the ``agentos`` server's tool-call timeout (#729); no other server."""
    return f'mcp_servers.agentos.{CODEX_TOOL_TIMEOUT_KEY}={int(seconds)}'


#: #701: bridge actions the CLI's own web search replaces on a native-search
#: turn, so the model searches with Codex's or Claude's own tool instead.
NATIVE_SEARCH_REPLACED = frozenset({'web_search', 'bounded_public_research'})


def native_search_withheld():
    """Bridge actions a turn with the CLI's own web search never offers (#678 P1, #701).

    Every owner-private *store* read (``agent_runtime.PRIVATE_PROVENANCE``:
    notes, Memory, documents, folder names, calendar): the CLI writes its own
    search queries, which AgentOS cannot compose or redact, so a turn that
    may search natively cannot read those stores mid-turn.  The browser tools
    stay (#701, owner decision in the issue): their output is mediated before
    it reaches the CLI, and native search stays as the pre-turn gate decided.
    The bridge's own public search tools are withheld too
    (``NATIVE_SEARCH_REPLACED``): the CLI's own search is preferred.
    """
    from .agent_runtime import BROWSER_ACTIONS, PRIVATE_PROVENANCE
    return (frozenset(PRIVATE_PROVENANCE) - BROWSER_ACTIONS) | NATIVE_SEARCH_REPLACED


def turn_actions(profile, native_search=False, only=None):
    """The bridge actions one turn offers: the profile's, minus private reads when native search is on.

    ``only`` (#710) is the orchestrator's validated per-request subset, or
    None for the profile's usual set.  It can only narrow the set.
    """
    actions = profile_actions(profile)
    if native_search:
        withheld = native_search_withheld()
        actions = tuple(action for action in actions if action not in withheld)
    if only is not None:
        actions = tuple(action for action in actions if action in only)
    return actions


def private_read_actions():
    """Bridge actions that read an owner-private store (#710).

    The CLI's own web search is never on in a turn that offers one of these
    (``native_search_withheld``); the orchestrator's per-request tool choice
    uses the same set to turn that search off when it selects one.
    """
    return native_search_withheld() - NATIVE_SEARCH_REPLACED


def claude_bridge_allowlist(profile, native_search=False, only=None):
    """Claude Code's official ``--allowedTools`` rule for exactly the
    profile's AgentOS bridge tools (#623).

    Under ``-p`` Claude Code denies every MCP call that no allow rule covers
    (observed, 2.1.280: "haven't granted").  Each name is exact - no
    ``mcp__agentos`` server-wide rule, no wildcard - so a bridge tool the
    profile does not declare stays denied, and no built-in tool (Read, Bash,
    WebFetch, ...) is named, so their permission behaviour is unchanged.
    """
    return ['--allowedTools', ','.join(f'mcp__agentos__{action}' for action in turn_actions(profile, native_search, only))]


_VERSION_PATTERNS = {'codex': re.compile(r'^codex-cli (\d+\.\d+\.\d+)\s*$'),
                     'claude-code': re.compile(r'^(\d+\.\d+\.\d+) \(Claude Code\)\s*$')}


def parse_cli_version(engine_id, text):
    """The exact version an official CLI reports for ``--version``, or None."""
    pattern = _VERSION_PATTERNS.get(engine_id)
    lines = [line for line in (text or '').splitlines() if line.strip()]
    match = pattern.match(lines[-1]) if pattern and lines else None
    return match.group(1) if match else None


def profile_actions(profile):
    return tuple(CLI_PROFILES[profile]['actions'])


def route_unavailable(profile):
    """Declared reasons for every action a CLI profile does not offer."""
    return dict(CLI_PROFILES[profile]['unavailable'])


def profile_status(profile):
    """What Settings, provenance and the doctor show about one profile."""
    declared = CLI_PROFILES[profile]
    return {'profile': profile, 'mode': declared['mode'], 'trust': declared['trust'],
            'limitation': declared['limitation'], 'tools': list(profile_actions(profile)),
            'unavailable': route_unavailable(profile)}


def mcp_tool(definition, mode=None, profile=None):
    """Project one native function definition onto the MCP ``Tool`` wire shape.

    Field names are the MCP wire aliases (``inputSchema``), checked against the
    adopted ``mcp_types.Tool`` in tests/test_mcp_bridge_protocol.py.  The
    manifest ``mode`` becomes the ``readOnlyHint`` annotation; it is a hint to
    the client and authorizes nothing.  #718: the isolated profile's proxy
    forwards only argument-less calls, so its tools do not offer ``status``.
    """
    function = definition['function']
    tool = {'name': function['name'], 'description': function['description'],
            'inputSchema': json.loads(json.dumps(function['parameters']))}
    if profile == ISOLATED_PROFILE:
        from .agent_runtime import STATUS_ARGUMENT
        tool['inputSchema'].get('properties', {}).pop(STATUS_ARGUMENT, None)
    if mode in ('read_only', 'bounded_write'):
        tool['annotations'] = {'readOnlyHint': mode == 'read_only'}
    return tool


def profile_mcp_tools(profile):
    """The MCP tool list of a profile from the built-in manifest alone.

    For the isolated bridge, which runs without an owner store: it is the same
    projection ``AgentOSMcpTools.definitions`` makes from a live Capabilities.
    """
    from .agent_runtime import action_definitions
    from .manifests import runtime_packages
    tools = {tool['id']: tool for package in runtime_packages([]) for tool in package['tools']}
    return [mcp_tool(definition, tools[definition['function']['name']]['mode'], profile)
            for definition in action_definitions(tools, profile_actions(profile))]


class ExecutionError(ValueError):
    """A safe, user-visible execution-boundary failure.

    ``failure_class``, ``exit_code`` and ``reason`` are bounded, redacted
    diagnostics for Work events and logs; they never contain the prompt.
    """
    def __init__(self, message, *, failure_class='', exit_code=None, reason='', meta=None):
        super().__init__(message)
        self.failure_class, self.exit_code, self.reason = failure_class, exit_code, reason
        self.meta = meta or {}

    def diagnostics(self):
        return {key: value for key, value in (('failure_class', self.failure_class),
                ('exit_code', self.exit_code), ('reason', self.reason)) if value not in ('', None)}


# Shared with the service for provenance redaction (#570).
SECRET_PATTERN = _SECRET


def _echoes(text, prompt):
    """True when ``text`` repeats any run of 24+ characters from the prompt.

    Every window of the (already bounded) text is checked, so an echo of the
    prompt's start, middle or end is caught regardless of alignment.
    """
    prompt = ' '.join(prompt.split())
    if len(prompt) < _ECHO_WINDOW:
        return len(prompt) >= 8 and prompt in text
    return any(text[start:start + _ECHO_WINDOW] in prompt
               for start in range(0, len(text) - _ECHO_WINDOW + 1))


def redact_reason(text, prompt=None):
    """Bound provider/CLI text before it is persisted, logged or shown.

    A reason that echoes the request is withheld entirely: providers may
    quote any part of it, so partial scrubbing is not trustworthy.
    """
    if not isinstance(text, str):
        return ''
    text = ' '.join(_CONTROL.sub(' ', text).split())
    # Check only what could be shown, before redaction can split an echo.
    text = text[:MAX_REASON_CHARS * 2]
    if isinstance(prompt, str) and _echoes(text, prompt):
        return '[요청 내용이 포함된 응답이라 표시하지 않습니다]'
    text = _SECRET.sub('[redacted]', text)
    return text if len(text) <= MAX_REASON_CHARS else text[:MAX_REASON_CHARS - 1] + '…'


def _provider_error(message):
    """Return (status, message) from a provider error that may be JSON text."""
    status = None
    for _ in range(3):
        if not isinstance(message, str):
            break
        try:
            data = json.loads(message)
        except ValueError:
            break
        if not isinstance(data, dict):
            break
        if isinstance(data.get('status'), int):
            status = data['status']
        error = data.get('error')
        message = error.get('message') if isinstance(error, dict) else error if isinstance(error, str) else data.get('message')
    return status, message if isinstance(message, str) else ''


# CLI output that means "no usable login", whatever the exit code (#571).
# Deterministic protocol classification, not semantic judgment.
_NOT_SIGNED_IN = re.compile(r'not logged in|please run /login|run `?claude setup-token|invalid api key|'
                            r'oauth token (?:has )?expired|codex login|not signed in', re.I)


def is_not_signed_in(text):
    return bool(_NOT_SIGNED_IN.search(text or ''))


#: #735: the CLIs' own "this model is not available to this account" signals,
#: as they print them (protocol classification, not a judgment of text).
#: Codex 0.153.4 (observed, Work a8e6aa7b): ``The '<model>' model is not
#: supported when using Codex with a ChatGPT account.``  Claude Code 2.1.x
#: tags an unknown or inaccessible ``--model`` on stderr (observed, #580).
CLAUDE_UNRECOGNIZED_MODEL_TAG = '[claude-code:unrecognized_model]'


def unsupported_model(engine_id, model, reason, stderr=''):
    """``model`` when the CLI's own failure says that model is unsupported for the account, else ''.

    Only the CLI's specific signal counts; a generic rejection that merely
    mentions the model (a context-length or content error) does not.
    """
    if not model:
        return ''
    if engine_id == 'codex':
        signal = re.compile(r"\bThe '" + re.escape(model) + r"' model is not supported\b")
        return model if signal.search(str(reason or '')) else ''
    if engine_id == 'claude-code':
        return model if CLAUDE_UNRECOGNIZED_MODEL_TAG in str(stderr or '')[-8000:] else ''
    return ''


LOGIN_COMMANDS = {'claude-code': 'claude setup-token', 'codex': 'codex login'}

#: Claude Code's built-in web search tool name (``claude --help``, 2.1.280).
CLAUDE_NATIVE_SEARCH_TOOL = 'WebSearch'
MAX_NATIVE_SEARCHES = 10
MAX_NATIVE_RESULTS = 10
#: A CLI's own words that its web search cannot run for this account or region
#: (protocol classification of its tool error, as ``_NOT_SIGNED_IN``).  Any
#: other tool error is a per-call failure, never a remembered refusal.
_NATIVE_REFUSAL = re.compile(r'only available in|not available (?:in|for) (?:your|this) (?:region|country|location|account|plan)|'
                             r'not supported in your (?:region|country)|web ?search (?:is )?(?:not enabled|disabled|unavailable|'
                             r'not available)', re.I)


def _native_row(value):
    """``{title, url}`` of one reported search result, or None; URLs are never invented.

    The URL must be a public http(s) URL with no whitespace or control
    character (``search_providers.public_http_url``); a value carrying a
    newline and appended text is refused whole.
    """
    from .search_providers import public_http_url
    if not isinstance(value, dict) or not public_http_url(value.get('url')):
        return None
    return {'title': ' '.join(str(value.get('title') or '').replace('\x7f', ' ').split())[:300], 'url': value['url']}


def _codex_searches(records):
    found = []
    for record in records:
        item = record.get('item')
        if record.get('type') != 'item.completed' or not isinstance(item, dict) or item.get('type') != 'web_search':
            continue
        action = item.get('action') if isinstance(item.get('action'), dict) else {}
        queries = [str(value)[:200] for value in [item.get('query'), action.get('query'), *(action.get('queries') or [])]
                   if isinstance(value, str) and value.strip()]
        results = item.get('results') if isinstance(item.get('results'), list) else []
        rows = [row for row in (_native_row(value) for value in results) if row]
        opened = _native_row({'url': action.get('url')})
        if opened and opened['url'] not in {row['url'] for row in rows}:
            rows.append(opened)
        failed = str(item.get('status') or '') == 'failed'
        found.append({'id': str(item.get('id') or '')[:80], 'engine': 'codex', 'action': str(action.get('type') or 'search')[:20],
                      'queries': list(dict.fromkeys(queries))[:5], 'results': [] if failed else rows[:MAX_NATIVE_RESULTS],
                      'state': 'failed' if failed else 'succeeded', 'reason': ''})
    return found


def _claude_searches(records):
    calls = {}

    def call_for(call_id):
        return calls.setdefault(call_id, {'id': call_id[:80], 'engine': 'claude-code', 'action': 'search', 'queries': [],
                                          'results': [], 'state': 'requested', 'reason': ''})
    for record in records:
        message = record.get('message') if isinstance(record.get('message'), dict) else {}
        content = message.get('content') if isinstance(message.get('content'), list) else []
        for part in content:
            if not isinstance(part, dict):
                continue
            if record.get('type') == 'assistant' and part.get('type') == 'tool_use' and part.get('name') == CLAUDE_NATIVE_SEARCH_TOOL:
                query = part.get('input', {}).get('query') if isinstance(part.get('input'), dict) else None
                call = call_for(str(part.get('id') or ''))
                if isinstance(query, str) and query.strip():
                    call['queries'] = [query[:200]]
            elif record.get('type') == 'user' and part.get('type') == 'tool_result' and str(part.get('tool_use_id') or '') in calls:
                call = calls[str(part.get('tool_use_id'))]
                reported = record.get('tool_use_result')
                rows = []
                if isinstance(reported, dict):
                    for block in reported.get('results') or []:
                        if isinstance(block, dict):
                            rows += [row for row in (_native_row(value) for value in block.get('content') or []) if row]
                text = part.get('content') if isinstance(part.get('content'), str) else (reported if isinstance(reported, str) else '')
                if part.get('is_error') is True or not isinstance(reported, dict):
                    # Only the CLI's own availability refusal is 'unavailable';
                    # any other tool error is a failed call.
                    state = 'unavailable' if _NATIVE_REFUSAL.search(str(text or '')) else 'failed'
                    call.update(state=state, reason=redact_reason(str(text or 'web search error')))
                else:
                    call.update(state='succeeded', results=rows[:MAX_NATIVE_RESULTS])
        for denial in record.get('permission_denials') or []:
            if isinstance(denial, dict) and denial.get('tool_name') == CLAUDE_NATIVE_SEARCH_TOOL:
                # A permission denial is AgentOS's own setting, not the CLI's availability.
                call_for(str(denial.get('tool_use_id') or 'denied')).update(state='denied', reason='permission denied')
    return [call for call in calls.values() if call['state'] != 'requested']


def native_searches(engine_id, records):
    """The CLI's own web searches in one turn's machine output (#678).

    Codex ``exec --json``: ``item.completed`` with ``item.type ==
    'web_search'`` (``query``, ``action`` of type search/open_page/
    find_in_page with ``query``/``queries``/``url``, optional ``results``).
    Claude Code ``stream-json``: an assistant ``tool_use`` named
    ``WebSearch`` and the user record's ``tool_use_result`` (``query``,
    ``results`` of ``{tool_use_id, content: [{title, url}]}`` or text).
    States: ``succeeded``; ``unavailable`` only for the CLI's own availability
    refusal (the installed Claude Code says web search is US-only); ``failed``
    for any other tool error; ``denied`` for a permission denial.  Only what
    the CLI reported is kept: a search that reported no URL has none, and a
    reported URL with whitespace or control characters is dropped.
    """
    if engine_id == 'codex':
        return _codex_searches(records)[:MAX_NATIVE_SEARCHES]
    if engine_id == 'claude-code':
        return _claude_searches(records)[:MAX_NATIVE_SEARCHES]
    return []


def live_native_search_steps(engine_id, record):
    """The CLI's own web-search steps one streamed record reports, while the run is live (#718).

    The same official event shapes ``native_searches`` reads after the run:
    Codex ``item.started``/``item.updated``/``item.completed`` of an item with
    ``type == 'web_search'``; Claude Code an assistant ``tool_use`` named
    ``WebSearch`` (running) and the user record's ``tool_result`` for it
    (done).  Returns ``[{'id', 'state': 'running'|'done', 'query'}]``; the
    query is the CLI's own, unredacted - the consumer redacts it exactly as
    the recorded event.  Nothing here is Evidence: the durable events are
    still written from ``cli_metadata`` after the run.
    """
    if not isinstance(record, dict):
        return []
    if engine_id == 'codex':
        item = record.get('item')
        kind = record.get('type')
        if kind not in ('item.started', 'item.updated', 'item.completed') or not isinstance(item, dict) \
                or item.get('type') != 'web_search':
            return []
        action = item.get('action') if isinstance(item.get('action'), dict) else {}
        queries = [value for value in [item.get('query'), action.get('query'), *(action.get('queries') or [])]
                   if isinstance(value, str) and value.strip()]
        return [{'id': str(item.get('id') or '')[:80], 'state': 'done' if kind == 'item.completed' else 'running',
                 'query': queries[0][:200] if queries else ''}]
    if engine_id == 'claude-code':
        message = record.get('message') if isinstance(record.get('message'), dict) else {}
        content = message.get('content') if isinstance(message.get('content'), list) else []
        steps = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if record.get('type') == 'assistant' and part.get('type') == 'tool_use' and part.get('name') == CLAUDE_NATIVE_SEARCH_TOOL:
                query = part.get('input', {}).get('query') if isinstance(part.get('input'), dict) else None
                steps.append({'id': str(part.get('id') or '')[:80], 'state': 'running',
                              'query': query[:200] if isinstance(query, str) else ''})
            elif record.get('type') == 'user' and part.get('type') == 'tool_result':
                steps.append({'id': str(part.get('tool_use_id') or '')[:80], 'state': 'done', 'query': ''})
        return steps
    return []


def live_progress_reader(engine_id, progress):
    """A per-line stdout callback that hands each live native-search step to ``progress`` (#718).

    Presentation only: a malformed line, an oversized line or a failing
    ``progress`` never affects the run or its final output.
    """
    def on_line(line):
        if len(line) > MAX_OUTPUT_BYTES:
            return
        try:
            record = json.loads(line)
        except ValueError:
            return
        for step in live_native_search_steps(engine_id, record):
            try:
                progress(step)
            except Exception:  # presentation must never fail the run
                LOG.debug('live progress sink failed', exc_info=False)
    return on_line
AUTH_HINT = '엔진 로그인이 필요합니다. 설정 › AI 연결에서 로그인을 확인하세요.'


def cli_metadata(engine_id, raw):
    """What the CLI itself reported about the run (#570). Absent fields stay
    absent: a missing model is "not reported", never guessed."""
    meta = {'reported_model': None, 'usage': None, 'tool_calls': [], 'num_turns': None, 'cost_usd': None}
    records = []
    lines = (raw or '').splitlines()
    # Keep the head (init record) and the tail (result record) of a long stream.
    for line in (lines if len(lines) <= 5000 else lines[:1000] + lines[-4000:]):
        # Tool results can be large and carry nothing this summary reads.
        if len(line) > MAX_OUTPUT_BYTES:
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            records.append(value)
    for record in records:
        models = record.get('modelUsage')
        if isinstance(models, dict) and models:
            meta['reported_model'] = ', '.join(str(name) for name in list(models)[:3])
        elif isinstance(record.get('model'), str) and record['model'] and not record['model'].startswith('<'):
            meta['reported_model'] = record['model'][:120]
        if isinstance(record.get('usage'), dict):
            meta['usage'] = {k: v for k, v in record['usage'].items() if isinstance(v, (int, float))}
        if isinstance(record.get('num_turns'), int):
            meta['num_turns'] = record['num_turns']
        if isinstance(record.get('total_cost_usd'), (int, float)):
            meta['cost_usd'] = record['total_cost_usd']
        message = record.get('message') if record.get('type') == 'assistant' else None
        if isinstance(message, dict) and isinstance(message.get('content'), list):
            for part in message['content']:
                if isinstance(part, dict) and part.get('type') == 'tool_use':
                    meta['tool_calls'].append({'type': 'tool_use', 'name': str(part.get('name') or '')[:80], 'status': 'requested'})
        for denial in record.get('permission_denials') or []:
            if isinstance(denial, dict):
                meta['tool_calls'].append({'type': 'tool_use', 'name': str(denial.get('tool_name') or '')[:80], 'status': 'denied'})
        item = record.get('item')
        if isinstance(item, dict) and item.get('type') in ('mcp_tool_call', 'command_execution', 'web_search', 'file_change'):
            name = item.get('tool') or item.get('name') or item.get('type')
            meta['tool_calls'].append({'type': item.get('type'), 'name': str(name)[:80], 'status': str(item.get('status') or '')[:20]})
    meta['tool_calls'] = meta['tool_calls'][:30]
    meta['native_searches'] = native_searches(engine_id, records)
    return meta


def display_argv(argv, prompt, instructions=''):
    """The command line with the prompt and instructions replaced by labels."""
    shown = []
    for part in argv:
        if prompt and part == prompt:
            shown.append(f'<prompt: {len(prompt.encode())} bytes>')
        elif instructions and part == instructions:
            shown.append(f'<AgentOS instructions: {len(instructions.encode())} bytes>')
        elif prompt and len(part) > 200:
            shown.append(part[:200] + '…')
        else:
            shown.append(part)
    return shown


#: #729: a bridge call that started and never completed (the CLI cancelled it,
#: timed out waiting, or the connection closed).
TOOL_INCOMPLETE = 'tool_incomplete'
TOOL_INCOMPLETE_TEXT = '도구 호출이 끝나기 전에 연결이 닫혀 결과를 받지 못했습니다.'


def incomplete_bridge_calls(rows):
    """``[(tool, host_action)]`` of bridge calls that went ``running`` with no result after (#729).

    ``rows`` are ``(tool, status, detail)`` of one attempt, in order.  A call
    is paired with the next ``succeeded``/``failed`` bridge event of the same
    tool; what is left over never completed.
    """
    open_calls = []
    for tool, status, detail in rows:
        try:
            data = json.loads(detail or '{}')
        except (TypeError, ValueError):
            data = {}
        if not isinstance(data, dict) or data.get('scope') != 'subscription-mcp-bridge':
            continue
        if status == 'running':
            open_calls.append((tool, data.get('host_action') or tool))
        elif status in ('succeeded', 'failed'):
            match = next((index for index, (name, _action) in enumerate(open_calls) if name == tool), None)
            if match is not None:
                open_calls.pop(match)
    return open_calls


def failure_details(engine_id, stdout, stderr, prompt=None):
    """Summarise a failed CLI turn from its official machine output.

    Codex ``exec --json`` reports failures as ``turn.failed``/``error``
    events; Claude Code's result record (``json`` or the last ``stream-json`` line) sets ``is_error``.  When
    neither is observable, the last stderr line is the only evidence.
    """
    status, message = None, ''
    lines = (stdout or '')[-MAX_OUTPUT_BYTES:].splitlines()
    for line in reversed(lines):
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        raw = None
        if engine_id == 'codex' and record.get('type') == 'turn.failed' and isinstance(record.get('error'), dict):
            raw = record['error'].get('message')
        elif engine_id == 'codex' and record.get('type') == 'error':
            raw = record.get('message')
        elif engine_id == 'claude-code' and record.get('is_error') is True:
            raw = record.get('result') or record.get('error')
        if raw:
            status, message = _provider_error(raw)
            break
    if not message:
        tail = [line for line in (stderr or '')[-8000:].splitlines() if line.strip()]
        message = tail[-1] if tail else ''
    return status, redact_reason(message, prompt)


#: How often a running CLI is checked for the owner's Stop (#607 AX-10).
STOP_POLL_SECONDS = 0.25
ENGINE_STOPPED = '소유자가 멈춤을 요청해 구독 엔진 실행과 그 하위 프로세스를 종료했습니다.'


class EngineInterrupted(Exception):
    """The CLI's process group was killed because the Work was stopped or ran out of time."""
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def kill_process_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        process.kill()


#: After the process group is killed, how long a streamed run may still drain
#: its pipes before they are closed (a descendant outside the group may hold them).
KILL_DRAIN_SECONDS = 2.0


class StreamLimitExceeded(Exception):
    """The CLI's combined stdout and stderr passed ``MAX_STREAM_BYTES`` while being read (#736 review)."""


class _StreamedOutput:
    """``Popen.communicate`` for a binary-pipe process, with stdout seen line by line (#718).

    Single-threaded and non-blocking (``selectors``): every read is bounded
    by the caller's timeout, so a descendant that keeps stdout/stderr open
    after the CLI exits can never hold the run past its deadline or Stop -
    ``communicate`` raises ``subprocess.TimeoutExpired`` exactly as
    ``Popen.communicate(timeout=...)`` does, and ``close`` releases the pipes.
    The returned text is decoded the way text-mode ``communicate`` decodes
    (locale encoding, universal newlines), so ``cli_metadata`` and the result
    parsing are unchanged; ``on_line`` only sees each stdout line earlier.
    """
    def __init__(self, process, on_line, limit=None):
        import locale
        import selectors
        self.process, self.on_line, self.limit = process, on_line, limit
        self.encoding = locale.getpreferredencoding(False)
        self.stdout, self.stderr, self.partial = bytearray(), bytearray(), bytearray()
        self.selector = selectors.DefaultSelector()
        for stream in (process.stdout, process.stderr):
            os.set_blocking(stream.fileno(), False)
            self.selector.register(stream.fileno(), selectors.EVENT_READ, stream is process.stdout)

    def _line(self, raw):
        if self.on_line is None:
            return
        try:
            self.on_line(raw.decode(self.encoding, 'replace').replace('\r\n', '\n'))
        except Exception:  # presentation must never fail the run
            pass

    def _read(self, fd, is_stdout):
        try:
            chunk = os.read(fd, 65536)
        except (BlockingIOError, InterruptedError):
            return
        if not chunk:
            self.selector.unregister(fd)
            if is_stdout and self.partial:
                self._line(bytes(self.partial))
                self.partial.clear()
            return
        if not is_stdout:
            self.stderr += chunk
        else:
            self.stdout += chunk
        # #736 review: the whole-stream bound is enforced while reading, on
        # both pipes and whatever the exit code, so a runaway CLI is stopped
        # as soon as it passes the bound instead of after it exits.
        if self.limit is not None and len(self.stdout) + len(self.stderr) > self.limit:
            raise StreamLimitExceeded()
        if not is_stdout:
            return
        self.partial += chunk
        while True:
            end = self.partial.find(b'\n')
            if end < 0:
                break
            self._line(bytes(self.partial[:end + 1]))
            del self.partial[:end + 1]

    def _text(self, data):
        return bytes(data).decode(self.encoding).replace('\r\n', '\n').replace('\r', '\n')

    def communicate(self, timeout):
        """Both pipes at EOF and the process exited within ``timeout``, or ``TimeoutExpired``."""
        end = time.monotonic() + max(0.0, timeout)
        while self.selector.get_map():
            left = end - time.monotonic()
            if left <= 0:
                raise subprocess.TimeoutExpired(self.process.args, timeout)
            for key, _events in self.selector.select(left):
                self._read(key.fd, key.data)
        self.process.wait(timeout=max(0.0, end - time.monotonic()) or 0.01)
        return self._text(self.stdout), self._text(self.stderr)

    def close(self):
        """Stop reading and close both pipes (after a kill)."""
        try:
            self.selector.close()
        finally:
            for stream in (self.process.stdout, self.process.stderr):
                try:
                    stream.close()
                except OSError:
                    pass


def bounded_run(runner, argv, *, cwd, env, timeout, interrupted=None, on_line=None):
    """Run one CLI with no shell in its own process group.

    With the real ``subprocess.run`` a timeout kills the whole group, so the
    native binary behind a wrapper script (Codex's ``codex.js``) and a CLI's
    MCP bridge child are not left running.  #607: ``interrupted`` is polled
    while the CLI runs; when it answers (the owner's Stop, the Work's shared
    deadline) the group is killed at once and ``EngineInterrupted`` carries
    the reason.  An injected test runner receives ``start_new_session=True``.
    #718: ``on_line`` receives each stdout line while the CLI runs (live
    progress); the returned output is unchanged.  #736 review: every run reads
    its binary pipes itself (``_StreamedOutput``) and is killed, with the named
    ``STREAM_TOO_LARGE`` error, as soon as its combined output passes
    ``MAX_STREAM_BYTES``.
    """
    if runner is not subprocess.run:
        return runner(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                      timeout=timeout, shell=False, start_new_session=True)
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, shell=False, start_new_session=True)
    streamed = _StreamedOutput(process, on_line, limit=MAX_STREAM_BYTES)
    try:
        return _bounded_wait(process, streamed, argv, timeout, interrupted)
    except StreamLimitExceeded:
        kill_process_group(process)
        streamed.close()
        try:
            process.wait(timeout=KILL_DRAIN_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        LOG.warning('engine output passed the stream bound; process group killed')
        raise ExecutionError(STREAM_TOO_LARGE, failure_class='invalid-output') from None


def _bounded_wait(process, streamed, argv, timeout, interrupted):
    """``bounded_run``'s wait loop over one streamed process (Stop, deadline and the kill drain)."""
    deadline = time.monotonic() + timeout
    while True:
        left = deadline - time.monotonic()
        wait = min(STOP_POLL_SECONDS, left) if interrupted else left
        try:
            # Bounded like ``communicate``: a descendant holding the pipes
            # open after the CLI exits keeps this raising until Stop or the
            # deadline kills the group below.
            stdout, stderr = streamed.communicate(max(0.01, wait))
            streamed.close()
            return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            try:
                reason = interrupted() if interrupted else None
            except Exception:
                reason = None
            if reason or time.monotonic() >= deadline:
                kill_process_group(process)
                # The group is gone; a descendant that left it may still
                # hold the pipes, so draining is bounded and the pipes are
                # closed either way.
                try:
                    streamed.communicate(KILL_DRAIN_SECONDS)
                except (subprocess.TimeoutExpired, StreamLimitExceeded):
                    pass
                finally:
                    streamed.close()
                try:
                    process.wait(timeout=KILL_DRAIN_SECONDS)
                except subprocess.TimeoutExpired:
                    pass
                if reason:
                    raise EngineInterrupted(reason) from None
                raise subprocess.TimeoutExpired(argv, timeout) from None


@dataclass(frozen=True)
class ExecutionResult:
    content: str
    engine: str
    exit_code: int
    meta: dict = None


class AgentOSMcpTools:
    """The only tool facade that may be offered to a subscription engine.

    It offers the intersection of its route profile and the Work's current
    ``Capabilities.definitions()``, recomputed on every list and call, so a
    tool removed from the Work after discovery is refused, not remembered.
    """
    PROFILE = BOUNDED_PROFILE
    #: #678: set for a turn that may use the CLI's own web search; private reads are then not offered.
    native_search = False
    #: #701: why the CLI's own web search is off for this turn (a ``NATIVE_REASONS`` key), or ''.
    native_search_reason = ''
    #: #701: the service-side browser relay's address (a directory) for this turn, or None.
    browser_relay = None
    #: #701: in the bridge process, the client that forwards browser calls to the service.
    relay = None
    #: #718: the service's live-progress sink for the CLI's own steps during this turn, or None.
    progress = None
    #: #710: the orchestrator's validated tool subset for this turn, or None (the profile's set).
    only = None

    def __init__(self, capabilities, native_search=False):
        self.capabilities = capabilities
        self.native_search = bool(native_search)

    def _offered(self):
        allowed = set(turn_actions(self.PROFILE, self.native_search and self.PROFILE == BOUNDED_PROFILE, self.only))
        return {definition['function']['name']: definition for definition in self.capabilities.definitions()
                if definition['function']['name'] in allowed}

    def _search_note(self):
        """#701: the sentence a search-off CLI turn adds to the bridge search tools.

        It names why the CLI's own search is off and that the providers listed
        in the description answer instead; a provider's own caveat comes from
        the provider (``describe_options``), never from a branch here.
        """
        if self.native_search or not self.native_search_reason:
            return ''
        from .search_providers import NATIVE_REASONS
        why = NATIVE_REASONS.get(self.native_search_reason, '')
        return (" The CLI's own web search is off for this turn" + (f' ({why})' if why else '')
                + '; this tool answers with the providers listed above.')

    def definitions(self):
        # Fresh JSON-compatible copies: callers must not mutate the contract.
        from .agent_runtime import SEARCH_BACKED_ACTIONS
        tools = getattr(self.capabilities, 'tools', {}) or {}
        note = self._search_note()
        listed = []
        for name, definition in sorted(self._offered().items()):
            tool = mcp_tool(definition, (tools.get(name) or {}).get('mode'), self.PROFILE)
            if note and (tools.get(name) or {}).get('host_action') in SEARCH_BACKED_ACTIONS:
                tool['description'] += note
            listed.append(tool)
        return listed

    def call(self, name, arguments):
        if not isinstance(arguments, dict):
            raise ExecutionError('MCP 도구 인수는 객체여야 합니다.')
        definition = self._offered().get(name) if isinstance(name, str) else None
        if definition is None:
            raise ExecutionError('허용하지 않은 AgentOS MCP 도구 또는 인수입니다.')
        from .agent_runtime import check_arguments, split_status
        # #718: the optional status is display text; the bridge records it on
        # the running event and nothing here reads it.
        arguments, _status = split_status(arguments)
        parameters = definition['function']['parameters']
        try:
            check_arguments(parameters, arguments)
        except ValueError:
            raise ExecutionError('허용하지 않은 AgentOS MCP 도구 또는 인수입니다.') from None
        if any(not arguments[field].strip() for field in parameters['required']):
            raise ExecutionError('MCP 도구의 필수 문자열 인수가 비어 있습니다.')
        # #701/#774: in the bridge process a browser or owner-state tool runs in
        # the AgentOS service (its BrowserSession, Memory approval, calendar
        # connector, preparation acceptance, budget and mediation); the bridge
        # only forwards the validated call.
        from .agent_runtime import HOST_RELAYED_ACTIONS
        host_action = ((getattr(self.capabilities, 'tools', {}) or {}).get(name) or {}).get('host_action')
        if host_action in HOST_RELAYED_ACTIONS and self.relay is not None:
            return self.relay.call(name, arguments)
        # Capabilities is AgentOS-owned and applies its normal validation,
        # document boundary, egress, evidence and idempotency rules.
        return self.capabilities.execute(name, arguments)


class ReadOnlyAgentOSMcpTools(AgentOSMcpTools):
    """Isolated-engine facade: the deliberately restricted isolation profile."""
    PROFILE = ISOLATED_PROFILE


class StrictIsolatedAgentOSMcpTools(AgentOSMcpTools):
    """Host-CLI facade under the strict-isolated profile (#616).

    ``qualification`` is the owner's stored qualification record for this CLI
    (version, platform, binary identity, resolved paths and, for Codex, the
    verified feature-disable plan).  The adapter refuses to launch unless the
    current CLI and paths still match it; without one nothing runs.
    """
    PROFILE = STRICT_PROFILE

    def __init__(self, capabilities, qualification=None):
        super().__init__(capabilities)
        self.qualification = dict(qualification) if isinstance(qualification, dict) else None

    @property
    def qualified_version(self):
        return (self.qualification or {}).get('version')


class BoundedExecutionAdapter:
    """Start an official subscription CLI with no shell and no inherited env.

    The adapter intentionally has no generic argv, cwd, environment, or tool
    configuration parameters.  Expanding those is a security design change,
    not an engine prompt option.
    """
    def __init__(self, finder=None, runner=subprocess.run, runtime_root=None, codex_home=None, credentials=None):
        from shutil import which
        self.finder = finder or which
        self.runner = runner
        configured_root = runtime_root or os.environ.get('AGENTOS_ENGINE_RUNS')
        self.runtime_root = Path(configured_root).expanduser() if configured_root else Path.home()/'.local/share/agentos/engine-runs'
        self.codex_home = Path(codex_home).expanduser() if codex_home else None
        # Narrow credential source (#571): returns the owner-provided token for
        # an engine or ''. Only Claude Code uses it, as its documented
        # CLAUDE_CODE_OAUTH_TOKEN; HOME stays the empty per-turn directory.
        self.credentials = credentials or (lambda engine_id: '')

    def environment(self, engine_id, binary, run_dir):
        env = {'HOME': str(run_dir), 'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}
        env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
        if engine_id == 'claude-code':
            token = self.credentials('claude-code')
            if isinstance(token, str) and token:
                env['CLAUDE_CODE_OAUTH_TOKEN'] = token
            return env
        if engine_id != 'codex':
            return env
        # Codex owns its official session under CODEX_HOME. AgentOS never
        # reads, copies, logs, exports, or persists that profile; the CLI reads
        # it directly while its working directory remains a fresh sandbox.
        profile = self.codex_home or Path(os.environ.get('CODEX_HOME', Path.home()/'.codex')).expanduser()
        if not profile.is_dir():
            raise ExecutionError('Codex의 공식 로그인 프로필을 찾지 못했습니다. Codex에서 다시 로그인하세요.')
        env['CODEX_HOME'] = str(profile)
        binary_path = Path(binary)
        if binary_path.is_absolute():
            env['PATH'] = str(binary_path.parent) + ':' + env['PATH']
        return env

    def login_status(self, engine_id, binary=None):
        """Ask the official CLI whether it is signed in, under the same
        environment AgentOS uses to run it (#571). Local and read-only: no
        model request, no credential file is read by AgentOS.

        Returns {'state': 'signed-in'|'signed-out'|'unknown', 'detail': str}.
        """
        binaries = {'codex': 'codex', 'claude-code': 'claude'}
        if engine_id not in binaries:
            return {'state': 'unknown', 'detail': 'unsupported engine'}
        binary = binary or self.finder(binaries[engine_id])
        if not binary:
            return {'state': 'signed-out', 'detail': 'CLI not found'}
        argv = [binary, 'auth', 'status', '--json'] if engine_id == 'claude-code' else [binary, 'login', 'status']
        self.runtime_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(dir=self.runtime_root, prefix='login-') as folder:
            try:
                env = self.environment(engine_id, binary, Path(folder))
            except ExecutionError:
                return {'state': 'signed-out', 'detail': 'login profile not found'}
            try:
                done = self.runner(argv, cwd=folder, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                                   text=True, timeout=20, shell=False)
            except (subprocess.TimeoutExpired, OSError) as exc:
                return {'state': 'unknown', 'detail': type(exc).__name__}
        out = (done.stdout or '') + '\n' + (getattr(done, 'stderr', '') or '')
        if engine_id == 'claude-code':
            try:
                data = json.loads(done.stdout or '')
            except ValueError:
                data = None
            if isinstance(data, dict) and isinstance(data.get('loggedIn'), bool):
                # `claude auth status` only sees that a token is present; it
                # does not validate it. Report that honestly until a real run
                # confirms or rejects the token.
                if data['loggedIn'] and data.get('authMethod') == 'oauth_token':
                    return {'state': 'token-saved', 'detail': 'oauth_token'}
                return {'state': 'signed-in' if data['loggedIn'] else 'signed-out',
                        'detail': str(data.get('authMethod') or '')[:40]}
            return {'state': 'signed-out' if is_not_signed_in(out) else 'unknown', 'detail': 'unparsed status'}
        if done.returncode == 0 and re.search(r'logged in', out, re.I) and not re.search(r'not logged in', out, re.I):
            return {'state': 'signed-in', 'detail': ''}
        # Only an explicit "not logged in" is a sign-out; any other failure
        # (older CLI, transient error) stays unknown.
        # Match the explicit phrase only: usage text of an older CLI mentions
        # `codex login` and must not read as a sign-out.
        if re.search(r'\bnot\s+(?:logged|signed)\s+in\b', out, re.I):
            return {'state': 'signed-out', 'detail': ''}
        return {'state': 'unknown', 'detail': 'unparsed status'}

    def command(self, engine_id, binary, prompt, mcp_config, instructions='', profile=BOUNDED_PROFILE,
                disabled_features=(), model=None, native_search=False, only=None, tool_timeout=None):
        """The argv of one Work turn.

        ``native_search`` (#678) lets the trusted-local turn use the CLI's own
        web search: Codex ``-c web_search="live"`` (``exec`` has no
        ``--search`` flag), Claude Code ``--tools WebSearch`` with
        ``WebSearch`` added to the exact ``--allowedTools`` list.  Without it
        Codex gets ``web_search="disabled"`` and the Claude Code argv is
        unchanged.  The strict-isolated profile never enables it: its qualified
        feature plan keeps every non-allowlisted feature off.  Judgment calls
        (``decision_adapters``) are a separate argv and keep search disabled.
        """
        if profile not in HOST_CLI_PROFILES:
            raise ExecutionError('지원하지 않는 구독 엔진 실행 프로필입니다.')
        # #679: the owner's Main AI model for this CLI, as the CLI's own
        # documented `--model` flag (one argv element; the shape is checked).
        # None: the CLI's own default for this isolated invocation.
        from .decision_adapters import valid_model_id
        if model is not None and not valid_model_id(model):
            raise ExecutionError('모델 이름 형식을 확인하세요.', failure_class='invalid-configuration')
        model_args = ['--model', model] if model else []
        strict = profile == STRICT_PROFILE
        native_search = bool(native_search) and not strict
        if engine_id == 'codex':
            # `exec` is non-interactive and JSON output is required so prose
            # around an answer cannot be mistaken for execution evidence.
            bridge = json.loads(Path(mcp_config).read_text())['mcpServers']['agentos']
            # --ignore-user-config keeps the owner's own Codex defaults (model,
            # MCP servers, plugins) out of this bounded turn; login still
            # comes from CODEX_HOME.  --ephemeral keeps no session files.
            # trusted-local: --ignore-rules so an "always allow" CODEX_HOME exec
            # rule cannot run a command outside the read-only sandbox (#636,
            # the #616 review P1 finding); an older CLI rejects the unknown
            # flag and the turn fails instead of running without it.
            sandbox = (strict_launch_arguments('codex', disabled_features) if strict
                       else ['--sandbox', 'read-only', '--ignore-rules',
                             '-c', 'web_search="live"' if native_search else 'web_search="disabled"'])
            # --ignore-user-config also drops the owner's config.toml model, so
            # the owner's Main AI model choice is passed explicitly (#679).
            return [binary, 'exec', '--json', *sandbox, '--skip-git-repo-check',
                    '--ignore-user-config', '--ephemeral',
                    '-c', f'mcp_servers.agentos.command={json.dumps(sys.executable)}',
                    '-c', f'mcp_servers.agentos.args={json.dumps(bridge["args"])}',
                    # #709: AgentOS decides its own bridge tools (see CODEX_BRIDGE_APPROVAL_MODE).
                    '-c', codex_bridge_approval_argument(),
                    # #729: the agentos server's own tool-call timeout (see CODEX_TOOL_TIMEOUT_KEY).
                    *(['-c', codex_bridge_timeout_argument(tool_timeout)] if tool_timeout else []), *model_args, prompt]
        if engine_id == 'claude-code':
            # #570: stream-json (which requires --verbose with -p) reports the
            # session model and each tool_use; its last line is the same result
            # record that `json` prints, so answer parsing is unchanged.
            argv = [binary, '-p', prompt, '--output-format', 'stream-json', '--verbose',
                    '--strict-mcp-config', '--mcp-config', str(mcp_config), *model_args]
            if instructions:
                # #569: AgentOS instructions travel as a system-prompt addition,
                # the conversation and request as the prompt.
                argv += ['--append-system-prompt', instructions]
            # #623: trusted-local pre-approves only its declared bridge tools;
            # strict also removes every built-in tool.  --allowedTools is variadic,
            # so it must stay the last argument.  #709: nothing else is needed for
            # AgentOS to decide its own bridge tools here: HOME is the turn's own
            # directory (no owner settings, so no other permission mode), and an
            # exact allow rule is the approval Claude Code's -p mode checks.
            if strict:
                argv += strict_launch_arguments('claude-code')
            elif native_search:
                # Only WebSearch among the built-in tools, pre-approved by its exact name.
                # The private-read bridge tools are neither listed nor pre-approved (#678 P1).
                allow = claude_bridge_allowlist(BOUNDED_PROFILE, native_search=True, only=only)
                argv += ['--tools', CLAUDE_NATIVE_SEARCH_TOOL, allow[0], ','.join(filter(None, (allow[1], CLAUDE_NATIVE_SEARCH_TOOL)))]
            else:
                # #710: only the orchestrator's subset is pre-approved when it chose one.
                argv += claude_bridge_allowlist(BOUNDED_PROFILE, only=only)
            return argv
        raise ExecutionError('지원하는 구독 엔진을 선택하세요.')

    def runtime_version(self, engine_id, binary, run_dir):
        """The version the CLI itself reports, run in the AgentOS environment.

        Local and model-free; no credential is passed to this call.
        """
        env = {key: value for key, value in self.environment(engine_id, binary, run_dir).items()
               if key != 'CLAUDE_CODE_OAUTH_TOKEN'}
        try:
            done = self.runner([binary, '--version'], cwd=run_dir, env=env, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, timeout=20, shell=False)
        except (subprocess.TimeoutExpired, OSError):
            return None
        return parse_cli_version(engine_id, done.stdout) if done.returncode == 0 else None

    def _login_profile(self):
        return Path(self.codex_home or os.environ.get('CODEX_HOME', Path.home() / '.codex')).expanduser()

    #: codex.js's PLATFORM_PACKAGE_BY_TARGET, keyed by (sys.platform, machine).
    CODEX_NATIVE_PACKAGES = {
        ('darwin', 'arm64'): ('aarch64-apple-darwin', 'codex-darwin-arm64'),
        ('darwin', 'x86_64'): ('x86_64-apple-darwin', 'codex-darwin-x64'),
        ('linux', 'aarch64'): ('aarch64-unknown-linux-musl', 'codex-linux-arm64'),
        ('linux', 'x86_64'): ('x86_64-unknown-linux-musl', 'codex-linux-x64'),
    }
    #: Mach-O (64-bit, either byte order), fat/universal Mach-O and ELF.
    NATIVE_MAGIC = (b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\x7fELF')

    @classmethod
    def _native_file(cls, path):
        try:
            with open(path, 'rb') as stream:
                return stream.read(4) in cls.NATIVE_MAGIC
        except OSError:
            return False

    @classmethod
    def native_cli_binary(cls, engine_id, binary):
        """The native executable the CLI launcher actually runs, or ``''``.

        Claude Code's launcher resolves to its native binary.  The npm/Homebrew
        ``codex`` resolves to the ``codex.js`` shim, which spawns the platform
        package's ``vendor/<triple>/bin/codex``; that lookup is mirrored here
        (the shim's ``findCodexExecutable``: Node package resolution from the
        shim's directory, then the package's own ``vendor``).  Anything else,
        such as a shell wrapper or an unknown layout, gives ``''``, which
        fails strict qualification closed.
        """
        if not binary:
            return ''
        resolved = Path(os.path.realpath(binary))
        if engine_id == 'codex' and resolved.suffix == '.js':
            import platform
            target = cls.CODEX_NATIVE_PACKAGES.get((sys.platform, platform.machine()))
            if not target:
                return ''
            triple, package = target
            vendor = resolved.parent.parent / 'vendor'
            # require.resolve('@openai/<package>/package.json') walks up from
            # the shim's directory, skipping directories named node_modules.
            for directory in (resolved.parent, *resolved.parent.parents):
                if directory.name == 'node_modules':
                    continue
                candidate = directory / 'node_modules' / '@openai' / package
                if (candidate / 'package.json').is_file():
                    vendor = candidate / 'vendor'
                    break
            resolved = vendor / triple / 'bin' / 'codex'
            if not resolved.is_file():
                return ''
            resolved = resolved.resolve()
        return str(resolved) if resolved.is_file() and cls._native_file(resolved) else ''

    @staticmethod
    def _sha256(path):
        if not path:
            return None
        import hashlib
        digest = hashlib.sha256()
        try:
            with open(path, 'rb') as stream:
                for chunk in iter(lambda: stream.read(1 << 20), b''):
                    digest.update(chunk)
        except OSError:
            return None
        return digest.hexdigest()

    def strict_digests(self, engine_id, binary):
        """sha256 of the launched file and of the native executable it runs."""
        return {'binary_sha256': self._sha256(os.path.realpath(binary) if binary else ''),
                'native_sha256': self._sha256(self.native_cli_binary(engine_id, binary))}

    def strict_binding(self, engine_id, binary, store_root):
        """What a strict qualification is bound to, computed without a subprocess.

        Platform, the resolved CLI launcher and the native executable it runs
        with their (#580) fingerprints, and the resolved owner store, home,
        engine runtime root and (Codex) login profile.  A change to any of
        them makes the qualification stale; the sha256 digests are compared
        separately on every strict turn.
        """
        from .decision_adapters import cli_fingerprint
        native = self.native_cli_binary(engine_id, binary)
        binding = {'platform': sys.platform, 'binary': os.path.realpath(binary) if binary else '',
                   'fingerprint': cli_fingerprint(binary), 'native_binary': native,
                   'native_fingerprint': cli_fingerprint(native) if native else '',
                   'home': str(Path.home().resolve()),
                   'runtime_root': str(Path(self.runtime_root).expanduser().resolve()),
                   'store': str(Path(store_root).expanduser().resolve()) if store_root else ''}
        if engine_id == 'codex':
            binding['codex_home'] = str(self._login_profile().resolve())
        return binding

    def strict_binding_mismatch(self, engine_id, qualification, store_root, binary=None):
        """Binding fields that no longer match a stored qualification (no subprocess)."""
        recorded = (qualification or {}).get('binding')
        if not isinstance(recorded, dict):
            return ['binding']
        binary = binary or self.finder({'codex': 'codex', 'claude-code': 'claude'}.get(engine_id, ''))
        current = self.strict_binding(engine_id, binary, store_root)
        return sorted(key for key in current if recorded.get(key) != current[key])

    def _codex_sandbox_denies(self, binary, run_dir, target):
        """Run the CLI's own sandbox runner under the strict permissions profile.

        ``/bin/ls`` output is discarded, so no protected content is read into
        AgentOS.  The runner gets an empty CODEX_HOME so the owner's Codex
        config cannot change the policy under test (``exec`` ignores it too).
        Returns True when the listing was refused, False when it succeeded.
        """
        home = run_dir / '.codex-qualify'
        home.mkdir(exist_ok=True, mode=0o700)
        env = {**self.environment('codex', binary, run_dir), 'CODEX_HOME': str(home)}
        argv = [binary, 'sandbox', '-C', str(run_dir), '-c', CODEX_STRICT_TABLE, '-P', CODEX_STRICT_PERMISSIONS,
                '--', '/bin/ls', str(target)]
        done = self.runner(argv, cwd=run_dir, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=30, shell=False)
        return done.returncode != 0

    def _codex_feature_plan(self, binary, run_dir):
        """Reuse the #580 allowlist plan for the strict Work profile.

        ``codex features list`` (local, no model) with an empty CODEX_HOME,
        ``--disable`` every listed non-removed feature outside
        ``strict_allowed_features()``, list again with those disables and
        fail closed unless only allowlisted features remain enabled.
        Returns ``(plan, remaining)``; ValueError on anything unparsable.
        """
        from .decision_adapters import codex_disable_plan, codex_still_enabled, parse_codex_features
        home = run_dir / '.codex-qualify'
        home.mkdir(exist_ok=True, mode=0o700)
        env = {**self.environment('codex', binary, run_dir), 'CODEX_HOME': str(home)}
        allowed = strict_allowed_features()

        def listing(argv):
            done = self.runner(argv, cwd=run_dir, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                               text=True, timeout=30, shell=False)
            if done.returncode != 0:
                raise ValueError(f'features list exit {done.returncode}')
            return parse_codex_features(done.stdout)
        plan = codex_disable_plan(listing([binary, 'features', 'list']), allowed)
        argv = [binary, 'features', 'list']
        for feature in plan:
            argv += ['--disable', feature]
        return plan, codex_still_enabled(listing(argv), allowed)

    def qualify_strict(self, engine_id, binary=None, store_root=None):
        """No-model qualification of the strict-isolated profile for one CLI.

        Passes only when all hold: a tested platform and CLI version; an
        engine runtime root outside the paths Codex's baseline keeps readable;
        and, for Codex, (a) its own sandbox runner under the exact permissions
        profile refuses the owner store, home, the login profile and a sibling
        turn directory while a control listing of the turn directory succeeds,
        and (b) the #580-style feature plan leaves only allowlisted features.
        The record binds the resolved binary (path, sha256, fingerprint) and
        paths.  It never contains file content.  Claude Code's confinement is
        structural (no built-in tools), so version, platform and paths are
        its checks.
        """
        declared = CLI_PROFILES[STRICT_PROFILE]['runtimes'].get(engine_id)
        if declared is None:
            return {'engine': engine_id, 'qualified': False, 'version': None, 'checks': [], 'reason': 'unsupported engine'}
        binary = binary or self.finder({'codex': 'codex', 'claude-code': 'claude'}[engine_id])
        if not binary:
            return {'engine': engine_id, 'qualified': False, 'version': None, 'checks': [], 'reason': 'CLI not found'}
        # The process-level evidence is per platform (Codex: macOS Seatbelt).
        checks = [{'check': 'tested-platform', 'observed': sys.platform,
                   'expected': list(declared['tested_platforms']), 'passed': sys.platform in declared['tested_platforms']}]
        if not checks[0]['passed']:
            return {'engine': engine_id, 'profile': STRICT_PROFILE, 'qualified': False, 'version': None,
                    'checks': checks, 'reason': 'tested-platform'}
        runtime_root = Path(self.runtime_root).expanduser().resolve()
        under_baseline = any(runtime_root == Path(root).resolve() or Path(root).resolve() in runtime_root.parents
                             for root in BASELINE_READABLE_ROOTS)
        checks.append({'check': 'runtime-root-not-baseline-readable', 'passed': not under_baseline})
        disabled, version = None, None
        if not under_baseline:
            self.runtime_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.TemporaryDirectory(dir=self.runtime_root, prefix='qualify-') as folder, \
                    tempfile.TemporaryDirectory(dir=self.runtime_root, prefix='qualify-sibling-') as sibling:
                run_dir = Path(folder)
                try:
                    version = self.runtime_version(engine_id, binary, run_dir)
                    checks.append({'check': 'tested-version', 'observed': version,
                                   'expected': list(declared['tested_versions']),
                                   'passed': version in declared['tested_versions']})
                    if engine_id == 'codex' and checks[-1]['passed']:
                        checks.append({'check': 'turn-directory-readable',
                                       'passed': not self._codex_sandbox_denies(binary, run_dir, run_dir)})
                        checks.append({'check': 'sibling-turn-denied',
                                       'passed': self._codex_sandbox_denies(binary, run_dir, Path(sibling))})
                        for target in (Path.home(), self._login_profile(), *([store_root] if store_root else [])):
                            target = Path(target).expanduser()
                            if not target.is_dir():
                                continue
                            checks.append({'check': 'protected-directory-denied', 'target': target.name or str(target),
                                           'passed': self._codex_sandbox_denies(binary, run_dir, target)})
                        try:
                            plan, remaining = self._codex_feature_plan(binary, run_dir)
                            checks.append({'check': 'tool-features-allowlisted', 'passed': bool(plan) and not remaining,
                                           'still_enabled': remaining})
                            disabled = plan if plan and not remaining else None
                        except ValueError as exc:
                            checks.append({'check': 'tool-features-allowlisted', 'passed': False, 'error': str(exc)[:120]})
                except (ExecutionError, subprocess.TimeoutExpired, OSError) as exc:
                    checks.append({'check': 'runner', 'passed': False, 'error': type(exc).__name__})
        binding = self.strict_binding(engine_id, binary, store_root)
        digests = self.strict_digests(engine_id, binary)
        checks.append({'check': 'native-binary-identified',
                       'passed': bool(binding['native_binary']) and all(digests.values())})
        qualified = all(check['passed'] for check in checks)
        failed = [check['check'] for check in checks if not check['passed']]
        return {'engine': engine_id, 'profile': STRICT_PROFILE, 'qualified': qualified, 'version': version,
                'checks': checks, 'binding': binding, **digests,
                'disabled_features': disabled if engine_id == 'codex' else None,
                'reason': '' if qualified else ', '.join(dict.fromkeys(failed)) or 'not checked'}

    @staticmethod
    def _content(engine_id, raw):
        """The final answer text of one CLI turn's machine output.

        #736: both CLIs stream every tool result before the answer, so only
        the final answer record is bounded by ``MAX_OUTPUT_BYTES``; the whole
        stream has the larger runaway guard ``MAX_STREAM_BYTES``.  The error
        names which bound was hit.
        """
        raw = raw or ''
        if len(raw.encode()) > MAX_STREAM_BYTES:
            raise ExecutionError(STREAM_TOO_LARGE)
        lines = [line for line in raw.splitlines() if line.strip()]
        if engine_id == 'claude-code':
            # The result record is the last line of the stream.
            lines = lines[-1:]
        try:
            # Machine output is JSONL.  Only structured records are examined;
            # progress/event text is never concatenated into an answer.
            records = [(json.loads(line), line) for line in lines]
            data = records[-1][0]
        except (TypeError, ValueError, IndexError):
            raise ExecutionError('엔진이 요구된 구조화된 응답을 반환하지 않았습니다.') from None
        answer_line = records[-1][1]
        if engine_id == 'codex':
            # Codex ends JSONL with usage/completion metadata. Select the last
            # structured agent message instead of treating that terminal event
            # as response text or exposing the event stream to the owner.
            content = None
            for candidate, line in reversed(records):
                if not isinstance(candidate, dict):
                    continue
                item = candidate.get('item')
                if isinstance(item, dict) and item.get('type') == 'agent_message':
                    text = item.get('text')
                    if isinstance(text, str) and text.strip():
                        content, answer_line = text, line
                        break
                text = candidate.get('content') or candidate.get('output')
                if isinstance(text, str) and text.strip():
                    content, answer_line = text, line
                    break
        else:
            content = data.get('result') if isinstance(data, dict) else None
        if len(answer_line.encode()) > MAX_OUTPUT_BYTES:
            raise ExecutionError(FINAL_RECORD_TOO_LARGE)
        if not isinstance(content, str) or not content.strip():
            raise ExecutionError('엔진 응답에 최종 텍스트 결과가 없습니다.')
        return content[:24_000]

    def execute(self, engine_id, prompt, tools, *, context=None, model=None):
        instructions = ''
        if context and engine_id == 'claude-code':
            # Claude Code accepts a system-prompt addition; send the shared
            # instructions there and only conversation + request as the prompt.
            from .agent_runtime import render_turn_prompt
            instructions = context['instructions']
            prompt = render_turn_prompt(context, include_instructions=False)
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode()) > MAX_PROMPT_BYTES:
            raise ExecutionError('요청은 비어 있지 않은 48KB 이하의 텍스트여야 합니다.')
        binaries = {'codex': 'codex', 'claude-code': 'claude'}
        if engine_id not in binaries:
            raise ExecutionError('지원하는 구독 엔진을 선택하세요.')
        binary = self.finder(binaries[engine_id])
        if not binary:
            raise ExecutionError('연결한 구독 엔진 CLI를 격리된 런타임에서 찾지 못했습니다.')
        # Only declarative tool metadata is written here.  Tool calls must be
        # served by the AgentOS MCP bridge, never by engine-provided commands.
        self.runtime_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.runtime_root.chmod(0o700)
        with tempfile.TemporaryDirectory(dir=self.runtime_root, prefix='turn-') as folder:
            run_dir = Path(folder)
            config = run_dir / 'agentos-mcp.json'
            profile = getattr(tools, 'PROFILE', BOUNDED_PROFILE)
            # #678: a native-search turn's bridge never serves private reads.
            native_search = bool(getattr(tools, 'native_search', False)) and profile == BOUNDED_PROFILE
            # #701: only the trusted-local route is ever given the service's browser relay.
            relay = getattr(tools, 'browser_relay', None) if profile == BOUNDED_PROFILE else None
            search_off = str(getattr(tools, 'native_search_reason', '') or '') if not native_search else ''
            # #710: the orchestrator's per-request subset narrows what the bridge offers.
            only = getattr(tools, 'only', None)
            only = None if only is None else frozenset(str(name) for name in only)
            # Both supported CLIs receive this per-turn bridge configuration.
            # The engine gets no store handle; the bridge alone owns validated
            # access to the AgentOS tool facade.
            config.write_text(json.dumps({'mcpServers': {'agentos': {
                'command': sys.executable,
                # The bridge never needs the CLI's own credential.
                **({'env': {'CLAUDE_CODE_OAUTH_TOKEN': ''}} if engine_id == 'claude-code' else {}),
                'args': ['-m', 'personal_agent.mcp_bridge', '--data', str(tools.capabilities.store.root), '--job', tools.capabilities.job_id,
                         # The bridge is a separate process: hand it this Work's
                         # private-source provenance so its public egress closes
                         # exactly as the in-process Capabilities would.
                         *[f'--provenance={label}' for label in sorted(getattr(tools.capabilities, 'private_provenance', ()) or ())],
                         # #701: the bridge serves exactly this route's profile.
                         f'--profile={profile}',
                         *(['--native-search'] if native_search else []),
                         *([f'--search-off-reason={search_off}'] if search_off else []),
                         *([f'--only={",".join(sorted(only))}'] if only is not None else []),
                         *([f'--browser-relay={relay}'] if relay else []),
                         # #774: the relay serves owner-state tools even when no browser is served.
                         *(['--relay-no-browser'] if relay and not getattr(tools, 'relay_browser', True) else [])],
            }}}, ensure_ascii=False), encoding='utf-8')
            env = self.environment(engine_id, binary, run_dir)
            disabled = ()
            if profile == STRICT_PROFILE:
                # #616: never launch an unqualified CLI under the strict
                # profile and never fall back to trusted-local; the owner
                # requalifies after a CLI upgrade or chooses another profile.
                # Platform, binary and paths are checked too: a data folder
                # moved to another OS or install keeps its record but is
                # refused here.
                declared = CLI_PROFILES[STRICT_PROFILE]['runtimes'][engine_id]
                qualification = getattr(tools, 'qualification', None) or {}
                stale = self.strict_binding_mismatch(engine_id, qualification, tools.capabilities.store.root, binary)
                disabled = qualification.get('disabled_features') or ()
                if engine_id == 'codex' and not disabled:
                    stale.append('disabled_features')
                if not stale:
                    # Review N2: the qualified bytes, not only path/size/mtime.
                    current = self.strict_digests(engine_id, binary)
                    stale += [key for key, value in current.items() if not value or value != qualification.get(key)]
                version = (self.runtime_version(engine_id, binary, run_dir)
                           if sys.platform in declared['tested_platforms'] and not stale else None)
                if stale or version is None or version not in declared['tested_versions'] \
                        or version != qualification.get('version'):
                    LOG.warning('engine turn refused engine=%s profile=%s version=%s', engine_id, profile, version or '-')
                    raise ExecutionError('엄격 격리 프로필이 현재 CLI 버전 또는 플랫폼에서 검증되지 않아 실행하지 않았습니다. '
                                         '설정에서 다시 검증하거나 다른 실행 프로필을 선택하세요.',
                                         failure_class='isolation-unqualified',
                                         reason=f'stale: {", ".join(stale) or "version"}; observed version {version or "unknown"}')
            # #607 AX-10: the CLI gets at most the Work's remaining shared
            # budget, and the owner's Stop kills its process group mid-run.
            budget = getattr(tools.capabilities, 'budget', None)
            timeout = MAX_TIMEOUT_SECONDS
            if budget is not None and hasattr(budget, 'remaining'):
                timeout = max(1, min(MAX_TIMEOUT_SECONDS, int(budget.remaining())))
            interrupted = getattr(budget, 'interrupted', None)
            started = time.monotonic()
            LOG.info('engine turn started engine=%s profile=%s', engine_id, profile)
            # #678: the facade says whether this turn may use the CLI's own web search.
            # #729: the bridge tools this turn offers bound Codex's per-call timeout.
            offered = [action for action in turn_actions(profile, native_search, only)
                       if (relay is not None and getattr(tools, 'relay_browser', True)) or action not in _BROWSER_ACTIONS]
            argv = self.command(engine_id, binary, prompt, config, instructions, profile=profile, disabled_features=disabled,
                                model=model or None, native_search=native_search, only=only,
                                tool_timeout=bridge_tool_timeout(offered, timeout))
            run_meta = {'argv': display_argv(argv, prompt, instructions), 'requested_model': model or None}
            try:
                if self.runner is subprocess.run:
                    # #718: the facade's live-progress sink (set by the service), if any.
                    progress = getattr(tools, 'progress', None)
                    completed = bounded_run(self.runner, argv, cwd=run_dir, env=env, timeout=timeout,
                                            interrupted=interrupted,
                                            on_line=live_progress_reader(engine_id, progress) if callable(progress) else None)
                else:
                    completed = self.runner(argv, cwd=run_dir,
                                            env=env, stdin=subprocess.DEVNULL, capture_output=True,
                                            text=True, timeout=timeout, shell=False)
            except EngineInterrupted as exc:
                elapsed_ms = int((time.monotonic() - started) * 1000)
                LOG.warning('engine turn interrupted engine=%s reason=%s', engine_id, exc.reason)
                if exc.reason == 'stopped':
                    raise ExecutionError(ENGINE_STOPPED, failure_class='stopped',
                                         meta={**run_meta, 'duration_ms': elapsed_ms}) from None
                raise ExecutionError('이 작업의 처리 시간 한도에 도달해 구독 엔진 실행과 그 하위 프로세스를 종료했습니다.',
                                     failure_class='deadline_exceeded', meta={**run_meta, 'duration_ms': elapsed_ms}) from None
            except subprocess.TimeoutExpired as exc:
                LOG.warning('engine turn timed out engine=%s after=%ss', engine_id, timeout)
                # A Work whose shared deadline, not the CLI cap, ended the run
                # is typed deadline_exceeded (#607); both kill the group.
                failure_class = 'deadline_exceeded' if timeout < MAX_TIMEOUT_SECONDS else 'timeout'
                raise ExecutionError(f'구독 엔진이 {timeout}초 안에 응답하지 않아 실행과 그 하위 프로세스를 종료했습니다.',
                                     failure_class=failure_class, meta={**run_meta, 'duration_ms': timeout * 1000}) from exc
            except OSError as exc:
                LOG.warning('engine turn could not start engine=%s error=%s', engine_id, type(exc).__name__)
                raise ExecutionError('구독 엔진 CLI를 실행하지 못했습니다.', failure_class='start-failed') from exc
            elapsed = time.monotonic() - started
            if completed.returncode != 0:
                # Remove the stored credential's literal value before any
                # output is parsed, logged or shown, whatever its format.
                secret = self.credentials(engine_id) if engine_id == 'claude-code' else ''
                scrub = (lambda text: (text or '').replace(secret, '[redacted]')) if isinstance(secret, str) and len(secret) >= 8 else (lambda text: text or '')
                stdout, stderr = scrub(completed.stdout), scrub(getattr(completed, 'stderr', ''))
                status, reason = failure_details(engine_id, stdout, stderr, prompt)
                failure_class, hint = 'engine-failed', ''
                for match, name, text in _STATUS_HINTS:
                    if status is not None and match(status):
                        failure_class, hint = name, text
                        break
                # Only the structured error and stderr: stdout carries model
                # and tool text that may merely mention signing in.
                if failure_class == 'engine-failed' and is_not_signed_in(' '.join((reason or '', stderr[-4000:]))):
                    failure_class, hint = 'auth', AUTH_HINT
                LOG.warning('engine turn failed engine=%s exit_code=%s class=%s status=%s duration=%.1fs reason=%s',
                            engine_id, completed.returncode, failure_class, status, elapsed, reason or '-')
                message = f'{ENGINE_NAMES[engine_id]} 엔진이 작업을 완료하지 못했습니다(종료 코드 {completed.returncode}).'
                if hint:
                    message += ' ' + hint
                if reason:
                    message += f' 엔진 응답: {reason}'
                # #735: the CLI's own unsupported-model signal, for the requested model only.
                refused = unsupported_model(engine_id, model, reason, stderr)
                raise ExecutionError(message, failure_class=failure_class,
                                     exit_code=completed.returncode, reason=reason,
                                     meta={**run_meta, **cli_metadata(engine_id, stdout),
                                           'duration_ms': int(elapsed * 1000),
                                           **({'unsupported_model': refused} if refused else {})})
            try:
                content = self._content(engine_id, completed.stdout)
            except ExecutionError as exc:
                LOG.warning('engine turn returned no usable result engine=%s duration=%.1fs', engine_id, elapsed)
                raise ExecutionError(str(exc), failure_class='invalid-output', exit_code=0,
                                     meta={**run_meta, **cli_metadata(engine_id, completed.stdout), 'duration_ms': int(elapsed * 1000)}) from None
            LOG.info('engine turn succeeded engine=%s duration=%.1fs', engine_id, elapsed)
            return ExecutionResult(content, engine_id, completed.returncode,
                                   {**run_meta, **cli_metadata(engine_id, completed.stdout), 'duration_ms': int(elapsed * 1000)})

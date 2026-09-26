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
import subprocess
import sys
import tempfile
import time


MAX_PROMPT_BYTES = 48_000
MAX_OUTPUT_BYTES = 96_000
MAX_TIMEOUT_SECONDS = 120
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

#: The verified limitation of the trusted-local profile (owner decision on
#: #604).  The CLI's own built-in tools can read local host files that AgentOS
#: never mediates, so those reads carry no AgentOS provenance and the public
#: reads offered here cannot be closed by it.  Observed with a no-model probe of
#: `codex sandbox -P :read-only` (the policy behind `codex exec --sandbox
#: read-only`) on codex-cli 0.153.4: a fake owner store, a home file and the
#: turn directory were readable; network and writes were blocked.  Claude Code
#: 2.1.280 documents that its file tools may read outside the working directory
#: unless `--restricted` is used (not observed locally).  The owner accepts this
#: trusted-local-worker risk; strict read isolation is #616 AGENCY-ISOLATION-01.
TRUSTED_LOCAL_LIMITATION = ('the CLI may read host files outside AgentOS provenance '
                            '(verified: codex sandbox -P :read-only, codex-cli 0.153.4)')

#: The verified limitation of the strict-isolated profile (#616).  Observed
#: with no-model process tests that drive the exact argv below through a real
#: `codex exec` / `claude -p` against a local fake provider on a fake store
#: (tests/test_strict_isolation.py): the owner store, the home directory and
#: CODEX_HOME were unreadable, the turn directory was readable (Codex) and the
#: AgentOS bridge still served its tools.  Codex's `:minimal` platform set
#: keeps OS paths and /tmp readable; an explicit deny does not override it.
STRICT_ISOLATED_LIMITATION = ('the CLI reads only its turn directory and AgentOS-mediated tool results; '
                              'owner store and home reads are denied at process level, but Codex still '
                              'reads OS system paths and /tmp; qualified only for the tested CLI versions')

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
        'actions': ('bounded_public_research', 'list_notes', 'save_note', 'weather', 'web_search'),
        # Approvals bound to the direct-API model fingerprint are not carried to
        # another provider: doing so would silently change the data destination.
        'unavailable': {
            'public_page_read': _API_BOUND_PAGES,
            'find_files': _API_BOUND_DOCUMENTS, 'read_file': _API_BOUND_DOCUMENTS, 'list_roots': _API_BOUND_DOCUMENTS,
            'calendar_query': _CALENDAR, 'calendar_draft_create': _CALENDAR,
            'calendar_draft_update': _CALENDAR, 'calendar_draft_cancel': _CALENDAR,
            'save_memory': _MEMORY, 'list_memory': _MEMORY,
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
            'list_agents', 'delegate_agent')},
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
        # The bridge serves the bounded action set (mcp_bridge.serve); a test
        # keeps these identical so the bridge needs no profile argument.
        'actions': ('bounded_public_research', 'list_notes', 'save_note', 'weather', 'web_search'),
        'unavailable': {
            'public_page_read': _API_BOUND_PAGES,
            'find_files': _API_BOUND_DOCUMENTS, 'read_file': _API_BOUND_DOCUMENTS, 'list_roots': _API_BOUND_DOCUMENTS,
            'calendar_query': _CALENDAR, 'calendar_draft_create': _CALENDAR,
            'calendar_draft_update': _CALENDAR, 'calendar_draft_cancel': _CALENDAR,
            'save_memory': _MEMORY, 'list_memory': _MEMORY,
            'list_agents': _SPECIALISTS, 'delegate_agent': _SPECIALISTS,
        },
        # Only these exact CLI versions passed the process-level tests; any
        # other version is refused until requalified (no silent downgrade).
        'runtimes': {
            'codex': {'tested_versions': ('0.153.4',), 'tested_platforms': ('darwin',), 'live_tested_version': None,
                      'enforcement': f'Codex permissions profile {CODEX_STRICT_PERMISSIONS} (Seatbelt) '
                                     'instead of --sandbox read-only; apps, multi-agent and hosted web search off'},
            'claude-code': {'tested_versions': ('2.1.280',), 'tested_platforms': ('darwin',), 'live_tested_version': None,
                            'enforcement': 'no built-in tools (--tools ""), --restricted, '
                                           'only the offered AgentOS MCP tools allowed'},
        },
    },
}
BOUNDED_PROFILE, ISOLATED_PROFILE, STRICT_PROFILE = 'trusted-local', 'isolated-agentos-mcp', 'strict-isolated'
#: Profiles the owner can choose for the host subscription CLI route.
HOST_CLI_PROFILES = (BOUNDED_PROFILE, STRICT_PROFILE)


def strict_launch_arguments(engine_id):
    """CLI arguments that confine one engine under the strict-isolated profile.

    Codex: the permissions profile replaces ``--sandbox read-only`` (never
    both).  Apps/connectors, sub-agents and the provider-hosted web search are
    input channels AgentOS does not mediate, so they are switched off.
    Claude Code: no built-in tool at all (no Read/Bash/WebFetch/WebSearch/
    Agent), ``--restricted`` so no settings file can re-add one, and only the
    profile's AgentOS MCP tools are pre-approved; without that approval ``-p``
    denies every MCP call (observed, 2.1.280).
    """
    if engine_id == 'codex':
        return ['-c', f'default_permissions="{CODEX_STRICT_PERMISSIONS}"', '-c', CODEX_STRICT_TABLE,
                '--disable', 'apps', '--disable', 'multi_agent', '-c', 'web_search="disabled"']
    if engine_id == 'claude-code':
        return ['--tools', '', '--restricted', '--allowedTools',
                ','.join(f'mcp__agentos__{action}' for action in profile_actions(STRICT_PROFILE))]
    raise ExecutionError('지원하는 구독 엔진을 선택하세요.')


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


def mcp_tool(definition, mode=None):
    """Project one native function definition onto the MCP ``Tool`` wire shape.

    Field names are the MCP wire aliases (``inputSchema``), checked against the
    adopted ``mcp_types.Tool`` in tests/test_mcp_bridge_protocol.py.  The
    manifest ``mode`` becomes the ``readOnlyHint`` annotation; it is a hint to
    the client and authorizes nothing.
    """
    function = definition['function']
    tool = {'name': function['name'], 'description': function['description'],
            'inputSchema': json.loads(json.dumps(function['parameters']))}
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
    return [mcp_tool(definition, tools[definition['function']['name']]['mode'])
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


LOGIN_COMMANDS = {'claude-code': 'claude setup-token', 'codex': 'codex login'}
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

    def __init__(self, capabilities):
        self.capabilities = capabilities

    def _offered(self):
        allowed = set(profile_actions(self.PROFILE))
        return {definition['function']['name']: definition for definition in self.capabilities.definitions()
                if definition['function']['name'] in allowed}

    def definitions(self):
        # Fresh JSON-compatible copies: callers must not mutate the contract.
        tools = getattr(self.capabilities, 'tools', {}) or {}
        return [mcp_tool(definition, (tools.get(name) or {}).get('mode'))
                for name, definition in sorted(self._offered().items())]

    def call(self, name, arguments):
        if not isinstance(arguments, dict):
            raise ExecutionError('MCP 도구 인수는 객체여야 합니다.')
        definition = self._offered().get(name) if isinstance(name, str) else None
        if definition is None:
            raise ExecutionError('허용하지 않은 AgentOS MCP 도구 또는 인수입니다.')
        from .agent_runtime import check_arguments
        parameters = definition['function']['parameters']
        try:
            check_arguments(parameters, arguments)
        except ValueError:
            raise ExecutionError('허용하지 않은 AgentOS MCP 도구 또는 인수입니다.') from None
        if any(not arguments[field].strip() for field in parameters['required']):
            raise ExecutionError('MCP 도구의 필수 문자열 인수가 비어 있습니다.')
        # Capabilities is AgentOS-owned and applies its normal validation,
        # document boundary, egress, evidence and idempotency rules.
        return self.capabilities.execute(name, arguments)


class ReadOnlyAgentOSMcpTools(AgentOSMcpTools):
    """Isolated-engine facade: the deliberately restricted isolation profile."""
    PROFILE = ISOLATED_PROFILE


class StrictIsolatedAgentOSMcpTools(AgentOSMcpTools):
    """Host-CLI facade under the strict-isolated profile (#616).

    ``qualified_version`` is the CLI version the owner's qualification
    passed on; the adapter refuses to launch any other version.
    """
    PROFILE = STRICT_PROFILE

    def __init__(self, capabilities, qualified_version=None):
        super().__init__(capabilities)
        self.qualified_version = qualified_version


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

    def command(self, engine_id, binary, prompt, mcp_config, instructions='', profile=BOUNDED_PROFILE):
        if profile not in HOST_CLI_PROFILES:
            raise ExecutionError('지원하지 않는 구독 엔진 실행 프로필입니다.')
        strict = profile == STRICT_PROFILE
        if engine_id == 'codex':
            # `exec` is non-interactive and JSON output is required so prose
            # around an answer cannot be mistaken for execution evidence.
            bridge = json.loads(Path(mcp_config).read_text())['mcpServers']['agentos']
            # --ignore-user-config keeps the owner's own Codex defaults (model,
            # MCP servers, plugins) out of this bounded turn; login still
            # comes from CODEX_HOME.  --ephemeral keeps no session files.
            sandbox = strict_launch_arguments('codex') if strict else ['--sandbox', 'read-only']
            return [binary, 'exec', '--json', *sandbox, '--skip-git-repo-check',
                    '--ignore-user-config', '--ephemeral',
                    '-c', f'mcp_servers.agentos.command={json.dumps(sys.executable)}',
                    '-c', f'mcp_servers.agentos.args={json.dumps(bridge["args"])}', prompt]
        if engine_id == 'claude-code':
            # #570: stream-json (which requires --verbose with -p) reports the
            # session model and each tool_use; its last line is the same result
            # record that `json` prints, so answer parsing is unchanged.
            argv = [binary, '-p', prompt, '--output-format', 'stream-json', '--verbose',
                    '--strict-mcp-config', '--mcp-config', str(mcp_config)]
            if instructions:
                # #569: AgentOS instructions travel as a system-prompt addition,
                # the conversation and request as the prompt.
                argv += ['--append-system-prompt', instructions]
            if strict:
                argv += strict_launch_arguments('claude-code')
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

    def qualify_strict(self, engine_id, binary=None, protected=()):
        """No-model qualification of the strict-isolated profile for one CLI.

        Passes only for a tested CLI version and, for Codex, when its own
        sandbox runner under the exact permissions profile refuses every
        ``protected`` directory (the owner store, home and CODEX_HOME) while
        a control listing of the turn directory succeeds.  The result never
        contains file content.  Claude Code's confinement is structural (no
        built-in tools), so its version pin is the check.
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
        self.runtime_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(dir=self.runtime_root, prefix='qualify-') as folder:
            run_dir = Path(folder)
            try:
                version = self.runtime_version(engine_id, binary, run_dir)
                checks.append({'check': 'tested-version', 'observed': version,
                               'expected': list(declared['tested_versions']),
                               'passed': version in declared['tested_versions']})
                if engine_id == 'codex' and checks[-1]['passed']:
                    checks.append({'check': 'turn-directory-readable',
                                   'passed': not self._codex_sandbox_denies(binary, run_dir, run_dir)})
                    login_profile = self.codex_home or Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))
                    for target in (Path.home(), login_profile, *protected):
                        target = Path(target).expanduser()
                        if not target.is_dir():
                            continue
                        checks.append({'check': 'protected-directory-denied', 'target': target.name or str(target),
                                       'passed': self._codex_sandbox_denies(binary, run_dir, target)})
            except (ExecutionError, subprocess.TimeoutExpired, OSError) as exc:
                checks.append({'check': 'runner', 'passed': False, 'error': type(exc).__name__})
        qualified = bool(checks) and all(check['passed'] for check in checks)
        failed = [check['check'] for check in checks if not check['passed']]
        return {'engine': engine_id, 'profile': STRICT_PROFILE, 'qualified': qualified,
                'version': checks[1].get('observed') if len(checks) > 1 else None, 'checks': checks,
                'reason': '' if qualified else ', '.join(dict.fromkeys(failed)) or 'not checked'}

    @staticmethod
    def _content(engine_id, raw):
        if engine_id == 'claude-code':
            # The stream carries tool results before the result record; bound
            # the answer record itself rather than the whole event stream.
            lines = [line for line in (raw or '').splitlines() if line.strip()]
            raw = lines[-1] if lines else ''
        if len(raw.encode()) > MAX_OUTPUT_BYTES:
            raise ExecutionError('엔진 응답이 안전한 크기 제한을 초과했습니다.')
        try:
            # Codex's machine output is JSONL.  Only examine its last complete
            # event, never concatenate progress/event text into an answer.
            records = [json.loads(line) for line in raw.splitlines() if line.strip()]
            data = records[-1]
        except (TypeError, ValueError, IndexError):
            raise ExecutionError('엔진이 요구된 구조화된 응답을 반환하지 않았습니다.') from None
        if engine_id == 'codex':
            # Codex ends JSONL with usage/completion metadata. Select the last
            # structured agent message instead of treating that terminal event
            # as response text or exposing the event stream to the owner.
            content = None
            for candidate in reversed(records):
                if not isinstance(candidate, dict):
                    continue
                item = candidate.get('item')
                if isinstance(item, dict) and item.get('type') == 'agent_message':
                    text = item.get('text')
                    if isinstance(text, str) and text.strip():
                        content = text
                        break
                text = candidate.get('content') or candidate.get('output')
                if isinstance(text, str) and text.strip():
                    content = text
                    break
        else:
            content = data.get('result') if isinstance(data, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ExecutionError('엔진 응답에 최종 텍스트 결과가 없습니다.')
        return content[:24_000]

    def execute(self, engine_id, prompt, tools, *, context=None):
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
                         *[f'--provenance={label}' for label in sorted(getattr(tools.capabilities, 'private_provenance', ()) or ())]],
            }}}, ensure_ascii=False), encoding='utf-8')
            env = self.environment(engine_id, binary, run_dir)
            profile = getattr(tools, 'PROFILE', BOUNDED_PROFILE)
            if profile == STRICT_PROFILE:
                # #616: never launch an unqualified CLI under the strict
                # profile and never fall back to trusted-local; the owner
                # requalifies after a CLI upgrade or chooses another profile.
                version = self.runtime_version(engine_id, binary, run_dir)
                tested = CLI_PROFILES[STRICT_PROFILE]['runtimes'][engine_id]['tested_versions']
                if version is None or version not in tested or version != getattr(tools, 'qualified_version', None):
                    LOG.warning('engine turn refused engine=%s profile=%s version=%s', engine_id, profile, version or '-')
                    raise ExecutionError('엄격 격리 프로필이 현재 CLI 버전에서 검증되지 않아 실행하지 않았습니다. '
                                         '설정에서 다시 검증하거나 다른 실행 프로필을 선택하세요.',
                                         failure_class='isolation-unqualified',
                                         reason=f'observed version {version or "unknown"}')
            started = time.monotonic()
            LOG.info('engine turn started engine=%s profile=%s', engine_id, profile)
            argv = self.command(engine_id, binary, prompt, config, instructions, profile=profile)
            run_meta = {'argv': display_argv(argv, prompt, instructions), 'requested_model': None}
            try:
                completed = self.runner(argv, cwd=run_dir,
                                        env=env, stdin=subprocess.DEVNULL, capture_output=True,
                                        text=True, timeout=MAX_TIMEOUT_SECONDS, shell=False)
            except subprocess.TimeoutExpired as exc:
                LOG.warning('engine turn timed out engine=%s after=%ss', engine_id, MAX_TIMEOUT_SECONDS)
                raise ExecutionError(f'구독 엔진이 {MAX_TIMEOUT_SECONDS}초 안에 응답하지 않았습니다.',
                                     failure_class='timeout', meta={**run_meta, 'duration_ms': MAX_TIMEOUT_SECONDS * 1000}) from exc
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
                raise ExecutionError(message, failure_class=failure_class,
                                     exit_code=completed.returncode, reason=reason,
                                     meta={**run_meta, **cli_metadata(engine_id, stdout),
                                           'duration_ms': int(elapsed * 1000)})
            try:
                content = self._content(engine_id, completed.stdout)
            except ExecutionError as exc:
                LOG.warning('engine turn returned no usable result engine=%s duration=%.1fs', engine_id, elapsed)
                raise ExecutionError(str(exc), failure_class='invalid-output', exit_code=0,
                                     meta={**run_meta, **cli_metadata(engine_id, completed.stdout), 'duration_ms': int(elapsed * 1000)}) from None
            LOG.info('engine turn succeeded engine=%s duration=%.1fs', engine_id, elapsed)
            return ExecutionResult(content, engine_id, completed.returncode,
                                   {**run_meta, **cli_metadata(engine_id, completed.stdout), 'duration_ms': int(elapsed * 1000)})

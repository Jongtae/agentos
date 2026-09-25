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


MCP_TOOLS = (
    {'name': 'list_notes', 'description': 'List saved AgentOS notes.'},
    {'name': 'save_note', 'description': 'Save an explicitly requested personal note.',
     'input_schema': {'type': 'object', 'properties': {'content': {'type': 'string', 'maxLength': 12000}}, 'required': ['content'], 'additionalProperties': False}},
    {'name': 'web_search', 'description': 'Search public web snippets through AgentOS.',
     'input_schema': {'type': 'object', 'properties': {'query': {'type': 'string', 'maxLength': 500}}, 'required': ['query'], 'additionalProperties': False}},
)


class ExecutionError(ValueError):
    """A safe, user-visible execution-boundary failure.

    ``failure_class``, ``exit_code`` and ``reason`` are bounded, redacted
    diagnostics for Work events and logs; they never contain the prompt.
    """
    def __init__(self, message, *, failure_class='', exit_code=None, reason=''):
        super().__init__(message)
        self.failure_class, self.exit_code, self.reason = failure_class, exit_code, reason

    def diagnostics(self):
        return {key: value for key, value in (('failure_class', self.failure_class),
                ('exit_code', self.exit_code), ('reason', self.reason)) if value not in ('', None)}


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


def failure_details(engine_id, stdout, stderr, prompt=None):
    """Summarise a failed CLI turn from its official machine output.

    Codex ``exec --json`` reports failures as ``turn.failed``/``error``
    events; Claude Code ``--output-format json`` sets ``is_error``.  When
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


class AgentOSMcpTools:
    """The only tool facade that may be offered to a subscription engine."""
    def __init__(self, capabilities):
        self.capabilities = capabilities

    def definitions(self):
        # Return JSON-compatible copies: callers must not mutate the contract.
        return json.loads(json.dumps(MCP_TOOLS))

    def call(self, name, arguments):
        if not isinstance(arguments, dict):
            raise ExecutionError('MCP 도구 인수는 객체여야 합니다.')
        allowed = {
            'list_notes': set(),
            'save_note': {'content'},
            'web_search': {'query'},
        }
        if name not in allowed or set(arguments) - allowed[name]:
            raise ExecutionError('허용하지 않은 AgentOS MCP 도구 또는 인수입니다.')
        if name == 'list_notes' and arguments:
            raise ExecutionError('list_notes에는 인수가 없습니다.')
        if name in ('save_note', 'web_search'):
            value = arguments.get('content' if name == 'save_note' else 'query')
            if not isinstance(value, str) or not value.strip():
                raise ExecutionError('MCP 도구의 필수 문자열 인수가 비어 있습니다.')
        # Capabilities is AgentOS-owned and applies its normal validation,
        # document boundary, evidence and idempotency rules.
        return self.capabilities.execute(name, arguments)


class ReadOnlyAgentOSMcpTools(AgentOSMcpTools):
    """Isolated-engine facade limited to the sole approved read operation."""

    def definitions(self):
        return json.loads(json.dumps((MCP_TOOLS[0],)))

    def call(self, name, arguments):
        if name != 'list_notes' or arguments != {}:
            raise ExecutionError('격리 엔진에는 읽기 전용 메모 목록 도구만 허용됩니다.')
        return self.capabilities.execute('list_notes', {})


class BoundedExecutionAdapter:
    """Start an official subscription CLI with no shell and no inherited env.

    The adapter intentionally has no generic argv, cwd, environment, or tool
    configuration parameters.  Expanding those is a security design change,
    not an engine prompt option.
    """
    def __init__(self, finder=None, runner=subprocess.run, runtime_root=None, codex_home=None):
        from shutil import which
        self.finder = finder or which
        self.runner = runner
        configured_root = runtime_root or os.environ.get('AGENTOS_ENGINE_RUNS')
        self.runtime_root = Path(configured_root).expanduser() if configured_root else Path.home()/'.local/share/agentos/engine-runs'
        self.codex_home = Path(codex_home).expanduser() if codex_home else None

    def environment(self, engine_id, binary, run_dir):
        env = {'HOME': str(run_dir), 'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}
        env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
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

    def command(self, engine_id, binary, prompt, mcp_config, instructions=''):
        if engine_id == 'codex':
            # `exec` is non-interactive and JSON output is required so prose
            # around an answer cannot be mistaken for execution evidence.
            bridge = json.loads(Path(mcp_config).read_text())['mcpServers']['agentos']
            # --ignore-user-config keeps the owner's own Codex defaults (model,
            # MCP servers, plugins) out of this bounded turn; login still
            # comes from CODEX_HOME.  --ephemeral keeps no session files.
            return [binary, 'exec', '--json', '--sandbox', 'read-only', '--skip-git-repo-check',
                    '--ignore-user-config', '--ephemeral',
                    '-c', f'mcp_servers.agentos.command={json.dumps(sys.executable)}',
                    '-c', f'mcp_servers.agentos.args={json.dumps(bridge["args"])}', prompt]
        if engine_id == 'claude-code':
            argv = [binary, '-p', prompt, '--output-format', 'json', '--strict-mcp-config', '--mcp-config', str(mcp_config)]
            if instructions:
                # #569: AgentOS instructions travel as a system-prompt addition,
                # the conversation and request as the prompt.
                argv += ['--append-system-prompt', instructions]
            return argv
        raise ExecutionError('지원하는 구독 엔진을 선택하세요.')

    @staticmethod
    def _content(engine_id, raw):
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
                'args': ['-m', 'personal_agent.mcp_bridge', '--data', str(tools.capabilities.store.root), '--job', tools.capabilities.job_id],
            }}}, ensure_ascii=False), encoding='utf-8')
            env = self.environment(engine_id, binary, run_dir)
            started = time.monotonic()
            LOG.info('engine turn started engine=%s', engine_id)
            try:
                completed = self.runner(self.command(engine_id, binary, prompt, config, instructions), cwd=run_dir,
                                        env=env, stdin=subprocess.DEVNULL, capture_output=True,
                                        text=True, timeout=MAX_TIMEOUT_SECONDS, shell=False)
            except subprocess.TimeoutExpired as exc:
                LOG.warning('engine turn timed out engine=%s after=%ss', engine_id, MAX_TIMEOUT_SECONDS)
                raise ExecutionError(f'구독 엔진이 {MAX_TIMEOUT_SECONDS}초 안에 응답하지 않았습니다.',
                                     failure_class='timeout') from exc
            except OSError as exc:
                LOG.warning('engine turn could not start engine=%s error=%s', engine_id, type(exc).__name__)
                raise ExecutionError('구독 엔진 CLI를 실행하지 못했습니다.', failure_class='start-failed') from exc
            elapsed = time.monotonic() - started
            if completed.returncode != 0:
                status, reason = failure_details(engine_id, completed.stdout,
                                                 getattr(completed, 'stderr', ''), prompt)
                failure_class, hint = 'engine-failed', ''
                for match, name, text in _STATUS_HINTS:
                    if status is not None and match(status):
                        failure_class, hint = name, text
                        break
                LOG.warning('engine turn failed engine=%s exit_code=%s class=%s status=%s duration=%.1fs reason=%s',
                            engine_id, completed.returncode, failure_class, status, elapsed, reason or '-')
                message = f'{ENGINE_NAMES[engine_id]} 엔진이 작업을 완료하지 못했습니다(종료 코드 {completed.returncode}).'
                if hint:
                    message += ' ' + hint
                if reason:
                    message += f' 엔진 응답: {reason}'
                raise ExecutionError(message, failure_class=failure_class,
                                     exit_code=completed.returncode, reason=reason)
            try:
                content = self._content(engine_id, completed.stdout)
            except ExecutionError as exc:
                LOG.warning('engine turn returned no usable result engine=%s duration=%.1fs', engine_id, elapsed)
                raise ExecutionError(str(exc), failure_class='invalid-output', exit_code=0) from None
            LOG.info('engine turn succeeded engine=%s duration=%.1fs', engine_id, elapsed)
            return ExecutionResult(content, engine_id, completed.returncode)

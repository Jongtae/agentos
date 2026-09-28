"""Browser tools for a trusted-local CLI Work turn, executed by the AgentOS service (#701).

The CLI's MCP bridge (``mcp_bridge``) is a separate process started by the
CLI.  The owner-logged-in browser profile is held by the AgentOS service: one
``BrowserProfile`` with its in-process profile lock, the encrypted cookie jar
and its Keychain key, Settings' per-site delete that reaches the running
worker, and the per-step approval surfaces (Telegram ``p7w:`` buttons, web
Settings) that queue notifications and re-queue the Work.  Rather than start a
second profile holder in the bridge, the bridge forwards each browser call to
the service over this relay, and the service runs it through the same
``AgentOSMcpTools.call`` -> ``Capabilities.execute`` -> ``BrowserSession``
path the direct route uses.  Mediation, the label-independent payment guard,
approvals, budgets, repeat keys, the loopback refusal and the worker's
``AgentOS-Embedded`` user agent are therefore the service's, unchanged.

Transport (Adopt, standard library): ``socketserver.ThreadingUnixStreamServer``
on a Unix-domain socket inside a fresh ``tempfile.mkdtemp`` directory (mode
0700), one JSON line per request and per reply, one request per connection.
The first field of every request is a 256-bit key held in a 0600 file in that
directory; a request without it is refused before anything runs.  The relay
lives exactly as long as one CLI turn and serves only the five browser tools
of that one Work; everything else stays in the bridge.  No pickle, no
``multiprocessing.connection`` object loading.

What the relay grants: nothing beyond the bridge's own browser tool list.  A
caller holding the key (the CLI can read its own turn configuration) reaches
the same service-side checks the bridge reaches.
"""
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import socketserver
import tempfile
import threading

from .agent_runtime import BROWSER_ACTIONS, HOST_RELAYED_ACTIONS, REPEAT_PATH_TEXT, ToolError, path_key, result_page_digest

SOCKET_NAME = 's'
KEY_NAME = 'key'
#: One request line: a tool name and string arguments (browser_type text is
#: capped at 2000 characters by the session itself).
MAX_REQUEST_BYTES = 64 * 1024
#: One reply line: a mediated page snapshot.
MAX_REPLY_BYTES = 4 * 1024 * 1024
#: A browser step is bounded by the session's own timeouts and the Work budget;
#: this only stops a relay call from waiting forever on a dead service.
CALL_SECONDS = 300
#: How long the service waits for a connected caller to send its request line.
REQUEST_SECONDS = 10
#: Owner-readable text of a relay that could not be reached; no path, no key.
RELAY_UNAVAILABLE_TEXT = ('AgentOS 브라우저 연결을 사용할 수 없어 이 단계를 실행하지 않았습니다. '
                          '작업이 끝났거나 AgentOS가 다시 시작됐을 수 있습니다.')


class RelayError(ValueError):
    """A relay-level refusal; carries no request content."""


def _error_payload(exc):
    """The typed shape of one failure, as the bridge maps it back (``relay_exception``)."""
    from .bounded_execution import ExecutionError
    if isinstance(exc, ExecutionError):
        return {'kind': 'invalid_arguments', 'message': str(exc)}
    if isinstance(exc, ToolError):
        return {'kind': 'tool', 'message': str(exc), 'code': exc.code, 'requires': exc.requires}
    if isinstance(exc, (TimeoutError, ConnectionError)) or (isinstance(exc, OSError) and not isinstance(exc, FileNotFoundError)):
        return {'kind': 'transient', 'message': ''}
    if isinstance(exc, ValueError):
        return {'kind': 'refused', 'message': str(exc)}
    return {'kind': 'failed', 'message': ''}


def relay_exception(error):
    """The exception a bridge raises for one relayed failure (the inverse of ``_error_payload``)."""
    from .bounded_execution import ExecutionError
    error = error if isinstance(error, dict) else {}
    kind, message = error.get('kind'), str(error.get('message') or '')
    if kind == 'invalid_arguments':
        return ExecutionError(message or '허용하지 않은 AgentOS MCP 도구 또는 인수입니다.')
    if kind == 'tool' and isinstance(error.get('code'), str) and error['code']:
        requires = error.get('requires') if isinstance(error.get('requires'), str) else None
        return ToolError(message or RELAY_UNAVAILABLE_TEXT, error['code'], requires=requires)
    if kind == 'transient':
        return ConnectionError('browser relay transient failure')
    if kind == 'refused':
        return ValueError(message)
    # An untyped failure: the bridge answers it with its own fixed text.
    return ValueError('')


class BrowserRelay:
    """The service half: serves one Work turn's browser calls through ``tools.call``.

    ``tools`` is the trusted-local ``AgentOSMcpTools`` facade built for this
    turn in the service (its ``Capabilities`` carries the browser profile
    factory, the approvals surface, the Work budget and the lookup sources).
    Calls are executed one at a time.
    """

    def __init__(self, tools):
        self.tools = tools
        self._lock = threading.Lock()
        self._closed = False
        # The page the next step acts on and the page steps already taken (#657).
        self._page, self._paths = None, set()
        self.directory = Path(tempfile.mkdtemp(prefix='agentos-br-'))
        os.chmod(self.directory, 0o700)
        self._key = secrets.token_hex(32)
        key_path = self.directory / KEY_NAME
        descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='ascii') as handle:
            handle.write(self._key)
        relay = self

        class Handler(socketserver.StreamRequestHandler):
            timeout = REQUEST_SECONDS

            def handle(self):
                try:
                    line = self.rfile.readline(MAX_REQUEST_BYTES + 1)
                except (OSError, ValueError):
                    return
                reply = relay._reply(line)
                try:
                    self.wfile.write(json.dumps(reply, ensure_ascii=False).encode('utf-8') + b'\n')
                except OSError:
                    pass

        self._server = socketserver.ThreadingUnixStreamServer(str(self.directory / SOCKET_NAME), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={'poll_interval': 0.2},
                                        name='agentos-cli-browser-relay', daemon=True)
        self._thread.start()

    @property
    def address(self):
        """What the bridge is told: the relay's private directory."""
        return str(self.directory)

    def _reply(self, line):
        if self._closed:
            return {'error': {'kind': 'tool', 'message': RELAY_UNAVAILABLE_TEXT, 'code': 'stopped'}}
        if len(line) > MAX_REQUEST_BYTES:
            return {'error': {'kind': 'invalid_arguments', 'message': ''}}
        try:
            request = json.loads(line.decode('utf-8'))
        except (UnicodeDecodeError, ValueError):
            return {'error': {'kind': 'invalid_arguments', 'message': ''}}
        if not isinstance(request, dict) or not hmac.compare_digest(str(request.get('key') or ''), self._key):
            return {'error': {'kind': 'tool', 'message': RELAY_UNAVAILABLE_TEXT, 'code': 'relay_refused'}}
        name, arguments = request.get('name'), request.get('arguments')
        tools = getattr(self.tools.capabilities, 'tools', {}) or {}
        # Only this Work's browser and owner-state tools (#774): every other tool stays in the bridge.
        if not isinstance(name, str) or (tools.get(name) or {}).get('host_action') not in HOST_RELAYED_ACTIONS:
            return {'error': {'kind': 'invalid_arguments', 'message': ''}}
        with self._lock:
            if self._closed:
                return {'error': {'kind': 'tool', 'message': RELAY_UNAVAILABLE_TEXT, 'code': 'stopped'}}
            # #657's repeat key, as the direct route's loop applies it: the same
            # page step (action, target and input digests) on the same page is
            # refused, not re-run (``agent_runtime.path_key``, reused).
            action = tools[name]['host_action']
            path = (path_key(action, arguments, self._page)
                    if action in BROWSER_ACTIONS and isinstance(arguments, dict) else None)
            if path is not None and path in self._paths:
                return {'error': _error_payload(ToolError(REPEAT_PATH_TEXT, 'repeat_path'))}
            if path is not None:
                self._paths.add(path)
            try:
                value = self.tools.call(name, arguments)
            except Exception as exc:   # every failure becomes a typed reply
                return {'error': _error_payload(exc)}
            if action in BROWSER_ACTIONS:
                self._page = result_page_digest(value) or self._page
            else:
                # #774 review: the service reads typed owner-state results (a missing
                # connector's ``needs_setup``) after the turn, as the direct route's memo.
                memo = getattr(self.tools.capabilities, 'memo', None)
                if isinstance(memo, dict):
                    memo[(name, json.dumps(arguments, sort_keys=True, ensure_ascii=False))] = value
            return {'ok': value}

    def close(self):
        """Stop serving; an in-flight call finishes first.  The directory and key are removed."""
        self._closed = True
        try:
            self._server.shutdown()
        finally:
            self._server.server_close()
            with self._lock:
                shutil.rmtree(self.directory, ignore_errors=True)


class RelayClient:
    """The bridge half: forwards one validated browser call and returns its value or raises its typed error."""

    def __init__(self, directory):
        self.directory = Path(directory)

    def _key(self):
        try:
            return (self.directory / KEY_NAME).read_text(encoding='ascii').strip()
        except OSError:
            raise ToolError(RELAY_UNAVAILABLE_TEXT, 'browser_relay_unavailable') from None

    def call(self, name, arguments):
        request = json.dumps({'key': self._key(), 'name': name, 'arguments': arguments}, ensure_ascii=False).encode('utf-8')
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(CALL_SECONDS)
                connection.connect(str(self.directory / SOCKET_NAME))
                connection.sendall(request + b'\n')
                reader = connection.makefile('rb')
                line = reader.readline(MAX_REPLY_BYTES + 1)
        except (FileNotFoundError, ConnectionRefusedError):
            raise ToolError(RELAY_UNAVAILABLE_TEXT, 'browser_relay_unavailable') from None
        if not line or len(line) > MAX_REPLY_BYTES:
            raise ToolError(RELAY_UNAVAILABLE_TEXT, 'browser_relay_unavailable')
        try:
            reply = json.loads(line.decode('utf-8'))
        except (UnicodeDecodeError, ValueError):
            raise ToolError(RELAY_UNAVAILABLE_TEXT, 'browser_relay_unavailable') from None
        if isinstance(reply, dict) and 'ok' in reply:
            return reply['ok']
        raise relay_exception(reply.get('error') if isinstance(reply, dict) else None)


def unused_browser_factory():
    """The bridge's ``Capabilities.browser`` placeholder: the tools are listed, calls go to the relay.

    Never a driver: were it ever called, the call is refused, not run in the bridge.
    """
    raise ToolError(RELAY_UNAVAILABLE_TEXT, 'browser_relay_unavailable')


def RELAYED_PREPARATIONS(*_args, **_kwargs):
    """The bridge's ``Capabilities.preparations`` placeholder (#774): ``schedule_preparation`` is
    listed, and its calls go to the service, where acceptance is decided.  Never run in the bridge."""
    raise ToolError(RELAY_UNAVAILABLE_TEXT, 'browser_relay_unavailable')


def RELAYED_SETTINGS(*_args, **_kwargs):
    """The bridge's ``Capabilities.settings`` placeholder (#814): ``settings_read`` and
    ``settings_change`` are listed, and their calls go to the service, which holds the owner
    settings and their confirmation.  Never run in the bridge."""
    raise ToolError(RELAY_UNAVAILABLE_TEXT, 'browser_relay_unavailable')


def RELAYED_INFORMATION_USE(*_args, **_kwargs):
    """The bridge's ``Capabilities.information_use`` placeholder (#826): ``information_use`` is
    listed, and its calls go to the service, which holds the Work records and the stored-secret
    redaction.  Never run in the bridge."""
    raise ToolError(RELAY_UNAVAILABLE_TEXT, 'browser_relay_unavailable')


def RELAYED_LOCATION_REQUEST(*_args, **_kwargs):
    """The bridge's ``Capabilities.location_request`` placeholder (#774): ``ask_location`` is
    listed, and its calls go to the service, which holds the paired Telegram chat.  Never run in the bridge."""
    raise ToolError(RELAY_UNAVAILABLE_TEXT, 'browser_relay_unavailable')

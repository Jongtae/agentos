"""Single-use, task-bound MCP capabilities for an isolated engine.

The proxy intentionally does not trust a registered facade's tool catalogue.
It exposes one read-only operation and never gives the isolated caller a
generic capability object, owner store, or broad dispatch primitive.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import json
import secrets
import threading
import time
from typing import Callable


@dataclass
class _Capability:
    task_id: str
    tools: object
    expires_at: float
    used: bool = False


class CapabilityRejected(ValueError):
    """A safe capability rejection whose message contains no token details."""

    def __init__(self, reason: str):
        super().__init__("isolated MCP capability rejected")
        self.reason = reason


class TaskCapabilityRegistry:
    """In-memory registry of 256-bit bearer capabilities bound to one task."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._entries: dict[str, _Capability] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _valid_token(token: object) -> bool:
        if not isinstance(token, str) or not token:
            return False
        try:
            padding = "=" * (-len(token) % 4)
            decoded = base64.b64decode(token + padding, altchars=b"-_", validate=True)
        except (ValueError, TypeError):
            return False
        return len(decoded) == 32

    def register(self, task_id: str, tools: object, *, ttl_seconds: float = 30.0, token: str | None = None) -> str:
        """Register an AgentOSMcpTools-like facade and return a 256-bit token."""
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("task_id must be a non-empty string")
        if not callable(getattr(tools, "call", None)):
            raise ValueError("tools must provide a callable call method")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)) or ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        expires_at = self._clock() + float(ttl_seconds)
        with self._lock:
            if token is not None:
                if not self._valid_token(token) or token in self._entries:
                    raise ValueError("token must be a fresh 256-bit bearer capability")
                self._entries[token] = _Capability(task_id, tools, expires_at)
                return token
            while True:
                token = secrets.token_urlsafe(32)
                if token not in self._entries:
                    self._entries[token] = _Capability(task_id, tools, expires_at)
                    return token

    def revoke(self, token: object) -> None:
        """Remove an execution-scoped capability without revealing its state."""
        if isinstance(token, str):
            with self._lock:
                self._entries.pop(token, None)

    def consume(self, token: object, task_id: object) -> object:
        """Consume a matching capability before any registered code can run."""
        if not self._valid_token(token) or not isinstance(task_id, str) or not task_id:
            raise CapabilityRejected("invalid")
        with self._lock:
            entry = self._entries.get(token)
            if entry is None:
                raise CapabilityRejected("invalid")
            if entry.used:
                raise CapabilityRejected("replayed")
            if self._clock() >= entry.expires_at:
                entry.used = True
                raise CapabilityRejected("expired")
            # A wrong task consumes the bearer capability.  It cannot later be
            # replayed with corrected task metadata after a substitution try.
            entry.used = True
            if task_id != entry.task_id:
                raise CapabilityRejected("invalid")
            return entry.tools


class IsolatedMcpProxy:
    """Strict one-request JSON-RPC handler for the read-only notes capability."""

    def __init__(self, registry: TaskCapabilityRegistry):
        if not isinstance(registry, TaskCapabilityRegistry):
            raise ValueError("registry must be a TaskCapabilityRegistry")
        self.registry = registry

    @staticmethod
    def _error(ident, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": message}}

    @staticmethod
    def _decode(raw_request: object) -> dict:
        if isinstance(raw_request, str):
            raw_request = raw_request.encode("utf-8")
        if not isinstance(raw_request, bytes):
            raise ValueError("request must be JSON bytes or text")

        def reject_duplicates(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate JSON key")
                value[key] = item
            return value

        decoded = json.loads(raw_request.decode("utf-8"), object_pairs_hook=reject_duplicates)
        if not isinstance(decoded, dict):
            raise ValueError("request must be an object")
        return decoded

    def handle(self, raw_request: object, *, token: object, task_id: object) -> dict:
        """Handle one authenticated request and always return safe JSON-RPC."""
        ident = None
        try:
            request = self._decode(raw_request)
            ident = request.get("id")
            if isinstance(ident, bool) or not isinstance(ident, (str, int)):
                raise ValueError("invalid request id")
            if set(request) != {"jsonrpc", "id", "method", "params"}:
                raise ValueError("invalid request fields")
            if request["jsonrpc"] != "2.0" or request["method"] != "tools/call":
                raise ValueError("unsupported request")
            params = request["params"]
            if not isinstance(params, dict) or set(params) != {"name", "arguments"}:
                raise ValueError("invalid params")
            if params["name"] != "list_notes" or params["arguments"] != {}:
                raise LookupError("tool rejected")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._error(None, -32700, "Invalid JSON")
        except LookupError:
            return self._error(ident, -32601, "Tool not available")
        except (TypeError, ValueError):
            return self._error(ident, -32600, "Invalid MCP request")

        try:
            tools = self.registry.consume(token, task_id)
        except CapabilityRejected as exc:
            codes = {"expired": -32002, "replayed": -32003}
            return self._error(ident, codes.get(exc.reason, -32001), "Capability rejected")

        try:
            value = tools.call("list_notes", {})
            encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            # Facade exception text can contain private data or implementation
            # details.  It must never cross this process boundary.
            return self._error(ident, -32603, "AgentOS tool failed")
        return {
            "jsonrpc": "2.0",
            "id": ident,
            "result": {"content": [{"type": "text", "text": encoded}]},
        }

    def handle_json(self, raw_request: object, *, token: object, task_id: object) -> str:
        """Return the response as compact JSON suitable for an IPC transport."""
        return json.dumps(
            self.handle(raw_request, token=token, task_id=task_id),
            ensure_ascii=False,
            separators=(",", ":"),
        )


# The longer name is useful to callers that want the boundary in the type name.
IsolatedMcpCapabilityRegistry = TaskCapabilityRegistry

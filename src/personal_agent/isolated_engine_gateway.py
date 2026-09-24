"""Capability-scoped client for an isolated subscription-engine worker.

The gateway deliberately knows nothing about AgentOS storage or engine login
profiles.  A worker receives one prompt, one engine identifier, and one
single-use capability.  Keeping this boundary small makes it possible to run
the worker without mounting the owner-state volume.
"""

from __future__ import annotations

import ipaddress
import json
import re
import secrets
import socket
import threading
from http.client import HTTPConnection
from urllib.parse import urlsplit


class EngineGatewayError(RuntimeError):
    """Base error for a rejected or failed isolated-engine request."""


class InvalidGatewayEndpoint(EngineGatewayError):
    """The configured endpoint is outside the local/private trust boundary."""


class InvalidCapability(EngineGatewayError):
    """A capability is unknown or has already been consumed."""


class InvalidEngineResponse(EngineGatewayError):
    """The worker did not return the narrow response contract."""


def _validated_endpoint(endpoint: str, internal_hosts: frozenset[str]):
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise InvalidGatewayEndpoint("invalid engine gateway URL") from exc

    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/", "/execute")
    ):
        raise InvalidGatewayEndpoint(
            "engine gateway must be an explicit local/internal HTTP endpoint"
        )

    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost":
        # Do not perform a second DNS lookup for the special local name.
        return parsed, "127.0.0.1", port
    if host in internal_hosts:
        return parsed, host, port

    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        # Do not resolve arbitrary names here: an explicit allowlist avoids DNS
        # rebinding and makes a Compose service name an intentional boundary.
        raise InvalidGatewayEndpoint("engine gateway host is not allowlisted") from exc

    if (
        address.is_unspecified
        or address.is_multicast
        or address.is_reserved
        or not (address.is_loopback or address.is_private or address.is_link_local)
    ):
        raise InvalidGatewayEndpoint("engine gateway host is not local or private")
    return parsed, host, port


def _safe_worker_error(raw: bytes, content_type: str) -> str:
    """Return one bounded, redacted sidecar error detail when available."""
    if content_type.split(";", 1)[0].strip().lower() != "application/json":
        return ""
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    if not isinstance(value, dict) or set(value) != {"error"} or not isinstance(value["error"], str):
        return ""
    detail = " ".join(value["error"].split())[:300]
    fixed = {
        "engine execution failed",
        "engine execution failed: MCP bridge argument parsing failed",
        "engine execution failed: engine command-line invocation failed",
        "engine returned invalid JSON",
        "engine returned no final result",
    }
    if detail in fixed:
        return detail
    if re.fullmatch(r"engine execution failed: engine process exited with status [0-9]{1,3}", detail):
        return detail
    return ""


class IsolatedEngineGateway:
    """Send capability-scoped work to a local, isolated engine endpoint.

    Capabilities are consumed before network I/O.  A timeout or malformed
    response therefore cannot cause an ambiguous task to be replayed with the
    same token.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        timeout: float = 10.0,
        internal_hosts=("engine",),
        max_response_bytes: int = 1_048_576,
    ):
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        allowlist = frozenset(str(host).rstrip(".").lower() for host in internal_hosts)
        parsed, host, port = _validated_endpoint(endpoint, allowlist)
        self._host = host
        self._port = port
        self._path = parsed.path or "/execute"
        self._timeout = timeout
        self._max_response_bytes = max_response_bytes
        self._capabilities: dict[str, tuple[str, str, str, bool]] = {}
        self._lock = threading.Lock()

    def issue_task_token(self, *, prompt: str, engine_id: str, task_id: str = "") -> str:
        """Create a random capability bound to exactly one prompt and engine."""
        if not isinstance(prompt, str) or not prompt:
            raise ValueError("prompt must be a non-empty string")
        if not isinstance(engine_id, str) or not engine_id:
            raise ValueError("engine_id must be a non-empty string")
        if not isinstance(task_id, str):
            raise ValueError("task_id must be a string")
        with self._lock:
            while True:
                token = secrets.token_urlsafe(32)
                if token not in self._capabilities:
                    self._capabilities[token] = (prompt, engine_id, task_id, False)
                    return token

    def _consume(self, token: str, prompt: str, engine_id: str, task_id: str) -> None:
        if not isinstance(token, str) or not token:
            raise InvalidCapability("invalid engine task capability")
        with self._lock:
            capability = self._capabilities.get(token)
            if capability is None or capability[3]:
                raise InvalidCapability("unknown or already-used engine task capability")
            expected_prompt, expected_engine, expected_task, _used = capability
            # Presentation consumes the bearer capability even when the caller
            # attempts to substitute a different task.
            self._capabilities[token] = (expected_prompt, expected_engine, expected_task, True)
            if (prompt, engine_id, task_id) != (expected_prompt, expected_engine, expected_task):
                raise InvalidCapability("engine task does not match its capability")

    def execute(self, *, prompt: str, engine_id: str, token: str, task_id: str = "") -> str:
        """Execute one task and return the worker's text result.

        Only the prompt, engine id, bearer, and (for integrated jobs) opaque
        task id cross the process boundary.  The method cannot accept a store,
        filesystem path, profile path, or arbitrary metadata object.
        """
        if not isinstance(prompt, str) or not prompt:
            raise ValueError("prompt must be a non-empty string")
        if not isinstance(engine_id, str) or not engine_id:
            raise ValueError("engine_id must be a non-empty string")
        if not isinstance(task_id, str):
            raise ValueError("task_id must be a string")
        self._consume(token, prompt, engine_id, task_id)

        payload = {"prompt": prompt, "engine_id": engine_id, "token": token}
        # Backwards-compatible for direct callers while integrated jobs carry
        # the opaque task id needed for their authenticated MCP callback.
        if task_id:
            payload["task_id"] = task_id
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        connection = HTTPConnection(self._host, self._port, timeout=self._timeout)
        try:
            connection.request(
                "POST",
                self._path,
                body=body,
                headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
            )
            response = connection.getresponse()
            raw = response.read(self._max_response_bytes + 1)
        except (OSError, TimeoutError, socket.timeout) as exc:
            raise EngineGatewayError("isolated engine request failed") from exc
        finally:
            connection.close()

        if response.status != 200:
            detail = _safe_worker_error(raw, response.getheader("Content-Type", ""))
            suffix = f": {detail}" if detail else ""
            raise InvalidEngineResponse(f"isolated engine returned HTTP {response.status}{suffix}")
        if len(raw) > self._max_response_bytes:
            raise InvalidEngineResponse("isolated engine response exceeded the byte limit")
        if response.getheader("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise InvalidEngineResponse("isolated engine response is not JSON")
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidEngineResponse("isolated engine response is not valid JSON") from exc
        if set(decoded) != {"result"} or not isinstance(decoded["result"], str):
            raise InvalidEngineResponse("isolated engine response violates the result contract")
        return decoded["result"]

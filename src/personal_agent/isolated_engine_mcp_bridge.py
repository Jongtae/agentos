"""Narrow stdio MCP bridge for the isolated Codex sidecar.

Protocol discovery is answered in-process.  The single approved tool call is
forwarded to AgentOS's internal HTTP callback with the execution-scoped bearer
capability; no owner storage or filesystem path is accepted by this process.

The protocol version comes from the mcp-types registry, but that
package's envelope models are deliberately not adopted: JSONRPCRequest
accepts an unknown top-level key and model_dump then drops it, so a
request this bridge rejects would be normalised into a clean-looking
one and forwarded. Envelope validation stays hand-written here.
"""

from __future__ import annotations

import argparse
from http.client import HTTPConnection
import json
import sys
from urllib.parse import urlsplit

from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS, LATEST_HANDSHAKE_VERSION


from .bounded_execution import ISOLATED_PROFILE, profile_mcp_tools

# #604: derived from the one native action source for the restricted isolation
# profile, not a bridge-local copy.  The profile's only action takes no
# arguments, which is what the ``arguments == {}`` check below enforces.
ISOLATED_TOOLS = profile_mcp_tools(ISOLATED_PROFILE)
ISOLATED_TOOL_NAMES = frozenset(tool["name"] for tool in ISOLATED_TOOLS)


def negotiated_protocol_version(offered):
    """Return the handshake revision this bridge will speak with the engine.

    The supported set is the ``mcp_types`` registry rather than a literal, so
    it tracks the official SDK.  ``initialize`` is a handshake method, so an
    unrecognised offer is answered with the newest *handshake* revision;
    ``LATEST_PROTOCOL_VERSION`` may name a stateless per-request revision this
    bridge does not implement.  Only a known revision is echoed back, so an
    arbitrary engine-supplied string is never reflected to the peer.
    """
    if isinstance(offered, str) and offered in HANDSHAKE_PROTOCOL_VERSIONS:
        return offered
    return LATEST_HANDSHAKE_VERSION


class BridgeError(ValueError):
    """A bridge failure whose message is safe to return to the engine."""


def _callback_parts(callback_url: str):
    try:
        parsed = urlsplit(callback_url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise BridgeError("invalid AgentOS callback") from exc
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path.startswith("/")
        or parsed.query
        or parsed.fragment
    ):
        raise BridgeError("invalid AgentOS callback")
    return parsed.hostname, port, parsed.path


def _send(value: dict) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _forward(callback_url: str, token: str, task_id: str, request: dict, timeout: float) -> dict:
    host, port, path = _callback_parts(callback_url)
    body = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    connection = HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request(
            "POST",
            path,
            body=body,
            headers={
                "Authorization": "Bearer " + token,
                "X-AgentOS-Task-ID": task_id,
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        response = connection.getresponse()
        raw = response.read(1_048_577)
    except OSError as exc:
        raise BridgeError("AgentOS callback failed") from exc
    finally:
        connection.close()
    if response.status != 200 or len(raw) > 1_048_576:
        raise BridgeError("AgentOS callback failed")
    if response.getheader("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise BridgeError("AgentOS callback returned invalid JSON")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeError("AgentOS callback returned invalid JSON") from exc
    if not isinstance(value, dict) or value.get("jsonrpc") != "2.0" or value.get("id") != request["id"]:
        raise BridgeError("AgentOS callback returned an invalid MCP response")
    if set(value) not in ({"jsonrpc", "id", "result"}, {"jsonrpc", "id", "error"}):
        raise BridgeError("AgentOS callback returned an invalid MCP response")
    return value


def _request_error(ident, code: int = -32602) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": ident,
        "error": {"code": code, "message": "AgentOS MCP request rejected."},
    }


def serve(callback_url: str, token: str, task_id: str, *, timeout: float = 10.0) -> None:
    """Serve newline-delimited MCP JSON-RPC on stdin/stdout."""
    _callback_parts(callback_url)
    if not isinstance(token, str) or not token or not isinstance(task_id, str) or not task_id:
        raise BridgeError("missing execution capability")
    for line in sys.stdin:
        ident = None
        try:
            request = json.loads(line)
            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
                raise BridgeError("invalid request")
            ident = request.get("id")
            method = request.get("method")
            if method == "notifications/initialized":
                continue
            if isinstance(ident, bool) or not isinstance(ident, (str, int)):
                raise BridgeError("invalid request id")
            if method == "initialize":
                params = request.get("params")
                offered = params.get("protocolVersion") if isinstance(params, dict) else None
                result = {
                    "protocolVersion": negotiated_protocol_version(offered),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "agentos-isolated", "version": "1"},
                }
                _send({"jsonrpc": "2.0", "id": ident, "result": result})
            elif method == "tools/list":
                _send({"jsonrpc": "2.0", "id": ident, "result": {"tools": json.loads(json.dumps(ISOLATED_TOOLS))}})
            elif method == "tools/call":
                params = request.get("params")
                if (
                    set(request) != {"jsonrpc", "id", "method", "params"}
                    or not isinstance(params, dict)
                    or set(params) != {"name", "arguments"}
                    or params.get("name") not in ISOLATED_TOOL_NAMES
                    or params.get("arguments") != {}
                ):
                    _send(_request_error(ident, -32601))
                    continue
                _send(_forward(callback_url, token, task_id, request, timeout))
            else:
                _send(_request_error(ident, -32601))
        except (BridgeError, TypeError, ValueError, json.JSONDecodeError):
            _send(_request_error(ident))


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--callback", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)
    serve(args.callback, args.token, args.task_id, timeout=args.timeout)


if __name__ == "__main__":
    main()

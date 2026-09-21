"""Envelope and authority behaviour of the isolated-engine stdio MCP bridge.

REUSE-R2 (#426): these negative cases are the reason the bridge keeps its own
strict envelope allowlist instead of delegating validation to the permissive
``mcp_types`` JSON-RPC models, which accept and silently *strip* unknown
top-level keys rather than rejecting the request.
"""

import io
import json
import sys
import unittest
from unittest import mock

from mcp_types.version import LATEST_HANDSHAKE_VERSION

from personal_agent import isolated_engine_mcp_bridge as bridge


CALLBACK = "http://127.0.0.1:8787/internal/isolated-engine/mcp"
TOKEN = "work-scoped-token"
TASK = "task-42"


class FakeResponse:
    def __init__(self, payload, status=200, content_type="application/json"):
        self.status = status
        self._content_type = content_type
        if isinstance(payload, (dict, list)):
            self._body = json.dumps(payload).encode("utf-8")
        else:
            self._body = payload

    def read(self, _limit=None):
        return self._body

    def getheader(self, _name, default=""):
        return self._content_type or default


class FakeConnection:
    """Records every outbound callback so tests can assert fail-closed behaviour."""

    def __init__(self, response, sink):
        self._response = response
        self._sink = sink

    def factory(self, host, port, timeout=None):
        self._sink.append({"host": host, "port": port, "timeout": timeout})
        return self

    def request(self, method, path, body=None, headers=None):
        self._sink[-1].update({"method": method, "path": path, "body": body, "headers": headers})

    def getresponse(self):
        return self._response

    def close(self):
        pass


def run_bridge(requests, response=None):
    """Drive serve() over fake stdio; return (replies, recorded callbacks)."""
    lines = "".join(json.dumps(r) + "\n" if not isinstance(r, str) else r + "\n" for r in requests)
    sink = []
    connection = FakeConnection(response or FakeResponse({}), sink)
    out = io.StringIO()
    with mock.patch.object(sys, "stdin", io.StringIO(lines)), \
         mock.patch.object(sys, "stdout", out), \
         mock.patch.object(bridge, "HTTPConnection", connection.factory):
        bridge.serve(CALLBACK, TOKEN, TASK)
    replies = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
    return replies, sink


def call(**overrides):
    request = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {"name": "list_notes", "arguments": {}},
    }
    request.update(overrides)
    return request


class MalformedEnvelopeTests(unittest.TestCase):
    def test_non_json_line_is_rejected_without_a_callback(self):
        replies, sink = run_bridge(["{not json"])
        self.assertEqual(replies[0]["error"]["code"], -32602)
        self.assertIsNone(replies[0]["id"])
        self.assertEqual(sink, [])

    def test_non_object_payload_is_rejected(self):
        for payload in ([1, 2], "bare string", 5, None):
            with self.subTest(payload=payload):
                replies, sink = run_bridge([payload])
                self.assertEqual(replies[0]["error"]["code"], -32602)
                self.assertEqual(sink, [])

    def test_wrong_jsonrpc_version_is_rejected(self):
        replies, sink = run_bridge([call(jsonrpc="1.0")])
        self.assertEqual(replies[0]["error"]["code"], -32602)
        self.assertEqual(sink, [])

    def test_invalid_request_id_types_are_rejected(self):
        for ident in (True, False, None, 1.5, [1], {"a": 1}):
            with self.subTest(ident=ident):
                replies, sink = run_bridge([call(id=ident)])
                self.assertEqual(replies[0]["error"]["code"], -32602)
                self.assertEqual(sink, [])

    def test_unknown_top_level_key_is_rejected_not_silently_stripped(self):
        """mcp_types' JSONRPCRequest would accept this and drop the extra key."""
        replies, sink = run_bridge([call(evil="payload")])
        self.assertEqual(replies[0]["error"]["code"], -32601)
        self.assertEqual(sink, [])


class MethodAndAllowlistTests(unittest.TestCase):
    def test_unknown_method_is_rejected_without_a_callback(self):
        for method in ("resources/list", "prompts/get", "tools/unknown", "initialize/evil", ""):
            with self.subTest(method=method):
                replies, sink = run_bridge([call(method=method)])
                self.assertEqual(replies[0]["error"]["code"], -32601)
                self.assertEqual(sink, [])

    def test_tool_outside_the_allowlist_is_rejected_without_a_callback(self):
        for name in ("save_note", "web_search", "list_notes ", "LIST_NOTES", "", None):
            with self.subTest(name=name):
                replies, sink = run_bridge([call(params={"name": name, "arguments": {}})])
                self.assertEqual(replies[0]["error"]["code"], -32601)
                self.assertEqual(sink, [])

    def test_unexpected_tool_arguments_are_rejected(self):
        for params in (
            {"name": "list_notes", "arguments": {"path": "/etc/passwd"}},
            {"name": "list_notes"},
            {"name": "list_notes", "arguments": {}, "extra": 1},
            {"name": "list_notes", "arguments": None},
        ):
            with self.subTest(params=params):
                replies, sink = run_bridge([call(params=params)])
                self.assertEqual(replies[0]["error"]["code"], -32601)
                self.assertEqual(sink, [])

    def test_tools_list_exposes_only_the_single_approved_tool(self):
        replies, sink = run_bridge([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
        tools = replies[0]["result"]["tools"]
        self.assertEqual([tool["name"] for tool in tools], ["list_notes"])
        self.assertEqual(sink, [])


class CallbackResponseTests(unittest.TestCase):
    def test_mismatched_response_id_is_rejected(self):
        response = FakeResponse({"jsonrpc": "2.0", "id": 999, "result": {"content": []}})
        replies, sink = run_bridge([call()], response)
        self.assertEqual(replies[0]["error"]["code"], -32602)
        self.assertEqual(replies[0]["id"], 7)
        self.assertEqual(len(sink), 1)

    def test_malformed_callback_payloads_are_rejected(self):
        for payload in (
            {"jsonrpc": "1.0", "id": 7, "result": {}},
            {"jsonrpc": "2.0", "id": 7},
            {"jsonrpc": "2.0", "id": 7, "result": {}, "error": {}},
            {"jsonrpc": "2.0", "id": 7, "result": {}, "extra": 1},
            [1, 2, 3],
        ):
            with self.subTest(payload=payload):
                replies, _ = run_bridge([call()], FakeResponse(payload))
                self.assertEqual(replies[0]["error"]["code"], -32602)

    def test_non_json_content_type_is_rejected(self):
        response = FakeResponse(
            {"jsonrpc": "2.0", "id": 7, "result": {}}, content_type="text/html"
        )
        replies, _ = run_bridge([call()], response)
        self.assertEqual(replies[0]["error"]["code"], -32602)

    def test_non_200_status_is_rejected(self):
        response = FakeResponse({"jsonrpc": "2.0", "id": 7, "result": {}}, status=403)
        replies, _ = run_bridge([call()], response)
        self.assertEqual(replies[0]["error"]["code"], -32602)

    def test_approved_call_forwards_with_work_scoped_capability(self):
        response = FakeResponse({"jsonrpc": "2.0", "id": 7, "result": {"content": []}})
        replies, sink = run_bridge([call()], response)
        self.assertEqual(replies[0]["result"], {"content": []})
        self.assertEqual(len(sink), 1)
        headers = sink[0]["headers"]
        self.assertEqual(headers["Authorization"], "Bearer " + TOKEN)
        self.assertEqual(headers["X-AgentOS-Task-ID"], TASK)
        self.assertEqual(sink[0]["host"], "127.0.0.1")
        self.assertEqual(sink[0]["port"], 8787)


class HandshakeTests(unittest.TestCase):
    def test_initialize_negotiates_from_the_registry(self):
        replies, sink = run_bridge(
            [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}}]
        )
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2024-11-05")
        self.assertEqual(sink, [])

    def test_initialize_without_params_counter_offers_latest_handshake(self):
        replies, _ = run_bridge([{"jsonrpc": "2.0", "id": 1, "method": "initialize"}])
        self.assertEqual(replies[0]["result"]["protocolVersion"], LATEST_HANDSHAKE_VERSION)

    def test_initialized_notification_produces_no_reply(self):
        replies, sink = run_bridge([{"jsonrpc": "2.0", "method": "notifications/initialized"}])
        self.assertEqual(replies, [])
        self.assertEqual(sink, [])


class CallbackUrlTests(unittest.TestCase):
    def test_unsafe_callback_urls_are_refused_at_startup(self):
        for url in (
            "https://example.com/path",
            "http://example.com/path",
            "http://user:pw@127.0.0.1:8787/path",
            "http://127.0.0.1:8787/path?q=1",
            "http://127.0.0.1:8787/path#frag",
            "not-a-url",
        ):
            with self.subTest(url=url):
                with self.assertRaises(bridge.BridgeError):
                    bridge.serve(url, TOKEN, TASK)

    def test_missing_capability_is_refused_at_startup(self):
        for token, task in (("", TASK), (TOKEN, ""), (None, TASK), (TOKEN, None)):
            with self.subTest(token=token, task=task):
                with self.assertRaises(bridge.BridgeError):
                    bridge.serve(CALLBACK, token, task)


if __name__ == "__main__":
    unittest.main()

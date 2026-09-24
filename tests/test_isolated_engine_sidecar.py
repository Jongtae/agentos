import json
import stat
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from personal_agent.isolated_engine_sidecar import (
    MAX_OUTPUT_BYTES,
    MAX_PROMPT_BYTES,
    IsolatedEngineSidecar,
    SidecarError,
    make_handler,
)


class _AgentOSCallback(BaseHTTPRequestHandler):
    calls = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        type(self).calls.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "task_id": self.headers.get("X-AgentOS-Task-ID"),
                "content_type": self.headers.get("Content-Type"),
                "request": request,
            }
        )
        response = {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {"content": [{"type": "text", "text": json.dumps({"notes": ["private note"]})}]},
        }
        raw = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args):
        pass


FAKE_CODEX = r'''#!/usr/bin/env python3
import json
import os
import subprocess
import sys

assert sys.argv[1:6] == ["exec", "--json", "--sandbox", "read-only", "--skip-git-repo-check"]
assert os.listdir(".") == []
settings = {}
index = 6
while index < len(sys.argv) - 1:
    assert sys.argv[index] == "-c"
    name, raw = sys.argv[index + 1].split("=", 1)
    settings[name] = json.loads(raw)
    index += 2
process = subprocess.Popen(
    [settings["mcp_servers.agentos.command"], *settings["mcp_servers.agentos.args"]],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
)
def rpc(value, response=True):
    process.stdin.write(json.dumps(value) + "\n")
    process.stdin.flush()
    return json.loads(process.stdout.readline()) if response else None

initialized = rpc({"jsonrpc":"2.0","id":1,"method":"initialize","params":{}})
assert initialized["result"]["capabilities"] == {"tools": {}}
tools = rpc({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
assert [tool["name"] for tool in tools["result"]["tools"]] == ["list_notes"]
denied = rpc({"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"save_note","arguments":{"content":"changed"}}})
assert denied["error"]["code"] == -32601
notes = rpc({"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"list_notes","arguments":{}}})
process.stdin.close()
process.wait(timeout=2)
assert process.returncode == 0
text = notes["result"]["content"][0]["text"]
print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":text}}))
'''


class IsolatedEngineSidecarTests(unittest.TestCase):
    def setUp(self):
        _AgentOSCallback.calls = []
        self.callback = ThreadingHTTPServer(("127.0.0.1", 0), _AgentOSCallback)
        self.callback_thread = threading.Thread(target=self.callback.serve_forever, daemon=True)
        self.callback_thread.start()
        self.folder = tempfile.TemporaryDirectory()
        self.codex = Path(self.folder.name) / "codex"
        self.codex.write_text(FAKE_CODEX, encoding="utf-8")
        self.codex.chmod(self.codex.stat().st_mode | stat.S_IXUSR)
        callback_url = "http://127.0.0.1:%d/internal/isolated-engine/mcp" % self.callback.server_port
        sidecar = IsolatedEngineSidecar(callback_url, codex_binary=str(self.codex), timeout=5)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(sidecar))
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=1)
        self.callback.shutdown()
        self.callback.server_close()
        self.callback_thread.join(timeout=1)
        self.folder.cleanup()

    def _post(self, payload):
        raw = json.dumps(payload).encode()
        connection = HTTPConnection(*self.server.server_address, timeout=8)
        connection.request("POST", "/execute", body=raw, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        value = json.loads(response.read())
        connection.close()
        return response.status, value

    def test_fake_codex_uses_read_only_bridge_end_to_end(self):
        token = "-execution-secret"
        status, response = self._post(
            {"prompt": "list the notes", "engine_id": "codex", "token": token, "task_id": "job-7"}
        )

        self.assertEqual(status, 200)
        self.assertEqual(set(response), {"result"})
        self.assertIn("private note", response["result"])
        self.assertEqual(len(_AgentOSCallback.calls), 1, "denied mutation must not reach AgentOS")
        call = _AgentOSCallback.calls[0]
        self.assertEqual(call["path"], "/internal/isolated-engine/mcp")
        self.assertEqual(call["authorization"], "Bearer " + token)
        self.assertEqual(call["task_id"], "job-7")
        self.assertEqual(call["content_type"], "application/json")
        self.assertEqual(
            call["request"],
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "list_notes", "arguments": {}}},
        )

    def test_execute_contract_rejects_other_engine_and_extra_fields(self):
        base = {"prompt": "x", "engine_id": "codex", "token": "t", "task_id": "j"}
        for payload in ({**base, "engine_id": "claude-code"}, {**base, "store": "/owner"}):
            with self.subTest(payload=payload):
                status, response = self._post(payload)
                self.assertEqual(status, 400)
                self.assertEqual(set(response), {"error"})
        self.assertEqual(_AgentOSCallback.calls, [])



class IsolatedEngineSidecarBoundaryTests(unittest.TestCase):
    """Execution evidence for each boundary REUSE-R4 must preserve (#433).

    These drive a real child process, so the timeout, output ceiling,
    malformed-stream, non-zero-exit and missing-binary paths are observed
    rather than simulated.
    """

    PAYLOAD = {"prompt": "hello", "engine_id": "codex", "token": "t", "task_id": "j"}

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.made = 0

    def _sidecar(self, body, *, timeout=10.0):
        self.made += 1
        script = self.root / ("codex-%d" % self.made)
        script.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        return IsolatedEngineSidecar(
            "http://127.0.0.1:1/internal/isolated-engine/mcp",
            codex_binary=str(script),
            timeout=timeout,
        )

    @staticmethod
    def _emit(text):
        return (
            "import json, sys\n"
            "print(json.dumps({'type':'item.completed',"
            "'item':{'type':'agent_message','text':%s}}))\n" % text
        )

    # --- baseline: the same shape succeeds, so the negatives are not vacuous
    def test_well_formed_engine_stream_is_accepted(self):
        sidecar = self._sidecar(self._emit("'final answer'"))
        self.assertEqual(sidecar.execute(dict(self.PAYLOAD)), "final answer")

    # --- empty per-request workspace ----------------------------------------
    def test_engine_runs_in_an_empty_workspace_that_is_removed_afterwards(self):
        body = (
            "import json, os\n"
            "assert os.listdir('.') == [], os.listdir('.')\n"
            "print(json.dumps({'type':'item.completed',"
            "'item':{'type':'agent_message','text':os.getcwd()}}))\n"
        )
        sidecar = self._sidecar(body)
        first = sidecar.execute(dict(self.PAYLOAD))
        second = sidecar.execute(dict(self.PAYLOAD))
        self.assertNotEqual(first, second, "each request needs its own workspace")
        for workspace in (first, second):
            self.assertFalse(Path(workspace).exists(), "workspace must not outlive the request")

    def test_bridge_config_is_kept_outside_the_engine_workspace(self):
        body = (
            "import json, os\n"
            "print(json.dumps({'type':'item.completed',"
            "'item':{'type':'agent_message','text':json.dumps(os.listdir('.'))}}))\n"
        )
        sidecar = self._sidecar(body)
        self.assertEqual(json.loads(sidecar.execute(dict(self.PAYLOAD))), [])

    # --- sandbox flag stays an AgentOS decision ------------------------------
    def test_agentos_sets_the_read_only_sandbox_flags_itself(self):
        body = (
            "import json, sys\n"
            "print(json.dumps({'type':'item.completed',"
            "'item':{'type':'agent_message','text':json.dumps(sys.argv[1:6])}}))\n"
        )
        sidecar = self._sidecar(body)
        self.assertEqual(
            json.loads(sidecar.execute(dict(self.PAYLOAD))),
            ["exec", "--json", "--sandbox", "read-only", "--skip-git-repo-check"],
        )

    # --- timeout and output limits ------------------------------------------
    def test_engine_that_overruns_the_timeout_fails_closed(self):
        sidecar = self._sidecar("import time\ntime.sleep(30)\n", timeout=0.5)
        started = time.monotonic()
        with self.assertRaises(SidecarError):
            sidecar.execute(dict(self.PAYLOAD))
        elapsed = time.monotonic() - started
        # Without the per-request timeout the child would sleep for 30s and the
        # refusal would come from the empty stream instead of the kill, so the
        # wall clock is the only assertion that distinguishes the two.
        self.assertLess(elapsed, 10.0,
                        "the timeout must stop the engine, not the empty stream")

    def test_oversized_engine_output_is_refused(self):
        # Valid JSONL with a valid final message: only the ceiling rejects it.
        body = self._emit("'x' * %d" % MAX_OUTPUT_BYTES)
        with self.assertRaises(SidecarError):
            self._sidecar(body).execute(dict(self.PAYLOAD))

    def test_accepted_result_is_truncated_to_the_declared_ceiling(self):
        sidecar = self._sidecar(self._emit("'y' * 40000"))
        self.assertEqual(len(sidecar.execute(dict(self.PAYLOAD))), 24_000)

    # --- malformed stream / non-zero exit / missing binary -------------------
    def test_malformed_event_stream_is_refused(self):
        for body in ("print('not json at all')\n", "print('{\"item\": ')\n", "pass\n"):
            with self.subTest(body=body[:16]):
                with self.assertRaises(SidecarError):
                    self._sidecar(body).execute(dict(self.PAYLOAD))

    def test_event_stream_without_a_final_agent_message_is_refused(self):
        body = (
            "import json\n"
            "print(json.dumps({'type':'thread.started'}))\n"
            "print(json.dumps({'type':'item.completed',"
            "'item':{'type':'reasoning','text':'hidden thinking'}}))\n"
            "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':1}}))\n"
        )
        with self.assertRaises(SidecarError):
            self._sidecar(body).execute(dict(self.PAYLOAD))

    def test_non_zero_exit_is_refused_even_with_a_well_formed_answer(self):
        body = self._emit("'looks fine'") + "sys.exit(3)\n"
        with self.assertRaises(SidecarError) as caught:
            self._sidecar(body).execute(dict(self.PAYLOAD))
        self.assertIn("status 3", str(caught.exception))

    def test_runtime_error_prefix_is_not_misreported_as_cli_invocation_failure(self):
        body = (
            "import sys\n"
            "sys.stderr.write('error: provider authentication failed')\n"
            "sys.exit(7)\n"
        )
        with self.assertRaises(SidecarError) as caught:
            self._sidecar(body).execute(dict(self.PAYLOAD))
        message = str(caught.exception)
        self.assertIn("status 7", message)
        self.assertNotIn("command-line invocation", message)
        self.assertNotIn("provider authentication failed", message)

    def test_missing_engine_binary_fails_closed(self):
        sidecar = IsolatedEngineSidecar(
            "http://127.0.0.1:1/internal/isolated-engine/mcp",
            codex_binary=str(self.root / "definitely-absent"),
        )
        with self.assertRaises(SidecarError):
            sidecar.execute(dict(self.PAYLOAD))

    def test_engine_stderr_is_not_echoed_to_the_caller(self):
        body = (
            "import sys\n"
            "sys.stderr.write('SENSITIVE-ENGINE-DETAIL')\n"
            "sys.exit(1)\n"
        )
        with self.assertRaises(SidecarError) as caught:
            self._sidecar(body).execute(dict(self.PAYLOAD))
        self.assertNotIn("SENSITIVE-ENGINE-DETAIL", str(caught.exception))

    # --- request contract ----------------------------------------------------
    def test_invalid_requests_are_refused_before_the_engine_starts(self):
        marker = self.root / "spawned"
        body = "import pathlib\npathlib.Path(%r).write_text('yes')\n" % str(marker)
        sidecar = self._sidecar(body)
        invalid = [
            {**self.PAYLOAD, "prompt": ""},
            {**self.PAYLOAD, "prompt": "   "},
            {**self.PAYLOAD, "prompt": "z" * (MAX_PROMPT_BYTES + 1)},
            {**self.PAYLOAD, "prompt": 7},
            {**self.PAYLOAD, "token": ""},
            {**self.PAYLOAD, "token": None},
            {**self.PAYLOAD, "task_id": ""},
            {**self.PAYLOAD, "engine_id": "claude-code"},
            {**self.PAYLOAD, "store": "/owner"},
            {"prompt": "hello", "engine_id": "codex", "token": "t"},
        ]
        for payload in invalid:
            with self.subTest(payload=sorted(payload)):
                with self.assertRaises(SidecarError):
                    sidecar.execute(payload)
        self.assertFalse(marker.exists(), "no invalid request may reach the engine")

    def test_constructor_refuses_an_unbounded_or_unrouted_worker(self):
        for kwargs in ({"callback_url": ""}, {"codex_binary": ""}, {"timeout": 0},
                       {"timeout": -1}):
            with self.subTest(**kwargs):
                arguments = {"callback_url": "http://127.0.0.1:1/cb", **kwargs}
                url = arguments.pop("callback_url")
                with self.assertRaises(ValueError):
                    IsolatedEngineSidecar(url, **arguments)


class IsolatedEngineSidecarTransportTests(unittest.TestCase):
    """The HTTP surface rejects malformed framing before any engine work."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.marker = Path(self.folder.name) / "spawned"
        codex = Path(self.folder.name) / "codex"
        codex.write_text(
            "#!/usr/bin/env python3\nimport pathlib\npathlib.Path(%r).write_text('yes')\n"
            % str(self.marker),
            encoding="utf-8",
        )
        codex.chmod(codex.stat().st_mode | stat.S_IXUSR)
        sidecar = IsolatedEngineSidecar(
            "http://127.0.0.1:1/internal/isolated-engine/mcp",
            codex_binary=str(codex),
            timeout=5,
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(sidecar))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 1)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def _raw(self, body, *, path="/execute", content_type="application/json"):
        connection = HTTPConnection(*self.server.server_address, timeout=8)
        connection.request("POST", path, body=body,
                           headers={"Content-Type": content_type})
        response = connection.getresponse()
        value = json.loads(response.read())
        connection.close()
        return response.status, value

    def test_unknown_path_and_wrong_content_type_are_refused(self):
        status, value = self._raw(b'{"a":1}', path="/other")
        self.assertEqual((status, set(value)), (404, {"error"}))
        status, value = self._raw(b'{"a":1}', content_type="text/plain")
        self.assertEqual((status, set(value)), (415, {"error"}))

    def test_duplicate_json_keys_and_non_objects_are_refused(self):
        for body in (b'{"prompt":"a","prompt":"b"}', b'["prompt"]', b'"prompt"',
                     b'not json', b'\xff\xfe'):
            with self.subTest(body=body[:14]):
                status, value = self._raw(body)
                self.assertEqual((status, set(value)), (400, {"error"}))

    def test_oversized_request_body_is_refused(self):
        status, value = self._raw(json.dumps({"prompt": "z" * 70_000}).encode())
        self.assertEqual((status, set(value)), (400, {"error"}))

    def test_no_malformed_request_ever_started_the_engine(self):
        self.test_unknown_path_and_wrong_content_type_are_refused()
        self.test_duplicate_json_keys_and_non_objects_are_refused()
        self.test_oversized_request_body_is_refused()
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()

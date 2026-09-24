import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from personal_agent.isolated_engine_gateway import (
    EngineGatewayError,
    InvalidCapability,
    InvalidEngineResponse,
    InvalidGatewayEndpoint,
    IsolatedEngineGateway,
)


class _FixtureServer(ThreadingHTTPServer):
    daemon_threads = True


class _FixtureHandler(BaseHTTPRequestHandler):
    requests = []

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        type(self).requests.append(payload)

        prompt = payload["prompt"]
        if prompt == "timeout":
            time.sleep(0.15)
        if prompt == "bad-status":
            raw = json.dumps({"error": "engine execution failed: engine process exited with status 3"}).encode()
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if prompt == "bad-contract":
            response = {"result": "ignored", "store_path": "/state/data"}
        else:
            response = {"result": f"{payload['engine_id']} completed: {prompt}"}
        raw = json.dumps(response).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, _format, *_args):
        pass


class IsolatedEngineGatewayTests(unittest.TestCase):
    def setUp(self):
        _FixtureHandler.requests = []
        self.server = _FixtureServer(("127.0.0.1", 0), _FixtureHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.endpoint = f"http://{host}:{port}/execute"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)

    def test_real_http_round_trip_sends_only_bounded_task_fields(self):
        gateway = IsolatedEngineGateway(self.endpoint)
        token = gateway.issue_task_token(prompt="summarize approved notes", engine_id="codex")

        result = gateway.execute(prompt="summarize approved notes", engine_id="codex", token=token)

        self.assertEqual(result, "codex completed: summarize approved notes")
        self.assertEqual(
            _FixtureHandler.requests,
            [{"prompt": "summarize approved notes", "engine_id": "codex", "token": token}],
        )
        wire_payload = str({key: value for key, value in _FixtureHandler.requests[0].items() if key != "token"}).lower()
        for forbidden in ("store", "data", "profile", "path", "credential", "home"):
            self.assertNotIn(forbidden, wire_payload)

    def test_token_is_random_unknown_tokens_are_rejected_and_use_is_single_shot(self):
        gateway = IsolatedEngineGateway(self.endpoint)
        first = gateway.issue_task_token(prompt="task", engine_id="codex")
        second = gateway.issue_task_token(prompt="task", engine_id="codex")
        substitution = gateway.issue_task_token(prompt="task", engine_id="codex")
        self.assertNotEqual(first, second)

        with self.assertRaises(InvalidCapability):
            gateway.execute(prompt="task", engine_id="codex", token="invented-token")
        self.assertEqual(_FixtureHandler.requests, [])

        with self.assertRaises(InvalidCapability):
            gateway.execute(prompt="changed task", engine_id="codex", token=substitution)
        with self.assertRaises(InvalidCapability):
            gateway.execute(prompt="task", engine_id="codex", token=substitution)
        self.assertEqual(_FixtureHandler.requests, [])

        gateway.execute(prompt="task", engine_id="codex", token=first)
        with self.assertRaises(InvalidCapability):
            gateway.execute(prompt="task", engine_id="codex", token=first)
        self.assertEqual(len(_FixtureHandler.requests), 1)

    def test_public_or_ambiguous_endpoints_are_rejected_before_network_use(self):
        rejected = (
            "https://127.0.0.1:9000/execute",
            "http://example.com:9000/execute",
            "http://8.8.8.8:9000/execute",
            "http://user:pass@127.0.0.1:9000/execute",
            "http://127.0.0.1:9000/execute?redirect=public",
            "http://127.0.0.1:9000/arbitrary",
        )
        for endpoint in rejected:
            with self.subTest(endpoint=endpoint), self.assertRaises(InvalidGatewayEndpoint):
                IsolatedEngineGateway(endpoint)

        # A Compose service name is accepted only through the explicit internal allowlist.
        IsolatedEngineGateway("http://engine:9000/execute", internal_hosts={"engine"})
        with self.assertRaises(InvalidGatewayEndpoint):
            IsolatedEngineGateway("http://engine:9000/execute", internal_hosts=set())

    def test_invalid_response_and_timeout_fail_closed_and_consume_capability(self):
        gateway = IsolatedEngineGateway(self.endpoint, timeout=0.03)
        bad_contract = gateway.issue_task_token(prompt="bad-contract", engine_id="codex")
        with self.assertRaises(InvalidEngineResponse):
            gateway.execute(prompt="bad-contract", engine_id="codex", token=bad_contract)
        with self.assertRaises(InvalidCapability):
            gateway.execute(prompt="retry", engine_id="codex", token=bad_contract)

        bad_status = gateway.issue_task_token(prompt="bad-status", engine_id="codex")
        with self.assertRaises(InvalidEngineResponse) as caught:
            gateway.execute(prompt="bad-status", engine_id="codex", token=bad_status)
        self.assertIn("status 3", str(caught.exception))

        timed_out = gateway.issue_task_token(prompt="timeout", engine_id="codex")
        with self.assertRaises(EngineGatewayError):
            gateway.execute(prompt="timeout", engine_id="codex", token=timed_out)
        with self.assertRaises(InvalidCapability):
            gateway.execute(prompt="retry", engine_id="codex", token=timed_out)

    def test_worker_error_detail_is_redacted_before_surface(self):
        class SecretHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                self.rfile.read(length)
                raw = json.dumps({"error": "OPENAI_API_KEY=sk-secret /root/.codex/auth.json --token=SECRET /Users/alice/private"}).encode()
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            def log_message(self, _format, *_args):
                pass

        server = _FixtureServer(("127.0.0.1", 0), SecretHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            gateway = IsolatedEngineGateway(f"http://{host}:{port}/execute")
            token = gateway.issue_task_token(prompt="task", engine_id="codex")
            with self.assertRaises(InvalidEngineResponse) as caught:
                gateway.execute(prompt="task", engine_id="codex", token=token)
            message = str(caught.exception)
            self.assertNotIn("SECRET", message)
            self.assertNotIn("sk-secret", message)
            self.assertNotIn("OPENAI_API_KEY", message)
            self.assertNotIn("/Users/alice", message)
            self.assertNotIn("/root/.codex", message)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)


if __name__ == "__main__":
    unittest.main()

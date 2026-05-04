from __future__ import annotations

import json
import http.server
import socketserver
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
KERNELCTL = ROOT_DIR / "scripts" / "agentos-kernelctl"
SCRIPT = ROOT_DIR / "scripts" / "kernel_research_brief.py"


class ResearchBriefTests(unittest.TestCase):
    def _serve_fixture(self, body: str = "AgentOS deterministic research brief fixture") -> tuple[str, socketserver.TCPServer]:
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                raw = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, format: str, *args: object) -> None:
                return

        server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return f"http://127.0.0.1:{server.server_address[1]}/brief.txt", server

    def test_research_brief_exports_expected_shape(self) -> None:
        url, server = self._serve_fixture()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            proc = subprocess.run(
                [
                    str(KERNELCTL),
                    "research-brief",
                    "--workspace",
                    str(workspace),
                    "--message-text",
                    f"fetch {url}",
                    "--chat-id",
                    "1001",
                    "--allow-domain",
                    "127.0.0.1",
                    "--json",
                ],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(proc.stdout)
            self.assertTrue(Path(payload["artifacts"]["latest_research_brief_json"]).is_file())
        self.assertEqual(payload["schema_version"], "agentos-research-brief-response.v1")
        self.assertEqual(payload["workflow_id"], "research_brief_response")
        self.assertTrue(payload["research_brief_ready"])
        self.assertTrue(payload["internal_web_query_success"])
        self.assertTrue(payload["brief_artifact_exported"])
        self.assertTrue(payload["telegram_reply_ready"])
        self.assertIn("proof_pointer", payload["brief"])

    def test_validate_reports_success(self) -> None:
        url, server = self._serve_fixture()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            out = Path(td) / "brief.json"
            subprocess.run(
                [
                    str(SCRIPT),
                    "--workspace",
                    str(workspace),
                    "--message-text",
                    f"fetch {url}",
                    "--chat-id",
                    "1001",
                    "--allow-domain",
                    "127.0.0.1",
                    "--output",
                    str(out),
                ],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            validate = subprocess.run(
                [str(SCRIPT), "--validate", str(out), "--json"],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
        self.assertTrue(json.loads(validate.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()

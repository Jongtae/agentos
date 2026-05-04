#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

python3 - "$ROOT_DIR" <<'PY'
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

root = Path(sys.argv[1])


class WebHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = b"agentos live telegram send smoke content"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class TelegramHandler(BaseHTTPRequestHandler):
    sent_payloads = []

    def do_POST(self) -> None:  # noqa: N802
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        payload = json.loads(raw.decode("utf-8"))
        self.__class__.sent_payloads.append({"path": self.path, "payload": payload})
        body = json.dumps({"ok": True, "result": {"message_id": 42}}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


web_server = ThreadingHTTPServer(("127.0.0.1", 0), WebHandler)
web_thread = threading.Thread(target=web_server.serve_forever, daemon=True)
web_thread.start()
telegram_server = ThreadingHTTPServer(("127.0.0.1", 0), TelegramHandler)
telegram_thread = threading.Thread(target=telegram_server.serve_forever, daemon=True)
telegram_thread.start()

try:
    with tempfile.TemporaryDirectory() as td:
        workspace = Path(td) / "workspace"
        workspace.mkdir(parents=True)
        message_url = f"http://127.0.0.1:{web_server.server_port}/source"
        env = os.environ.copy()
        env.update(
            {
                "PYTHONPATH": str(root / "src"),
                "AGENTOS_TELEGRAM_BOT_TOKEN": "smoke-secret-token",
                "AGENTOS_TELEGRAM_API_BASE_URL": f"http://127.0.0.1:{telegram_server.server_port}",
                "AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS": "1001",
            }
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(root / "scripts" / "kernel_telegram_reply_surface.py"),
                "--workspace",
                str(workspace),
                "--message-text",
                message_url,
                "--chat-id",
                "1001",
                "--request-id",
                "smoke-live-send",
                "--send",
                "--json",
            ],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(proc.stdout)
        assert payload["reply_ready"] is True
        assert payload["send_attempted"] is True
        assert payload["reply_sent"] is True
        assert payload["proof"]["send_ok"] is True
        assert payload["transport"]["bot_token_configured"] is True
        rendered = json.dumps(payload, ensure_ascii=True)
        assert "smoke-secret-token" not in rendered
        assert len(TelegramHandler.sent_payloads) == 1
        sent = TelegramHandler.sent_payloads[0]
        assert sent["path"] == "/botsmoke-secret-token/sendMessage"
        assert sent["payload"]["chat_id"] == "1001"
        assert "AgentOS page fetch result" in sent["payload"]["text"]
finally:
    web_server.shutdown()
    web_server.server_close()
    web_thread.join(timeout=1)
    telegram_server.shutdown()
    telegram_server.server_close()
    telegram_thread.join(timeout=1)
PY

echo "kernel telegram live send smoke: PASS"

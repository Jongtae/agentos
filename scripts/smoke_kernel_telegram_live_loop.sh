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
        body = b"agentos telegram live loop smoke content"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class TelegramHandler(BaseHTTPRequestHandler):
    sent_payloads = []
    updates = []
    conflict_once = False
    delete_webhook_count = 0

    def do_GET(self) -> None:  # noqa: N802
        if "/deleteWebhook" in self.path:
            self.__class__.delete_webhook_count += 1
            body = json.dumps({"ok": True, "result": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if "/getUpdates" not in self.path:
            self.send_response(404)
            self.end_headers()
            return
        if self.__class__.conflict_once:
            self.__class__.conflict_once = False
            body = json.dumps({"ok": False, "description": "Conflict: webhook is active"}).encode("utf-8")
            self.send_response(409)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = json.dumps({"ok": True, "result": self.__class__.updates}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
        source_url = f"http://127.0.0.1:{web_server.server_port}/source"
        TelegramHandler.updates = [
            {
                "update_id": 3001,
                "message": {
                    "message_id": 51,
                    "date": 1,
                    "chat": {"id": 1001},
                    "text": source_url,
                },
            }
        ]
        TelegramHandler.conflict_once = True
        env = os.environ.copy()
        env.update(
            {
                "PYTHONPATH": str(root / "src"),
                "AGENTOS_TELEGRAM_BOT_TOKEN": "live-loop-smoke-token",
                "AGENTOS_TELEGRAM_API_BASE_URL": f"http://127.0.0.1:{telegram_server.server_port}",
                "AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS": "1001",
            }
        )
        proc = subprocess.run(
            [
                str(root / "scripts" / "agentos-kernelctl"),
                "telegram-live-loop",
                "--workspace",
                str(workspace),
                "--once",
                "--send",
                "--json",
            ],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 1, proc.stdout + proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["telegram_polling_attempted"] is True
        assert payload["telegram_live_update_received"] is False
        assert payload["telegram_live_message_routed"] is False
        assert payload["telegram_live_search_success"] is False
        assert payload["telegram_reply_sent"] is False
        assert payload["telegram_update_offset_persisted"] is False
        assert payload["transport"]["poll_conflict_detected"] is True
        assert payload["transport"]["webhook_active"] is True
        assert payload["transport"]["webhook_clear_attempted"] is False
        assert payload["summary"]["failure_class"] == "telegram_webhook_active"
        assert TelegramHandler.delete_webhook_count == 0
        rendered = json.dumps(payload, ensure_ascii=True)
        assert "live-loop-smoke-token" not in rendered
        assert TelegramHandler.sent_payloads == []
finally:
    web_server.shutdown()
    web_server.server_close()
    web_thread.join(timeout=1)
    telegram_server.shutdown()
    telegram_server.server_close()
    telegram_thread.join(timeout=1)
PY

echo "kernel telegram live loop smoke: PASS"

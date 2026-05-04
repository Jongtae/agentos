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


telegram_server = ThreadingHTTPServer(("127.0.0.1", 0), TelegramHandler)
telegram_thread = threading.Thread(target=telegram_server.serve_forever, daemon=True)
telegram_thread.start()

try:
    with tempfile.TemporaryDirectory() as td:
        workspace = Path(td) / "workspace"
        workspace.mkdir(parents=True)
        env_file = workspace / "agentos.env"
        env_file.write_text(
            "\n".join(
                [
                    "AGENTOS_TELEGRAM_BOT_TOKEN=webhook-smoke-token",
                    "AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS=1001",
                    "AGENTOS_TELEGRAM_TRANSPORT=webhook",
                    f"AGENTOS_TELEGRAM_API_BASE_URL=http://127.0.0.1:{telegram_server.server_port}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        update_path = workspace / "update.json"
        update_path.write_text(
            json.dumps(
                {
                    "update_id": 7001,
                    "message": {
                        "message_id": 9,
                        "date": 1,
                        "chat": {"id": 1001},
                        "text": "hi",
                    },
                }
            ),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env.update(
            {
                "PYTHONPATH": str(root / "src"),
                "AGENTOS_ENV_FILE": str(env_file),
            }
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(root / "scripts" / "kernel_telegram_webhookd.py"),
                "--workspace",
                str(workspace),
                "--update-json",
                str(update_path),
                "--json",
            ],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(proc.stdout)
        assert payload["telegram_webhook_update_received"] is True
        assert payload["telegram_webhook_message_routed"] is True
        assert payload["telegram_webhook_search_success"] is False
        assert payload["intent_dispatch"]["intent"] == "greeting"
        assert payload["intent_dispatch"]["web_search_used"] is False
        assert payload["telegram_reply_sent"] is True
        assert payload["summary"]["failure_class"] == ""
        rendered = json.dumps(payload, ensure_ascii=True)
        assert "webhook-smoke-token" not in rendered
        assert len(TelegramHandler.sent_payloads) == 1
        sent = TelegramHandler.sent_payloads[0]
        assert sent["path"] == "/botwebhook-smoke-token/sendMessage"
        assert sent["payload"]["chat_id"] == "1001"
        assert "AgentOS is online" in sent["payload"]["text"]
finally:
    telegram_server.shutdown()
    telegram_server.server_close()
    telegram_thread.join(timeout=1)
PY

echo "kernel telegram webhookd smoke: PASS"

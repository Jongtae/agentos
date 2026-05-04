#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$(mktemp -d)"
trap 'rm -rf "$WORKSPACE"' EXIT

OUT_JSON="$WORKSPACE/telegram-reply.json"

python3 - "$ROOT_DIR" "$WORKSPACE" "$OUT_JSON" <<'PY'
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
workspace = Path(sys.argv[2]).resolve()
out_json = Path(sys.argv[3]).resolve()


class WebHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = b"telegram reply surface smoke"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # noqa: A003
        return


class ApiHandler(BaseHTTPRequestHandler):
    requests = []

    def do_POST(self):  # noqa: N802
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        payload = json.loads(raw.decode("utf-8"))
        self.__class__.requests.append({"path": self.path, "payload": payload})
        body = json.dumps({"ok": True, "result": {"message_id": 1}}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # noqa: A003
        return


web_server = ThreadingHTTPServer(("127.0.0.1", 0), WebHandler)
web_thread = threading.Thread(target=web_server.serve_forever, daemon=True)
web_thread.start()
api_server = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
api_thread = threading.Thread(target=api_server.serve_forever, daemon=True)
api_thread.start()

env_file = workspace / "agentos.env"
env_file.write_text(
    "\n".join(
        [
            "AGENTOS_TELEGRAM_BOT_TOKEN=test-token",
            f"AGENTOS_TELEGRAM_API_BASE_URL=http://127.0.0.1:{api_server.server_port}",
        ]
    ) + "\n",
    encoding="utf-8",
)

try:
    target_url = f"http://127.0.0.1:{web_server.server_port}/plain"
    command = [
        str(root / "scripts" / "agentos-kernelctl"),
        "telegram-reply",
        "--workspace",
        str(workspace),
        "--message-text",
        target_url,
        "--chat-id",
        "1001",
        "--allow-domain",
        "127.0.0.1",
        "--send",
        "--output",
        str(out_json),
        "--json",
    ]
    env = dict(**__import__("os").environ)
    env["AGENTOS_ENV_FILE"] = str(env_file)
    subprocess.run(command, capture_output=True, text=True, check=True, env=env)
    payload = json.loads(out_json.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "agentos-telegram-reply-surface.v1"
    assert payload["reply_ready"] is True
    assert payload["reply_sent"] is True
    assert payload["reply_mode"] == "send_message"
    assert "latest_telegram_reply_surface_manifest_json" in payload["artifacts"]
    assert ApiHandler.requests[0]["path"] == "/bottest-token/sendMessage"

    validation = subprocess.run(
        [
            str(root / "scripts" / "kernel_telegram_reply_surface.py"),
            "--validate",
            str(out_json),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(validation.stdout)
    assert report == {"ok": True, "errors": [], "schema_version": "agentos-telegram-reply-surface.v1"}
    print("kernel telegram reply surface smoke: PASS")
finally:
    web_server.shutdown()
    web_server.server_close()
    web_thread.join(timeout=1)
    api_server.shutdown()
    api_server.server_close()
    api_thread.join(timeout=1)
PY

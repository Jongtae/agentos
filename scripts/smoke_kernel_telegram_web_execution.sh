#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$(mktemp -d)"
trap 'rm -rf "$WORKSPACE"' EXIT

mkdir -p "$WORKSPACE/data"

OUT_JSON="$WORKSPACE/telegram-web-execution.json"

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


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/plain":
            self.send_response(404)
            self.end_headers()
            return
        body = b"kernel telegram web execution smoke"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    target_url = f"http://127.0.0.1:{server.server_port}/plain"
    command = [
        str(root / "scripts" / "agentos-kernelctl"),
        "telegram-web-execution",
        "--workspace",
        str(workspace),
        "--message-text",
        target_url,
        "--allow-domain",
        "127.0.0.1",
        "--output",
        str(out_json),
        "--json",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    payload = json.loads(out_json.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "agentos-telegram-web-execution-surface.v1"
    assert payload["capability"] == "telegram_web_execution"
    assert payload["selected_path"] == "internal_web_access"
    assert payload["execution_target"] == "web_access"
    assert payload["proof"]["ok"] is True
    assert payload["execution_artifacts"]["web_access"]["native_handled"] is True
    assert "latest_telegram_web_execution_manifest_json" in payload["artifacts"]
    manifest = Path(payload["artifacts"]["latest_telegram_web_execution_manifest_json"])
    assert manifest.exists()

    validation = subprocess.run(
        [
            str(root / "scripts" / "kernel_telegram_web_execution.py"),
            "--validate",
            str(out_json),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(validation.stdout)
    assert report == {"ok": True, "errors": [], "schema_version": "agentos-telegram-web-execution-surface.v1"}
    print("kernel telegram web execution smoke: PASS")
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)
PY

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
SERVER_PID=""
cleanup() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

PORT_FILE="$TMP_DIR/telegram-port"
cat > "$TMP_DIR/fake_telegram_api.py" <<'PY'
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if "/getMe" in self.path:
            body = {"ok": True, "result": {"id": 42, "is_bot": True, "username": "agentos_smoke_bot"}}
        elif "/getUpdates" in self.path:
            body = {
                "ok": True,
                "result": [
                    {
                        "update_id": 10,
                        "message": {
                            "message_id": 1,
                            "chat": {"id": 1001},
                            "text": "/start",
                        },
                    }
                ],
            }
        else:
            self.send_response(404)
            self.end_headers()
            return
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        return


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
Path("__PORT_FILE__").write_text(str(server.server_address[1]), encoding="utf-8")
try:
    server.serve_forever()
finally:
    server.server_close()
PY
python3 - <<PY &
from pathlib import Path
script = Path("$TMP_DIR/fake_telegram_api.py")
script.write_text(script.read_text(encoding="utf-8").replace("__PORT_FILE__", "$PORT_FILE"), encoding="utf-8")
exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"))
PY
SERVER_PID=$!
for _ in $(seq 1 50); do
  [ -f "$PORT_FILE" ] && break
  sleep 0.1
done

WORKSPACE="$TMP_DIR/workspace"
ENV_FILE="$TMP_DIR/agentos.env"
mkdir -p "$WORKSPACE"
API_BASE="http://127.0.0.1:$(cat "$PORT_FILE")"

payload="$(scripts/agentos-kernelctl telegram-setup \
  --workspace "$WORKSPACE" \
  --env-file "$ENV_FILE" \
  --token "smoke-secret-token" \
  --api-base-url "$API_BASE" \
  --json)"

python3 - "$payload" "$ENV_FILE" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(sys.argv[1])
env_text = Path(sys.argv[2]).read_text(encoding="utf-8")
assert payload["proof"]["ok"], payload
assert payload["get_me_ok"] is True
assert payload["chat_id_auto_detected"] is True
assert payload["chat_id"] == "1001"
assert payload["env_written"] is True
rendered = json.dumps(payload, ensure_ascii=True)
assert "smoke-secret-token" not in rendered
assert 'AGENTOS_TELEGRAM_BOT_TOKEN="smoke-secret-token"' in env_text
assert 'AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS="1001"' in env_text
assert 'AGENTOS_TELEGRAM_TRANSPORT="polling"' in env_text
assert "AGENTOS_TELEGRAM_API_BASE_URL=" in env_text
PY

printf 'telegram setup smoke: PASS\n'

ENV_FILE_PAGE="$TMP_DIR/agentos-page.env"
URL_FILE="$TMP_DIR/setup-url"
PAGE_OUT="$TMP_DIR/setup-page.json"
scripts/agentos-kernelctl telegram-setup \
  --workspace "$WORKSPACE" \
  --env-file "$ENV_FILE_PAGE" \
  --api-base-url "$API_BASE" \
  --serve-http \
  --host 127.0.0.1 \
  --display-host 198.51.100.12 \
  --port 0 \
  --timeout-sec 10 \
  --url-file "$URL_FILE" \
  --json > "$PAGE_OUT" &
PAGE_PID=$!
for _ in $(seq 1 50); do
  [ -f "$URL_FILE" ] && break
  sleep 0.1
done

python3 - "$URL_FILE" <<'PY'
import sys
from pathlib import Path
from urllib import parse, request

url = Path(sys.argv[1]).read_text(encoding="utf-8").strip()
assert url.startswith("http://198.51.100.12:"), url
payload = parse.urlencode({"token": "smoke-page-secret", "chat_id": ""}).encode("utf-8")
req = request.Request(url.replace("198.51.100.12", "127.0.0.1"), data=payload, method="POST")
with request.urlopen(req, timeout=5) as response:
    body = response.read().decode("utf-8", errors="replace")
assert "Telegram is connected" in body, body
PY
wait "$PAGE_PID"

python3 - "$PAGE_OUT" "$ENV_FILE_PAGE" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
env_text = Path(sys.argv[2]).read_text(encoding="utf-8")
assert payload["completed"] is True, payload
assert payload["telegram_setup"]["chat_id"] == "1001", payload
rendered = json.dumps(payload, ensure_ascii=True)
assert "smoke-page-secret" not in rendered
assert 'AGENTOS_TELEGRAM_BOT_TOKEN="smoke-page-secret"' in env_text
assert 'AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS="1001"' in env_text
PY

printf 'telegram setup page smoke: PASS\n'

BG_WORKSPACE="$TMP_DIR/background-workspace"
BG_URL_FILE="$TMP_DIR/background-url"
mkdir -p "$BG_WORKSPACE"
scripts/agentos-kernelctl telegram-setup \
  --workspace "$BG_WORKSPACE" \
  --serve-http \
  --background \
  --host 127.0.0.1 \
  --display-host 127.0.0.1 \
  --port 0 \
  --timeout-sec 30 \
  --url-file "$BG_URL_FILE" \
  --json > "$TMP_DIR/background-page.json"

python3 - "$TMP_DIR/background-page.json" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
assert payload["setup_page_started"] is True, payload
assert payload["setup_page_background"] is True, payload
assert payload["failure_class"] == "", payload
assert payload["setup_page_url"].startswith("http://127.0.0.1:"), payload
PY

BG_PORT="$(python3 - "$TMP_DIR/background-page.json" <<'PY'
import json
import sys
from urllib.parse import urlparse

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(urlparse(payload["setup_page_url"]).port)
PY
)"

scripts/agentos-kernelctl telegram-setup \
  --workspace "$BG_WORKSPACE" \
  --serve-http \
  --background \
  --host 127.0.0.1 \
  --display-host 127.0.0.1 \
  --port "$BG_PORT" \
  --json > "$TMP_DIR/background-page-reuse.json"

python3 - "$TMP_DIR/background-page-reuse.json" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
assert payload["setup_page_started"] is True, payload
assert payload["setup_page_background"] is True, payload
assert payload["setup_page_already_running"] is True, payload
assert payload["failure_class"] == "", payload
PY

if [ -f "$BG_WORKSPACE/artifacts/telegram-setup/setup-page-server.pid" ]; then
  kill "$(cat "$BG_WORKSPACE/artifacts/telegram-setup/setup-page-server.pid")" 2>/dev/null || true
fi

printf 'telegram setup background reuse smoke: PASS\n'

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
            body = {"ok": True, "result": {"id": 42, "is_bot": True, "username": "agentos_receiver_bot"}}
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
        elif "/deleteWebhook" in self.path:
            body = {"ok": True, "result": True}
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

FAKE_BIN="$TMP_DIR/bin"
mkdir -p "$FAKE_BIN"
cat > "$FAKE_BIN/systemctl" <<SH
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$TMP_DIR/systemctl.log"
exit 0
SH
chmod +x "$FAKE_BIN/systemctl"

WORKSPACE="$TMP_DIR/workspace"
ENV_FILE="$TMP_DIR/agentos.env"
mkdir -p "$WORKSPACE"
API_BASE="http://127.0.0.1:$(cat "$PORT_FILE")"

payload="$(PATH="$FAKE_BIN:$PATH" scripts/agentos-kernelctl telegram-setup \
  --workspace "$WORKSPACE" \
  --env-file "$ENV_FILE" \
  --token "receiver-secret-token" \
  --api-base-url "$API_BASE" \
  --json)"

python3 - "$payload" "$TMP_DIR/systemctl.log" "$ENV_FILE" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(sys.argv[1])
systemctl_log = Path(sys.argv[2]).read_text(encoding="utf-8")
env_text = Path(sys.argv[3]).read_text(encoding="utf-8")

assert payload["proof"]["ok"] is True, payload
assert payload["summary"]["target_transport"] == "polling", payload
assert payload["summary"]["receiver_activation_attempted"] is True, payload
assert payload["summary"]["receiver_activation_ok"] is True, payload
assert payload["receiver_activation"]["service"] == "agentos-telegram-live-loop.service", payload
assert "restart agentos-telegram-live-loop.service" in systemctl_log, systemctl_log
assert 'AGENTOS_TELEGRAM_TRANSPORT="polling"' in env_text
assert 'AGENTOS_TELEGRAM_POLLING_ENABLED="true"' in env_text
rendered = json.dumps(payload, ensure_ascii=True)
assert "receiver-secret-token" not in rendered
PY

echo "telegram setup activates receiver smoke: PASS"

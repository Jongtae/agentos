#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$(mktemp -d)"
SERVER_PID=""
cleanup() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$WORKSPACE"
}
trap cleanup EXIT

cat >"$WORKSPACE/server.py" <<'PY'
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        raw = b"AgentOS deterministic research brief fixture"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format, *args):
        return

server = HTTPServer(("127.0.0.1", 0), Handler)
Path("PORT").write_text(str(server.server_port), encoding="utf-8")
server.serve_forever()
PY
(cd "$WORKSPACE" && python3 server.py) &
SERVER_PID="$!"
for _ in $(seq 1 50); do
  [ -s "$WORKSPACE/PORT" ] && break
  sleep 0.1
done
PORT="$(cat "$WORKSPACE/PORT")"
URL="http://127.0.0.1:$PORT/brief.txt"

OUT="$WORKSPACE/research-brief.json"
"$ROOT_DIR/scripts/agentos-kernelctl" research-brief \
  --workspace "$WORKSPACE" \
  --message-text "fetch $URL" \
  --chat-id 1001 \
  --allow-domain 127.0.0.1 \
  --output "$OUT" \
  --json >/tmp/agentos-research-brief.out

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["schema_version"] == "agentos-research-brief-response.v1"
assert payload["research_brief_ready"] is True
assert payload["internal_web_query_success"] is True
assert payload["brief_artifact_exported"] is True
assert payload["telegram_reply_ready"] is True
assert "proof_pointer" in payload["brief"]
assert Path(payload["artifacts"]["latest_research_brief_json"]).is_file()
PY

echo "kernel research brief smoke: PASS"

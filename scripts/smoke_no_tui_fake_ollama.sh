#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src"

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

WORKSPACE_DIR="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE_DIR"

FAKE_BIN_DIR="$TMP_DIR/bin"
mkdir -p "$FAKE_BIN_DIR"
FAKE_OLLAMA="$FAKE_BIN_DIR/ollama"

cat > "$FAKE_OLLAMA" <<'EOS'
#!/usr/bin/env sh
set -eu

cmd="${1:-}"
if [ -z "$cmd" ]; then
  exit 2
fi
shift || true

case "$cmd" in
  list)
    cat <<'OUT'
NAME            ID              SIZE      MODIFIED
llama3.1:8b     fake123456      4.7 GB    1 day ago
OUT
    ;;
  run)
    model="${1:-}"
    shift || true
    prompt="$*"

    if [ -z "$model" ]; then
      echo "missing model" >&2
      exit 2
    fi

    if printf "%s" "$prompt" | grep -q "Reply with exactly: HEALTH_OK"; then
      printf "HEALTH_OK\n"
    elif printf "%s" "$prompt" | grep -q "planning engine for AgentOS"; then
      printf '%s\n' '{"summary":"list files","steps":[{"tool_name":"file_list","description":"list root","args":{"path":"."},"is_destructive":false}]}'
    else
      printf '%s\n' '{"summary":"noop","steps":[]}'
    fi
    ;;
  *)
    echo "unsupported fake ollama cmd: $cmd" >&2
    exit 2
    ;;
esac
EOS
chmod +x "$FAKE_OLLAMA"

OLLAMA_PORT_FILE="$TMP_DIR/ollama-port"
cat > "$TMP_DIR/fake_ollama_http.py" <<'PY'
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/api/tags":
            self.send_response(404)
            self.end_headers()
            return
        encoded = json.dumps({"models": []}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self):
        if self.path != "/api/generate":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        payload = json.loads(raw or "{}")
        prompt = payload.get("prompt", "")
        if "Reply with exactly: HEALTH_OK" in prompt:
            body = {"response": "HEALTH_OK", "done": True}
        elif "planning engine for AgentOS" in prompt:
            body = {
                "response": '{"summary":"list files","steps":[{"tool_name":"file_list","description":"list root","args":{"path":"."},"is_destructive":false}]}',
                "done": True,
            }
        else:
            body = {"response": '{"summary":"noop","steps":[]}', "done": True}
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
script = Path("$TMP_DIR/fake_ollama_http.py")
script.write_text(script.read_text(encoding="utf-8").replace("__PORT_FILE__", "$OLLAMA_PORT_FILE"), encoding="utf-8")
exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"))
PY
SERVER_PID=$!
for _ in $(seq 1 50); do
  [ -f "$OLLAMA_PORT_FILE" ] && break
  sleep 0.1
done
OLLAMA_HOST="http://127.0.0.1:$(cat "$OLLAMA_PORT_FILE")"

cat > "$WORKSPACE_DIR/spec.yaml" <<EOF2
name: "smoke-ollama"
ai_model:
  provider: "openai"
  model: "gpt-4o-mini"
kernel_engine:
  provider: ""
  mode: "single"
  ollama:
    command: "$FAKE_OLLAMA"
    timeout_sec: 10
    model: "llama3.1:8b"
tools:
  bash: true
  file: true
  web: true
permissions:
  require_approval: true
memory:
  checkpointer: "sqlite"
  db_path: "./data/session.sqlite"
  store_path: "./data/memory.sqlite"
runtime:
  max_steps: 12
  max_message_window: 20
  workspace_root: "./"
EOF2

OUTPUT_FILE="$TMP_DIR/run.out"
PATH="$FAKE_BIN_DIR:$PATH" OLLAMA_HOST="$OLLAMA_HOST" python3 src/main.py --no-tui --workspace "$WORKSPACE_DIR" <<'EOF3' > "$OUTPUT_FILE"
1
list files in this directory
exit
EOF3

if ! rg -q "Selected kernel engine: ollama" "$OUTPUT_FILE"; then
  echo "[smoke] missing engine selection output"
  cat "$OUTPUT_FILE"
  exit 1
fi

if ! rg -q "AI:" "$OUTPUT_FILE"; then
  echo "[smoke] missing AI response"
  cat "$OUTPUT_FILE"
  exit 1
fi

if ! rg -q "spec.yaml" "$OUTPUT_FILE"; then
  echo "[smoke] missing expected listed file"
  cat "$OUTPUT_FILE"
  exit 1
fi

echo "no-tui fake-ollama smoke: PASS"

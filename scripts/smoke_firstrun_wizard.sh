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

FAKE_BIN_DIR="$TMP_DIR/bin"
PYTHON_BIN_DIR="$(dirname "$(command -v python3)")"
PYTHON_REAL="$(python3 -c 'import sys; print(sys.executable)')"
mkdir -p "$FAKE_BIN_DIR"

cat > "$FAKE_BIN_DIR/codex" <<'EOS'
#!/bin/sh
set -eu
out_file=""
prompt=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output-last-message)
      shift
      out_file="$1"
      ;;
    *)
      prompt="$1"
      ;;
  esac
  shift
done
if echo "$prompt" | grep -q 'Reply with exactly: HEALTH_OK'; then
  msg='HEALTH_OK'
else
  msg='{"summary":"noop","steps":[]}'
fi
if [ -n "$out_file" ]; then
  printf "%s" "$msg" > "$out_file"
fi
printf "%s\n" "$msg"
EOS
chmod +x "$FAKE_BIN_DIR/codex"

cat > "$FAKE_BIN_DIR/ollama" <<'EOS'
#!/bin/sh
set -eu
cmd="${1:-}"
shift || true
case "$cmd" in
  list)
    cat <<OUT
NAME            ID
llama3.1:8b     fake
OUT
    ;;
  run)
    model="${1:-}"
    shift || true
    prompt="${*:-}"
    if echo "$prompt" | grep -q 'Reply with exactly: HEALTH_OK'; then
      printf "HEALTH_OK\n"
    else
      printf "ok:%s\n" "$model"
    fi
    ;;
  *)
    echo "unsupported fake ollama cmd: $cmd" >&2
    exit 2
    ;;
esac
EOS
chmod +x "$FAKE_BIN_DIR/ollama"

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
        encoded = json.dumps({"models": [{"name": "llama3.1:8b"}]}).encode("utf-8")
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
            body = {"response": '{"summary":"noop","steps":[]}', "done": True}
        else:
            body = {"response": "ok", "done": True}
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

cat > "$FAKE_BIN_DIR/agentos-kernelctl" <<'EOS'
#!/bin/sh
set -eu
cmd="${1:-}"
shift || true
workspace=""
env_file=""
token=""
chat_id=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --workspace)
      shift
      workspace="${1:-}"
      ;;
    --env-file)
      shift
      env_file="${1:-}"
      ;;
    --token)
      shift
      token="${1:-}"
      ;;
    --chat-id)
      shift
      chat_id="${1:-}"
      ;;
  esac
  shift || true
done
case "$cmd" in
  telegram-setup)
    [ -n "$env_file" ] || env_file="$HOME/.config/agentos/env"
    [ -n "$chat_id" ] || chat_id="1001"
    mkdir -p "$(dirname "$env_file")"
    {
      printf 'AGENTOS_TELEGRAM_BOT_TOKEN="%s"\n' "$token"
      printf 'AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS="%s"\n' "$chat_id"
    } >> "$env_file"
    chmod 0600 "$env_file"
    printf '{"proof":{"ok":true},"get_me_ok":true,"chat_id_configured":true,"env_written":true}\n'
    exit 0
    ;;
  first-run-summary)
    mkdir -p "$workspace/artifacts/repo-free-first-run"
    cat > "$workspace/artifacts/repo-free-first-run/latest-first-run-summary.json" <<'OUT'
{"summary":{"capability_proof_ready":true},"document_access":{"native_handled":true},"web_access":{"native_handled":true}}
OUT
    ;;
  vm-e2e-proof)
    mkdir -p "$workspace/artifacts/control-plane-capabilities"
    cat > "$workspace/artifacts/control-plane-capabilities/latest-vm-e2e-proof.json" <<'OUT'
{"summary":{"vm_e2e_runtime_ok":true,"vm_e2e_capability_ok":true,"vm_e2e_intake_ok":true,"vm_e2e_service_permission_ok":true,"vm_e2e_escalation_integrity_ok":true}}
OUT
    ;;
esac
printf '{}\n'
EOS
chmod +x "$FAKE_BIN_DIR/agentos-kernelctl"

make_workspace() {
  local ws="$1"
  mkdir -p "$ws"
  cat > "$ws/spec.yaml" <<'EOF'
name: "firstrun-wizard-smoke"
ai_model:
  provider: "openai"
  model: "gpt-4o-mini"
kernel_engine:
  provider: ""
  mode: "single"
  codex:
    command: "codex"
    timeout_sec: 10
    model: ""
  ollama:
    command: "ollama"
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
  max_steps: 4
  max_message_window: 20
  workspace_root: "./"
EOF
}

assert_provider() {
  local ws="$1"
  local expected="$2"
  python3 - "$ws/spec.yaml" "$expected" <<'PY'
import sys
from pathlib import Path
import yaml

spec = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
provider = str(spec.get("kernel_engine", {}).get("provider", "")).strip()
if provider != sys.argv[2]:
    raise SystemExit(f"expected provider={sys.argv[2]!r}, got {provider!r}")
PY
}

# Case 1: Explicit local selection should take the recommended local path.
WS1="$TMP_DIR/ws1"
HOME1="$TMP_DIR/home1"
make_workspace "$WS1"
mkdir -p "$HOME1"
OUT1="$TMP_DIR/out1.txt"
printf '1\n' | HOME="$HOME1" PATH="$FAKE_BIN_DIR:$PATH" OLLAMA_HOST="$OLLAMA_HOST" AGENTOS_PYTHON_BIN="$PYTHON_REAL" DEFAULT_WORKSPACE="$WS1" scripts/agentos-firstrun --workspace "$WS1" >"$OUT1"
assert_provider "$WS1" "ollama"
rg -q 'AGENTOS_PROVIDER="ollama"' "$HOME1/.config/agentos/env"
rg -q 'AgentOS First Startup' "$OUT1"
rg -q '=== Step 1 of 2 — Local AI Runtime ===' "$OUT1"
rg -q 'Choose the runtime explicitly\. Setup will not continue without a choice\.' "$OUT1"
rg -q '1\) local Ollama LLM \(recommended\)' "$OUT1"
rg -q 'After setup you talk at ai>\. Use % only for Linux commands\.' "$OUT1"
rg -q 'AgentOS setup complete\. Provider '\''ollama'\'' is configured\.' "$OUT1"
rg -q 'Next path: AgentOS Managed Session -> ai>' "$OUT1"
rg -q 'At ai>, talk normally\. Use % only for Linux commands\.' "$OUT1"
rg -q 'ai>' "$OUT1"

# Case 1b: live bootstrap state and proof exports should persist on the local path.
WS1B="$TMP_DIR/ws1b"
HOME1B="$TMP_DIR/home1b"
LIVE1B="$TMP_DIR/live1b"
HANDOFF1B="$TMP_DIR/handoff1b.env"
make_workspace "$WS1B"
mkdir -p "$HOME1B"
OUT1B="$TMP_DIR/out1b.txt"
printf '1\n' | HOME="$HOME1B" PATH="$FAKE_BIN_DIR:$PATH" OLLAMA_HOST="$OLLAMA_HOST" AGENTOS_PYTHON_BIN="$PYTHON_REAL" DEFAULT_WORKSPACE="$WS1B" AGENTOS_LIVE_BOOTSTRAP_STATE_DIR="$LIVE1B" AGENTOS_HANDOFF_PATH="$HANDOFF1B" AGENTOS_KERNELCTL_BIN="$FAKE_BIN_DIR/agentos-kernelctl" scripts/agentos-firstrun --workspace "$WS1B" >"$OUT1B"
rg -q '"component":"agentos-live-session-bootstrap"' "$LIVE1B/live-session-status.json"
rg -q '"state":"welcome_launch_succeeded"' "$LIVE1B/live-session-status.json"
rg -q '"state":"managed_shell_invoked"' "$LIVE1B/welcome-status.json"
rg -q '^route=continue_to_agentos$' "$HANDOFF1B"
[ -s "$WS1B/artifacts/repo-free-first-run/latest-first-run-summary.json" ]
[ -s "$WS1B/artifacts/control-plane-capabilities/latest-vm-e2e-proof.json" ]
[ -s "$WS1B/artifacts/runtime-entry/latest-runtime-entry-status.json" ]
rg -q '"runtime_entry_mode":"tty"' "$WS1B/artifacts/runtime-entry/latest-runtime-entry-status.json"
rg -q '"workspace_writable":true' "$WS1B/artifacts/runtime-entry/latest-runtime-entry-status.json"
AGENTOS_SESSION_MANAGED=1 AGENTOS_SESSION_ENTRY=local_tty1 "$ROOT_DIR/scripts/agentos-kernelctl" guided-operator --workspace "$WS1B" --json > "$TMP_DIR/guided-operator-ws1b.json"
python3 - "$TMP_DIR/guided-operator-ws1b.json" <<'PY'
import json, sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["runtime_entry_mode"] == "tty"
assert payload["state_summary"]["session_origin"] == "local_managed_tty1"
assert payload["operator_context"]["session_origin"] == "local_managed_tty1"
PY

# Case 2: Codex path with API key input.
WS2="$TMP_DIR/ws2"
HOME2="$TMP_DIR/home2"
make_workspace "$WS2"
mkdir -p "$HOME2"
OUT2="$TMP_DIR/out2.txt"
printf '2\ntest-openai-key\n' | HOME="$HOME2" PATH="$FAKE_BIN_DIR:$PATH" OLLAMA_HOST="$OLLAMA_HOST" AGENTOS_PYTHON_BIN="$PYTHON_REAL" OPENAI_API_KEY=test-openai-key DEFAULT_WORKSPACE="$WS2" scripts/agentos-firstrun --workspace "$WS2" >"$OUT2"
assert_provider "$WS2" "codex"
rg -q 'OPENAI_API_KEY=' "$HOME2/.config/agentos/env"
rg -q 'AgentOS setup complete\. Provider '\''codex'\'' is configured\.' "$OUT2"
rg -q 'Next path: AgentOS Managed Session -> ai>' "$OUT2"

# Case 2b: Bootstrap local path when ollama is initially missing.
WS2B="$TMP_DIR/ws2b"
HOME2B="$TMP_DIR/home2b"
BOOTSTRAP_BIN_DIR="$TMP_DIR/bootstrap-bin"
BOOTSTRAP_INSTALLER="$TMP_DIR/install-ollama.sh"
make_workspace "$WS2B"
mkdir -p "$HOME2B" "$BOOTSTRAP_BIN_DIR"
OUT2B="$TMP_DIR/out2b.txt"
cat > "$BOOTSTRAP_BIN_DIR/zstd" <<'EOS'
#!/bin/sh
exit 0
EOS
chmod +x "$BOOTSTRAP_BIN_DIR/zstd"
cat > "$BOOTSTRAP_INSTALLER" <<EOS
#!/bin/sh
set -eu
cat > "$BOOTSTRAP_BIN_DIR/ollama" <<'EOF'
#!/bin/sh
set -eu
cmd="\${1:-}"
shift || true
case "\$cmd" in
  list)
    cat <<OUT
NAME            ID
llama3.1:8b     fake
OUT
    ;;
  pull)
    printf 'pulled %s\n' "\${1:-}"
    ;;
  run)
    printf 'HEALTH_OK\n'
    ;;
  *)
    exit 2
    ;;
esac
EOF
chmod +x "$BOOTSTRAP_BIN_DIR/ollama"
EOS
chmod +x "$BOOTSTRAP_INSTALLER"
printf '1\n' | HOME="$HOME2B" PATH="$BOOTSTRAP_BIN_DIR:$PYTHON_BIN_DIR:/usr/bin:/bin" OLLAMA_HOST="$OLLAMA_HOST" AGENTOS_PYTHON_BIN="$PYTHON_REAL" AGENTOS_OLLAMA_INSTALL_CMD="$BOOTSTRAP_INSTALLER" AGENTOS_OLLAMA_START_CMD=true AGENTOS_OLLAMA_PULL_CMD="$BOOTSTRAP_BIN_DIR/ollama pull llama3.1:8b" DEFAULT_WORKSPACE="$WS2B" scripts/agentos-firstrun --workspace "$WS2B" >"$OUT2B"
assert_provider "$WS2B" "ollama"
rg -q 'Bootstrap strategy: official_install_script' "$OUT2B"
rg -q 'AgentOS setup complete\. Provider '\''ollama'\'' is configured\.' "$OUT2B"

# Case 3: Invalid input recovery + deferred provider setup.
WS3="$TMP_DIR/ws3"
HOME3="$TMP_DIR/home3"
make_workspace "$WS3"
mkdir -p "$HOME3"
OUT3="$TMP_DIR/out3.txt"
printf '9\nguide\n' | HOME="$HOME3" PATH="$FAKE_BIN_DIR:$PATH" OLLAMA_HOST="$OLLAMA_HOST" AGENTOS_PYTHON_BIN="$PYTHON_REAL" DEFAULT_WORKSPACE="$WS3" scripts/agentos-firstrun --workspace "$WS3" >"$OUT3"
assert_provider "$WS3" "none"
rg -q 'AGENTOS_PROVIDER="none"' "$HOME3/.config/agentos/env"
rg -q 'Invalid selection\. Choose 1 for local, 2 for codex, or 3 for later\.' "$OUT3"
rg -q 'AgentOS setup complete\. Provider setup is deferred\.' "$OUT3"
rg -q 'Guide mode is fallback-only\. The next prompt will clearly mark this as degraded\.' "$OUT3"
rg -q 'Next path: AgentOS Managed Session -> ai>' "$OUT3"

# Case 4: Existing engine-only env should prompt for the required Telegram gate once,
# then persist the explicit later/degraded choice.
WS4="$TMP_DIR/ws4"
HOME4="$TMP_DIR/home4"
make_workspace "$WS4"
mkdir -p "$HOME4/.config/agentos"
PYTHONPATH="$ROOT_DIR/src" PATH="$FAKE_BIN_DIR:$PATH" OLLAMA_HOST="$OLLAMA_HOST" "$PYTHON_REAL" "$ROOT_DIR/src/main.py" --workspace "$WS4" --set-engine ollama >/dev/null
printf 'AGENTOS_PROVIDER="ollama"\n' > "$HOME4/.config/agentos/env"
OUT4="$TMP_DIR/out4.txt"
HOME="$HOME4" PATH="$FAKE_BIN_DIR:$PATH" OLLAMA_HOST="$OLLAMA_HOST" AGENTOS_PYTHON_BIN="$PYTHON_REAL" DEFAULT_WORKSPACE="$WS4" scripts/agentos-firstrun --workspace "$WS4" >"$OUT4"
assert_provider "$WS4" "ollama"
rg -q 'Kernel engine already configured' "$OUT4"
rg -q 'Telegram setup skipped' "$OUT4"
rg -q 'AGENTOS_TELEGRAM_SETUP_DEFERRED="1"' "$HOME4/.config/agentos/env"

# Case 5: Terminal-only Telegram setup should append runtime env without GUI.
WS5="$TMP_DIR/ws5"
HOME5="$TMP_DIR/home5"
make_workspace "$WS5"
mkdir -p "$HOME5"
OUT5="$TMP_DIR/out5.txt"
printf '1\n' | HOME="$HOME5" PATH="$FAKE_BIN_DIR:$PATH" OLLAMA_HOST="$OLLAMA_HOST" AGENTOS_PYTHON_BIN="$PYTHON_REAL" DEFAULT_WORKSPACE="$WS5" AGENTOS_KERNELCTL_BIN="$FAKE_BIN_DIR/agentos-kernelctl" AGENTOS_FIRSTRUN_TELEGRAM_SETUP=1 AGENTOS_FIRSTRUN_TELEGRAM_BOT_TOKEN="firstrun-secret" AGENTOS_FIRSTRUN_TELEGRAM_CHAT_ID="1001" scripts/agentos-firstrun --workspace "$WS5" >"$OUT5"
assert_provider "$WS5" "ollama"
rg -q 'Telegram Setup' "$OUT5"
rg -q 'Existing bot path selected\.' "$OUT5"
rg -q 'Telegram setup complete\. Next live check:' "$OUT5"
rg -q 'AGENTOS_TELEGRAM_BOT_TOKEN="firstrun-secret"' "$HOME5/.config/agentos/env"
rg -q 'AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS="1001"' "$HOME5/.config/agentos/env"

# Case 6: Setup page path should show a QR-first URL when no token is preseeded.
WS5B="$TMP_DIR/ws5b"
HOME5B="$TMP_DIR/home5b"
make_workspace "$WS5B"
mkdir -p "$HOME5B"
OUT5B="$TMP_DIR/out5b.txt"
printf '1\n' | HOME="$HOME5B" PATH="$FAKE_BIN_DIR:$PATH" OLLAMA_HOST="$OLLAMA_HOST" AGENTOS_PYTHON_BIN="$PYTHON_REAL" DEFAULT_WORKSPACE="$WS5B" AGENTOS_KERNELCTL_BIN="$FAKE_BIN_DIR/agentos-kernelctl" AGENTOS_FIRSTRUN_TELEGRAM_SETUP=1 AGENTOS_TELEGRAM_SETUP_PAGE_HOST=127.0.0.1 AGENTOS_TELEGRAM_SETUP_DISPLAY_HOST=127.0.0.1 AGENTOS_TELEGRAM_SETUP_PAGE_PORT=8787 scripts/agentos-firstrun --workspace "$WS5B" >"$OUT5B"
assert_provider "$WS5B" "ollama"
rg -q 'Scan this QR to open AgentOS setup' "$OUT5B"
rg -q 'http://127.0.0.1:8787/setup' "$OUT5B"
rg -q 'Best UTM setting: Network Mode = Bridged' "$OUT5B"
rg -q 'If UTM is Shared/NAT, use the Mac host browser fallback URL above' "$OUT5B"
rg -q 'Telegram setup complete\. Next live check:' "$OUT5B"

# Case 7: Engine setup must not silently continue when no runtime is selected.
WS6="$TMP_DIR/ws6"
HOME6="$TMP_DIR/home6"
make_workspace "$WS6"
mkdir -p "$HOME6"
OUT6="$TMP_DIR/out6.txt"
if printf '\n' | HOME="$HOME6" PATH="$FAKE_BIN_DIR:$PATH" OLLAMA_HOST="$OLLAMA_HOST" AGENTOS_PYTHON_BIN="$PYTHON_REAL" DEFAULT_WORKSPACE="$WS6" scripts/agentos-firstrun --workspace "$WS6" >"$OUT6"; then
  echo "expected firstrun to reject empty engine selection"
  exit 1
fi
rg -q 'Please choose 1, 2, or 3\. Enter alone is not a selection\.' "$OUT6"
if [ -f "$HOME6/.config/agentos/env" ] && rg -q 'AGENTOS_PROVIDER=' "$HOME6/.config/agentos/env"; then
  echo "engine provider should not be saved without explicit selection"
  exit 1
fi

echo "firstrun wizard smoke: PASS"

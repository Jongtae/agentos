#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE_DIR="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE_DIR"

FAKE_CODEX="$TMP_DIR/fake-codex.sh"
cat > "$FAKE_CODEX" <<'EOS'
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

if printf "%s" "$prompt" | grep -q "Reply with exactly: HEALTH_OK"; then
  msg="HEALTH_OK"
elif printf "%s" "$prompt" | grep -q "planning engine for AgentOS"; then
  msg='{"summary":"list files","steps":[{"tool_name":"file_list","description":"list root","args":{"path":"."},"is_destructive":false}]}'
else
  msg='{"summary":"noop","steps":[]}'
fi

if [ -n "$out_file" ]; then
  printf "%s" "$msg" > "$out_file"
fi
printf "%s\n" "$msg"
EOS
chmod +x "$FAKE_CODEX"

cat > "$WORKSPACE_DIR/spec.yaml" <<EOS
name: "phase2-smoke"
ai_model:
  provider: "openai"
  model: "gpt-4o-mini"
kernel_engine:
  provider: ""
  mode: "single"
  codex:
    command: "$FAKE_CODEX"
    timeout_sec: 10
    model: ""
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
EOS

OUTPUT_FILE="$TMP_DIR/run.out"
AGENTOS_USE_AGENT_RUNNER=1 OPENAI_API_KEY=dummy python3 src/main.py --no-tui --workspace "$WORKSPACE_DIR" <<'EOS' > "$OUTPUT_FILE"
2
list files in this directory
exit
EOS

if ! rg -q "Phase2 runner: agent_runner \(skeleton\)" "$OUTPUT_FILE"; then
  echo "[phase2-smoke] missing phase2 runner banner"
  cat "$OUTPUT_FILE"
  exit 1
fi

if ! rg -q "AI:" "$OUTPUT_FILE"; then
  echo "[phase2-smoke] missing AI response"
  cat "$OUTPUT_FILE"
  exit 1
fi

echo "phase2 runner smoke: PASS"

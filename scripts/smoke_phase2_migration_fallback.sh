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
name: "phase2-migration-smoke"
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

PHASE2_OUT="$TMP_DIR/phase2.out"
AGENTOS_USE_AGENT_RUNNER=1 OPENAI_API_KEY=dummy python3 src/main.py --no-tui --workspace "$WORKSPACE_DIR" <<'EOS' > "$PHASE2_OUT"
2
list files in this directory
exit
EOS

if ! rg -q "Phase2 runner: agent_runner \(skeleton\)" "$PHASE2_OUT"; then
  echo "[phase2-migration] phase2 mode banner missing"
  cat "$PHASE2_OUT"
  exit 1
fi

if ! rg -q "AI:" "$PHASE2_OUT"; then
  echo "[phase2-migration] phase2 mode missing AI response"
  cat "$PHASE2_OUT"
  exit 1
fi

PHASE1_OUT="$TMP_DIR/phase1.out"
AGENTOS_USE_AGENT_RUNNER=0 OPENAI_API_KEY=dummy python3 src/main.py --no-tui --workspace "$WORKSPACE_DIR" <<'EOS' > "$PHASE1_OUT"
list files in this directory
exit
EOS

if rg -q "Phase2 runner: agent_runner \(skeleton\)" "$PHASE1_OUT"; then
  echo "[phase2-migration] fallback to phase1 failed (phase2 banner still present)"
  cat "$PHASE1_OUT"
  exit 1
fi

if ! rg -q "AI:" "$PHASE1_OUT"; then
  echo "[phase2-migration] fallback mode missing AI response"
  cat "$PHASE1_OUT"
  exit 1
fi

echo "phase2 migration/fallback smoke: PASS"

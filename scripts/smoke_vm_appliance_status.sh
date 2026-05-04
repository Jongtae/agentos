#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

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
chmod +x "$FAKE_CODEX"

cat > "$WORKSPACE/spec.yaml" <<EOS
name: "vm-appliance-status-smoke"
ai_model:
  provider: "openai"
  model: "gpt-4o-mini"
kernel_engine:
  provider: "codex"
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
  max_steps: 4
  max_message_window: 20
  workspace_root: "./"
EOS

OUT="$TMP_DIR/status.out"
ENV_FILE="$TMP_DIR/agentos.env"
printf 'AGENTOS_PROVIDER=\"codex\"\n' > "$ENV_FILE"
FAKE_SYSTEMCTL="$TMP_DIR/fake-systemctl.sh"
cat > "$FAKE_SYSTEMCTL" <<'EOS'
#!/bin/sh
set -eu
case "$1" in
  is-active)
    echo active
    ;;
  is-enabled)
    echo enabled
    ;;
  *)
    echo unknown
    ;;
esac
EOS
chmod +x "$FAKE_SYSTEMCTL"

OPENAI_API_KEY=dummy \
AGENTOS_ENV_FILE="$ENV_FILE" \
AGENTOS_SYSTEMCTL_CMD="$FAKE_SYSTEMCTL" \
AGENTOS_SESSION_MANAGED=1 \
AGENTOS_SESSION_ENTRY=local_tty1 \
AGENTOS_SESSION_BANNER_VERSION=phase49-v1 \
scripts/vm_appliance_status.sh --workspace "$WORKSPACE" > "$OUT"

for needle in \
  "AgentOS VM Appliance Status" \
  "Health summary:" \
  "Runtime status:" \
  "Broker status:" \
  "setup_status: configured" \
  "session_origin: local_managed_tty1"
do
  if ! rg -q "$needle" "$OUT"; then
    echo "[vm-appliance-status-smoke] missing output: $needle"
    cat "$OUT"
    exit 1
  fi
done

echo "vm appliance status smoke: PASS"

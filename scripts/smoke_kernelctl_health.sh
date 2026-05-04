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
name: "kernel-health-smoke"
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

FAKE_SYSTEMCTL_ACTIVE="$TMP_DIR/fake-systemctl-active.sh"
cat > "$FAKE_SYSTEMCTL_ACTIVE" <<'EOS'
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
chmod +x "$FAKE_SYSTEMCTL_ACTIVE"

GOOD_JSON="$TMP_DIR/health-good.json"
OPENAI_API_KEY=dummy AGENTOS_SYSTEMCTL_CMD="$FAKE_SYSTEMCTL_ACTIVE" "$ROOT_DIR/scripts/agentos-kernelctl" health --workspace "$WORKSPACE" --parser-cmd sh --json > "$GOOD_JSON"
python3 - "$GOOD_JSON" <<'PY'
import json
import sys
payload = json.loads(open(sys.argv[1], 'r', encoding='utf-8').read())
if not payload.get('ok', False):
    raise SystemExit('expected health ok=true')
if payload.get('service', {}).get('active') != 'active':
    raise SystemExit('expected service active')
if payload.get('checks', {}).get('policy_ready_ok') is not True:
    raise SystemExit('expected policy_ready_ok=true')
if 'policy_ready' not in payload:
    raise SystemExit('expected policy_ready section')
PY

FAKE_SYSTEMCTL_INACTIVE="$TMP_DIR/fake-systemctl-inactive.sh"
cat > "$FAKE_SYSTEMCTL_INACTIVE" <<'EOS'
#!/bin/sh
set -eu
case "$1" in
  is-active)
    echo failed
    ;;
  is-enabled)
    echo enabled
    ;;
  *)
    echo unknown
    ;;
esac
EOS
chmod +x "$FAKE_SYSTEMCTL_INACTIVE"

set +e
OPENAI_API_KEY=dummy AGENTOS_SYSTEMCTL_CMD="$FAKE_SYSTEMCTL_INACTIVE" "$ROOT_DIR/scripts/agentos-kernelctl" health --workspace "$WORKSPACE" --parser-cmd sh --json >/dev/null
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo "[kernel-health-smoke] expected non-zero for inactive service"
  exit 1
fi

echo "kernelctl health smoke: PASS"

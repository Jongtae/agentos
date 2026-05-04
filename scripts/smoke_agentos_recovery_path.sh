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
name: "agentos-recovery-path-smoke"
kernel_engine:
  provider: "codex"
  mode: "single"
  codex:
    command: "$FAKE_CODEX"
    timeout_sec: 10
    model: ""
runtime:
  workspace_root: "./"
EOS

OUT_JSON="$TMP_DIR/status.json"
ENV_FILE="$TMP_DIR/agentos.env"
printf 'AGENTOS_PROVIDER="codex"\n' > "$ENV_FILE"
OPENAI_API_KEY=dummy \
AGENTOS_ENV_FILE="$ENV_FILE" \
AGENTOS_SESSION_MANAGED=1 \
AGENTOS_SESSION_ENTRY=live_appliance \
AGENTOS_LIVE_APPLIANCE=1 \
scripts/agentos-kernelctl status --workspace "$WORKSPACE" --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
recovery = payload.get('recovery_hints', {})
if recovery.get('path_label') != 'AgentOS Recovery':
    raise SystemExit('expected AgentOS Recovery path label')
if recovery.get('recommended_rejoin_summary') != ['AgentOS Recovery', 'Return to AgentOS', 'ai>']:
    raise SystemExit('expected recovery summary path')
if recovery.get('recommended_rejoin_path', [])[0] != 'AgentOS Recovery':
    raise SystemExit('expected AgentOS Recovery rejoin path start')
runtime = payload.get('runtime_status', {})
recovery_path = runtime.get('recovery_path', {})
if recovery_path.get('label') != 'AgentOS Recovery':
    raise SystemExit('expected runtime recovery label')
if recovery_path.get('recommended_rejoin_summary') != ['AgentOS Recovery', 'Return to AgentOS', 'ai>']:
    raise SystemExit('expected runtime recovery summary path')
if recovery_path.get('entry_points', [])[0].get('trigger') != 'AGENTOS_BOOT_AUTOSTART=0':
    raise SystemExit('expected recovery ladder level 1 trigger')
print('agentos recovery path smoke: PASS')
PY

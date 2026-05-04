#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

INSTALL_ROOT="$TMP_DIR/root"
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
name: "kernel-repair-report-file-smoke"
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

AGENTOS_INSTALL_ROOT="$INSTALL_ROOT" \
AGENTOS_ENABLE_SYSTEMD=0 \
DEFAULT_WORKSPACE="$WORKSPACE" \
"$ROOT_DIR/scripts/install_kernel_boot_integration.sh"

python3 - "$INSTALL_ROOT/etc/profile.d/agentos-kernel-autostart.sh" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
body = p.read_text(encoding='utf-8')
body = body.replace('--kernel-mode', '--kernelmode')
p.write_text(body, encoding='utf-8')
PY

REPORT_FILE="$TMP_DIR/repair-report.json"
OUT_JSON="$TMP_DIR/repair-output.json"
"$ROOT_DIR/scripts/agentos-kernelctl" repair \
  --workspace "$WORKSPACE" \
  --install-root "$INSTALL_ROOT" \
  --report-file "$REPORT_FILE" \
  --json > "$OUT_JSON"

python3 - "$OUT_JSON" "$REPORT_FILE" <<'PY'
import json
import sys
out_payload = json.loads(open(sys.argv[1], 'r', encoding='utf-8').read())
file_payload = json.loads(open(sys.argv[2], 'r', encoding='utf-8').read())
if not out_payload.get('ok', False):
    raise SystemExit('expected repair output ok=true')
if not file_payload.get('ok', False):
    raise SystemExit('expected report file ok=true')
if file_payload.get('report_file') != sys.argv[2]:
    raise SystemExit('expected report_file path to be recorded in report file')
if file_payload.get('mode') != 'apply':
    raise SystemExit('expected mode=apply')
if not file_payload.get('repaired', False):
    raise SystemExit('expected repaired=true for drifted profile')
if not file_payload.get('after', {}).get('ok', False):
    raise SystemExit('expected after.ok=true in report file')
PY

"$ROOT_DIR/scripts/agentos-kernelctl" audit --install-root "$INSTALL_ROOT" --json >/dev/null

echo "kernelctl repair report-file smoke: PASS"

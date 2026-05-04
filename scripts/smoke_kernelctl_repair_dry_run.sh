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
name: "kernel-repair-dry-run-smoke"
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

python3 - "$INSTALL_ROOT/etc/systemd/system/agentos-kernel.service" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
body = p.read_text(encoding='utf-8')
body = body.replace('--doctor', '--docter')
p.write_text(body, encoding='utf-8')
PY

set +e
"$ROOT_DIR/scripts/agentos-kernelctl" audit --install-root "$INSTALL_ROOT" --json >/dev/null
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo "[kernel-repair-dry-run-smoke] expected non-zero audit for drifted service"
  exit 1
fi

OUT_JSON="$TMP_DIR/repair-dry-run.json"
"$ROOT_DIR/scripts/agentos-kernelctl" repair --workspace "$WORKSPACE" --install-root "$INSTALL_ROOT" --dry-run --json > "$OUT_JSON"
python3 - "$OUT_JSON" <<'PY'
import json
import sys
payload = json.loads(open(sys.argv[1], 'r', encoding='utf-8').read())
if payload.get('mode') != 'dry_run':
    raise SystemExit('expected mode=dry_run')
if not payload.get('ok', False):
    raise SystemExit('expected dry-run to succeed')
if not payload.get('needs_repair', False):
    raise SystemExit('expected needs_repair=true')
if payload.get('repaired', True):
    raise SystemExit('expected repaired=false on dry-run')
if payload.get('before', {}).get('ok', True):
    raise SystemExit('expected drift before dry-run')
if payload.get('after', {}).get('ok', True):
    raise SystemExit('expected drift to remain after dry-run')
PY

set +e
"$ROOT_DIR/scripts/agentos-kernelctl" audit --install-root "$INSTALL_ROOT" --json >/dev/null
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo "[kernel-repair-dry-run-smoke] expected drift to remain after dry-run"
  exit 1
fi

echo "kernelctl repair dry-run smoke: PASS"

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
name: "kernel-repair-smoke"
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

# introduce drift so repair path has work to do
python3 - "$INSTALL_ROOT/etc/profile.d/agentos-kernel-autostart.sh" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
body = p.read_text(encoding='utf-8')
body = body.replace('--kernel-mode', '--kernelmode')
p.write_text(body, encoding='utf-8')
PY

set +e
"$ROOT_DIR/scripts/agentos-kernelctl" audit --install-root "$INSTALL_ROOT" --json >/dev/null
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo "[kernel-repair-smoke] expected non-zero audit for drifted profile"
  exit 1
fi

OUT_JSON="$TMP_DIR/repair.json"
"$ROOT_DIR/scripts/agentos-kernelctl" repair --workspace "$WORKSPACE" --install-root "$INSTALL_ROOT" --json > "$OUT_JSON"
python3 - "$OUT_JSON" <<'PY'
import json
import sys
payload = json.loads(open(sys.argv[1], 'r', encoding='utf-8').read())
if not payload.get('ok', False):
    raise SystemExit('expected repair ok=true')
if not payload.get('repaired', False):
    raise SystemExit('expected repair attempted when drift exists')
if not payload.get('after', {}).get('ok', False):
    raise SystemExit('expected post-repair audit ok=true')
PY

"$ROOT_DIR/scripts/agentos-kernelctl" audit --install-root "$INSTALL_ROOT" --json >/dev/null

echo "kernelctl repair smoke: PASS"

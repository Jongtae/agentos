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
name: "kernel-repair-report-retention-smoke"
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

REPORT_DIR="$TMP_DIR/reports"
mkdir -p "$REPORT_DIR"

for i in 1 2 3; do
  python3 - "$INSTALL_ROOT/etc/profile.d/agentos-kernel-autostart.sh" "$i" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
i = sys.argv[2]
body = p.read_text(encoding='utf-8')
body = body.replace('--kernel-mode', f'--kernel-mode-{i}')
p.write_text(body, encoding='utf-8')
PY

  OUT_JSON="$TMP_DIR/repair-$i.json"
  "$ROOT_DIR/scripts/agentos-kernelctl" repair \
    --workspace "$WORKSPACE" \
    --install-root "$INSTALL_ROOT" \
    --report-dir "$REPORT_DIR" \
    --report-retain 2 \
    --json > "$OUT_JSON"

  python3 - "$OUT_JSON" <<'PY'
import json
import sys
payload = json.loads(open(sys.argv[1], 'r', encoding='utf-8').read())
if not payload.get('ok', False):
    raise SystemExit('expected repair output ok=true')
ret = payload.get('report_retention')
if not ret or ret.get('keep') != 2:
    raise SystemExit('expected report_retention.keep=2')
PY
done

python3 - "$REPORT_DIR" <<'PY'
from pathlib import Path
import sys
files = sorted(Path(sys.argv[1]).glob("kernel-repair-*.json"))
if len(files) != 2:
    raise SystemExit(f"expected 2 retained report files, got {len(files)}")
PY

"$ROOT_DIR/scripts/agentos-kernelctl" audit --install-root "$INSTALL_ROOT" --json >/dev/null

echo "kernelctl repair report-retention smoke: PASS"

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
name: "kernel-repair-selective-smoke"
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

python3 - "$INSTALL_ROOT/etc/systemd/system/getty@tty1.service.d/override.conf" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
body = p.read_text(encoding='utf-8')
body = body.replace('--autologin', '--autologn')
p.write_text(body, encoding='utf-8')
PY

set +e
"$ROOT_DIR/scripts/agentos-kernelctl" audit --install-root "$INSTALL_ROOT" --json >/dev/null
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo "[kernel-repair-selective-smoke] expected non-zero audit for drifted getty override"
  exit 1
fi

OUT_LIST="$TMP_DIR/checks.json"
"$ROOT_DIR/scripts/agentos-kernelctl" repair --list-checks --json > "$OUT_LIST"
python3 - "$OUT_LIST" <<'PY'
import json
import sys
payload = json.loads(open(sys.argv[1], 'r', encoding='utf-8').read())
required = {"service", "getty_override", "profile_autostart", "agentos_shell", "agentos_kernelctl"}
checks = set(payload.get("checks", []))
if not required.issubset(checks):
    raise SystemExit("expected full check list")
PY

OUT_SCOPE_SKIP="$TMP_DIR/repair-scope-skip.json"
"$ROOT_DIR/scripts/agentos-kernelctl" repair --workspace "$WORKSPACE" --install-root "$INSTALL_ROOT" --checks service --json > "$OUT_SCOPE_SKIP"
python3 - "$OUT_SCOPE_SKIP" <<'PY'
import json
import sys
payload = json.loads(open(sys.argv[1], 'r', encoding='utf-8').read())
if not payload.get("ok", False):
    raise SystemExit("expected scoped no-op to succeed")
if payload.get("needs_repair", True):
    raise SystemExit("expected needs_repair=false for unrelated scoped check")
if payload.get("repaired", True):
    raise SystemExit("expected repaired=false for unrelated scoped check")
PY

# drift should remain because service scope does not include getty_override drift
set +e
"$ROOT_DIR/scripts/agentos-kernelctl" audit --install-root "$INSTALL_ROOT" --json >/dev/null
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo "[kernel-repair-selective-smoke] expected drift to remain after unrelated scoped repair"
  exit 1
fi

OUT_SCOPE_FIX="$TMP_DIR/repair-scope-fix.json"
"$ROOT_DIR/scripts/agentos-kernelctl" repair --workspace "$WORKSPACE" --install-root "$INSTALL_ROOT" --checks getty_override --json > "$OUT_SCOPE_FIX"
python3 - "$OUT_SCOPE_FIX" <<'PY'
import json
import sys
payload = json.loads(open(sys.argv[1], 'r', encoding='utf-8').read())
if payload.get("checks_requested") != ["getty_override"]:
    raise SystemExit("expected checks_requested to reflect scoped repair")
if not payload.get("needs_repair", False):
    raise SystemExit("expected needs_repair=true for scoped drift")
if not payload.get("repaired", False):
    raise SystemExit("expected repaired=true for scoped drift")
if not payload.get("after", {}).get("ok", False):
    raise SystemExit("expected post-repair audit to pass")
PY

"$ROOT_DIR/scripts/agentos-kernelctl" audit --install-root "$INSTALL_ROOT" --json >/dev/null

echo "kernelctl repair selective smoke: PASS"

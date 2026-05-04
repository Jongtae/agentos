#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INIT="$ROOT_DIR/image-assets/live/bin/agentos-state-root-init"
INSTALLER="$ROOT_DIR/image-assets/live/bin/agentos-install-appliance"
WELCOME="$ROOT_DIR/image-assets/live/bin/agentos-welcome-shell"
HANDOFF="$ROOT_DIR/image-assets/live/bin/agentos-handoff"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

STATE_ROOT="$TMP_DIR/state-root"
REQ_FILE="$TMP_DIR/install.env"
HANDOFF_FILE="$TMP_DIR/handoff.env"
MARKER="$STATE_ROOT/workspaces/persist.marker"
STATUS_JSON="$TMP_DIR/status.json"
SESSION_JSON="$TMP_DIR/session.json"
WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"
cat > "$WORKSPACE/spec.yaml" <<EOS
name: "state-root-smoke"
kernel_engine:
  provider: "none"
  mode: "single"
runtime:
  workspace_root: "./"
EOS

AGENTOS_STATE_ROOT="$STATE_ROOT" bash "$INIT" >/dev/null
printf '%s\n' 'keep-me' > "$MARKER"
install_code=0
if AGENTOS_INSTALL_APPLIANCE_BIN="$INSTALLER" \
  AGENTOS_STATE_ROOT_INIT_BIN="$INIT" \
  AGENTOS_STATE_ROOT="$STATE_ROOT" \
  AGENTOS_INSTALL_REQUEST_FILE="$REQ_FILE" \
  AGENTOS_HANDOFF_BIN="$HANDOFF" \
  AGENTOS_HANDOFF_FILE="$HANDOFF_FILE" \
  bash "$WELCOME" install >/dev/null; then
  install_code=0
else
  install_code=$?
fi

test "$install_code" -eq 10
test -f "$MARKER"
rg -q '^keep-me$' "$MARKER"
rg -q '^written_by=agentos-state-root-init.v1$' "$STATE_ROOT/state-layout.env"

AGENTOS_STATE_ROOT="$STATE_ROOT" scripts/agentos-kernelctl status --workspace "$WORKSPACE" --json > "$STATUS_JSON" || true
AGENTOS_STATE_ROOT="$STATE_ROOT" scripts/agentos-kernelctl session-contract --workspace "$WORKSPACE" --json > "$SESSION_JSON"

python3 - "$STATUS_JSON" "$SESSION_JSON" <<'PY'
import json
import sys
from pathlib import Path
status = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
session = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
runtime = status.get('runtime_status', {})
usage = runtime.get('state_root_usage', {})
if usage.get('initialized') is not True:
    raise SystemExit('expected initialized state root usage')
if 'workspaces' not in usage.get('present_paths', []):
    raise SystemExit('expected workspaces path present')
if session.get('runtime_status', {}).get('state_root_usage', {}).get('initialized') is not True:
    raise SystemExit('expected session contract to expose initialized state root usage')
print('agentos state root persistence smoke: PASS')
PY

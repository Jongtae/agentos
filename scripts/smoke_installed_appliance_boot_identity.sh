#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INSTALLED_BOOT="$ROOT_DIR/image-assets/live/bin/agentos-installed-boot"
HANDOFF="$ROOT_DIR/image-assets/live/bin/agentos-handoff"
STATE_INIT="$ROOT_DIR/image-assets/live/bin/agentos-state-root-init"
SLOT_SWITCH_EVIDENCE="$ROOT_DIR/image-assets/live/bin/agentos-slot-switch-evidence"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

BOOT_FILE="$TMP_DIR/installed.env"
HANDOFF_FILE="$TMP_DIR/handoff.env"
STATE_ROOT="$TMP_DIR/state-root"
STATUS_JSON="$TMP_DIR/status.json"
SESSION_JSON="$TMP_DIR/session.json"
SWITCH_JSON="$TMP_DIR/slot-switch.json"
WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"
cat > "$WORKSPACE/spec.yaml" <<EOS
name: "installed-boot-identity-smoke"
kernel_engine:
  provider: "none"
  mode: "single"
runtime:
  workspace_root: "./"
EOS

mkdir -p "$STATE_ROOT/slots"
cat > "$STATE_ROOT/slots/next-boot.env" <<'EOF'
schema_version=agentos-next-boot.v1
bootable_slot=B
staged_from_slot=A
rollback_slot=A
payload_file=/tmp/agentos-payload.json
payload_version=v-smoke-switch
payload_channel=preview
payload_digest=abc123
EOF

AGENTOS_INSTALLED_BOOT_FILE="$BOOT_FILE" \
AGENTOS_HANDOFF_BIN="$HANDOFF" \
AGENTOS_HANDOFF_FILE="$HANDOFF_FILE" \
AGENTOS_STATE_ROOT="$STATE_ROOT" \
AGENTOS_STATE_ROOT_INIT_BIN="$STATE_INIT" \
AGENTOS_SLOT_SWITCH_EVIDENCE_BIN="$SLOT_SWITCH_EVIDENCE" \
AGENTOS_ACTIVE_SLOT=B \
AGENTOS_INACTIVE_SLOT=A \
AGENTOS_NEXT_SLOT=B \
bash "$INSTALLED_BOOT" >/dev/null

rg -q '^origin=installed_appliance_boot$' "$BOOT_FILE"
rg -q '^identity_label=Installed AgentOS Boot$' "$BOOT_FILE"
rg -q '^route=installed_appliance_boot$' "$HANDOFF_FILE"

AGENTOS_SESSION_MANAGED=1 \
AGENTOS_SESSION_ENTRY=installed_appliance \
AGENTOS_INSTALLED_APPLIANCE=1 \
AGENTOS_INSTALLED_BOOT_FILE="$BOOT_FILE" \
AGENTOS_STATE_ROOT="$STATE_ROOT" \
scripts/agentos-kernelctl status --workspace "$WORKSPACE" --json > "$STATUS_JSON" || true

AGENTOS_SESSION_MANAGED=1 \
AGENTOS_SESSION_ENTRY=installed_appliance \
AGENTOS_INSTALLED_APPLIANCE=1 \
AGENTOS_INSTALLED_BOOT_FILE="$BOOT_FILE" \
AGENTOS_STATE_ROOT="$STATE_ROOT" \
scripts/agentos-kernelctl session-contract --workspace "$WORKSPACE" --json > "$SESSION_JSON"

AGENTOS_INSTALLED_BOOT_FILE="$BOOT_FILE" \
AGENTOS_STATE_ROOT="$STATE_ROOT" \
scripts/agentos-kernelctl installed-slot-switch-evidence --json > "$SWITCH_JSON"

python3 - "$STATUS_JSON" "$SESSION_JSON" "$SWITCH_JSON" <<'PY'
import json, sys
from pathlib import Path
status = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
runtime = status.get('runtime_status', {})
installed = runtime.get('installed_boot', {})
if installed.get('available') is not True:
    raise SystemExit('expected installed boot available')
if installed.get('manifest_exists') is not True:
    raise SystemExit('expected installed boot manifest exists')
if installed.get('origin') != 'installed_appliance_boot':
    raise SystemExit('expected installed boot origin')
session = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
if session.get('runtime_status', {}).get('installed_boot', {}).get('available') is not True:
    raise SystemExit('expected session contract installed boot availability')
switch = json.loads(Path(sys.argv[3]).read_text(encoding='utf-8'))
if switch.get('switch_confirmed') is not True:
    raise SystemExit('expected slot switch confirmation')
if switch.get('planned_slot') != 'B' or switch.get('observed_slot') != 'B':
    raise SystemExit('expected planned/observed slot B')
print('installed appliance boot identity smoke: PASS')
PY

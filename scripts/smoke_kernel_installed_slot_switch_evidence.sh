#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

STATE_ROOT="$TMP_DIR/state"
SLOTS_DIR="$STATE_ROOT/slots"
mkdir -p "$SLOTS_DIR"

cat > "$SLOTS_DIR/slot-state.env" <<'EOF'
schema_version=agentos-slot-metadata.v1
active_slot=B
inactive_slot=A
rollback_slot=A
next_slot=B
health_state=healthy
EOF

cat > "$SLOTS_DIR/next-boot.env" <<'EOF'
schema_version=agentos-next-boot.v1
bootable_slot=B
staged_from_slot=A
rollback_slot=A
payload_file=/tmp/agentos-payload.json
payload_version=v-smoke-switch
payload_channel=preview
payload_digest=abc123
EOF

INSTALLED_BOOT_FILE="$TMP_DIR/installed.env"
cat > "$INSTALLED_BOOT_FILE" <<'EOF'
origin=installed_appliance_boot
identity_path=AgentOS Setup -> AgentOS Managed Session -> ai>
EOF

EVIDENCE_FILE="$TMP_DIR/slot-switch.env"
cat > "$EVIDENCE_FILE" <<'EOF'
planned_slot=B
observed_slot=B
switch_confirmed=true
evidence_status=ready
transition_kind=booted_planned_slot
payload_version=v-smoke-switch
payload_channel=preview
identity_path=AgentOS Setup -> AgentOS Managed Session -> ai>
EOF

OUT="$TMP_DIR/installed-slot-switch.json"
AGENTOS_STATE_ROOT="$STATE_ROOT" \
AGENTOS_INSTALLED_BOOT_FILE="$INSTALLED_BOOT_FILE" \
AGENTOS_SLOT_SWITCH_EVIDENCE_FILE="$EVIDENCE_FILE" \
python3 "$ROOT_DIR/scripts/kernel_installed_slot_switch_evidence.py" --output "$OUT"

AGENTOS_STATE_ROOT="$STATE_ROOT" \
AGENTOS_INSTALLED_BOOT_FILE="$INSTALLED_BOOT_FILE" \
AGENTOS_SLOT_SWITCH_EVIDENCE_FILE="$EVIDENCE_FILE" \
python3 "$ROOT_DIR/scripts/kernel_installed_slot_switch_evidence.py" --validate "$OUT" --json >/dev/null

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if payload.get('schema_version') != 'agentos-installed-slot-switch-evidence.v1':
    raise SystemExit('expected installed slot switch evidence schema')
if payload.get('switch_confirmed') is not True:
    raise SystemExit('expected switch confirmation')
if payload.get('planned_slot') != 'B' or payload.get('observed_slot') != 'B':
    raise SystemExit('expected planned/observed slot B')
print('kernel installed slot switch evidence smoke: PASS')
PY

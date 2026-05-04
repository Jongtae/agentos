#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

STATE_ROOT="$TMP_DIR/state-root"
SLOTS_DIR="$STATE_ROOT/slots"
mkdir -p "$SLOTS_DIR"
cat > "$SLOTS_DIR/slot-state.env" <<'STATE'
schema_version=agentos-slot-metadata.v1
active_slot=B
inactive_slot=A
rollback_slot=A
next_slot=B
health_state=healthy
STATE
cat > "$SLOTS_DIR/next-boot.env" <<'NEXT'
schema_version=agentos-next-boot.v1
bootable_slot=B
staged_from_slot=A
rollback_slot=A
payload_file=/tmp/payload.json
payload_version=v-checklist
payload_channel=preview
payload_digest=abc123
NEXT
cat > "$TMP_DIR/installed.env" <<'INSTALLED'
origin=installed_appliance_boot
identity_path=AgentOS Setup -> AgentOS Managed Session -> ai>
INSTALLED
cat > "$TMP_DIR/switch.env" <<'SWITCH'
planned_slot=B
observed_slot=B
switch_confirmed=true
evidence_status=ready
transition_kind=booted_planned_slot
payload_version=v-checklist
payload_channel=preview
identity_path=AgentOS Setup -> AgentOS Managed Session -> ai>
SWITCH
python3 - <<'PY' "$TMP_DIR"
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
(root / 'boot-flow-proof.json').write_text(json.dumps({'schema_version':'agentos-remastered-boot-flow-proof.v1','proof_status':'ready'}) + '\n', encoding='utf-8')
(root / 'boot-target-activation.json').write_text(json.dumps({'schema_version':'agentos-boot-target-activation.v1','boot_target_contract':'agentos_continue_boot_target.v1','activation_status':'ready'}) + '\n', encoding='utf-8')
(root / 'vm-first-screen-evidence.json').write_text(json.dumps({'schema_version':'agentos-vm-first-screen-evidence.v1','evidence_contract':'agentos_vm_first_screen_evidence.v1','evidence_status':'ready'}) + '\n', encoding='utf-8')
PY

OUT="$TMP_DIR/checklist.json"
AGENTOS_STATE_ROOT="$STATE_ROOT" \
AGENTOS_INSTALLED_BOOT_FILE="$TMP_DIR/installed.env" \
AGENTOS_SLOT_SWITCH_EVIDENCE_FILE="$TMP_DIR/switch.env" \
python3 "$ROOT_DIR/scripts/kernel_remastered_vm_boot_checklist.py" \
  --report-dir "$TMP_DIR/reports" \
  --boot-flow-proof "$TMP_DIR/boot-flow-proof.json" \
  --boot-target-activation "$TMP_DIR/boot-target-activation.json" \
  --vm-first-screen-evidence "$TMP_DIR/vm-first-screen-evidence.json" \
  --output "$OUT"

python3 "$ROOT_DIR/scripts/kernel_remastered_vm_boot_checklist.py" --validate "$OUT"
python3 - <<'PY' "$OUT"
import json, pathlib, sys
payload = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert payload['schema_version'] == 'agentos-remastered-vm-boot-checklist.v1'
assert payload['summary']['ok'] is True
assert payload['summary']['boot_flow_ready'] is True
assert payload['summary']['installed_switch_ready'] is True
print('kernel remastered VM boot checklist smoke: PASS')
PY

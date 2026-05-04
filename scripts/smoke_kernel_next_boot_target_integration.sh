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
active_slot=A
inactive_slot=B
rollback_slot=A
next_slot=B
health_state=staged_update_pending
EOF

cat > "$SLOTS_DIR/next-boot.env" <<'EOF'
schema_version=agentos-next-boot.v1
bootable_slot=B
staged_from_slot=A
rollback_slot=A
payload_file=/tmp/agentos-payload.json
payload_version=v-smoke-next
payload_channel=preview
payload_digest=abc123
EOF

OUT="$TMP_DIR/next-boot-target.json"
AGENTOS_STATE_ROOT="$STATE_ROOT" python3 "$ROOT_DIR/scripts/kernel_next_boot_target_integration.py" --output "$OUT"
AGENTOS_STATE_ROOT="$STATE_ROOT" python3 "$ROOT_DIR/scripts/kernel_next_boot_target_integration.py" --validate "$OUT" --json >/dev/null

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if payload.get('schema_version') != 'agentos-next-boot-target-integration.v1':
    raise SystemExit('expected next-boot target integration schema')
if payload.get('target_slot') != 'B':
    raise SystemExit('expected target slot B')
if payload.get('target_role') != 'installed_slot_b':
    raise SystemExit('expected installed slot b role')
if payload.get('target_origin') != 'installed_appliance_boot':
    raise SystemExit('expected installed appliance boot origin')
if payload.get('transition_kind') != 'switch_to_inactive_slot':
    raise SystemExit('expected inactive-slot transition')
if payload.get('payload_version') != 'v-smoke-next':
    raise SystemExit('expected payload version')
print('kernel next-boot target integration smoke: PASS')
PY

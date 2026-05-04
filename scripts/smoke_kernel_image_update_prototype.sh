#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

STATE_ROOT="$TMP_DIR/state-root"
OUT_JSON="$TMP_DIR/image-update.json"
META_FILE="$STATE_ROOT/slots/slot-state.env"
NEXT_BOOT_FILE="$STATE_ROOT/slots/next-boot.env"

AGENTOS_STATE_ROOT="$STATE_ROOT" bash "$ROOT_DIR/image-assets/live/bin/agentos-slot-metadata-init" >/dev/null
AGENTOS_STATE_ROOT="$STATE_ROOT" python3 "$ROOT_DIR/scripts/kernel_image_update_prototype.py" --version v-smoke-update --channel preview --output "$OUT_JSON"
AGENTOS_STATE_ROOT="$STATE_ROOT" python3 "$ROOT_DIR/scripts/kernel_slot_update_contract.py" --output "$TMP_DIR/slot-update.json"

python3 - "$OUT_JSON" "$META_FILE" "$NEXT_BOOT_FILE" "$TMP_DIR/slot-update.json" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
meta = Path(sys.argv[2]).read_text(encoding='utf-8')
next_boot = Path(sys.argv[3]).read_text(encoding='utf-8')
slot_contract = json.loads(Path(sys.argv[4]).read_text(encoding='utf-8'))
if payload.get('schema_version') != 'agentos-image-update-prototype.v1':
    raise SystemExit('expected image update prototype schema')
if payload.get('target_slot') != 'B':
    raise SystemExit('expected target slot B')
if payload.get('stage_status') != 'staged':
    raise SystemExit('expected staged status')
if 'next_slot=B' not in meta:
    raise SystemExit('expected next slot B in slot metadata')
if 'health_state=staged_update_pending' not in meta:
    raise SystemExit('expected staged health state in slot metadata')
if 'bootable_slot=B' not in next_boot:
    raise SystemExit('expected next boot slot B')
if 'payload_version=v-smoke-update' not in next_boot:
    raise SystemExit('expected next boot payload version')
if slot_contract.get('stage_status') != 'staged':
    raise SystemExit('expected staged slot update contract')
if slot_contract.get('next_boot_exists') is not True:
    raise SystemExit('expected next boot metadata surfaced')
if slot_contract.get('staged_payload_exists') is not True:
    raise SystemExit('expected staged payload surfaced')
print('kernel image update prototype smoke: PASS')
PY

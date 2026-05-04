#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

STATE_ROOT="$TMP_DIR/state-root"
OUT_JSON="$TMP_DIR/slot-recovery.json"

AGENTOS_STATE_ROOT="$STATE_ROOT" \
AGENTOS_SLOT_HEALTH_STATE=health_gate_failed \
AGENTOS_ACTIVE_SLOT=B \
AGENTOS_INACTIVE_SLOT=A \
AGENTOS_ROLLBACK_SLOT=B \
bash "$ROOT_DIR/image-assets/live/bin/agentos-slot-metadata-init" >/dev/null

AGENTOS_STATE_ROOT="$STATE_ROOT" python3 "$ROOT_DIR/scripts/kernel_slot_recovery_logic.py" --output "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if payload.get('schema_version') != 'agentos-slot-recovery-logic.v1':
    raise SystemExit('expected slot recovery logic schema')
if payload.get('failed_health_gate') is not True:
    raise SystemExit('expected failed health gate true')
if payload.get('recovery_required') is not True:
    raise SystemExit('expected recovery required true')
if payload.get('rollback_candidate') != 'B':
    raise SystemExit('expected rollback candidate B')
if payload.get('next_action') != 'rollback_to_slot_b':
    raise SystemExit('expected rollback_to_slot_b action')
print('kernel slot recovery logic smoke: PASS')
PY

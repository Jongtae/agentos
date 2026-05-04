#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INIT="$ROOT_DIR/image-assets/live/bin/agentos-slot-metadata-init"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

STATE_ROOT="$TMP_DIR/state-root"
META_FILE="$STATE_ROOT/slots/slot-state.env"
OUT_JSON="$TMP_DIR/slot-update.json"

AGENTOS_STATE_ROOT="$STATE_ROOT" \
AGENTOS_ACTIVE_SLOT=B \
AGENTOS_INACTIVE_SLOT=A \
AGENTOS_ROLLBACK_SLOT=B \
AGENTOS_NEXT_SLOT=A \
bash "$INIT" >/dev/null

rg -q '^active_slot=B$' "$META_FILE"
rg -q '^inactive_slot=A$' "$META_FILE"
rg -q '^next_slot=A$' "$META_FILE"

AGENTOS_STATE_ROOT="$STATE_ROOT" \
AGENTOS_ACTIVE_SLOT=B \
AGENTOS_INACTIVE_SLOT=A \
AGENTOS_ROLLBACK_SLOT=B \
AGENTOS_NEXT_SLOT=A \
python3 "$ROOT_DIR/scripts/kernel_slot_update_contract.py" --output "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json, sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if payload.get('active_slot') != 'B':
    raise SystemExit('expected active slot B')
if payload.get('inactive_slot') != 'A':
    raise SystemExit('expected inactive slot A')
if payload.get('next_slot') != 'A':
    raise SystemExit('expected next slot A')
if payload.get('metadata_exists') is not True:
    raise SystemExit('expected slot metadata exists')
print('agentos slot metadata smoke: PASS')
PY

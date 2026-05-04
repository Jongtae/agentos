#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

OUT_JSON="$TMP_DIR/slot-update-contract.json"
python3 "$ROOT_DIR/scripts/kernel_slot_update_contract.py" --output "$OUT_JSON"
python3 "$ROOT_DIR/scripts/kernel_slot_update_contract.py" --validate "$OUT_JSON" --json > "$TMP_DIR/validate.json"

python3 - "$OUT_JSON" "$TMP_DIR/validate.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
validate = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-slot-update-contract.v1":
    raise SystemExit("expected slot update contract schema")
if payload.get("active_slot") != "A" or payload.get("inactive_slot") != "B":
    raise SystemExit("expected default A/B slots")
if payload.get("update_model") != "image_based_ab_updates":
    raise SystemExit("expected image-based update model")
if payload.get("metadata_exists") is not False:
    raise SystemExit("expected metadata_exists false on default contract path")
if validate.get("ok") is not True:
    raise SystemExit("expected validation to pass")
PY

echo "kernel slot update contract smoke: PASS"

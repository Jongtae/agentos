#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

OUT_JSON="$TMP_DIR/system-image-layout.json"
python3 "$ROOT_DIR/scripts/kernel_system_image_layout.py" --output "$OUT_JSON"
python3 "$ROOT_DIR/scripts/kernel_system_image_layout.py" --validate "$OUT_JSON" --json > "$TMP_DIR/validate.json"

python3 - "$OUT_JSON" "$TMP_DIR/validate.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
validate = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-system-image-layout.v1":
    raise SystemExit("expected system image layout schema")
ids = [entry.get("id") for entry in payload.get("partition_contract", [])]
for required in ("efi", "system_a", "system_b", "state", "recovery"):
    if required not in ids:
        raise SystemExit(f"missing required partition id: {required}")
if validate.get("ok") is not True:
    raise SystemExit("expected validation to pass")
PY

echo "kernel system image layout smoke: PASS"

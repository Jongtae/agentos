#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

OUT_JSON="$TMP_DIR/image-release-identity.json"
python3 "$ROOT_DIR/scripts/kernel_image_release_identity.py" --version v-chromeos-reset --channel dev --output "$OUT_JSON"
python3 "$ROOT_DIR/scripts/kernel_image_release_identity.py" --validate "$OUT_JSON" --json > "$TMP_DIR/validate.json"

python3 - "$OUT_JSON" "$TMP_DIR/validate.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
validate = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-image-release-identity.v1":
    raise SystemExit("expected image release identity schema")
if payload.get("version") != "v-chromeos-reset":
    raise SystemExit("expected custom version")
if payload.get("channel") != "dev":
    raise SystemExit("expected custom channel")
if payload.get("update_model") != "image_based_ab_updates":
    raise SystemExit("expected image-based update model")
if payload.get("next_slot") != "B":
    raise SystemExit("expected next slot B")
if "slot_metadata_file" not in payload:
    raise SystemExit("expected slot metadata file")
if "next_boot_file" not in payload:
    raise SystemExit("expected next boot file")
if validate.get("ok") is not True:
    raise SystemExit("expected validation to pass")
PY

echo "kernel image release identity smoke: PASS"

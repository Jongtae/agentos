#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

OUT_JSON="$TMP_DIR/recovery-mode-contract.json"
python3 "$ROOT_DIR/scripts/kernel_recovery_mode_contract.py" --output "$OUT_JSON"
python3 "$ROOT_DIR/scripts/kernel_recovery_mode_contract.py" --validate "$OUT_JSON" --json > "$TMP_DIR/validate.json"

python3 - "$OUT_JSON" "$TMP_DIR/validate.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
validate = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-recovery-mode-contract.v1":
    raise SystemExit("expected recovery mode schema")
if payload.get("label") != "Recovery":
    raise SystemExit("expected recovery label")
if payload.get("primary_return_action") != "Return to AgentOS":
    raise SystemExit("expected Return to AgentOS")
if "slot_recovery" not in payload:
    raise SystemExit("expected slot recovery summary")
if validate.get("ok") is not True:
    raise SystemExit("expected validation to pass")
PY

echo "kernel recovery mode contract smoke: PASS"

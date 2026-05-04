#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

OUT_JSON="$TMP_DIR/state-partition-contract.json"
python3 "$ROOT_DIR/scripts/kernel_state_partition_contract.py" --output "$OUT_JSON"
python3 "$ROOT_DIR/scripts/kernel_state_partition_contract.py" --validate "$OUT_JSON" --json > "$TMP_DIR/validate.json"

python3 - "$OUT_JSON" "$TMP_DIR/validate.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
validate = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-state-partition-contract.v1":
    raise SystemExit("expected state partition schema")
if payload.get("state_root") != "/var/lib/agentos":
    raise SystemExit("expected state root")
if "workspace_state" not in (payload.get("mutable_contract") or {}):
    raise SystemExit("expected workspace_state mutable contract")
if validate.get("ok") is not True:
    raise SystemExit("expected validation to pass")
PY

echo "kernel state partition contract smoke: PASS"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
USER_ROOT="$TMP_DIR/agentos-data/user"
OUT="$TMP_DIR/preview.json"
mkdir -p "$WORKSPACE" "$USER_ROOT"

PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 scripts/phase2_runtime_preview.py \
  --workspace "$WORKSPACE" \
  --user-root "$USER_ROOT" \
  --prompt "status" \
  --output "$OUT" \
  --json >/dev/null

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-phase2-runtime-preview.v1"
assert payload["product_target"] is False
assert payload["proof"]["ok"] is True
assert payload["proof"]["docker_claims_boot_proof"] is False
assert payload["intent_dispatch"]["intent"] == "runtime_status"
assert Path(payload["record_path"]).exists()
assert str(payload["record_path"]).startswith(payload["user_data_root"])
PY

echo "phase2 runtime preview smoke: PASS"


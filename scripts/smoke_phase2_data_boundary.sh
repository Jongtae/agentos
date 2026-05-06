#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

OUT="$TMP_DIR/boundary.json"
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 scripts/kernel_phase2_data_boundary.py \
  --root "$TMP_DIR/agentos-data" \
  --output "$OUT" \
  --json >/dev/null

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-phase2-data-boundary.v1"
assert payload["secret_values_present"] is False
assert payload["proof"]["ok"] is True
assert payload["proof"]["user_state_separated"] is True
assert payload["proof"]["cache_not_user_record"] is True
assert Path(payload["sample_user_record"]).exists()
PY

echo "phase2 data boundary smoke: PASS"


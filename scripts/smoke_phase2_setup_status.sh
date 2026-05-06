#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

OUT="$TMP_DIR/setup-status.json"
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 scripts/kernel_phase2_setup_status.py \
  --workspace "$TMP_DIR/workspace" \
  --user-root "$TMP_DIR/agentos-data/user" \
  --output "$OUT" \
  --json >/dev/null

python3 - "$OUT" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
assert payload["schema_version"] == "agentos-phase2-setup-status.v1"
assert payload["runtime_ready"] is True
assert payload["overall_state"] == "degraded"
assert payload["secrets_redacted"] is True
assert payload["proof"]["secret_values_printed"] is False
assert payload["adapters"]["telegram"]["state"] == "missing"
assert payload["adapters"]["gmail"]["state"] == "missing"
PY

echo "phase2 setup status smoke: PASS"


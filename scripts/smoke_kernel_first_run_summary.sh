#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
OUT_JSON="$TMP_DIR/first-run-summary.json"
mkdir -p "$WORKSPACE"

python3 "$ROOT_DIR/scripts/kernel_first_run_summary.py" \
  --workspace "$WORKSPACE" \
  --output "$OUT_JSON" \
  --json >/dev/null

python3 "$ROOT_DIR/scripts/kernel_first_run_summary.py" --validate "$OUT_JSON" --json >/dev/null

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["summary"]["document_native_handled"] is True
assert payload["summary"]["web_handled"] is True
assert payload["summary"]["capability_proof_ready"] is True
assert "latest_first_run_summary_manifest_json" in payload["artifacts"]
print("kernel first run summary smoke: PASS")
PY

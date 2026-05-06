#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

OUT="$TMP_DIR/result.json"
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 scripts/kernel_phase2_capability_result.py \
  --workspace "$TMP_DIR/workspace" \
  --intent status \
  --capability runtime_status \
  --status ok \
  --output "Runtime ready" \
  --json >"$OUT"

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-phase2-capability-result.v1"
assert payload["status"] == "ok"
assert payload["activity_state"] == "completed"
assert payload["record"]["durable"] is True
assert Path(payload["record"]["path"]).exists()
assert payload["recovery"]["required"] is False
PY

echo "phase2 capability result smoke: PASS"


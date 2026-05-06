#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

OUT="$TMP_DIR/recovery.json"
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 scripts/kernel_phase2_lifecycle_recovery.py \
  --workspace "$TMP_DIR/workspace" \
  --action restart-runtime \
  --json >"$OUT"

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-phase2-lifecycle-recovery.v1"
assert payload["requested_action"] == "restart-runtime"
assert payload["needs_confirmation"] is True
assert payload["destructive_action_executed"] is False
assert payload["simulated_control"] is True
assert payload["activity"]["kind"] == "recovery.suggested"
assert payload["proof"]["blocker"] == "confirmation_required"
assert payload["proof"]["runtime_proof_completed"] is False
assert Path(payload["manifest_path"]).exists()
PY

echo "phase2 lifecycle recovery smoke: PASS"

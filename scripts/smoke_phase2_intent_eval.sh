#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 scripts/phase2_intent_eval.py --json >/tmp/agentos-phase2-intent-eval.json || true
python3 - <<'PY'
import json
from pathlib import Path

payload = json.loads(Path("/tmp/agentos-phase2-intent-eval.json").read_text())
assert payload["schema_version"] == "agentos-phase2-intent-eval-result.v1"
assert payload["case_count"] >= 18
assert payload["failed_count"] == 0
PY

echo "phase2 intent eval seed smoke: PASS"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

USER_ROOT="$TMP_DIR/user-data"
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 scripts/kernel_phase2_records.py \
  --user-root "$USER_ROOT" \
  --append \
  --title "Phase 2 roadmap review" \
  --body "Gmail fixture draft and runtime records should be searchable by the operator." \
  --source gmail_fixture \
  --tag phase-2 \
  --json >/dev/null

OUT="$TMP_DIR/find.json"
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 scripts/kernel_phase2_records.py \
  --user-root "$USER_ROOT" \
  --find \
  --query roadmap \
  --json >"$OUT"

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-phase2-records.v1"
assert payload["matched_count"] == 1
assert payload["records"][0]["source"] == "gmail_fixture"
assert payload["boundary"]["user_owned"] is True
assert payload["boundary"]["secrets_allowed"] is False
assert payload["boundary"]["second_brain_claimed"] is False
assert Path(payload["records_path"]).exists()
assert payload["proof"]["record_lookup_ready"] is True
PY

echo "phase2 records smoke: PASS"

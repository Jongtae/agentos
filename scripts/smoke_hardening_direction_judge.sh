#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

OUT="$TMP_DIR/hardening-direction.json"
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 "$ROOT_DIR/scripts/kernel_hardening_direction_judge.py" \
  --root "$ROOT_DIR" \
  --output "$OUT" \
  --fail-on-reject

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-hardening-direction-judge.v1", payload
assert payload["verdict"] in {"accept", "accept_with_risk"}, payload
assert payload["phase_focus"]["phase2_closeout_recorded"] is True, payload
assert payload["phase_focus"]["hardening_loop_active"] is True, payload
assert payload["proof"]["runtime_first_language_present"] is True, payload
assert payload["proof"]["cleanup_policy_present"] is True, payload
assert payload["proof"]["vm_iso_blocker_explicit"] is True, payload
assert payload["completion_tracks"], payload
if payload["next_forward_candidates"]:
    assert any(candidate["safe_without_external_state"] for candidate in payload["next_forward_candidates"]), payload
else:
    blocker_ids = {blocker.get("id") for blocker in payload.get("blockers", [])}
    assert {"live-gmail-oauth", "vm-iso-proof"} <= blocker_ids, payload
PY

echo "hardening direction judge smoke: PASS"

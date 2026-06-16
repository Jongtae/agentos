#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/agentos-phase2-updater-state.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

READY_JSON="$TMP_DIR/ready.json"
ROLLBACK_JSON="$TMP_DIR/rollback.json"
BLOCKED_JSON="$TMP_DIR/blocked.json"

python3 "$ROOT_DIR/scripts/kernel_phase2_updater_state.py" --workspace "$TMP_DIR" --output "$READY_JSON" --json > "$TMP_DIR/ready.stdout.json"
python3 "$ROOT_DIR/scripts/kernel_phase2_updater_state.py" --validate "$READY_JSON" --json > "$TMP_DIR/ready.validate.json"

python3 "$ROOT_DIR/scripts/kernel_phase2_updater_state.py" --workspace "$TMP_DIR" --state rollback-needed --output "$ROLLBACK_JSON" --json > "$TMP_DIR/rollback.stdout.json"
python3 "$ROOT_DIR/scripts/kernel_phase2_updater_state.py" --validate "$ROLLBACK_JSON" --json > "$TMP_DIR/rollback.validate.json"

python3 "$ROOT_DIR/scripts/kernel_phase2_updater_state.py" --workspace "$TMP_DIR" --state blocked --output "$BLOCKED_JSON" --json > "$TMP_DIR/blocked.stdout.json"
python3 "$ROOT_DIR/scripts/kernel_phase2_updater_state.py" --validate "$BLOCKED_JSON" --json > "$TMP_DIR/blocked.validate.json"

python3 - "$READY_JSON" "$ROLLBACK_JSON" "$BLOCKED_JSON" "$TMP_DIR/ready.validate.json" "$TMP_DIR/rollback.validate.json" "$TMP_DIR/blocked.validate.json" <<'PY'
import json
import sys
from pathlib import Path

ready = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
rollback = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
blocked = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
validations = [json.loads(Path(path).read_text(encoding="utf-8")) for path in sys.argv[4:]]

assert all(item["ok"] for item in validations), validations
assert ready["schema_version"] == "agentos-phase2-updater-state.v1"
assert ready["state"]["status"] == "ready"
assert ready["runtime_rejoin"]["target"] == "codex_cli_managed_session"
for payload in (ready, rollback, blocked):
    proof = payload["proof"]
    assert proof["destructive_action_executed"] is False
    assert proof["live_updater_executed"] is False
    assert proof["vm_iso_proof_completed"] is False
    assert proof["fixture_or_contract_only"] is True
    assert payload["state"]["managed_runtime_return_required"] is True
assert rollback["state"]["status"] == "needs_recovery"
assert rollback["state"]["rollback_requested"] is True
assert blocked["state"]["status"] == "blocked"
assert blocked["blockers"], blocked
assert blocked["blockers"][0]["id"] == "vm-or-live-updater-proof-required"
PY

echo "PASS phase2 updater state smoke"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
USER_ROOT="$TMP_DIR/user"
mkdir -p "$WORKSPACE"
printf 'phase2 cli fixture\n' >"$WORKSPACE/notes.txt"

run_phase2() {
  local name="$1"
  local message="$2"
  PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" scripts/agentos-kernelctl phase2-run \
    --workspace "$WORKSPACE" \
    --user-root "$USER_ROOT" \
    --message "$message" \
    --allow-domain example.com \
    --json >"$TMP_DIR/${name}.json"
}

run_phase2 status "status"
run_phase2 workspace "list files in workspace"
run_phase2 gmail "draft a reply to my Gmail roadmap email"
run_phase2 calendar "summarize my upcoming calendar roadmap meeting"
run_phase2 records "find my roadmap records"
run_phase2 web "summarize https://example.com"
run_phase2 lifecycle "restart runtime"
run_phase2 update "update AgentOS"
run_phase2 rollback "rollback AgentOS"

PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" scripts/agentos-kernelctl phase2-run \
  --workspace "$WORKSPACE" \
  --user-root "$USER_ROOT" \
  --prompt "status" >"$TMP_DIR/human.txt"

python3 - "$TMP_DIR" "$USER_ROOT" <<'PY'
import json
import sys
from pathlib import Path

tmp_dir = Path(sys.argv[1])
user_root = Path(sys.argv[2])

expected = {
    "status": ("runtime_status", "runtime_status", "completed"),
    "workspace": ("local_workspace_search", "local_workspace_search", "completed"),
    "gmail": ("gmail_read_or_draft", "gmail_read_or_draft", "completed"),
    "calendar": ("calendar_readonly", "calendar_readonly", "completed"),
    "records": ("record_lookup", "record_lookup", "completed"),
    "web": ("web_search_summary", "research_brief_response", "completed"),
    "lifecycle": ("lifecycle_recovery", "lifecycle_recovery", "blocked"),
    "update": ("lifecycle_recovery", "lifecycle_recovery", "blocked"),
    "rollback": ("lifecycle_recovery", "lifecycle_recovery", "blocked"),
}

for name, (intent, capability, status) in expected.items():
    payload = json.loads((tmp_dir / f"{name}.json").read_text())
    assert payload["schema_version"] == "agentos-phase2-run.v1", payload
    assert payload["intent"] == intent, payload
    assert payload["capability"] == capability, payload
    assert payload["status"] == status, payload
    assert payload["permission"]["secret_material_redacted"] is True, payload
    assert payload["outcome"], payload
    assert payload["response"].strip(), payload
    assert payload["proof"]["testable_cli_surface"] is True, payload
    assert payload["proof"]["destructive_action_executed"] is False, payload
    assert payload["proof"]["permission_checked"] is True, payload
    assert payload["proof"]["outcome_checked"] is True, payload
    assert payload["proof"]["secrets_redacted"] is True, payload
    assert payload["activity_feed"]["event_count"] >= 4, payload
    assert Path(payload["artifacts"]["record_path"]).exists(), payload
    assert payload["record"]["source"] == "phase2_run", payload

status_payload = json.loads((tmp_dir / "status.json").read_text())
assert status_payload["permission"]["level"] == "safe_read"
assert status_payload["outcome"] == "completed"

gmail = json.loads((tmp_dir / "gmail.json").read_text())
assert gmail["permission"]["level"] == "external_read"
assert gmail["outcome"] == "completed"
assert gmail["proof"]["gmail_fixture_mode"] is True
assert gmail["proof"]["live_gmail_oauth_completed"] is False
assert gmail["blockers"][0]["id"] == "gmail-oauth-live"

calendar = json.loads((tmp_dir / "calendar.json").read_text())
assert calendar["permission"]["level"] == "external_read"
assert calendar["outcome"] == "completed"
assert calendar["proof"]["calendar_fixture_mode"] is True
assert calendar["capability_result"]["proof"]["read_only"] is True
assert calendar["capability_result"]["proof"]["mutation_executed"] is False
assert calendar["blockers"][0]["id"] == "calendar-live-oauth"

web = json.loads((tmp_dir / "web.json").read_text())
assert web["proof"]["browser_fallback_contract_attached"] is True
assert web["proof"]["live_browser_executed"] is False
assert Path(web["artifacts"]["browser_fallback_contract"]).exists()
browser_fallback = web["capability_result"]["browser_fallback"]
assert browser_fallback["schema_version"] == "agentos-phase2-browser-fallback-contract.v1"
assert browser_fallback["routing"]["internal_capability_preferred"] is True
assert browser_fallback["routing"]["browser_is_default"] is False
assert browser_fallback["proof"]["live_browser_executed"] is False

lifecycle = json.loads((tmp_dir / "lifecycle.json").read_text())
assert lifecycle["permission"]["level"] == "lifecycle_confirmed"
assert lifecycle["outcome"] == "blocked_needs_confirmation"
assert lifecycle["recovery"]["required"] is True
assert lifecycle["blockers"][0]["id"] == "lifecycle-confirmation-required"
assert "confirm restart-runtime" in lifecycle["response"]
assert lifecycle["proof"]["updater_state_contract_attached"] is True
assert Path(lifecycle["artifacts"]["updater_state_manifest"]).exists()

update = json.loads((tmp_dir / "update.json").read_text())
assert update["proof"]["updater_state_contract_attached"] is True
assert update["proof"]["live_updater_executed"] is False
assert update["proof"]["vm_iso_proof_completed"] is False
assert "confirm stage-update" in update["response"]
assert Path(update["artifacts"]["updater_state_manifest"]).exists()
assert update["capability_result"]["updater_state"]["state"]["status"] == "blocked"
assert any(blocker["id"] == "vm-or-live-updater-proof-required" for blocker in update["blockers"])

rollback = json.loads((tmp_dir / "rollback.json").read_text())
assert rollback["proof"]["updater_state_contract_attached"] is True
assert rollback["proof"]["live_updater_executed"] is False
assert rollback["proof"]["destructive_action_executed"] is False
assert "confirm rollback" in rollback["response"]
assert rollback["capability_result"]["updater_state"]["state"]["status"] == "needs_recovery"

records_path = user_root / "records" / "records.jsonl"
assert records_path.exists()
assert len(records_path.read_text().splitlines()) >= 6

human = (tmp_dir / "human.txt").read_text()
assert "AgentOS Phase 2 run" in human
assert "intent:" in human
assert "permission:" in human
assert "outcome:" in human
assert "record:" in human
PY

echo "phase2 run cli smoke: PASS"

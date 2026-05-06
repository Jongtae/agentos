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
run_phase2 records "find my roadmap records"
run_phase2 lifecycle "restart runtime"

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
    "records": ("record_lookup", "record_lookup", "completed"),
    "lifecycle": ("lifecycle_recovery", "lifecycle_recovery", "blocked"),
}

for name, (intent, capability, status) in expected.items():
    payload = json.loads((tmp_dir / f"{name}.json").read_text())
    assert payload["schema_version"] == "agentos-phase2-run.v1", payload
    assert payload["intent"] == intent, payload
    assert payload["capability"] == capability, payload
    assert payload["status"] == status, payload
    assert payload["response"].strip(), payload
    assert payload["proof"]["testable_cli_surface"] is True, payload
    assert payload["proof"]["destructive_action_executed"] is False, payload
    assert payload["activity_feed"]["event_count"] >= 4, payload
    assert Path(payload["artifacts"]["record_path"]).exists(), payload
    assert payload["record"]["source"] == "phase2_run", payload

gmail = json.loads((tmp_dir / "gmail.json").read_text())
assert gmail["proof"]["gmail_fixture_mode"] is True
assert gmail["proof"]["live_gmail_oauth_completed"] is False
assert gmail["blockers"][0]["id"] == "gmail-oauth-live"

lifecycle = json.loads((tmp_dir / "lifecycle.json").read_text())
assert lifecycle["blockers"][0]["id"] == "lifecycle-confirmation-required"
assert "confirm restart-runtime" in lifecycle["response"]

records_path = user_root / "records" / "records.jsonl"
assert records_path.exists()
assert len(records_path.read_text().splitlines()) >= 5

human = (tmp_dir / "human.txt").read_text()
assert "AgentOS Phase 2 run" in human
assert "intent:" in human
assert "record:" in human
PY

echo "phase2 run cli smoke: PASS"

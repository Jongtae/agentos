#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
REPORT_DIR="$TMP_DIR/reports"
HISTORY_DIR="$TMP_DIR/history"
POLICY_DIR="$WORKSPACE/artifacts/kernel-policy"
mkdir -p "$HISTORY_DIR" "$POLICY_DIR"

cat > "$WORKSPACE/spec.yaml" <<'YAML'
name: limited-preview-readiness-smoke
kernel_engine:
  provider: none
  mode: single
runtime:
  workspace_root: ./
YAML

cat > "$WORKSPACE/artifacts/runtime_trace.jsonl" <<'JSONL'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","event":"run_start","payload":{}}
JSONL

cat > "$WORKSPACE/artifacts/os_events.jsonl" <<'JSONL'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","source":"journald","kind":"session.login","actor":{"uid":1000},"object":{"session_id":"agentos:tty1"},"action":"login","decision":{"state":"observed"},"correlation":{"session_id":"agentos:tty1","session_origin":"live_appliance_boot","next_managed_entry":"ai_shell"},"raw_ref":{"collector":"journald"}}
JSONL

cat > "$POLICY_DIR/profile-lifecycle.json" <<'JSON'
{"bridge_state":"reloaded","reload_state":"applied","disable_state":"inactive","operator_state":"ready"}
JSON
cat > "$POLICY_DIR/enforced-pilot.json" <<'JSON'
{"enabled":true,"policy_target":"destructive_action_approval"}
JSON
cat > "$POLICY_DIR/shadow-report.json" <<'JSON'
{"summary":{"policies_total":1},"policy_targets":[{"target":"fs_workspace_boundary","readiness_score":85,"false_positive_count":0,"false_deny_count":0,"lifecycle_state":"shadow","recommended_next_state":"guarded_enforce"}]}
JSON
cat > "$POLICY_DIR/bridge-state.json" <<'JSON'
{"effective_state":"enabled"}
JSON
cat > "$HISTORY_DIR/window-1.json" <<'JSON'
{"schema_version":"agentos-validation-window.v1","label":"window-1","generated_at_utc":"2026-04-13T00:00:00Z","summary":{"runtime_ok":true,"session_phase":"ai_shell","session_origin":"live_appliance_boot","install_validation_ok":true,"audit_ok":true,"diagnostics_ok":true,"diagnostics_readiness_status":"ready","approval_forensic_status":"requested","policy_targets":{"destructive_action_approval":"candidate"},"overall_state":"ready"}}
JSON
cat > "$WORKSPACE/feedback.json" <<'JSON'
{"evaluator_id":"smoke-evaluator","channel":"guided_eval","session_label":"smoke-session","recommendation":"hold","summary":"Need one more walkthrough.","findings":[{"title":"Recovery wording","severity":"medium","area":"recovery","detail":"Clarify one step.","artifact_ref":""}],"follow_up_requests":[]}
JSON

OUT_JSON="$TMP_DIR/limited-preview-readiness.json"
python3 scripts/kernel_limited_preview_readiness_scoreboard.py \
  --workspace "$WORKSPACE" \
  --report-dir "$REPORT_DIR" \
  --history-dir "$HISTORY_DIR" \
  --feedback-file "$WORKSPACE/feedback.json" \
  --session-id agentos:tty1 \
  --snapshot-label scoreboard \
  --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-limited-preview-readiness-scoreboard.v1":
    raise SystemExit("expected limited preview readiness scoreboard schema")
if payload["summary"].get("limited_preview_decision") != "extend_limited_preview":
    raise SystemExit("expected extend_limited_preview decision")
if payload["summary"].get("recovery_confidence") != "watch":
    raise SystemExit("expected recovery_confidence watch")
if not Path(payload["artifacts"]["limited_preview_readiness_scoreboard_json"]).exists():
    raise SystemExit("expected limited preview scoreboard artifact")
print("kernel limited preview readiness scoreboard smoke: PASS")
PY

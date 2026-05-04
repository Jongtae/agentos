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
name: feedback-triage-smoke
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

cat > "$HISTORY_DIR/window-1.json" <<'JSON'
{"schema_version":"agentos-validation-window.v1","label":"window-1","generated_at_utc":"2026-04-13T00:00:00Z","summary":{"runtime_ok":true,"session_phase":"ai_shell","session_origin":"live_appliance_boot","install_validation_ok":true,"audit_ok":true,"diagnostics_ok":true,"diagnostics_readiness_status":"ready","approval_forensic_status":"requested","policy_targets":{"destructive_action_approval":"candidate"},"overall_state":"ready"}}
JSON

cat > "$WORKSPACE/feedback.json" <<'JSON'
{"evaluator_id":"smoke-evaluator","channel":"guided_eval","session_label":"smoke-session","recommendation":"hold","summary":"Need one more walkthrough.","findings":[{"title":"Boot wording","severity":"high","area":"boot","detail":"Clarify the boot story.","artifact_ref":""},{"title":"Recovery wording","severity":"medium","area":"recovery","detail":"Clarify one step.","artifact_ref":""},{"title":"Packaging polish","severity":"low","area":"artifact_packaging","detail":"Can wait.","artifact_ref":""}],"follow_up_requests":[]}
JSON

OUT_JSON="$TMP_DIR/feedback-triage.json"
python3 scripts/kernel_feedback_triage.py \
  --workspace "$WORKSPACE" \
  --report-dir "$REPORT_DIR" \
  --history-dir "$HISTORY_DIR" \
  --feedback-file "$WORKSPACE/feedback.json" \
  --session-id agentos:tty1 \
  --snapshot-label triage \
  --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-feedback-triage.v1":
    raise SystemExit("expected feedback triage schema")
triage_root = Path(payload["triage_root"])
triage_dir = Path(payload["triage_dir"])
if triage_root.name != "feedback-triage":
    raise SystemExit("expected feedback-triage layout root")
for name in ["feedback-triage.md", "feedback-triage.json"]:
    if not (triage_dir / name).exists():
        raise SystemExit(f"missing feedback triage artifact: {name}")
if payload["summary"].get("blocker_count") != 1:
    raise SystemExit("expected exactly one blocker")
if payload["summary"].get("watch_count") != 1:
    raise SystemExit("expected exactly one watch")
if payload["summary"].get("polish_count") != 1:
    raise SystemExit("expected exactly one polish")
if payload["summary"].get("must_fix_before_broader_preview") != ["Boot wording", "Recovery wording"]:
    raise SystemExit("unexpected must-fix list")
if payload["summary"].get("can_wait_until_after_broader_preview") != ["Packaging polish"]:
    raise SystemExit("unexpected can-wait list")
print("kernel feedback triage smoke: PASS")
PY

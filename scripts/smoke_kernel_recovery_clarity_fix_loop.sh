#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)/.."
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
ARTIFACTS="$WORKSPACE/artifacts"
mkdir -p "$ARTIFACTS/kernel-policy" "$ARTIFACTS/validation-history"

cat >"$WORKSPACE/spec.yaml" <<'EOF'
name: smoke
EOF

: >"$ARTIFACTS/runtime_trace.jsonl"
cat >"$ARTIFACTS/os_events.jsonl" <<'EOF'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","source":"journald","kind":"session.login","actor":{"uid":1000},"object":{"session_id":"agentos:tty1"},"action":"login","decision":{"state":"observed"},"correlation":{"session_id":"agentos:tty1","session_origin":"live_appliance_boot","next_managed_entry":"ai_shell"},"raw_ref":{"collector":"journald"}}
EOF

cat >"$ARTIFACTS/kernel-policy/shadow-report.json" <<'EOF'
{"summary":{"policies_total":1},"policy_targets":[{"target":"fs_workspace_boundary","readiness_score":85,"false_positive_count":0,"false_deny_count":0,"lifecycle_state":"shadow","recommended_next_state":"guarded_enforce"}]}
EOF

cat >"$ARTIFACTS/kernel-policy/bridge-state.json" <<'EOF'
{"effective_state":"enabled"}
EOF

cat >"$ARTIFACTS/validation-history/window-1.json" <<'EOF'
{"schema_version":"agentos-validation-window.v1","label":"window-1","generated_at_utc":"2026-04-13T00:00:00Z","summary":{"runtime_ok":true,"session_phase":"ai_shell","session_origin":"live_appliance_boot","install_validation_ok":true,"audit_ok":true,"diagnostics_ok":true,"diagnostics_readiness_status":"ready","approval_forensic_status":"requested","policy_targets":{"destructive_action_approval":"candidate"},"overall_state":"ready"}}
EOF

cat >"$TMP_DIR/feedback.json" <<'EOF'
{"evaluator_id":"smoke-evaluator","channel":"guided_eval","session_label":"smoke-session","recommendation":"hold","summary":"Need one more walkthrough.","findings":[{"title":"Recovery wording","severity":"medium","area":"recovery","detail":"Clarify one step.","artifact_ref":"artifacts.evaluator_guide_markdown"},{"title":"Recovery runbook note","severity":"low","area":"operator_handoff","detail":"Operator note can wait.","artifact_ref":"docs/runbooks/agentos-operations-runbook.md"}]}
EOF

OUT_JSON="$TMP_DIR/recovery-fix-loop.json"
python3 "$ROOT_DIR/scripts/kernel_recovery_clarity_fix_loop.py" \
  --workspace "$WORKSPACE" \
  --report-dir "$ARTIFACTS/public-preview" \
  --feedback-file "$TMP_DIR/feedback.json" \
  --snapshot-label smoke \
  --output "$OUT_JSON" \
  --json

python3 "$ROOT_DIR/scripts/kernel_recovery_clarity_fix_loop.py" --validate "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json, pathlib, sys
payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
assert payload["schema_version"] == "agentos-recovery-clarity-fix-loop.v1"
assert payload["summary"]["overall_state"] == "watch"
assert payload["summary"]["runtime_copy_state"] == "watch"
assert payload["summary"]["operator_notes_state"] == "watch"
assert pathlib.Path(payload["artifacts"]["recovery_clarity_fix_loop_json"]).exists()
print("kernel recovery clarity fix loop smoke: PASS")
PY

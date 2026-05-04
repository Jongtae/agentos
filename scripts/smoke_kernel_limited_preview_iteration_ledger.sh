#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)/.."
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
ARTIFACTS="$WORKSPACE/artifacts"
mkdir -p "$ARTIFACTS/kernel-policy" "$ARTIFACTS/validation-history" "$ARTIFACTS/public-preview/limited-preview-iteration-ledger"

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
{"evaluator_id":"smoke-evaluator","channel":"guided_eval","session_label":"smoke-session","recommendation":"hold","summary":"Need one more walkthrough.","findings":[{"title":"Recovery wording","severity":"medium","area":"recovery","detail":"Clarify one step.","artifact_ref":"artifacts.evaluator_guide_markdown"}]}
EOF

cat >"$ARTIFACTS/public-preview/limited-preview-iteration-ledger/latest-limited-preview-iteration-ledger.json" <<'EOF'
{"snapshot_label":"previous","summary":{"current_watch_items":["Recovery wording","Legacy watch item","boot_messaging","install_later_messaging"]}}
EOF

OUT_JSON="$TMP_DIR/limited-preview-iteration-ledger.json"
python3 "$ROOT_DIR/scripts/kernel_limited_preview_iteration_ledger.py" \
  --workspace "$WORKSPACE" \
  --report-dir "$ARTIFACTS/public-preview" \
  --feedback-file "$TMP_DIR/feedback.json" \
  --snapshot-label smoke \
  --output "$OUT_JSON" \
  --json

python3 "$ROOT_DIR/scripts/kernel_limited_preview_iteration_ledger.py" --validate "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json, pathlib, sys
payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
assert payload["schema_version"] == "agentos-limited-preview-iteration-ledger.v1"
assert payload["summary"]["iteration_state"] == "improving"
assert "Legacy watch item" in payload["summary"]["fixed_since_last_iteration"]
assert "Recovery wording" in payload["summary"]["still_watching"]
assert "boot_messaging" in payload["summary"]["still_watching"]
assert "install_later_messaging" in payload["summary"]["still_watching"]
assert pathlib.Path(payload["artifacts"]["limited_preview_iteration_ledger_manifest_json"]).exists()
print("kernel limited preview iteration ledger smoke: PASS")
PY

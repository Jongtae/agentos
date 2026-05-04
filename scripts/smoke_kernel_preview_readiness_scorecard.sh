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
: >"$ARTIFACTS/os_events.jsonl"

cat >"$ARTIFACTS/kernel-policy/shadow-report.json" <<'EOF'
{"summary":{"policies_total":1},"policy_targets":[{"target":"fs_workspace_boundary","readiness_score":85,"false_positive_count":0,"false_deny_count":0,"lifecycle_state":"shadow","recommended_next_state":"guarded_enforce"}]}
EOF

cat >"$ARTIFACTS/kernel-policy/bridge-state.json" <<'EOF'
{"effective_state":"enabled"}
EOF

cat >"$TMP_DIR/feedback.json" <<'EOF'
{"evaluator_id":"smoke-evaluator","channel":"guided_eval","session_label":"smoke-session","recommendation":"hold","summary":"Need one more walkthrough.","findings":[{"title":"Recovery wording","severity":"medium","area":"recovery","detail":"Clarify one step."}]}
EOF

REPORT_JSON="$TMP_DIR/scorecard.json"
python3 "$ROOT_DIR/scripts/kernel_preview_readiness_scorecard.py" \
  --workspace "$WORKSPACE" \
  --report-dir "$ARTIFACTS/public-preview" \
  --feedback-file "$TMP_DIR/feedback.json" \
  --snapshot-label smoke \
  --output "$REPORT_JSON" \
  --json

python3 "$ROOT_DIR/scripts/kernel_preview_readiness_scorecard.py" --validate "$REPORT_JSON"

python3 - "$REPORT_JSON" <<'PY'
import json, pathlib, sys
payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["schema_version"] == "agentos-preview-readiness-scorecard.v1"
assert payload["summary"]["recommendation"] == "hold"
assert payload["summary"]["readiness_band"] in {"ready", "watch", "hold"}
assert payload["summary"]["recovery_clarity"] == "watch"
assert pathlib.Path(payload["artifacts"]["preview_readiness_scorecard_json"]).exists()
print("kernel preview readiness scorecard smoke: PASS")
PY

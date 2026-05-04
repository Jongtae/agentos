#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
ARTIFACTS="$WORKSPACE/artifacts"
mkdir -p "$ARTIFACTS/kernel-policy" "$ARTIFACTS/validation-history"
printf 'name: smoke\n' > "$WORKSPACE/spec.yaml"
: > "$ARTIFACTS/runtime_trace.jsonl"
cat > "$ARTIFACTS/os_events.jsonl" <<'EOF'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","source":"journald","kind":"session.login","actor":{"uid":1000},"object":{"session_id":"agentos:tty1"},"action":"login","decision":{"state":"observed"},"correlation":{"session_id":"agentos:tty1","session_origin":"live_appliance_boot","next_managed_entry":"ai_shell"},"raw_ref":{"collector":"journald"}}
EOF
cat > "$ARTIFACTS/kernel-policy/shadow-report.json" <<'EOF'
{"summary":{"policies_total":1},"policy_targets":[{"target":"fs_workspace_boundary","readiness_score":85,"false_positive_count":0,"false_deny_count":0,"lifecycle_state":"shadow","recommended_next_state":"guarded_enforce"}]}
EOF
cat > "$ARTIFACTS/kernel-policy/bridge-state.json" <<'EOF'
{"effective_state":"enabled"}
EOF
cat > "$ARTIFACTS/validation-history/window-1.json" <<'EOF'
{"schema_version":"agentos-validation-window.v1","label":"window-1","generated_at_utc":"2026-04-13T00:00:00Z","summary":{"runtime_ok":true,"session_phase":"ai_shell","session_origin":"live_appliance_boot","install_validation_ok":true,"audit_ok":true,"diagnostics_ok":true,"diagnostics_readiness_status":"ready","approval_forensic_status":"requested","policy_targets":{"destructive_action_approval":"candidate"},"overall_state":"ready"}}
EOF

OUT_JSON="$TMP_DIR/recovery-watch-reevaluation.json"
python3 scripts/kernel_recovery_watch_reevaluation.py \
  --workspace "$WORKSPACE" \
  --report-dir "$ARTIFACTS/public-preview" \
  --snapshot-label smoke \
  --output "$OUT_JSON" \
  --json >/dev/null

python3 scripts/kernel_recovery_watch_reevaluation.py --validate "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json, pathlib, sys
payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
assert payload["schema_version"] == "agentos-recovery-watch-reevaluation.v1"
assert payload["summary"]["recovery_state"] in {"watch", "ready"}
assert payload["recovery_copy_consistency_manifest"]["schema_version"] == "agentos-recovery-copy-consistency.v1"
assert payload["recovery_clarity_fix_loop_manifest"]["schema_version"] == "agentos-recovery-clarity-fix-loop.v1"
assert pathlib.Path(payload["artifacts"]["recovery_watch_reevaluation_manifest_json"]).exists()
print("kernel recovery watch re-evaluation smoke: PASS")
PY

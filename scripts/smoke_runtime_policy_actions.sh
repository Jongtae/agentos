#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE_DIR="$TMP_DIR/workspace"
ARTIFACTS_DIR="$WORKSPACE_DIR/artifacts"
mkdir -p "$ARTIFACTS_DIR"

TRACE_FILE="$ARTIFACTS_DIR/runtime_trace.jsonl"
cat > "$TRACE_FILE" <<'EOF'
{"timestamp_utc":"2026-01-01T00:00:00+00:00","event":"approval_requested","payload":{}}
{"timestamp_utc":"2026-01-01T00:00:01+00:00","event":"approval_decision","payload":{"approved":false}}
{"timestamp_utc":"2026-01-01T00:00:02+00:00","event":"step_blocked","payload":{}}
EOF

OUT_JSON="$(AGENTOS_SLO_MAX_DENIED_RATE=0.10 python3 scripts/runtime_policy_actions_report.py --workspace "$WORKSPACE_DIR" --trace-file "$TRACE_FILE")"
python3 - "$OUT_JSON" <<'PY'
import json
import sys

obj = json.loads(sys.argv[1])
for field in ["ok", "workspace", "overall_state", "action_count", "severity_counts", "actions"]:
    if field not in obj:
        raise SystemExit(f"missing root field: {field}")

if int(obj.get("action_count", 0)) < 1:
    raise SystemExit("expected at least one action")

for field in ["info", "warn", "critical"]:
    if field not in obj.get("severity_counts", {}):
        raise SystemExit(f"missing severity bucket: {field}")

for action in obj.get("actions", []):
    for field in ["id", "severity", "title", "reason", "recommended_command", "category", "auto_safe"]:
        if field not in action:
            raise SystemExit(f"missing action field: {field}")
PY

echo "runtime policy actions smoke: PASS"

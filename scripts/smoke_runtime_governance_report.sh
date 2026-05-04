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

OUT_JSON="$(python3 scripts/runtime_governance_report.py --workspace "$WORKSPACE_DIR" --trace-file "$TRACE_FILE")"
python3 - "$OUT_JSON" <<'PY'
import json
import sys

obj = json.loads(sys.argv[1])
required_root = ["ok", "workspace", "trace_file", "policy_pressure", "retention_health", "slo", "overall_state"]
for field in required_root:
    if field not in obj:
        raise SystemExit(f"missing root field: {field}")

for field in ["approval_requested", "approval_denied", "approval_blocked", "denied_rate", "approval_anomaly"]:
    if field not in obj.get("policy_pressure", {}):
        raise SystemExit(f"missing policy_pressure field: {field}")

slo = obj.get("slo", {})
for field in ["ok", "thresholds", "checks"]:
    if field not in slo:
        raise SystemExit(f"missing slo field: {field}")

checks = slo.get("checks", {})
for field in ["denied_rate_ok", "blocked_steps_ok", "retention_pending_ok"]:
    if field not in checks:
        raise SystemExit(f"missing slo.checks field: {field}")
PY

echo "runtime governance report smoke: PASS"

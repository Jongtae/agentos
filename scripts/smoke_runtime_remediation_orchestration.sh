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
printf "{}\n" > "$TRACE_FILE"

DRY_JSON="$(python3 scripts/runtime_remediation_orchestrate.py --workspace "$WORKSPACE_DIR" --trace-file "$TRACE_FILE" --dry-run)"
python3 - "$DRY_JSON" <<'PY'
import json
import sys

obj = json.loads(sys.argv[1])
for field in ["ok", "workspace", "mode", "plan", "execution", "rollback"]:
    if field not in obj:
        raise SystemExit(f"missing root field: {field}")
if obj.get("mode") != "dry-run":
    raise SystemExit("dry-run mode mismatch")
for field in ["action_total", "auto_safe_count", "manual_review_count", "critical_count", "sequence"]:
    if field not in obj.get("plan", {}):
        raise SystemExit(f"missing plan field: {field}")
PY

APPLY_JSON="$(python3 scripts/runtime_remediation_orchestrate.py --workspace "$WORKSPACE_DIR" --trace-file "$TRACE_FILE" --apply)"
python3 - "$APPLY_JSON" <<'PY'
import json
import sys

obj = json.loads(sys.argv[1])
if obj.get("mode") != "apply":
    raise SystemExit("apply mode mismatch")
exec_ = obj.get("execution", {})
if int(exec_.get("executed", 0)) < 1:
    raise SystemExit("expected executed >= 1 in apply mode")
rb = obj.get("rollback", {})
for field in ["required", "candidate_count", "candidates"]:
    if field not in rb:
        raise SystemExit(f"missing rollback field: {field}")
PY

echo "runtime remediation orchestration smoke: PASS"

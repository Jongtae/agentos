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

DRY_JSON="$(python3 scripts/runtime_policy_actions_execute.py --workspace "$WORKSPACE_DIR" --trace-file "$TRACE_FILE" --dry-run)"
python3 - "$DRY_JSON" <<'PY'
import json
import sys

obj = json.loads(sys.argv[1])
exec_ = obj.get("execution", {})
if bool(exec_.get("apply", True)):
    raise SystemExit("dry-run should set apply=false")
if int(exec_.get("would_execute", 0)) < 1:
    raise SystemExit("dry-run expected would_execute >= 1")
for field in ["action_total", "executed", "would_execute", "skipped", "errors", "results"]:
    if field not in exec_:
        raise SystemExit(f"missing execution field: {field}")
PY

APPLY_JSON="$(python3 scripts/runtime_policy_actions_execute.py --workspace "$WORKSPACE_DIR" --trace-file "$TRACE_FILE" --apply)"
python3 - "$APPLY_JSON" <<'PY'
import json
import sys

obj = json.loads(sys.argv[1])
exec_ = obj.get("execution", {})
if not bool(exec_.get("apply", False)):
    raise SystemExit("apply mode should set apply=true")
if int(exec_.get("executed", 0)) < 1:
    raise SystemExit("apply mode expected executed >= 1")
PY

echo "runtime policy execution smoke: PASS"

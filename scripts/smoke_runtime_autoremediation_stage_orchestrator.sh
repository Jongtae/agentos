#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# 1) dry-run orchestrator baseline
WS1="$TMP_DIR/workspace-dry"
mkdir -p "$WS1/artifacts"
printf "{}\n" > "$WS1/artifacts/runtime_trace.jsonl"

DRY_JSON="$(python3 scripts/runtime_autoremediation_stage_orchestrator.py --workspace "$WS1" --trace-file "$WS1/artifacts/runtime_trace.jsonl" --dry-run --runs 2 --now-epoch 1000 --run-interval-sec 300)"
python3 - "$DRY_JSON" <<'PY'
import json
import sys

obj = json.loads(sys.argv[1])
for field in ["stage", "stage_tuning", "auto_pause", "pause_state", "resume_gate", "run_id"]:
    if field not in obj:
        raise SystemExit(f"missing orchestrator field: {field}")
if int(obj.get("stage_exit_code", -1)) != 0:
    raise SystemExit("expected stage_exit_code=0 in dry-run baseline")
if bool((obj.get("auto_pause", {}) or {}).get("should_pause", False)):
    raise SystemExit("did not expect auto-pause in dry-run baseline")
PY

# 2) apply orchestrator blocked scenario => rc=4,5,6,7,8,9
WS2="$TMP_DIR/workspace-blocked"
mkdir -p "$WS2/artifacts"
printf "{}\n" > "$WS2/artifacts/runtime_trace.jsonl"
printf "old\n" > "$WS2/artifacts/runtime_trace.jsonl.1"
cat > "$WS2/artifacts/autoremediation_cadence_state.json" <<'JSON'
{"last_apply_epoch":1000,"apply_history_epochs":[1000]}
JSON

set +e
BLOCKED_JSON="$(AGENTOS_SLO_MAX_RETENTION_PENDING=0 AGENTOS_TRACE_KEEP_ARCHIVES=0 python3 scripts/runtime_autoremediation_stage_orchestrator.py --workspace "$WS2" --trace-file "$WS2/artifacts/runtime_trace.jsonl" --apply --runs 2 --now-epoch 1100 --run-interval-sec 300)"
BLOCKED_RC=$?
set -e

if [ "$BLOCKED_RC" -ne 4 ] && [ "$BLOCKED_RC" -ne 5 ] && [ "$BLOCKED_RC" -ne 6 ] && [ "$BLOCKED_RC" -ne 7 ] && [ "$BLOCKED_RC" -ne 8 ] && [ "$BLOCKED_RC" -ne 9 ]; then
  echo "expected blocked orchestrator rc=4, 5, 6, 7, 8, or 9, got $BLOCKED_RC"
  exit 1
fi
python3 - "$BLOCKED_JSON" <<'PY'
import json
import sys

obj = json.loads(sys.argv[1])
if int(obj.get("stage_exit_code", 0)) == 0:
    raise SystemExit("expected stage_exit_code != 0 for blocked orchestrator scenario")
for field in ["stage_tuning", "auto_pause", "pause_state", "resume_gate", "override_window", "override_budget", "forced_resume", "override_audit"]:
    if field not in obj:
        raise SystemExit(f"missing field in blocked orchestrator payload: {field}")
PY

echo "runtime autoremediation stage-orchestrator smoke: PASS"

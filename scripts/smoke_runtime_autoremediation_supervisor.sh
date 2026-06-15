#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# 1) dry-run baseline
WS1="$TMP_DIR/workspace-dry"
mkdir -p "$WS1/artifacts"
printf "{}\n" > "$WS1/artifacts/runtime_trace.jsonl"

DRY_JSON="$(python3 scripts/runtime_autoremediation_supervisor.py --workspace "$WS1" --trace-file "$WS1/artifacts/runtime_trace.jsonl" --dry-run --now-epoch 1000)"
python3 - "$DRY_JSON" <<'PY'
import json
import sys
obj = json.loads(sys.argv[1])
for field in ["cycle", "governance", "handoff", "run_id"]:
    if field not in obj:
        raise SystemExit(f"missing supervisor field: {field}")
if int(obj.get("cycle_exit_code", -1)) != 0:
    raise SystemExit("expected dry-run cycle_exit_code=0")
if "project_direction" not in (obj.get("cycle", {}) or {}):
    raise SystemExit("missing project_direction in supervisor cycle payload")
PY

# 2) apply blocked path => rc=3
WS2="$TMP_DIR/workspace-blocked"
mkdir -p "$WS2/artifacts"
printf "{}\n" > "$WS2/artifacts/runtime_trace.jsonl"
printf "old\n" > "$WS2/artifacts/runtime_trace.jsonl.1"
cat > "$WS2/artifacts/autoremediation_cadence_state.json" <<'JSON'
{"last_apply_epoch":1000,"apply_history_epochs":[1000]}
JSON

set +e
BLOCKED_JSON="$(AGENTOS_SLO_MAX_RETENTION_PENDING=0 AGENTOS_TRACE_KEEP_ARCHIVES=0 python3 scripts/runtime_autoremediation_supervisor.py --workspace "$WS2" --trace-file "$WS2/artifacts/runtime_trace.jsonl" --apply --now-epoch 1100)"
BLOCKED_RC=$?
set -e

if [ "$BLOCKED_RC" -ne 3 ]; then
  echo "expected blocked supervisor rc=3, got $BLOCKED_RC"
  exit 1
fi
python3 - "$BLOCKED_JSON" <<'PY'
import json
import sys
obj = json.loads(sys.argv[1])
if int(obj.get("cycle_exit_code", -1)) != 3:
    raise SystemExit("expected cycle_exit_code=3 when blocked")
if (obj.get("governance", {}) or {}).get("decision") != "hold":
    raise SystemExit("expected governance decision hold on blocked apply")
PY

# 3) project direction gate blocks apply when hardening risks repetition.
WS3="$TMP_DIR/workspace-direction-gate"
mkdir -p "$WS3/artifacts"
printf "{}\n" > "$WS3/artifacts/runtime_trace.jsonl"
printf "old\n" > "$WS3/artifacts/runtime_trace.jsonl.1"

set +e
GATED_JSON="$(AGENTOS_SLO_MAX_RETENTION_PENDING=0 AGENTOS_TRACE_KEEP_ARCHIVES=0 python3 scripts/runtime_autoremediation_supervisor.py --workspace "$WS3" --trace-file "$WS3/artifacts/runtime_trace.jsonl" --apply --now-epoch 2000 --gate-project-direction)"
GATED_RC=$?
set -e

if [ "$GATED_RC" -ne 3 ]; then
  echo "expected direction-gated supervisor rc=3, got $GATED_RC"
  exit 1
fi
python3 - "$GATED_JSON" <<'PY'
import json
import sys
obj = json.loads(sys.argv[1])
if int(obj.get("cycle_exit_code", -1)) != 3:
    raise SystemExit("expected cycle_exit_code=3 when project direction blocks apply")
if (obj.get("governance", {}) or {}).get("reason") not in {"project_direction_risk", "project_direction_rejected"}:
    raise SystemExit("expected project direction governance reason")
PY

echo "runtime autoremediation supervisor smoke: PASS"

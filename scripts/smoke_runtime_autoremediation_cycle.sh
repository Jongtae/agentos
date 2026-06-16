#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# 1) Dry-run baseline
WS1="$TMP_DIR/workspace-dry"
mkdir -p "$WS1/artifacts"
printf "{}\n" > "$WS1/artifacts/runtime_trace.jsonl"

DRY_JSON="$(python3 scripts/runtime_autoremediation_cycle.py --workspace "$WS1" --trace-file "$WS1/artifacts/runtime_trace.jsonl" --dry-run --now-epoch 1000)"
python3 - "$DRY_JSON" <<'PY'
import json
import sys
obj = json.loads(sys.argv[1])
for field in ["scheduler", "cadence", "project_direction", "orchestration", "escalation", "state_updates"]:
    if field not in obj:
        raise SystemExit(f"missing field: {field}")
if obj.get("execution_mode") != "dry-run":
    raise SystemExit("dry-run execution_mode mismatch")
if (obj.get("project_direction", {}) or {}).get("verdict") not in {"accept", "accept_with_risk"}:
    raise SystemExit("project direction verdict mismatch")
PY

# 2) Apply blocked by cadence interval => rc=3
WS2="$TMP_DIR/workspace-blocked"
mkdir -p "$WS2/artifacts"
printf "{}\n" > "$WS2/artifacts/runtime_trace.jsonl"
printf "old\n" > "$WS2/artifacts/runtime_trace.jsonl.1"
cat > "$WS2/artifacts/autoremediation_cadence_state.json" <<'JSON'
{"last_apply_epoch":1000,"apply_history_epochs":[1000]}
JSON

set +e
BLOCKED_JSON="$(AGENTOS_SLO_MAX_RETENTION_PENDING=0 AGENTOS_TRACE_KEEP_ARCHIVES=0 python3 scripts/runtime_autoremediation_cycle.py --workspace "$WS2" --trace-file "$WS2/artifacts/runtime_trace.jsonl" --apply --now-epoch 1100 --cadence-min-interval-sec 300)"
BLOCKED_RC=$?
set -e

if [ "$BLOCKED_RC" -ne 3 ]; then
  echo "expected blocked cycle rc=3, got $BLOCKED_RC"
  exit 1
fi
python3 - "$BLOCKED_JSON" <<'PY'
import json
import sys
obj = json.loads(sys.argv[1])
if obj.get("execution_mode") != "dry-run":
    raise SystemExit("blocked cycle should be dry-run")
if (obj.get("cadence", {}) or {}).get("reason") != "min_interval_not_elapsed":
    raise SystemExit("blocked cycle cadence reason mismatch")
PY

# 3) Direction gate blocks apply when the roadmap judge reports risk.
WS_GATE="$TMP_DIR/workspace-direction-gate"
mkdir -p "$WS_GATE/artifacts"
printf "{}\n" > "$WS_GATE/artifacts/runtime_trace.jsonl"
printf "old\n" > "$WS_GATE/artifacts/runtime_trace.jsonl.1"

set +e
GATED_JSON="$(AGENTOS_SLO_MAX_RETENTION_PENDING=0 AGENTOS_TRACE_KEEP_ARCHIVES=0 python3 scripts/runtime_autoremediation_cycle.py --workspace "$WS_GATE" --trace-file "$WS_GATE/artifacts/runtime_trace.jsonl" --apply --now-epoch 2000 --scheduler-cooldown-sec 10 --cadence-min-interval-sec 10 --gate-project-direction)"
GATED_RC=$?
set -e

if [ "$GATED_RC" -ne 3 ]; then
  echo "expected direction-gated cycle rc=3, got $GATED_RC"
  exit 1
fi
python3 - "$GATED_JSON" <<'PY'
import json
import sys
obj = json.loads(sys.argv[1])
if obj.get("execution_mode") != "dry-run":
    raise SystemExit("direction-gated cycle should remain dry-run")
if (obj.get("project_direction", {}) or {}).get("verdict") not in {"accept_with_risk", "reject"}:
    raise SystemExit("expected project direction to block apply in current repeated hardening state")
PY

# 4) Apply eligible path without direction gate => rc=0 + state writes
WS3="$TMP_DIR/workspace-eligible"
mkdir -p "$WS3/artifacts"
printf "{}\n" > "$WS3/artifacts/runtime_trace.jsonl"
printf "old\n" > "$WS3/artifacts/runtime_trace.jsonl.1"

set +e
ELIGIBLE_JSON="$(AGENTOS_SLO_MAX_RETENTION_PENDING=0 AGENTOS_TRACE_KEEP_ARCHIVES=0 python3 scripts/runtime_autoremediation_cycle.py --workspace "$WS3" --trace-file "$WS3/artifacts/runtime_trace.jsonl" --apply --now-epoch 2000 --scheduler-cooldown-sec 10 --cadence-min-interval-sec 10)"
ELIGIBLE_RC=$?
set -e

if [ "$ELIGIBLE_RC" -ne 0 ]; then
  echo "expected eligible cycle rc=0, got $ELIGIBLE_RC"
  exit 1
fi
python3 - "$ELIGIBLE_JSON" <<'PY'
import json
import sys
obj = json.loads(sys.argv[1])
if obj.get("execution_mode") != "apply":
    raise SystemExit("eligible cycle should execute apply mode")
updates = obj.get("state_updates", {}) or {}
for key in ["scheduler", "cadence", "escalation"]:
    if not bool((updates.get(key, {}) or {}).get("written", False)):
        raise SystemExit(f"expected state update write for {key}")
PY

echo "runtime autoremediation cycle smoke: PASS"

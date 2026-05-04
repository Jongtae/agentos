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

DRY_JSON="$(python3 scripts/runtime_autoremediation_step.py --workspace "$WS1" --trace-file "$WS1/artifacts/runtime_trace.jsonl" --dry-run --now-epoch 1000)"
python3 - "$DRY_JSON" <<'PY'
import json
import sys
obj = json.loads(sys.argv[1])
for field in ["ok", "workspace", "requested_mode", "execution_mode", "scheduler", "orchestration", "state_update"]:
    if field not in obj:
        raise SystemExit(f"missing root field: {field}")
if obj.get("requested_mode") != "dry-run":
    raise SystemExit("dry-run requested_mode mismatch")
if obj.get("execution_mode") != "dry-run":
    raise SystemExit("dry-run execution_mode mismatch")
PY

# 2) Apply request blocked by cooldown/eligibility => rc=3
WS2="$TMP_DIR/workspace-blocked"
mkdir -p "$WS2/artifacts"
printf "{}\n" > "$WS2/artifacts/runtime_trace.jsonl"
cat > "$WS2/artifacts/autoremediation_scheduler_state.json" <<'JSON'
{"last_apply_epoch":1000,"consecutive_applies":1}
JSON

set +e
BLOCKED_JSON="$(python3 scripts/runtime_autoremediation_step.py --workspace "$WS2" --trace-file "$WS2/artifacts/runtime_trace.jsonl" --apply --now-epoch 1100 --cooldown-sec 300)"
BLOCKED_RC=$?
set -e

if [ "$BLOCKED_RC" -ne 3 ]; then
  echo "expected blocked apply rc=3, got $BLOCKED_RC"
  exit 1
fi

python3 - "$BLOCKED_JSON" <<'PY'
import json
import sys
obj = json.loads(sys.argv[1])
if obj.get("execution_mode") != "dry-run":
    raise SystemExit("blocked apply should downgrade to dry-run execution_mode")
if bool((obj.get("state_update", {}) or {}).get("written", True)):
    raise SystemExit("blocked apply should not write state")
PY

# 3) Apply eligible path => rc=0 + state write
WS3="$TMP_DIR/workspace-eligible"
mkdir -p "$WS3/artifacts"
printf "{}\n" > "$WS3/artifacts/runtime_trace.jsonl"
printf "old\n" > "$WS3/artifacts/runtime_trace.jsonl.1"

set +e
ELIGIBLE_JSON="$(AGENTOS_SLO_MAX_RETENTION_PENDING=0 AGENTOS_TRACE_KEEP_ARCHIVES=0 python3 scripts/runtime_autoremediation_step.py --workspace "$WS3" --trace-file "$WS3/artifacts/runtime_trace.jsonl" --apply --now-epoch 2000 --cooldown-sec 10)"
ELIGIBLE_RC=$?
set -e

if [ "$ELIGIBLE_RC" -ne 0 ]; then
  echo "expected eligible apply rc=0, got $ELIGIBLE_RC"
  exit 1
fi

python3 - "$ELIGIBLE_JSON" <<'PY'
import json
import sys
obj = json.loads(sys.argv[1])
if obj.get("execution_mode") != "apply":
    raise SystemExit("eligible apply should run in apply mode")
if not bool((obj.get("state_update", {}) or {}).get("written", False)):
    raise SystemExit("eligible apply should write state")
PY

echo "runtime autoremediation smoke: PASS"

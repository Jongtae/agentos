#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# 1) dry-run campaign baseline
WS1="$TMP_DIR/workspace-dry"
mkdir -p "$WS1/artifacts"
printf "{}\n" > "$WS1/artifacts/runtime_trace.jsonl"

DRY_JSON="$(python3 scripts/runtime_autoremediation_campaign.py --workspace "$WS1" --trace-file "$WS1/artifacts/runtime_trace.jsonl" --dry-run --runs 2 --now-epoch 1000 --run-interval-sec 300)"
python3 - "$DRY_JSON" <<'PY'
import json
import sys
obj = json.loads(sys.argv[1])
for field in ["run_results", "campaign_governance", "campaign_review", "run_id"]:
    if field not in obj:
        raise SystemExit(f"missing campaign field: {field}")
if int(obj.get("runs_requested", 0)) != 2:
    raise SystemExit("expected runs_requested=2")
if len(obj.get("run_results", [])) != 2:
    raise SystemExit("expected exactly 2 run results")
PY

# 2) apply campaign with a blocked first run => rc=4
WS2="$TMP_DIR/workspace-blocked"
mkdir -p "$WS2/artifacts"
printf "{}\n" > "$WS2/artifacts/runtime_trace.jsonl"
printf "old\n" > "$WS2/artifacts/runtime_trace.jsonl.1"
cat > "$WS2/artifacts/autoremediation_cadence_state.json" <<'JSON'
{"last_apply_epoch":1000,"apply_history_epochs":[1000]}
JSON

set +e
BLOCKED_JSON="$(AGENTOS_SLO_MAX_RETENTION_PENDING=0 AGENTOS_TRACE_KEEP_ARCHIVES=0 python3 scripts/runtime_autoremediation_campaign.py --workspace "$WS2" --trace-file "$WS2/artifacts/runtime_trace.jsonl" --apply --runs 2 --now-epoch 1100 --run-interval-sec 300)"
BLOCKED_RC=$?
set -e

if [ "$BLOCKED_RC" -ne 4 ]; then
  echo "expected blocked campaign rc=4, got $BLOCKED_RC"
  exit 1
fi
python3 - "$BLOCKED_JSON" <<'PY'
import json
import sys
obj = json.loads(sys.argv[1])
run_results = obj.get("run_results", [])
if len(run_results) != 2:
    raise SystemExit("expected 2 run_results in blocked scenario")
if sum(1 for item in run_results if int(item.get("exit_code", 0)) != 0) < 1:
    raise SystemExit("expected at least one failed run in blocked scenario")
PY

echo "runtime autoremediation campaign smoke: PASS"

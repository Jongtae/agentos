#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WS="$TMP_DIR/workspace-override-budget"
mkdir -p "$WS/artifacts"
printf "{}\n" > "$WS/artifacts/runtime_trace.jsonl"
cat > "$WS/artifacts/autoremediation_pause_state.json" <<'JSON'
{
  "is_paused": true,
  "paused_since_epoch": 800,
  "cooldown_until_epoch": 1600,
  "pause_reason": "rollback_budget_exhausted",
  "pause_severity": "critical",
  "resume_attempt_count": 2,
  "last_resume_attempt_epoch": 900
}
JSON
cat > "$WS/artifacts/autoremediation_override_budget_state.json" <<'JSON'
{
  "override_applied_epochs": [700, 800, 900]
}
JSON

set +e
OUT_JSON="$(python3 scripts/runtime_autoremediation_stage_orchestrator.py --workspace "$WS" --trace-file "$WS/artifacts/runtime_trace.jsonl" --dry-run --resume-requested --operator-override-requested --now-epoch 1000 --run-interval-sec 300)"
OUT_RC=$?
set -e

if [ "$OUT_RC" -ne 9 ]; then
  echo "expected override-budget block rc=9, got $OUT_RC"
  exit 1
fi

python3 - "$OUT_JSON" <<'PY'
import json
import sys

obj = json.loads(sys.argv[1])
for field in ["override_window", "override_budget", "forced_resume", "override_audit"]:
    if field not in obj:
        raise SystemExit(f"missing override-budget field: {field}")

decision = (obj.get("forced_resume", {}) or {}).get("decision", {})
if str(decision.get("status", "")) != "block":
    raise SystemExit("expected forced_resume.decision.status=block")
if str(decision.get("reason", "")) != "override_budget_exhausted":
    raise SystemExit("expected forced_resume reason=override_budget_exhausted")

budget = obj.get("override_budget", {}) or {}
if str(budget.get("status", "")) != "block":
    raise SystemExit("expected override_budget.status=block")
PY

echo "runtime autoremediation override-budget smoke: PASS"

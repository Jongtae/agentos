#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WS="$TMP_DIR/workspace-operator-override"
mkdir -p "$WS/artifacts"
printf "{}\n" > "$WS/artifacts/runtime_trace.jsonl"
cat > "$WS/artifacts/autoremediation_pause_state.json" <<'JSON'
{
  "is_paused": true,
  "paused_since_epoch": 800,
  "cooldown_until_epoch": 1600,
  "pause_reason": "rollback_budget_exhausted",
  "pause_severity": "critical",
  "resume_attempt_count": 5,
  "last_resume_attempt_epoch": 900
}
JSON

set +e
OUT_JSON="$(python3 scripts/runtime_autoremediation_stage_orchestrator.py --workspace "$WS" --trace-file "$WS/artifacts/runtime_trace.jsonl" --dry-run --resume-requested --operator-override-requested --override-duration-sec 900 --now-epoch 1000 --run-interval-sec 300)"
OUT_RC=$?
set -e

if [ "$OUT_RC" -ne 0 ]; then
  echo "expected operator-override forced resume rc=0, got $OUT_RC"
  exit 1
fi

python3 - "$OUT_JSON" <<'PY'
import json
import sys

obj = json.loads(sys.argv[1])
for field in ["override_window", "override_budget", "forced_resume", "override_audit", "pause_state", "resume_gate"]:
    if field not in obj:
        raise SystemExit(f"missing operator-override field: {field}")

decision = (obj.get("forced_resume", {}) or {}).get("decision", {})
if str(decision.get("status", "")) != "allow":
    raise SystemExit("expected forced_resume.decision.status=allow")
if str(decision.get("reason", "")) != "operator_override_active":
    raise SystemExit("expected forced_resume reason=operator_override_active")
if not bool(decision.get("forced", False)):
    raise SystemExit("expected forced_resume.decision.forced=true")
PY

echo "runtime autoremediation operator-override smoke: PASS"

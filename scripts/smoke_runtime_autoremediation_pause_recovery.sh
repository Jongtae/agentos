#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WS="$TMP_DIR/workspace-pause-recovery"
mkdir -p "$WS/artifacts"
printf "{}\n" > "$WS/artifacts/runtime_trace.jsonl"
cat > "$WS/artifacts/autoremediation_pause_state.json" <<'JSON'
{
  "is_paused": true,
  "paused_since_epoch": 800,
  "cooldown_until_epoch": 900,
  "pause_reason": "rollback_budget_exhausted",
  "pause_severity": "critical",
  "resume_attempt_count": 5,
  "last_resume_attempt_epoch": 950
}
JSON

set +e
OUT_JSON="$(python3 scripts/runtime_autoremediation_stage_orchestrator.py --workspace "$WS" --trace-file "$WS/artifacts/runtime_trace.jsonl" --dry-run --resume-requested --now-epoch 1000 --run-interval-sec 300)"
OUT_RC=$?
set -e

if [ "$OUT_RC" -ne 8 ]; then
  echo "expected pause-recovery forced-resume block rc=8, got $OUT_RC"
  exit 1
fi

python3 - "$OUT_JSON" <<'PY'
import json
import sys

obj = json.loads(sys.argv[1])
for field in ["pause_state", "resume_gate", "override_window", "forced_resume", "stage_tuning", "auto_pause"]:
    if field not in obj:
        raise SystemExit(f"missing pause-recovery field: {field}")

decision = (obj.get("resume_gate", {}) or {}).get("decision", {})
if str(decision.get("status", "")) != "block":
    raise SystemExit("expected resume_gate.decision.status=block")
if str(decision.get("reason", "")) != "max_resume_attempts_reached":
    raise SystemExit("expected resume_gate block reason=max_resume_attempts_reached")
forced = (obj.get("forced_resume", {}) or {}).get("decision", {})
if str(forced.get("status", "")) != "block":
    raise SystemExit("expected forced_resume.decision.status=block")
PY

echo "runtime autoremediation pause-recovery smoke: PASS"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT_DIR/src"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

python3 "$ROOT_DIR/src/broker_emit.py" \
  --workspace "$WORKSPACE" \
  --kind operator_control \
  --action policy_enforce_enable \
  --state override \
  --reason "operator override active" \
  --component smoke >/dev/null

RAW="$(scripts/agentos-kernelctl broker-status --workspace "$WORKSPACE" --json)"
python3 - <<'PY' "$RAW"
import json
import sys

payload = json.loads(sys.argv[1])
if not payload.get("ok", False):
    raise SystemExit("expected broker status ok=true")
activity = payload.get("activity", {}) or {}
counts = activity.get("counts", {}) or {}
if int(counts.get("broker.exec_request", 0)) < 1:
    raise SystemExit("expected broker.exec_request count >= 1")
request_kind_counts = activity.get("request_kind_counts", {}) or {}
decision_state_counts = activity.get("decision_state_counts", {}) or {}
if int(request_kind_counts.get("operator_control", 0)) < 1:
    raise SystemExit("expected operator_control request_kind summary")
if int(decision_state_counts.get("override", 0)) < 1:
    raise SystemExit("expected override decision summary")
if "policy_enforce_enable" not in (activity.get("recent_actions", []) or []):
    raise SystemExit("expected recent_actions to include policy_enforce_enable")
if not (activity.get("high_risk_recent", []) or []):
    raise SystemExit("expected high_risk_recent summary")
print("broker status smoke ok")
PY

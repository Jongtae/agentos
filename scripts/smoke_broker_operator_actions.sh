#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

python3 "$ROOT_DIR/scripts/kernel_policy_bridge.py" \
  --workspace "$WORKSPACE" \
  --output-dir "$WORKSPACE/artifacts/kernel-policy" \
  --reload \
  --parser-cmd true \
  --json >/dev/null

python3 "$ROOT_DIR/scripts/kernel_policy_enforced_pilot.py" \
  --workspace "$WORKSPACE" \
  --enable \
  --confirm \
  --json >/dev/null

ROOT_DIR="$ROOT_DIR" python3 - <<'PY' "$WORKSPACE"
import sys
import os
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(Path(os.environ["ROOT_DIR"]) / "src"))
from kernel.event_fabric.report import query_events

decision_report = query_events(root, kind="broker.exec_decision", limit=10)
request_report = query_events(root, kind="broker.exec_request", limit=10)
decisions = decision_report.get("events", []) or []
requests = request_report.get("events", []) or []
request_kinds = {str((item.get("decision") or {}).get("request_kind", "")) for item in decisions}
actions = {str(item.get("action", "")) for item in requests}
if "operator_control" not in request_kinds:
    raise SystemExit("expected operator_control broker decisions")
if "policy_bridge_reload" not in actions or "policy_enforce_enable" not in actions:
    raise SystemExit(f"expected brokered operator actions, got {sorted(actions)}")
print("broker operator actions smoke: PASS")
PY

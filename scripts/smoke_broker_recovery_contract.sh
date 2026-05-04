#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT_DIR/src"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE_BYPASS="$TMP_DIR/workspace-bypass"
HOME_BYPASS="$TMP_DIR/home-bypass"
mkdir -p "$WORKSPACE_BYPASS" "$HOME_BYPASS"

HOME="$HOME_BYPASS" \
AGENTOS_REPO_ROOT="$ROOT_DIR" \
AGENTOS_BROKER_BYPASS=1 \
AGENTOS_FIRSTRUN_CHOICE=3 \
DEFAULT_WORKSPACE="$WORKSPACE_BYPASS" \
scripts/agentos-firstrun --workspace "$WORKSPACE_BYPASS" >/dev/null

if [ -f "$WORKSPACE_BYPASS/artifacts/os_events.jsonl" ]; then
  echo "expected no broker events when AGENTOS_BROKER_BYPASS=1" >&2
  exit 1
fi

WORKSPACE_OVERRIDE="$TMP_DIR/workspace-override"
mkdir -p "$WORKSPACE_OVERRIDE"

python3 "$ROOT_DIR/src/broker_emit.py" \
  --workspace "$WORKSPACE_OVERRIDE" \
  --kind override \
  --action emergency_recovery \
  --state override \
  --reason "operator forced recovery bypass" \
  --component agentos-profile \
  --path tty1_autostart \
  --object-field "status=override_active" >/dev/null

python3 - <<'PY' "$WORKSPACE_OVERRIDE"
import sys
from pathlib import Path
from kernel.event_fabric.report import query_events

workspace = Path(sys.argv[1])
report = query_events(workspace, kind="broker.exec_decision", limit=5)
if report["returned_events"] != 1:
    raise SystemExit("expected one override decision event")
event = report["events"][0]
if event["decision"]["request_kind"] != "override":
    raise SystemExit("expected override request kind")
if event["decision"]["state"] != "override":
    raise SystemExit("expected override decision state")
print("broker recovery contract smoke ok")
PY

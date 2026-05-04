#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT_DIR/src"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
HOME_DIR="$TMP_DIR/home"
mkdir -p "$WORKSPACE" "$HOME_DIR"

python3 "$ROOT_DIR/src/broker_emit.py" \
  --workspace "$WORKSPACE" \
  --kind session_entry \
  --action tty1_autostart \
  --state allowed \
  --reason "managed AgentOS shell session entry on tty1" \
  --component agentos-profile \
  --path tty1_autostart \
  --object-field "user_name=tester" \
  --object-field "tty=/dev/tty1" \
  --correlation-field "session_id=tester:tty1" >/dev/null

HOME="$HOME_DIR" \
AGENTOS_REPO_ROOT="$ROOT_DIR" \
AGENTOS_SESSION_ID="tester:tty1" \
AGENTOS_FIRSTRUN_CHOICE="3" \
DEFAULT_WORKSPACE="$WORKSPACE" \
scripts/agentos-firstrun --workspace "$WORKSPACE" >/dev/null

python3 - <<'PY' "$WORKSPACE"
import sys
from pathlib import Path
from kernel.event_fabric.report import query_events

workspace = Path(sys.argv[1])
session_decisions = query_events(workspace, kind="broker.exec_decision", limit=20)
firstrun_decisions = [
    event for event in session_decisions["events"]
    if (event.get("actor") or {}).get("component") == "agentos-firstrun"
]
if not session_decisions["event_file_exists"]:
    raise SystemExit("expected os_events.jsonl to exist")
if session_decisions["returned_events"] < 2:
    raise SystemExit("expected at least two broker exec decisions")
if not firstrun_decisions:
    raise SystemExit("expected firstrun broker decision event")
print("broker session entry smoke ok")
PY

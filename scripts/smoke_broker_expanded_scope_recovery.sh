#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE_BYPASS="$TMP_DIR/workspace-bypass"
mkdir -p "$WORKSPACE_BYPASS"

AGENTOS_BROKER_BYPASS=1 \
python3 "$ROOT_DIR/scripts/kernel_policy_bridge.py" \
  --workspace "$WORKSPACE_BYPASS" \
  --output-dir "$WORKSPACE_BYPASS/artifacts/kernel-policy" \
  --reload \
  --parser-cmd true \
  --json >/dev/null

if [ -f "$WORKSPACE_BYPASS/artifacts/os_events.jsonl" ]; then
  echo "expected no broker events when AGENTOS_BROKER_BYPASS=1 for operator control" >&2
  exit 1
fi

WORKSPACE_OVERRIDE="$TMP_DIR/workspace-override"
INSTALL_ROOT="$TMP_DIR/root-override"
mkdir -p "$WORKSPACE_OVERRIDE" "$INSTALL_ROOT"

DEFAULT_WORKSPACE="$WORKSPACE_OVERRIDE" \
AGENTOS_INSTALL_ROOT="$INSTALL_ROOT" \
AGENTOS_ENABLE_SYSTEMD=0 \
AGENTOS_BROKER_OVERRIDE=1 \
"$ROOT_DIR/scripts/install_kernel_boot_integration.sh" >/dev/null

ROOT_DIR="$ROOT_DIR" python3 - <<'PY' "$WORKSPACE_OVERRIDE"
import os
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
sys.path.insert(0, str(Path(os.environ["ROOT_DIR"]) / "src"))
from kernel.event_fabric.report import query_events

report = query_events(workspace, kind="broker.exec_decision", limit=10)
events = report.get("events", []) or []
install_events = [item for item in events if str((item.get("decision") or {}).get("request_kind", "")) == "install_control"]
if not install_events:
    raise SystemExit("expected install_control override events")
states = {str((item.get("decision") or {}).get("state", "")) for item in install_events}
if "override" not in states:
    raise SystemExit(f"expected override state for expanded install path, got {sorted(states)}")
print("broker expanded scope recovery smoke: PASS")
PY

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
INSTALL_ROOT="$TMP_DIR/root"
mkdir -p "$WORKSPACE" "$INSTALL_ROOT"

DEFAULT_WORKSPACE="$WORKSPACE" \
AGENTOS_INSTALL_ROOT="$INSTALL_ROOT" \
AGENTOS_ENABLE_SYSTEMD=0 \
"$ROOT_DIR/scripts/install_kernel_boot_integration.sh" >/dev/null

DEFAULT_WORKSPACE="$WORKSPACE" \
AGENTOS_INSTALL_ROOT="$INSTALL_ROOT" \
AGENTOS_DISABLE_SYSTEMD=0 \
"$ROOT_DIR/scripts/uninstall_kernel_boot_integration.sh" >/dev/null

ROOT_DIR="$ROOT_DIR" python3 - <<'PY' "$WORKSPACE"
import sys
import os
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(Path(os.environ["ROOT_DIR"]) / "src"))
from kernel.event_fabric.report import query_events

decision_report = query_events(root, kind="broker.exec_decision", limit=20)
request_report = query_events(root, kind="broker.exec_request", limit=20)
decisions = decision_report.get("events", []) or []
requests = request_report.get("events", []) or []
install_request_kinds = {
    str((item.get("decision") or {}).get("request_kind", ""))
    for item in decisions
}
if "install_control" not in install_request_kinds:
    raise SystemExit("expected install_control broker decisions")
actions = {str(item.get("action", "")) for item in requests}
expected = {"install_kernel_boot_integration", "install_kernel_boot_systemd_apply", "uninstall_kernel_boot_integration"}
missing = sorted(expected - actions)
if missing:
    raise SystemExit(f"missing install-control broker actions: {missing}")
print("broker install paths smoke: PASS")
PY

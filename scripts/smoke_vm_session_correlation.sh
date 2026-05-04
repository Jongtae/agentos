#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
INSTALL_ROOT="$TMP_DIR/install-root"
FLOW_OUT="$TMP_DIR/vm-flow.out"
SESSIONS_JSON="$TMP_DIR/sessions.json"
AUDIT_JSON="$TMP_DIR/audit.json"

mkdir -p "$WORKSPACE" "$INSTALL_ROOT"

scripts/vm_demo_flow.sh --workspace "$WORKSPACE" --dry-run > "$FLOW_OUT"
rg -q "AgentOS Setup appear on tty1" "$FLOW_OUT"
rg -q "ai>" "$FLOW_OUT"

AGENTOS_INSTALL_ROOT="$INSTALL_ROOT" \
AGENTOS_ENABLE_SYSTEMD=0 \
AGENTOS_BROKER_BYPASS=1 \
bash "$ROOT_DIR/scripts/install_kernel_boot_integration.sh" >/dev/null

WORKSPACE="$WORKSPACE" PYTHONPATH="$ROOT_DIR/src" python3 - <<'PY'
import os
from pathlib import Path

from kernel.event_fabric.collectors import append_events_jsonl
from kernel.event_fabric.schema import build_os_event_record

workspace = Path(os.environ["WORKSPACE"])
events = [
    build_os_event_record(
        source="journald",
        kind="session.login",
        action="login",
        object={"session_id": "8", "user_name": "agentos"},
        correlation={"session_id": "8", "boot_id": "boot-vm-1", "session_origin": "local_managed_tty1"},
        timestamp_utc="2026-04-14T00:00:01+00:00",
    ),
    build_os_event_record(
        source="broker",
        kind="broker.exec_request",
        action="request",
        object={"component": "agentos-firstrun", "path": "firstrun"},
        decision={"state": "allowed"},
        correlation={
            "session_id": "8",
            "boot_id": "boot-vm-1",
            "request_id": "req-vm-boot",
            "next_managed_entry": "ai_shell",
        },
        timestamp_utc="2026-04-14T00:00:02+00:00",
    ),
    build_os_event_record(
        source="journald",
        kind="systemd.unit_state",
        action="state_change",
        object={"unit": "agentos-kernel.service", "state": "started", "state_family": "active", "session_id": "8"},
        correlation={"session_id": "8", "boot_id": "boot-vm-1", "next_managed_entry": "ai_shell"},
        timestamp_utc="2026-04-14T00:00:03+00:00",
    ),
]
append_events_jsonl(workspace / "artifacts" / "os_events.jsonl", events)
PY

scripts/agentos-kernelctl sessions --workspace "$WORKSPACE" --session-id 8 --json > "$SESSIONS_JSON"
python3 scripts/kernel_boot_audit.py --install-root "$INSTALL_ROOT" --workspace "$WORKSPACE" --json > "$AUDIT_JSON"

python3 - "$SESSIONS_JSON" "$AUDIT_JSON" <<'PY'
import json
import sys
from pathlib import Path

sessions = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
audit = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

ownership = sessions.get("ownership_summary", {})
evidence = sessions.get("correlation_evidence", {})
if ownership.get("session_phase") != "ai_shell":
    raise SystemExit("expected vm session ownership phase ai_shell")
if ownership.get("session_origin") != "local_managed_tty1":
    raise SystemExit("expected vm session ownership origin local_managed_tty1")
if evidence.get("request_ids") != ["req-vm-boot"]:
    raise SystemExit("expected vm request_id evidence")

fabric = (audit.get("event_fabric") or {})
session_correlation = fabric.get("session_correlation") or {}
if session_correlation.get("request_ids") != ["req-vm-boot"]:
    raise SystemExit("expected audit session correlation request id")
if (fabric.get("session_ownership") or {}).get("session_phase") != "ai_shell":
    raise SystemExit("expected audit session ownership phase ai_shell")
PY

echo "vm session correlation smoke: PASS"

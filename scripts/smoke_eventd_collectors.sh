#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

WORKSPACE="$WORKSPACE" PYTHONPATH="$ROOT_DIR/src" python3 - <<'PY'
import os
from pathlib import Path

from kernel.event_fabric.collectors import (
    ProcessSnapshot,
    append_events_jsonl,
    dbus_message_event,
    file_access_candidate_event,
    journald_systemd_logind_event,
    network_connect_candidate_event,
    process_exec_exit_events,
)

workspace = Path(os.environ["WORKSPACE"])
events = []
events.extend(
    process_exec_exit_events(
        {10: ProcessSnapshot(pid=10, ppid=1, comm="old", exe="/usr/bin/old")},
        {11: ProcessSnapshot(pid=11, ppid=1, comm="bash", exe="/bin/bash")},
        correlation={"run_id": "smoke-e49"},
    )
)
events.append(
    file_access_candidate_event(
        candidate_path="../outside.txt",
        action="read",
        workspace_root=str(workspace),
        actor={"pid": 11, "comm": "bash"},
        correlation={"run_id": "smoke-e49"},
    )
)
events.append(
    network_connect_candidate_event(
        host="blocked.example",
        port=443,
        allowlist=["openai.com"],
        actor={"pid": 11, "comm": "curl"},
        correlation={"run_id": "smoke-e49"},
    )
)
events.append(
    journald_systemd_logind_event(
        {
            "__CURSOR": "cursor:smoke:systemd",
            "_PID": "1",
            "_UID": "0",
            "_COMM": "systemd",
            "_EXE": "/usr/lib/systemd/systemd",
            "_SYSTEMD_UNIT": "agentos-eventd.service",
            "MESSAGE": "Started agentos-eventd.service - AgentOS Event Fabric.",
        },
        correlation={"run_id": "smoke-e49"},
    )
)
events.append(
    journald_systemd_logind_event(
        {
            "__CURSOR": "cursor:smoke:systemd:reload",
            "_PID": "1",
            "_UID": "0",
            "_COMM": "systemd",
            "_EXE": "/usr/lib/systemd/systemd",
            "MESSAGE": "Reloading agentos-kernel.service - AgentOS Managed Shell Bootstrap Service.",
        },
        correlation={"run_id": "smoke-e49"},
    )
)
events.append(
    dbus_message_event(
        bus="system",
        path="/org/freedesktop/login1",
        interface="org.freedesktop.login1.Manager",
        member="SessionNew",
        message_type="signal",
        sender="org.freedesktop.login1",
        body={"session_id": "8"},
        correlation={"run_id": "smoke-e49"},
    )
)
events.append(
    dbus_message_event(
        bus="system",
        path="/org/freedesktop/systemd1/unit/agentos_2deventd_2eservice",
        interface="org.freedesktop.systemd1.Unit",
        member="PropertiesChanged",
        message_type="signal",
        sender="org.freedesktop.systemd1",
        body={"unit": "agentos-eventd.service"},
        correlation={"run_id": "smoke-e49"},
    )
)

normalized = [event for event in events if event is not None]
append_events_jsonl(workspace / "artifacts" / "os_events.jsonl", normalized)
PY

OUT_JSON="$TMP_DIR/events.json"
scripts/agentos-kernelctl events --workspace "$WORKSPACE" --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "process.exec",
    "process.exit",
    "file.outside_workspace_candidate",
    "network.connect_candidate",
    "systemd.unit_state",
    "dbus.message",
}
observed = {item.get("kind") for item in payload.get("events", [])}
missing = sorted(expected - observed)
if missing:
    raise SystemExit(f"missing event kinds: {missing}")
if payload.get("returned_events", 0) < len(expected):
    raise SystemExit("expected all collector events to be returned")
reload_events = [
    item for item in payload.get("events", [])
    if item.get("kind") == "systemd.unit_state" and (item.get("object") or {}).get("unit") == "agentos-kernel.service"
]
if not reload_events:
    raise SystemExit("expected reloading unit-state coverage for agentos-kernel.service")
if (reload_events[-1].get("object") or {}).get("state_family") != "transitional":
    raise SystemExit("expected reloading systemd event to expose transitional state family")
dbus_classes = {
    (item.get("object") or {}).get("message_class")
    for item in payload.get("events", [])
    if item.get("kind") == "dbus.message"
}
if "logind.session_lifecycle" not in dbus_classes or "systemd.unit_lifecycle" not in dbus_classes:
    raise SystemExit(f"expected richer dbus message classes, got {sorted(dbus_classes)}")
PY

FILTER_JSON="$TMP_DIR/network.json"
scripts/agentos-kernelctl events --workspace "$WORKSPACE" --kind network.connect_candidate --limit 5 --json > "$FILTER_JSON"

python3 - "$FILTER_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("matched_events") != 1:
    raise SystemExit("expected exactly one matched network event")
event = (payload.get("events") or [{}])[0]
if event.get("kind") != "network.connect_candidate":
    raise SystemExit("expected filtered event kind to be network.connect_candidate")
PY

UNIT_JSON="$TMP_DIR/systemd-unit.json"
scripts/agentos-kernelctl events --workspace "$WORKSPACE" --kind systemd.unit_state --unit agentos-kernel.service --json > "$UNIT_JSON"

python3 - "$UNIT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("matched_events") != 1:
    raise SystemExit("expected exactly one matched systemd unit event")
event = (payload.get("events") or [{}])[0]
obj = event.get("object") or {}
if obj.get("unit") != "agentos-kernel.service":
    raise SystemExit("expected systemd unit filter to keep only agentos-kernel.service")
if obj.get("state") != "reloading":
    raise SystemExit("expected filtered unit event to preserve reloading state")
PY

SOURCE_JSON="$TMP_DIR/dbus-source.json"
scripts/agentos-kernelctl events --workspace "$WORKSPACE" --source dbus --json > "$SOURCE_JSON"

python3 - "$SOURCE_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("matched_events") != 2:
    raise SystemExit("expected exactly two dbus events after source filtering")
retention = payload.get("retention") or {}
if retention.get("rotation_max_bytes", 0) <= 0:
    raise SystemExit("expected rotation_max_bytes in event query retention metadata")
PY

echo "eventd collectors smoke: PASS"

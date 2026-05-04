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

from kernel.event_fabric.collectors import append_events_jsonl
from kernel.event_fabric.schema import build_os_event_record

workspace = Path(os.environ["WORKSPACE"])
events = [
    build_os_event_record(
        source="journald",
        kind="session.login",
        action="login",
        object={"session_id": "8", "user_name": "agentos"},
        correlation={"session_id": "8", "boot_id": "boot-1", "session_origin": "local_managed_tty1"},
        timestamp_utc="2026-04-14T00:00:01+00:00",
    ),
    build_os_event_record(
        source="journald",
        kind="systemd.unit_state",
        action="state_change",
        object={"unit": "agentos-kernel.service", "state": "started", "session_id": "8"},
        correlation={"session_id": "8", "boot_id": "boot-1", "next_managed_entry": "ai_shell"},
        timestamp_utc="2026-04-14T00:00:02+00:00",
    ),
    build_os_event_record(
        source="journald",
        kind="session.logout",
        action="logout",
        object={"session_id": "8"},
        correlation={"session_id": "8"},
        timestamp_utc="2026-04-14T00:00:03+00:00",
    ),
]
append_events_jsonl(workspace / "artifacts" / "os_events.jsonl", events)
PY

OUT_JSON="$TMP_DIR/sessions.json"
scripts/agentos-kernelctl sessions --workspace "$WORKSPACE" --session-id 8 --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
timeline = payload.get("timeline", [])
if [item.get("kind") for item in timeline] != ["session.login", "systemd.unit_state", "session.logout"]:
    raise SystemExit("unexpected session event ordering")
if timeline[1].get("summary") != "agentos-kernel.service started":
    raise SystemExit("expected systemd unit summary in timeline")
ownership = payload.get("ownership_summary", {})
if ownership.get("session_phase") != "ai_shell":
    raise SystemExit("expected ai_shell ownership phase")
if ownership.get("session_origin") != "local_managed_tty1":
    raise SystemExit("expected local_managed_tty1 ownership origin")
PY

echo "event session timeline smoke: PASS"

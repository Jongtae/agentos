#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 - "$TMP_DIR/workspace" <<'PY'
import json
import sys
from pathlib import Path

from kernel.operator_activity import (
    ACTIVITY_DECISION_STATES,
    ACTIVITY_EVENT_KINDS,
    append_activity_event,
    build_activity_feed_payload,
)

workspace = Path(sys.argv[1])
events = [
    ("operator.request_received", "Operator", "Request received", "received"),
    ("intent.classified", "AgentOS", "Intent classified", "classified"),
    ("capability.started", "AgentOS", "Capability started", "running"),
    ("capability.degraded", "AgentOS", "Capability degraded", "degraded"),
    ("capability.blocked", "AgentOS", "Capability blocked", "blocked"),
    ("recovery.suggested", "AgentOS", "Recovery suggested", "suggested"),
    ("capability.completed", "AgentOS", "Capability completed", "completed"),
]
for kind, source, message, state in events:
    assert kind in ACTIVITY_EVENT_KINDS
    assert state in ACTIVITY_DECISION_STATES
    append_activity_event(
        workspace,
        kind=kind,
        source_label=source,
        human_message=message,
        request_id="phase2-activity-vocab",
        intent="gmail_read_or_draft",
        capability="gmail_fixture",
        decision={"state": state},
    )

payload = build_activity_feed_payload(workspace, limit=20)
kinds = {event["kind"] for event in payload["events"]}
for kind, *_ in events:
    assert kind in kinds, kinds
assert payload["activity_feed_ready"] is True
print(json.dumps(payload, ensure_ascii=True))
PY

echo "phase2 activity vocabulary smoke: PASS"

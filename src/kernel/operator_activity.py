from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from kernel.event_fabric.collectors import append_events_jsonl
from kernel.event_fabric.schema import build_os_event_record, os_event_log_path

ACTIVITY_SCHEMA_VERSION = "agentos-operator-activity-feed.v1"

ACTIVITY_EVENT_KINDS = {
    "operator.request_received",
    "telegram.message_received",
    "intent.classified",
    "capability.started",
    "capability.completed",
    "capability.blocked",
    "capability.degraded",
    "capability.failed",
    "recovery.suggested",
    "telegram.reply_sent",
    "setup.completed",
}

ACTIVITY_DECISION_STATES = {
    "received",
    "classified",
    "running",
    "completed",
    "blocked",
    "degraded",
    "failed",
    "sent",
    "suggested",
    "observed",
}


def append_activity_event(
    workspace_dir: str | Path,
    *,
    kind: str,
    source_label: str,
    human_message: str,
    request_id: str = "",
    intent: str = "",
    capability: str = "",
    actor: dict | None = None,
    object: dict | None = None,
    action: str = "",
    decision: dict | None = None,
    raw_ref: dict | None = None,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    event_object = dict(object or {})
    event_object["human_message"] = str(human_message).strip()
    if source_label:
        event_object["source_label"] = str(source_label).strip()
    if intent:
        event_object["intent"] = str(intent).strip()
    if capability:
        event_object["capability"] = str(capability).strip()

    correlation = {"request_id": str(request_id).strip()} if request_id else {}
    event = build_os_event_record(
        source="runtime",
        kind=kind,
        actor=actor or {"surface": source_label or "agentos"},
        object=event_object,
        action=action or kind.replace(".", "_"),
        decision=decision or {"state": "observed"},
        correlation=correlation,
        raw_ref=raw_ref or {"surface": "operator_activity"},
    )
    append_events_jsonl(os_event_log_path(workspace), [event])
    return event.to_dict()


def read_activity_events(workspace_dir: str | Path, *, limit: int = 30) -> list[dict]:
    path = os_event_log_path(Path(workspace_dir).resolve())
    rows: list[dict] = []
    if not path.exists():
        return rows
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return rows
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except Exception:
            continue
        kind = str(event.get("kind", "")).strip()
        obj = event.get("object") if isinstance(event.get("object"), dict) else {}
        if kind not in ACTIVITY_EVENT_KINDS and not obj.get("human_message"):
            continue
        rows.append(_humanize_event(event))
        if len(rows) >= max(1, int(limit)):
            break
    return list(reversed(rows))


def build_activity_feed_payload(workspace_dir: str | Path, *, limit: int = 30) -> dict:
    workspace = Path(workspace_dir).resolve()
    events = read_activity_events(workspace, limit=limit)
    return {
        "schema_version": ACTIVITY_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "capability": "activity_feed",
        "activity_feed_ready": True,
        "event_count": len(events),
        "events": events,
        "summary": {
            "activity_feed_ready": True,
            "event_count": len(events),
            "latest_human_message": events[-1]["human_message"] if events else "",
        },
        "artifacts": {
            "os_events_jsonl": str(os_event_log_path(workspace)),
        },
    }


def _humanize_event(event: dict) -> dict:
    obj = event.get("object") if isinstance(event.get("object"), dict) else {}
    correlation = event.get("correlation") if isinstance(event.get("correlation"), dict) else {}
    timestamp = str(event.get("timestamp_utc", "")).strip()
    label = str(obj.get("source_label", "") or _label_for_kind(str(event.get("kind", "")))).strip()
    human = str(obj.get("human_message", "")).strip() or _message_for_kind(str(event.get("kind", "")), obj)
    return {
        "timestamp_utc": timestamp,
        "time": _short_time(timestamp),
        "kind": str(event.get("kind", "")).strip(),
        "label": label,
        "human_message": human,
        "intent": str(obj.get("intent", "")).strip(),
        "capability": str(obj.get("capability", "")).strip(),
        "request_id": str(correlation.get("request_id", "")).strip(),
    }


def _short_time(timestamp: str) -> str:
    if not timestamp:
        return ""
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).strftime("%H:%M")
    except Exception:
        return timestamp[:5]


def _label_for_kind(kind: str) -> str:
    if kind.startswith("telegram."):
        return "Telegram"
    if kind.startswith("operator."):
        return "Operator"
    if kind.startswith("intent."):
        return "AgentOS"
    if kind.startswith("capability."):
        return "AgentOS"
    if kind.startswith("setup."):
        return "Setup"
    return "AgentOS"


def _message_for_kind(kind: str, obj: dict) -> str:
    if kind == "intent.classified":
        return f"Understood as: {obj.get('intent', 'unknown')}"
    if kind == "capability.started":
        return f"Running capability: {obj.get('capability', 'unknown')}"
    if kind == "capability.completed":
        return f"Completed capability: {obj.get('capability', 'unknown')}"
    if kind == "capability.blocked":
        return f"Capability blocked: {obj.get('capability', 'unknown')}"
    if kind == "capability.degraded":
        return f"Capability degraded: {obj.get('capability', 'unknown')}"
    if kind == "capability.failed":
        return f"Capability failed: {obj.get('capability', 'unknown')}"
    if kind == "recovery.suggested":
        return f"Recovery suggested: {obj.get('capability', 'unknown')}"
    if kind == "telegram.reply_sent":
        return "Reply sent to Telegram"
    return kind

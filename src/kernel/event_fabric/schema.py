from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from kernel.event_fabric.correlation import normalize_correlation_context

DEFAULT_OS_EVENT_LOG_FILENAME = "os_events.jsonl"
DEFAULT_OS_EVENT_LOG_MAX_BYTES = 5 * 1024 * 1024

OS_EVENT_REQUIRED_FIELDS = (
    "timestamp_utc",
    "source",
    "kind",
    "actor",
    "object",
    "action",
    "decision",
    "correlation",
    "raw_ref",
)

OS_EVENT_ALLOWED_SOURCES = (
    "ebpf",
    "audit",
    "journald",
    "dbus",
    "runtime",
    "broker",
    "kernel",
    "manual",
)


@dataclass(frozen=True)
class OSEventRecord:
    timestamp_utc: str
    source: str
    kind: str
    actor: dict
    object: dict
    action: str
    decision: dict
    correlation: dict
    raw_ref: dict

    def to_dict(self) -> dict:
        return asdict(self)


def build_os_event_record(
    *,
    source: str,
    kind: str,
    actor: dict | None = None,
    object: dict | None = None,
    action: str = "",
    decision: dict | None = None,
    correlation: dict | None = None,
    raw_ref: dict | None = None,
    timestamp_utc: str = "",
) -> OSEventRecord:
    return OSEventRecord(
        timestamp_utc=timestamp_utc or datetime.now(timezone.utc).isoformat(),
        source=(source or "").strip().lower(),
        kind=(kind or "").strip(),
        actor=actor or {},
        object=object or {},
        action=(action or "").strip(),
        decision=decision or {},
        correlation=normalize_correlation_context(correlation),
        raw_ref=raw_ref or {},
    )


def validate_os_event_payload(payload: dict) -> tuple[bool, str]:
    for key in OS_EVENT_REQUIRED_FIELDS:
        if key not in payload:
            return False, f"missing required field: {key}"

    if not isinstance(payload.get("actor"), dict):
        return False, "actor must be an object"
    if not isinstance(payload.get("object"), dict):
        return False, "object must be an object"
    if not isinstance(payload.get("decision"), dict):
        return False, "decision must be an object"
    if not isinstance(payload.get("correlation"), dict):
        return False, "correlation must be an object"
    if not isinstance(payload.get("raw_ref"), dict):
        return False, "raw_ref must be an object"

    source = str(payload.get("source", "")).strip().lower()
    if not source:
        return False, "source must be non-empty"
    if source not in OS_EVENT_ALLOWED_SOURCES:
        return False, f"unsupported source: {source}"

    kind = str(payload.get("kind", "")).strip()
    if not kind:
        return False, "kind must be non-empty"

    action = str(payload.get("action", "")).strip()
    if not action:
        return False, "action must be non-empty"

    timestamp_utc = str(payload.get("timestamp_utc", "")).strip()
    if not timestamp_utc:
        return False, "timestamp_utc must be non-empty"

    return True, "ok"


def os_event_log_path(workspace_dir: Path) -> Path:
    return Path(workspace_dir) / "artifacts" / DEFAULT_OS_EVENT_LOG_FILENAME


def os_event_archive_path(workspace_dir: Path) -> Path:
    active = os_event_log_path(workspace_dir)
    return active.with_suffix(active.suffix + ".1")


def os_event_storage_contract(workspace_dir: Path) -> dict:
    active = os_event_log_path(workspace_dir)
    archive = os_event_archive_path(workspace_dir)
    return {
        "format": "jsonl",
        "active_file": str(active),
        "archive_file": str(archive),
        "rotation_trigger": {
            "type": "size_bytes",
            "max_bytes": DEFAULT_OS_EVENT_LOG_MAX_BYTES,
        },
        "archive_retention": {
            "type": "single_archive",
            "keep_archives": 1,
        },
        "writer_contract": {
            "append_only": True,
            "ascii_json": True,
        },
    }

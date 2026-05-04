from __future__ import annotations

import json
from pathlib import Path

from kernel.event_fabric.schema import (
    DEFAULT_OS_EVENT_LOG_MAX_BYTES,
    os_event_archive_path,
    os_event_log_path,
)
from kernel.event_fabric.session_contract import build_session_ownership_summary, session_correlation_contract


def query_events(
    workspace_dir: str | Path,
    *,
    kind: str = "",
    unit: str = "",
    source: str = "",
    limit: int = 20,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    event_file = os_event_log_path(workspace)
    archive_file = os_event_archive_path(workspace)
    limit = max(1, int(limit))
    normalized_kind = str(kind).strip()
    normalized_unit = str(unit).strip()
    normalized_source = str(source).strip().lower()

    records = _read_events(event_file)
    total_events = len(records)
    if normalized_source:
        records = [item for item in records if str(item.get("source", "")).strip().lower() == normalized_source]
    if normalized_kind:
        records = [item for item in records if item.get("kind") == normalized_kind]
    if normalized_unit:
        records = [item for item in records if str((item.get("object") or {}).get("unit", "")).strip() == normalized_unit]
    selected = records[-limit:]
    active_size_bytes = event_file.stat().st_size if event_file.exists() else 0
    archive_size_bytes = archive_file.stat().st_size if archive_file.exists() else 0

    return {
        "ok": True,
        "exit_code": 0,
        "workspace": str(workspace),
        "event_file": str(event_file),
        "archive_file": str(archive_file),
        "event_file_exists": event_file.exists(),
        "archive_file_exists": archive_file.exists(),
        "filter": {
            "source": normalized_source,
            "kind": normalized_kind,
            "unit": normalized_unit,
            "limit": limit,
        },
        "retention": {
            "rotation_max_bytes": DEFAULT_OS_EVENT_LOG_MAX_BYTES,
            "active_size_bytes": active_size_bytes,
            "archive_size_bytes": archive_size_bytes,
            "active_bytes_remaining": max(0, DEFAULT_OS_EVENT_LOG_MAX_BYTES - active_size_bytes),
            "archive_present": archive_file.exists(),
        },
        "total_events": total_events,
        "matched_events": len(records),
        "returned_events": len(selected),
        "events": selected,
    }


def query_process_lineage(
    workspace_dir: str | Path,
    *,
    correlation_key: str = "",
    correlation_value: str = "",
    limit: int = 50,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    event_file = os_event_log_path(workspace)
    archive_file = os_event_archive_path(workspace)
    limit = max(1, int(limit))
    normalized_key = str(correlation_key).strip()
    normalized_value = str(correlation_value).strip()

    records = [item for item in _read_events(event_file) if item.get("kind") in {"process.exec", "process.exit"}]
    total_process_events = len(records)
    if normalized_key and normalized_value:
        records = [
            item
            for item in records
            if str((item.get("correlation") or {}).get(normalized_key, "")).strip() == normalized_value
        ]

    selected = records[-limit:]
    nodes: dict[int, dict] = {}
    roots: set[int] = set()
    for event in selected:
        actor = event.get("actor") or {}
        pid = _int_or_none(actor.get("pid"))
        if pid is None:
            continue
        ppid = _int_or_none(actor.get("ppid"))
        node = nodes.get(pid)
        if node is None and event.get("kind") != "process.exec":
            continue
        if node is None:
            node = nodes.setdefault(
                pid,
                {
                    "pid": pid,
                    "ppid": ppid,
                    "comm": actor.get("comm", ""),
                    "exe": actor.get("exe", ""),
                    "events": [],
                    "children": [],
                    "correlation": event.get("correlation") or {},
                },
            )
        node["ppid"] = ppid
        node["comm"] = actor.get("comm", node["comm"])
        node["exe"] = actor.get("exe", node["exe"])
        node["correlation"] = event.get("correlation") or node["correlation"]
        node["events"].append(
            {
                "timestamp_utc": event.get("timestamp_utc", ""),
                "kind": event.get("kind", ""),
                "action": event.get("action", ""),
            }
        )

    for pid, node in list(nodes.items()):
        ppid = node.get("ppid")
        if ppid in nodes:
            nodes[ppid]["children"].append(pid)
        else:
            roots.add(pid)

    lineage_nodes = [nodes[pid] for pid in sorted(nodes)]
    for node in lineage_nodes:
        node["children"] = sorted(set(node["children"]))
    root_pids = sorted(pid for pid in roots if pid in nodes)

    return {
        "ok": True,
        "exit_code": 0,
        "workspace": str(workspace),
        "event_file": str(event_file),
        "archive_file": str(archive_file),
        "event_file_exists": event_file.exists(),
        "archive_file_exists": archive_file.exists(),
        "filter": {
            "correlation_key": normalized_key,
            "correlation_value": normalized_value,
            "limit": limit,
        },
        "total_process_events": total_process_events,
        "matched_process_events": len(records),
        "returned_process_events": len(selected),
        "root_pids": root_pids,
        "nodes": lineage_nodes,
    }


def query_session_timeline(
    workspace_dir: str | Path,
    *,
    session_id: str = "",
    limit: int = 50,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    event_file = os_event_log_path(workspace)
    archive_file = os_event_archive_path(workspace)
    limit = max(1, int(limit))
    normalized_session_id = str(session_id).strip()

    records = _read_events(event_file)
    timeline_kinds = {"session.login", "session.logout", "systemd.unit_state"}
    timeline: list[dict] = []
    for item in records:
        item_session_id = str((item.get("object") or {}).get("session_id", "")).strip()
        correlation_session_id = str((item.get("correlation") or {}).get("session_id", "")).strip()
        if normalized_session_id and normalized_session_id not in {item_session_id, correlation_session_id}:
            continue
        session_linked = bool(item_session_id or correlation_session_id)
        if item.get("kind") not in timeline_kinds and not session_linked:
            continue
        timeline.append(
            {
                "timestamp_utc": item.get("timestamp_utc", ""),
                "kind": item.get("kind", ""),
                "action": item.get("action", ""),
                "session_id": item_session_id or correlation_session_id,
                "summary": _session_timeline_summary(item),
                "actor": item.get("actor") or {},
                "object": item.get("object") or {},
                "correlation": item.get("correlation") or {},
            }
        )

    timeline.sort(key=lambda item: item.get("timestamp_utc", ""))
    selected = timeline[-limit:]
    latest_session_id = ""
    latest_origin = "noninteractive"
    latest_next_entry = "setup_session"
    latest_boot_id = ""
    banner_version = ""
    observed_boot_ids: list[str] = []
    observed_request_ids: list[str] = []
    observed_approval_ids: list[str] = []
    for item in selected:
        latest_session_id = str(item.get("session_id", "")).strip() or latest_session_id
        correlation = item.get("correlation") or {}
        boot_id = str(correlation.get("boot_id", "")).strip()
        latest_boot_id = boot_id or latest_boot_id
        latest_origin = (
            str(correlation.get("session_origin", "") or correlation.get("origin", "")).strip() or latest_origin
        )
        latest_next_entry = str(correlation.get("next_managed_entry", "")).strip() or latest_next_entry
        banner_version = str(correlation.get("banner_version", "")).strip() or banner_version
        request_id = str(correlation.get("request_id", "")).strip()
        approval_id = str(correlation.get("approval_id", "")).strip()
        if boot_id and boot_id not in observed_boot_ids:
            observed_boot_ids.append(boot_id)
        if request_id and request_id not in observed_request_ids:
            observed_request_ids.append(request_id)
        if approval_id and approval_id not in observed_approval_ids:
            observed_approval_ids.append(approval_id)
    setup_status = "configured" if latest_next_entry == "ai_shell" else "pending"

    return {
        "ok": True,
        "exit_code": 0,
        "workspace": str(workspace),
        "event_file": str(event_file),
        "archive_file": str(archive_file),
        "event_file_exists": event_file.exists(),
        "archive_file_exists": archive_file.exists(),
        "filter": {
            "session_id": normalized_session_id,
            "limit": limit,
        },
        "matched_events": len(timeline),
        "returned_events": len(selected),
        "session_contract": session_correlation_contract(),
        "ownership_summary": build_session_ownership_summary(
            session_origin=latest_origin,
            setup_status=setup_status,
            next_managed_entry=latest_next_entry,
            session_id=latest_session_id,
            boot_id=latest_boot_id,
            banner_version=banner_version,
        ),
        "correlation_evidence": {
            "session_id": latest_session_id,
            "boot_ids": observed_boot_ids,
            "request_ids": observed_request_ids,
            "approval_ids": observed_approval_ids,
        },
        "timeline": selected,
    }


def event_coverage_summary(workspace_dir: str | Path, *, sample_limit: int = 200) -> dict:
    workspace = Path(workspace_dir).resolve()
    report = query_events(workspace, limit=max(1, int(sample_limit)))
    rows = report.get("events", []) or []

    source_counts: dict[str, int] = {}
    kind_counts: dict[str, int] = {}
    dbus_classes: set[str] = set()
    systemd_states: set[str] = set()
    systemd_units: set[str] = set()

    for row in rows:
        source = str(row.get("source", "")).strip().lower()
        kind = str(row.get("kind", "")).strip()
        if source:
            source_counts[source] = source_counts.get(source, 0) + 1
        if kind:
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
        obj = row.get("object") or {}
        if kind == "dbus.message":
            message_class = str(obj.get("message_class", "")).strip()
            if message_class:
                dbus_classes.add(message_class)
        if kind == "systemd.unit_state":
            state = str(obj.get("state", "")).strip()
            unit = str(obj.get("unit", "")).strip()
            if state:
                systemd_states.add(state)
            if unit:
                systemd_units.add(unit)

    expected_sources = ["kernel", "journald", "dbus", "broker"]
    observed_sources = sorted(source_counts)
    return {
        "sample_limit": max(1, int(sample_limit)),
        "sampled_events": len(rows),
        "observed_sources": observed_sources,
        "source_counts": source_counts,
        "observed_kinds": sorted(kind_counts),
        "kind_counts": kind_counts,
        "dbus_message_classes": sorted(dbus_classes),
        "systemd_states": sorted(systemd_states),
        "systemd_units": sorted(systemd_units),
        "gaps": {
            "missing_expected_sources": [item for item in expected_sources if item not in observed_sources],
            "missing_systemd_unit_state": "systemd.unit_state" not in kind_counts,
            "missing_dbus_classification": not bool(dbus_classes),
        },
        "retention": report.get("retention", {}),
    }


def _read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []

    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except Exception:
        return None


def _session_timeline_summary(item: dict) -> str:
    kind = str(item.get("kind", "")).strip()
    obj = item.get("object") or {}
    if kind == "session.login":
        session_id = obj.get("session_id", "")
        user_name = obj.get("user_name", "")
        return f"session {session_id} login {user_name}".strip()
    if kind == "session.logout":
        session_id = obj.get("session_id", "")
        return f"session {session_id} logout".strip()
    if kind == "systemd.unit_state":
        unit = obj.get("unit", "")
        state = obj.get("state", "")
        family = obj.get("state_family", "")
        if family:
            return f"{unit} {state} [{family}]".strip()
        return f"{unit} {state}".strip()
    return f"{kind} {item.get('action', '')}".strip()

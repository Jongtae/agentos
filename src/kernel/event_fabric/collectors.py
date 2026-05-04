from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from kernel.event_fabric.schema import DEFAULT_OS_EVENT_LOG_MAX_BYTES, OSEventRecord, build_os_event_record


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    ppid: int
    comm: str
    exe: str

    def actor(self) -> dict:
        return {
            "pid": self.pid,
            "ppid": self.ppid,
            "comm": self.comm,
            "exe": self.exe,
        }


@dataclass(frozen=True)
class FileAccessCandidate:
    path: str
    action: str
    workspace_root: str
    actor: dict


@dataclass(frozen=True)
class NetworkConnectCandidate:
    host: str
    port: int
    allowlist: list[str]
    actor: dict


@dataclass(frozen=True)
class JournaldEventCandidate:
    cursor: str
    kind: str
    action: str
    actor: dict
    object: dict
    raw: dict


@dataclass(frozen=True)
class DBusMessageCandidate:
    bus: str
    path: str
    interface: str
    member: str
    message_type: str
    sender: str
    destination: str
    actor: dict


def read_process_snapshot(ps_cmd: str = "ps") -> dict[int, ProcessSnapshot]:
    proc = subprocess.run(
        [ps_cmd, "-Ao", "pid=,ppid=,comm=,command="],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ps snapshot failed")

    snapshot: dict[int, ProcessSnapshot] = {}
    for line in (proc.stdout or "").splitlines():
        row = line.strip()
        if not row:
            continue
        parts = row.split(None, 3)
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except ValueError:
            continue
        snapshot[pid] = ProcessSnapshot(pid=pid, ppid=ppid, comm=parts[2], exe=parts[3])
    return snapshot


def process_exec_exit_events(
    previous: dict[int, ProcessSnapshot],
    current: dict[int, ProcessSnapshot],
    *,
    source: str = "kernel",
    correlation: dict | None = None,
) -> list[OSEventRecord]:
    events: list[OSEventRecord] = []
    correlation = correlation or {}

    for pid in sorted(set(current) - set(previous)):
        proc = current[pid]
        events.append(
            build_os_event_record(
                source=source,
                kind="process.exec",
                actor=proc.actor(),
                object={"pid": proc.pid, "exe": proc.exe},
                action="exec",
                decision={"state": "observed"},
                correlation=dict(correlation),
                raw_ref={"collector": "process_snapshot_diff", "pid": proc.pid},
            )
        )

    for pid in sorted(set(previous) - set(current)):
        proc = previous[pid]
        events.append(
            build_os_event_record(
                source=source,
                kind="process.exit",
                actor=proc.actor(),
                object={"pid": proc.pid, "exe": proc.exe},
                action="exit",
                decision={"state": "observed"},
                correlation=dict(correlation),
                raw_ref={"collector": "process_snapshot_diff", "pid": proc.pid},
            )
        )

    return events


def append_events_jsonl(
    path: Path,
    events: list[OSEventRecord],
    *,
    max_bytes: int = DEFAULT_OS_EVENT_LOG_MAX_BYTES,
    archive_path: Path | None = None,
) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload_lines = [json.dumps(event.to_dict(), ensure_ascii=True) for event in events]
    payload = "".join(f"{line}\n" for line in payload_lines)
    _rotate_event_log(path, payload.encode("utf-8"), max_bytes=max(1, int(max_bytes)), archive_path=archive_path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload)
    return len(events)


def _resolved_candidate_path(candidate_path: str, workspace_root: str) -> tuple[Path, Path]:
    workspace = Path(workspace_root).resolve()
    raw = Path(candidate_path)
    if raw.is_absolute():
        candidate = raw.resolve()
    else:
        candidate = (workspace / raw).resolve()
    return candidate, workspace


def is_outside_workspace(candidate_path: str, workspace_root: str) -> bool:
    candidate, workspace = _resolved_candidate_path(candidate_path, workspace_root)
    return not candidate.is_relative_to(workspace)


def file_access_candidate_event(
    *,
    candidate_path: str,
    action: str,
    workspace_root: str,
    actor: dict | None = None,
    source: str = "kernel",
    correlation: dict | None = None,
) -> OSEventRecord | None:
    candidate, workspace = _resolved_candidate_path(candidate_path, workspace_root)
    if not is_outside_workspace(candidate_path, workspace_root):
        return None

    return build_os_event_record(
        source=source,
        kind="file.outside_workspace_candidate",
        actor=actor or {},
        object={
            "path": str(candidate),
            "workspace_root": str(workspace),
        },
        action=(action or "").strip() or "open",
        decision={"state": "candidate", "policy_target": "fs_workspace_boundary"},
        correlation=correlation or {},
        raw_ref={
            "collector": "file_access_candidate",
            "input_path": candidate_path,
        },
    )


def is_allowlisted_host(host: str, allowlist: list[str]) -> bool:
    normalized = (host or "").strip().lower().rstrip(".")
    for item in allowlist:
        allowed = str(item).strip().lower().rstrip(".")
        if not allowed:
            continue
        if normalized == allowed or normalized.endswith(f".{allowed}"):
            return True
    return False


def network_connect_candidate_event(
    *,
    host: str,
    port: int,
    allowlist: list[str],
    actor: dict | None = None,
    source: str = "kernel",
    correlation: dict | None = None,
) -> OSEventRecord | None:
    normalized_host = (host or "").strip().lower().rstrip(".")
    if not normalized_host or is_allowlisted_host(normalized_host, allowlist):
        return None

    return build_os_event_record(
        source=source,
        kind="network.connect_candidate",
        actor=actor or {},
        object={
            "host": normalized_host,
            "port": int(port),
            "allowlist": [str(item).strip().lower().rstrip(".") for item in allowlist if str(item).strip()],
        },
        action="connect",
        decision={"state": "candidate", "policy_target": "network_allowlist"},
        correlation=correlation or {},
        raw_ref={
            "collector": "network_connect_candidate",
            "input_host": host,
        },
    )


def journald_systemd_logind_event(
    entry: dict,
    *,
    correlation: dict | None = None,
    source: str = "journald",
) -> OSEventRecord | None:
    message = str(entry.get("MESSAGE", "")).strip()
    cursor = str(entry.get("__CURSOR", "")).strip()
    actor = _journald_actor(entry)

    if _is_logind_login(entry, message):
        session_id = _session_id_from_entry(entry, message, login=True)
        return build_os_event_record(
            source=source,
            kind="session.login",
            actor=actor,
            object={
                "session_id": session_id,
                "user_id": str(entry.get("USER_ID", "") or entry.get("_UID", "")).strip(),
                "user_name": str(entry.get("USER_NAME", "")).strip(),
                "message": message,
            },
            action="login",
            decision={"state": "observed"},
            correlation=correlation or {},
            raw_ref={
                "collector": "journald_systemd_logind",
                "cursor": cursor,
                "identifier": str(entry.get("SYSLOG_IDENTIFIER", "")).strip(),
            },
        )

    if _is_logind_logout(entry, message):
        session_id = _session_id_from_entry(entry, message, login=False)
        return build_os_event_record(
            source=source,
            kind="session.logout",
            actor=actor,
            object={
                "session_id": session_id,
                "message": message,
            },
            action="logout",
            decision={"state": "observed"},
            correlation=correlation or {},
            raw_ref={
                "collector": "journald_systemd_logind",
                "cursor": cursor,
                "identifier": str(entry.get("SYSLOG_IDENTIFIER", "")).strip(),
            },
        )

    unit_name = _systemd_unit_name(entry, message)
    state = _systemd_unit_state(message)
    if unit_name and state:
        return build_os_event_record(
            source=source,
            kind="systemd.unit_state",
            actor=actor,
            object={
                "unit": unit_name,
                "state": state,
                "state_family": _systemd_state_family(state),
                "unit_type": _systemd_unit_type(unit_name),
                "message": message,
            },
            action="state_change",
            decision={"state": "observed"},
            correlation=correlation or {},
            raw_ref={
                "collector": "journald_systemd_logind",
                "cursor": cursor,
                "identifier": str(entry.get("SYSLOG_IDENTIFIER", "")).strip(),
            },
        )

    return None


def _journald_actor(entry: dict) -> dict:
    actor: dict[str, object] = {}
    for field, target in (
        ("_PID", "pid"),
        ("_UID", "uid"),
        ("_COMM", "comm"),
        ("_EXE", "exe"),
        ("_SYSTEMD_UNIT", "unit"),
    ):
        value = str(entry.get(field, "")).strip()
        if value:
            actor[target] = int(value) if field in {"_PID", "_UID"} and value.isdigit() else value
    return actor


def _is_logind_login(entry: dict, message: str) -> bool:
    return str(entry.get("SYSLOG_IDENTIFIER", "")).strip() == "systemd-logind" and message.startswith("New session ")


def _is_logind_logout(entry: dict, message: str) -> bool:
    return str(entry.get("SYSLOG_IDENTIFIER", "")).strip() == "systemd-logind" and message.startswith("Removed session ")


def _session_id_from_entry(entry: dict, message: str, *, login: bool) -> str:
    session_id = str(entry.get("SESSION_ID", "")).strip()
    if session_id:
        return session_id

    prefix = "New session " if login else "Removed session "
    if message.startswith(prefix):
        remainder = message[len(prefix) :]
        return remainder.split(None, 1)[0].rstrip(".")
    return ""


def _systemd_unit_state(message: str) -> str:
    lowered = message.lower()
    if lowered.startswith("started "):
        return "started"
    if lowered.startswith("stopped "):
        return "stopped"
    if lowered.startswith("starting "):
        return "starting"
    if lowered.startswith("stopping "):
        return "stopping"
    if lowered.startswith("failed "):
        return "failed"
    if lowered.startswith("failed to start "):
        return "failed"
    if lowered.startswith("failed to listen on "):
        return "failed"
    if lowered.startswith("dependency failed for "):
        return "dependency_failed"
    if lowered.startswith("reloading "):
        return "reloading"
    if lowered.startswith("reloaded "):
        return "reloaded"
    if lowered.startswith("restarting "):
        return "restarting"
    if lowered.startswith("reached target "):
        return "reached"
    if lowered.startswith("listening on "):
        return "listening"
    if lowered.startswith("mounting "):
        return "mounting"
    if lowered.startswith("mounted "):
        return "mounted"
    if lowered.startswith("unmounting "):
        return "unmounting"
    if lowered.startswith("unmounted "):
        return "unmounted"
    if lowered.startswith("activating "):
        return "activating"
    if lowered.startswith("deactivated "):
        return "deactivated"
    return ""


def _systemd_unit_name(entry: dict, message: str) -> str:
    direct = str(entry.get("_SYSTEMD_UNIT", "") or entry.get("UNIT", "")).strip()
    if direct:
        return direct

    patterns = (
        r"^(?:Started|Stopped|Starting|Stopping|Reloaded|Reloading|Restarting|Failed to start|Dependency failed for|Mounted|Mounting|Unmounted|Unmounting|Listening on)\s+([A-Za-z0-9_.@-]+\.(?:service|target|socket|mount|timer|path|scope|slice|device))\b",
        r"^(?:Failed|Activating|Deactivated)\s+([A-Za-z0-9_.@-]+\.(?:service|target|socket|mount|timer|path|scope|slice|device))\b",
        r"^(?:Reached target)\s+([A-Za-z0-9_.@-]+\.(?:target))\b",
    )
    for pattern in patterns:
        match = re.match(pattern, message.strip())
        if match:
            return match.group(1)
    return ""


def _systemd_unit_type(unit_name: str) -> str:
    name = str(unit_name).strip()
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1]


def _systemd_state_family(state: str) -> str:
    normalized = str(state).strip().lower()
    if normalized in {"starting", "stopping", "reloading", "restarting", "mounting", "unmounting", "activating"}:
        return "transitional"
    if normalized in {"started", "reloaded", "mounted", "listening", "reached"}:
        return "active"
    if normalized in {"stopped", "unmounted", "deactivated"}:
        return "inactive"
    if normalized in {"failed", "dependency_failed"}:
        return "failed"
    return "observed"


def dbus_message_event(
    *,
    bus: str,
    path: str,
    interface: str,
    member: str,
    message_type: str,
    sender: str = "",
    destination: str = "",
    actor: dict | None = None,
    body: dict | None = None,
    raw_ref: dict | None = None,
    correlation: dict | None = None,
    source: str = "dbus",
) -> OSEventRecord | None:
    normalized_path = str(path).strip()
    normalized_interface = str(interface).strip()
    normalized_member = str(member).strip()
    normalized_type = str(message_type).strip().lower()
    normalized_bus = str(bus).strip().lower() or "system"

    if not normalized_path or not normalized_interface or not normalized_member:
        return None

    return build_os_event_record(
        source=source,
        kind="dbus.message",
        actor=actor
        or {
            "sender": str(sender).strip(),
            "destination": str(destination).strip(),
            "bus": normalized_bus,
        },
        object={
            "bus": normalized_bus,
            "path": normalized_path,
            "interface": normalized_interface,
            "member": normalized_member,
            "message_type": normalized_type or "signal",
            "message_class": _dbus_message_class(
                bus=normalized_bus,
                path=normalized_path,
                interface=normalized_interface,
                member=normalized_member,
                message_type=normalized_type or "signal",
            ),
            "body": body or {},
        },
        action="message",
        decision={"state": "observed"},
        correlation=correlation or {},
        raw_ref={
            "collector": "dbus_monitor",
            **(raw_ref or {}),
        },
    )


def _dbus_message_class(*, bus: str, path: str, interface: str, member: str, message_type: str) -> str:
    normalized_bus = str(bus).strip().lower()
    normalized_path = str(path).strip()
    normalized_interface = str(interface).strip()
    normalized_member = str(member).strip()
    normalized_type = str(message_type).strip().lower()

    if normalized_interface == "org.freedesktop.login1.Manager":
        if normalized_member in {"SessionNew", "SessionRemoved"}:
            return "logind.session_lifecycle"
        if normalized_member in {"SeatNew", "SeatRemoved"}:
            return "logind.seat_lifecycle"
        return "logind.manager"

    if normalized_interface.startswith("org.freedesktop.systemd1"):
        if normalized_interface.endswith(".Unit") or "/unit/" in normalized_path:
            if normalized_member in {"PropertiesChanged", "JobRemoved", "Reloading"}:
                return "systemd.unit_lifecycle"
            return "systemd.unit"
        if normalized_interface.endswith(".Manager"):
            if normalized_member in {"JobNew", "JobRemoved", "UnitNew", "UnitRemoved"}:
                return "systemd.manager_lifecycle"
            return "systemd.manager"

    if normalized_bus == "session":
        if normalized_interface.startswith("org.freedesktop.portal."):
            return "portal.session"
        return "session_bus.generic"

    if normalized_type == "signal":
        return "signal.generic"
    if normalized_type == "method_call":
        return "method_call.generic"
    return "dbus.generic"


def _rotate_event_log(path: Path, payload_bytes: bytes, *, max_bytes: int, archive_path: Path | None = None) -> None:
    if not path.exists():
        return

    projected_size = path.stat().st_size + len(payload_bytes)
    if projected_size <= max_bytes:
        return

    archive = Path(archive_path) if archive_path else path.with_name(f"{path.name}.1")
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        archive.unlink()
    os.replace(path, archive)

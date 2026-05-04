from __future__ import annotations

import json
from pathlib import Path

STATE_FILE = "autoremediation_override_window_state.json"


def autoremediation_override_window_report(
    *,
    now_epoch: int,
    current_state: dict | None,
    override_requested: bool = False,
    override_duration_sec: int = 900,
) -> dict:
    now = max(0, int(now_epoch))
    state = _normalize_state(current_state)
    duration = max(60, int(override_duration_sec))

    status = "inactive"
    reason = "no_override_window"
    event = "no_change"
    next_check_epoch = now

    if bool(override_requested):
        state["override_until_epoch"] = now + duration
        if int(state["activated_at_epoch"]) <= 0:
            state["activated_at_epoch"] = now
        state["request_count"] = int(state["request_count"]) + 1
        state["last_requested_epoch"] = now
        status = "active"
        reason = "operator_override_requested"
        event = "override_activated"
        next_check_epoch = int(state["override_until_epoch"])
    elif int(state["override_until_epoch"]) > now:
        status = "active"
        reason = "override_window_active"
        event = "window_active"
        next_check_epoch = int(state["override_until_epoch"])
    elif int(state["override_until_epoch"]) > 0:
        status = "inactive"
        reason = "override_window_expired"
        event = "window_expired"
        state["override_until_epoch"] = 0
        state["activated_at_epoch"] = 0
        next_check_epoch = now

    remaining = max(0, int(state["override_until_epoch"]) - now)
    return {
        "ok": True,
        "now_epoch": now,
        "status": status,
        "reason": reason,
        "event": event,
        "remaining_sec": remaining,
        "next_check_epoch": int(next_check_epoch),
        "state": dict(state),
    }


def load_autoremediation_override_window_state(workspace_dir: Path) -> dict:
    path = _state_file_path(Path(workspace_dir).resolve())
    if not path.exists():
        return _default_state()
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_state()
    return _normalize_state(obj)


def save_autoremediation_override_window_state(
    workspace_dir: Path,
    *,
    state: dict,
) -> Path:
    workspace = Path(workspace_dir).resolve()
    path = _state_file_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _normalize_state(state)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return path


def _default_state() -> dict:
    return {
        "override_until_epoch": 0,
        "activated_at_epoch": 0,
        "request_count": 0,
        "last_requested_epoch": 0,
    }


def _normalize_state(raw: dict | None) -> dict:
    obj = raw or {}
    base = _default_state()
    return {
        "override_until_epoch": max(0, int(obj.get("override_until_epoch", base["override_until_epoch"]) or 0)),
        "activated_at_epoch": max(0, int(obj.get("activated_at_epoch", base["activated_at_epoch"]) or 0)),
        "request_count": max(0, int(obj.get("request_count", base["request_count"]) or 0)),
        "last_requested_epoch": max(0, int(obj.get("last_requested_epoch", base["last_requested_epoch"]) or 0)),
    }


def _state_file_path(workspace: Path) -> Path:
    return workspace / "artifacts" / STATE_FILE

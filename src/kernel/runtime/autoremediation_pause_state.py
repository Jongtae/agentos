from __future__ import annotations

import json
from pathlib import Path

STATE_FILE = "autoremediation_pause_state.json"


def autoremediation_pause_state_report(
    *,
    now_epoch: int,
    current_state: dict | None,
    auto_pause: dict | None = None,
    resume_requested: bool = False,
) -> dict:
    now = max(0, int(now_epoch))
    state = _normalize_state(current_state)
    pause = auto_pause or {}

    was_paused = bool(state["is_paused"])
    event = "no_change"
    status = "paused" if was_paused else "active"
    reason = str(state["pause_reason"])

    if bool(pause.get("should_pause", False)):
        cooldown = max(60, int(pause.get("cooldown_sec", 0) or 0))
        state["is_paused"] = True
        state["paused_since_epoch"] = int(state["paused_since_epoch"] or now)
        state["cooldown_until_epoch"] = max(int(state["cooldown_until_epoch"]), now + cooldown)
        state["pause_reason"] = str(pause.get("reason", "pause_required"))
        state["pause_severity"] = str(pause.get("severity", "warn"))
        event = "pause_activated" if not was_paused else "pause_extended"
        status = "paused"
        reason = state["pause_reason"]
    elif bool(resume_requested):
        state["resume_attempt_count"] = int(state["resume_attempt_count"]) + 1
        state["last_resume_attempt_epoch"] = now
        if bool(state["is_paused"]) and now < int(state["cooldown_until_epoch"]):
            event = "resume_blocked_by_cooldown"
            status = "paused"
            reason = "cooldown_active"
        elif bool(state["is_paused"]):
            state["is_paused"] = False
            state["paused_since_epoch"] = 0
            state["cooldown_until_epoch"] = 0
            state["pause_reason"] = "resumed"
            state["pause_severity"] = "info"
            event = "resume_released"
            status = "active"
            reason = "resumed"
        else:
            event = "resume_noop_not_paused"
            status = "active"
            reason = "not_paused"

    cooldown_remaining = max(0, int(state["cooldown_until_epoch"]) - now)

    return {
        "ok": True,
        "now_epoch": now,
        "status": status,
        "reason": reason,
        "event": event,
        "cooldown_remaining_sec": cooldown_remaining,
        "state": dict(state),
    }


def load_autoremediation_pause_state(workspace_dir: Path) -> dict:
    path = _state_file_path(Path(workspace_dir).resolve())
    if not path.exists():
        return _default_state()
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_state()
    return _normalize_state(obj)


def save_autoremediation_pause_state(
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
        "is_paused": False,
        "paused_since_epoch": 0,
        "cooldown_until_epoch": 0,
        "pause_reason": "none",
        "pause_severity": "info",
        "resume_attempt_count": 0,
        "last_resume_attempt_epoch": 0,
    }


def _normalize_state(raw: dict | None) -> dict:
    obj = raw or {}
    base = _default_state()
    return {
        "is_paused": bool(obj.get("is_paused", base["is_paused"])),
        "paused_since_epoch": max(0, int(obj.get("paused_since_epoch", base["paused_since_epoch"]) or 0)),
        "cooldown_until_epoch": max(0, int(obj.get("cooldown_until_epoch", base["cooldown_until_epoch"]) or 0)),
        "pause_reason": str(obj.get("pause_reason", base["pause_reason"])),
        "pause_severity": str(obj.get("pause_severity", base["pause_severity"])),
        "resume_attempt_count": max(0, int(obj.get("resume_attempt_count", base["resume_attempt_count"]) or 0)),
        "last_resume_attempt_epoch": max(
            0,
            int(obj.get("last_resume_attempt_epoch", base["last_resume_attempt_epoch"]) or 0),
        ),
    }


def _state_file_path(workspace: Path) -> Path:
    return workspace / "artifacts" / STATE_FILE

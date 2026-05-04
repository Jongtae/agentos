from __future__ import annotations

import json
from pathlib import Path

STATE_FILE = "autoremediation_override_budget_state.json"


def autoremediation_override_budget_report(
    *,
    now_epoch: int,
    state: dict | None,
    window_size_sec: int = 86400,
    max_overrides_per_window: int = 3,
) -> dict:
    now = max(0, int(now_epoch))
    window = max(60, int(window_size_sec))
    limit = max(1, int(max_overrides_per_window))
    normalized = _normalize_state(state)

    cut = now - window
    events = [int(ts) for ts in normalized["override_applied_epochs"] if int(ts) >= cut]
    used = len(events)
    remaining = max(0, limit - used)

    status = "allow"
    reason = "budget_available"
    next_check_epoch = now
    if remaining <= 0:
        status = "block"
        reason = "override_budget_exhausted"
        next_check_epoch = min(events) + window if events else now + window

    return {
        "ok": True,
        "now_epoch": now,
        "status": status,
        "reason": reason,
        "next_check_epoch": int(next_check_epoch),
        "budget": {
            "window_size_sec": window,
            "max_overrides_per_window": limit,
            "used": used,
            "remaining": remaining,
        },
        "state": {
            "override_applied_epochs": events,
        },
    }


def load_autoremediation_override_budget_state(workspace_dir: Path) -> dict:
    path = _state_file_path(Path(workspace_dir).resolve())
    if not path.exists():
        return {"override_applied_epochs": []}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"override_applied_epochs": []}
    return _normalize_state(obj)


def save_autoremediation_override_budget_state(
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


def append_override_budget_event(state: dict | None, *, applied_epoch: int) -> dict:
    normalized = _normalize_state(state)
    applied = max(0, int(applied_epoch))
    events = list(normalized["override_applied_epochs"])
    events.append(applied)
    return {"override_applied_epochs": sorted(events)}


def _normalize_state(raw: dict | None) -> dict:
    obj = raw or {}
    events: list[int] = []
    for value in obj.get("override_applied_epochs", []) or []:
        try:
            iv = int(value)
        except Exception:
            continue
        if iv >= 0:
            events.append(iv)
    return {"override_applied_epochs": sorted(events)}


def _state_file_path(workspace: Path) -> Path:
    return workspace / "artifacts" / STATE_FILE

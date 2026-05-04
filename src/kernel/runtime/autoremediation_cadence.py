from __future__ import annotations

import json
from pathlib import Path

STATE_FILE = "autoremediation_cadence_state.json"


def autoremediation_cadence_report(
    *,
    now_epoch: int,
    scheduler_status: str,
    last_apply_epoch: int,
    apply_history_epochs: list[int] | None,
    min_interval_sec: int = 300,
    max_applies_per_hour: int = 3,
    max_applies_per_day: int = 12,
) -> dict:
    now = max(0, int(now_epoch))
    history = sorted(_normalize_history(apply_history_epochs))
    min_interval = max(0, int(min_interval_sec))
    per_hour = max(1, int(max_applies_per_hour))
    per_day = max(1, int(max_applies_per_day))
    last_apply = max(0, int(last_apply_epoch))

    hour_cutoff = now - 3600
    day_cutoff = now - 86400
    applies_last_hour = sum(1 for ts in history if ts >= hour_cutoff)
    applies_last_day = sum(1 for ts in history if ts >= day_cutoff)

    status = "hold"
    reason = "scheduler_not_eligible"
    next_allowed_epoch = now

    if scheduler_status != "apply":
        status = "hold"
        reason = "scheduler_not_eligible"
    elif last_apply > 0 and (now - last_apply) < min_interval:
        status = "hold"
        reason = "min_interval_not_elapsed"
        next_allowed_epoch = last_apply + min_interval
    elif applies_last_hour >= per_hour:
        status = "hold"
        reason = "hourly_budget_exceeded"
        recent = [ts for ts in history if ts >= hour_cutoff]
        next_allowed_epoch = min(recent) + 3600 if recent else now
    elif applies_last_day >= per_day:
        status = "hold"
        reason = "daily_budget_exceeded"
        recent = [ts for ts in history if ts >= day_cutoff]
        next_allowed_epoch = min(recent) + 86400 if recent else now
    else:
        status = "allow"
        reason = "eligible"

    return {
        "ok": True,
        "now_epoch": now,
        "limits": {
            "min_interval_sec": min_interval,
            "max_applies_per_hour": per_hour,
            "max_applies_per_day": per_day,
        },
        "status": status,
        "reason": reason,
        "next_allowed_epoch": int(next_allowed_epoch),
        "counts": {
            "applies_last_hour": int(applies_last_hour),
            "applies_last_day": int(applies_last_day),
            "history_count": len(history),
        },
        "state": {
            "last_apply_epoch": last_apply,
            "apply_history_epochs": history,
        },
    }


def load_autoremediation_cadence_state(workspace_dir: Path) -> dict:
    path = _state_file_path(Path(workspace_dir).resolve())
    if not path.exists():
        return {"last_apply_epoch": 0, "apply_history_epochs": []}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"last_apply_epoch": 0, "apply_history_epochs": []}
    return {
        "last_apply_epoch": int(obj.get("last_apply_epoch", 0) or 0),
        "apply_history_epochs": _normalize_history(obj.get("apply_history_epochs", [])),
    }


def save_autoremediation_cadence_state(
    workspace_dir: Path,
    *,
    last_apply_epoch: int,
    apply_history_epochs: list[int],
) -> Path:
    workspace = Path(workspace_dir).resolve()
    path = _state_file_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_apply_epoch": max(0, int(last_apply_epoch)),
        "apply_history_epochs": _normalize_history(apply_history_epochs),
    }
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return path


def append_apply_history(
    apply_history_epochs: list[int] | None,
    *,
    applied_epoch: int,
    now_epoch: int,
    retention_sec: int = 86400,
) -> list[int]:
    history = _normalize_history(apply_history_epochs)
    applied = max(0, int(applied_epoch))
    now = max(0, int(now_epoch))
    keep_after = now - max(0, int(retention_sec))
    history = [ts for ts in history if ts >= keep_after]
    history.append(applied)
    return sorted(history)


def _normalize_history(values: list[int] | None) -> list[int]:
    out: list[int] = []
    for value in values or []:
        try:
            iv = int(value)
        except Exception:
            continue
        if iv >= 0:
            out.append(iv)
    return sorted(out)


def _state_file_path(workspace: Path) -> Path:
    return workspace / "artifacts" / STATE_FILE

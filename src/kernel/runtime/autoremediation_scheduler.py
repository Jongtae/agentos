from __future__ import annotations

import json
import time
from pathlib import Path

from kernel.runtime.policy_actions import policy_actions_report

STATE_FILE = "autoremediation_scheduler_state.json"


def autoremediation_scheduler_report(
    workspace_dir: Path,
    trace_file: Path | None = None,
    now_epoch: int | None = None,
    cooldown_sec: int = 900,
    max_consecutive_applies: int = 3,
    actions: list[dict] | None = None,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    now = int(time.time() if now_epoch is None else now_epoch)
    cooldown = max(0, int(cooldown_sec))
    max_consecutive = max(1, int(max_consecutive_applies))

    state = load_autoremediation_state(workspace)
    action_list = list(actions or _load_actions(workspace, trace_file))

    actionable_auto_safe = [
        item
        for item in action_list
        if bool(item.get("auto_safe", False))
        and str(item.get("id", "")) != "no_action_required"
        and str(item.get("recommended_command", "")).strip()
    ]
    manual_review = [item for item in action_list if not bool(item.get("auto_safe", False))]
    critical_count = sum(1 for item in action_list if str(item.get("severity", "")) == "critical")

    decision_status = "skip"
    decision_reason = "no_auto_safe_actions"
    next_allowed_epoch = now

    last_apply_epoch = int(state.get("last_apply_epoch", 0) or 0)
    consecutive_applies = int(state.get("consecutive_applies", 0) or 0)

    if critical_count > 0 and manual_review:
        decision_status = "hold"
        decision_reason = "critical_manual_review_required"
    elif not actionable_auto_safe:
        decision_status = "skip"
        decision_reason = "no_auto_safe_actions"
    elif last_apply_epoch > 0 and (now - last_apply_epoch) < cooldown:
        decision_status = "skip"
        decision_reason = "cooldown_active"
        next_allowed_epoch = last_apply_epoch + cooldown
    elif consecutive_applies >= max_consecutive:
        decision_status = "hold"
        decision_reason = "max_consecutive_applies_reached"
    else:
        decision_status = "apply"
        decision_reason = "eligible"

    return {
        "ok": True,
        "workspace": str(workspace),
        "now_epoch": now,
        "scheduler": {
            "cooldown_sec": cooldown,
            "max_consecutive_applies": max_consecutive,
        },
        "decision": {
            "status": decision_status,
            "reason": decision_reason,
            "next_allowed_epoch": next_allowed_epoch,
            "eligible_action_ids": [str(item.get("id", "")) for item in actionable_auto_safe],
        },
        "summary": {
            "action_total": len(action_list),
            "auto_safe_action_count": len(actionable_auto_safe),
            "manual_review_count": len(manual_review),
            "critical_count": critical_count,
        },
        "state": {
            "last_apply_epoch": last_apply_epoch,
            "consecutive_applies": consecutive_applies,
        },
    }


def load_autoremediation_state(workspace_dir: Path) -> dict:
    path = _state_file_path(Path(workspace_dir).resolve())
    if not path.exists():
        return {"last_apply_epoch": 0, "consecutive_applies": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"last_apply_epoch": 0, "consecutive_applies": 0}
    return {
        "last_apply_epoch": int(data.get("last_apply_epoch", 0) or 0),
        "consecutive_applies": int(data.get("consecutive_applies", 0) or 0),
    }


def save_autoremediation_state(
    workspace_dir: Path,
    *,
    last_apply_epoch: int,
    consecutive_applies: int,
) -> Path:
    workspace = Path(workspace_dir).resolve()
    state_file = _state_file_path(workspace)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_apply_epoch": max(0, int(last_apply_epoch)),
        "consecutive_applies": max(0, int(consecutive_applies)),
    }
    state_file.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return state_file


def _load_actions(workspace: Path, trace_file: Path | None) -> list[dict]:
    payload = policy_actions_report(workspace_dir=workspace, trace_file=trace_file)
    return list(payload.get("actions", []))


def _state_file_path(workspace: Path) -> Path:
    return workspace / "artifacts" / STATE_FILE

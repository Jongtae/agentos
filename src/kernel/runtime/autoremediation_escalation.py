from __future__ import annotations

import json
from pathlib import Path

STATE_FILE = "autoremediation_escalation_state.json"


def autoremediation_escalation_report(
    *,
    now_epoch: int,
    cadence_status: str,
    cadence_reason: str,
    scheduler_reason: str,
    execution_errors: int,
    hold_streak: int,
    failure_streak: int,
    last_escalation_epoch: int,
    min_escalation_interval_sec: int = 900,
) -> dict:
    now = max(0, int(now_epoch))
    errors = max(0, int(execution_errors))
    holds = max(0, int(hold_streak))
    failures = max(0, int(failure_streak))
    last_escalation = max(0, int(last_escalation_epoch))
    interval = max(0, int(min_escalation_interval_sec))

    should_escalate = False
    reason = "no_escalation"
    severity = "info"

    if last_escalation > 0 and (now - last_escalation) < interval:
        reason = "escalation_cooldown_active"
    elif errors > 0 and failures >= 1:
        should_escalate = True
        reason = "execution_errors_detected"
        severity = "critical"
    elif scheduler_reason == "critical_manual_review_required":
        should_escalate = True
        reason = "critical_manual_review_required"
        severity = "critical"
    elif cadence_status == "hold" and holds >= 3:
        should_escalate = True
        reason = "persistent_cadence_hold"
        severity = "warn"
    elif cadence_status == "hold" and cadence_reason in {
        "hourly_budget_exceeded",
        "daily_budget_exceeded",
    }:
        should_escalate = True
        reason = "budget_guardrail_saturated"
        severity = "warn"

    event = {
        "title": _title_for_reason(reason),
        "severity": severity,
        "reason": reason,
        "cadence_status": cadence_status,
        "cadence_reason": cadence_reason,
        "scheduler_reason": scheduler_reason,
        "execution_errors": errors,
        "hold_streak": holds,
        "failure_streak": failures,
        "timestamp_epoch": now,
    }

    return {
        "ok": True,
        "should_escalate": bool(should_escalate),
        "reason": reason,
        "severity": severity,
        "cooldown": {
            "min_escalation_interval_sec": interval,
            "last_escalation_epoch": last_escalation,
            "next_allowed_epoch": last_escalation + interval if last_escalation > 0 else now,
        },
        "event": event,
    }


def load_autoremediation_escalation_state(workspace_dir: Path) -> dict:
    path = _state_file_path(Path(workspace_dir).resolve())
    if not path.exists():
        return {"last_escalation_epoch": 0, "hold_streak": 0, "failure_streak": 0}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"last_escalation_epoch": 0, "hold_streak": 0, "failure_streak": 0}
    return {
        "last_escalation_epoch": int(obj.get("last_escalation_epoch", 0) or 0),
        "hold_streak": int(obj.get("hold_streak", 0) or 0),
        "failure_streak": int(obj.get("failure_streak", 0) or 0),
    }


def save_autoremediation_escalation_state(
    workspace_dir: Path,
    *,
    last_escalation_epoch: int,
    hold_streak: int,
    failure_streak: int,
) -> Path:
    workspace = Path(workspace_dir).resolve()
    path = _state_file_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_escalation_epoch": max(0, int(last_escalation_epoch)),
        "hold_streak": max(0, int(hold_streak)),
        "failure_streak": max(0, int(failure_streak)),
    }
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return path


def _title_for_reason(reason: str) -> str:
    mapping = {
        "execution_errors_detected": "Autoremediation execution errors detected",
        "critical_manual_review_required": "Critical manual review required",
        "persistent_cadence_hold": "Autoremediation cadence hold is persistent",
        "budget_guardrail_saturated": "Autoremediation budget guardrail saturated",
        "escalation_cooldown_active": "Escalation cooldown active",
        "no_escalation": "No escalation required",
    }
    return mapping.get(reason, "Autoremediation escalation update")


def _state_file_path(workspace: Path) -> Path:
    return workspace / "artifacts" / STATE_FILE

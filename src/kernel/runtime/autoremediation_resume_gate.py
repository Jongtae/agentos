from __future__ import annotations


def autoremediation_resume_gate_report(
    *,
    now_epoch: int,
    pause_state: dict,
    rollback_budget: dict,
    stage_governance: dict,
    min_resume_interval_sec: int = 300,
    max_resume_attempts: int = 5,
) -> dict:
    now = max(0, int(now_epoch))
    pause = pause_state or {}
    budget = rollback_budget or {}
    governance = stage_governance or {}

    is_paused = bool(pause.get("is_paused", False))
    cooldown_until = max(0, int(pause.get("cooldown_until_epoch", 0) or 0))
    resume_attempt_count = max(0, int(pause.get("resume_attempt_count", 0) or 0))
    last_resume_attempt_epoch = max(0, int(pause.get("last_resume_attempt_epoch", 0) or 0))
    budget_status = str(budget.get("status", "allow"))
    stage_decision = str(governance.get("decision", "hold"))
    min_interval = max(0, int(min_resume_interval_sec))
    max_attempts = max(1, int(max_resume_attempts))

    status = "hold"
    reason = "paused_state_missing_signal"
    next_check_epoch = now
    eligible_resume = False

    if not is_paused:
        status = "allow"
        reason = "not_paused"
        eligible_resume = True
    elif now < cooldown_until:
        status = "hold"
        reason = "pause_cooldown_active"
        next_check_epoch = cooldown_until
    elif budget_status == "handoff":
        status = "block"
        reason = "rollback_budget_exhausted"
    elif stage_decision == "handoff":
        status = "hold"
        reason = "stage_handoff_required"
    elif resume_attempt_count >= max_attempts:
        status = "block"
        reason = "max_resume_attempts_reached"
    elif last_resume_attempt_epoch > 0 and (now - last_resume_attempt_epoch) < min_interval:
        status = "hold"
        reason = "resume_interval_not_elapsed"
        next_check_epoch = last_resume_attempt_epoch + min_interval
    else:
        status = "allow"
        reason = "resume_eligible"
        eligible_resume = True

    return {
        "ok": True,
        "now_epoch": now,
        "decision": {
            "status": status,
            "reason": reason,
            "next_check_epoch": int(next_check_epoch),
            "eligible_resume": bool(eligible_resume),
        },
        "inputs": {
            "is_paused": is_paused,
            "cooldown_until_epoch": cooldown_until,
            "resume_attempt_count": resume_attempt_count,
            "last_resume_attempt_epoch": last_resume_attempt_epoch,
            "rollback_budget_status": budget_status,
            "stage_decision": stage_decision,
            "min_resume_interval_sec": min_interval,
            "max_resume_attempts": max_attempts,
        },
    }

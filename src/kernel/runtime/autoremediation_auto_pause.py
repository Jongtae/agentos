from __future__ import annotations


def autoremediation_auto_pause_report(
    *,
    rollback_budget: dict,
    stage_governance: dict,
    consecutive_holds: int = 0,
    hold_pause_threshold: int = 3,
    pause_cooldown_sec: int = 900,
) -> dict:
    budget = rollback_budget or {}
    governance = stage_governance or {}

    budget_status = str(budget.get("status", "allow"))
    budget_reason = str(budget.get("reason", "unknown"))
    stage_decision = str(governance.get("decision", "hold"))
    stage_reason = str(governance.get("reason", "unknown"))
    holds = max(0, int(consecutive_holds))
    threshold = max(1, int(hold_pause_threshold))

    should_pause = False
    reason = "pause_not_required"
    severity = "info"

    if budget_status == "handoff":
        should_pause = True
        reason = "rollback_budget_exhausted"
        severity = "critical"
    elif stage_decision == "handoff":
        should_pause = True
        reason = "stage_handoff_required"
        severity = "warn"
    elif holds >= threshold and stage_decision == "hold":
        should_pause = True
        reason = "persistent_stage_hold"
        severity = "warn"

    return {
        "ok": True,
        "should_pause": should_pause,
        "reason": reason,
        "severity": severity,
        "cooldown_sec": max(60, int(pause_cooldown_sec)),
        "inputs": {
            "budget_status": budget_status,
            "budget_reason": budget_reason,
            "stage_decision": stage_decision,
            "stage_reason": stage_reason,
            "consecutive_holds": holds,
            "hold_pause_threshold": threshold,
        },
    }

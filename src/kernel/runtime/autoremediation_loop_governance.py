from __future__ import annotations


def autoremediation_loop_governance_report(
    *,
    cycle_payload: dict,
    max_hold_streak_before_handoff: int = 3,
    max_failure_streak_before_handoff: int = 2,
) -> dict:
    payload = cycle_payload or {}
    cycle_mode = str(payload.get("execution_mode", "dry-run"))
    scheduler = payload.get("scheduler", {}) or {}
    cadence = payload.get("cadence", {}) or {}
    escalation = payload.get("escalation", {}) or {}
    project_direction = payload.get("project_direction", {}) or {}

    scheduler_decision = (scheduler.get("decision", {}) or {}) if isinstance(scheduler, dict) else {}
    scheduler_status = str(scheduler_decision.get("status", "skip"))
    scheduler_reason = str(scheduler_decision.get("reason", ""))

    cadence_status = str(cadence.get("status", "hold"))
    cadence_reason = str(cadence.get("reason", ""))

    escalation_required = bool(escalation.get("should_escalate", False))
    escalation_reason = str(escalation.get("reason", ""))
    event = escalation.get("event", {}) or {}
    hold_streak = int(event.get("hold_streak", 0) or 0)
    failure_streak = int(event.get("failure_streak", 0) or 0)
    project_direction_verdict = str(project_direction.get("verdict", "accept"))
    project_direction_reason = str(project_direction.get("reason", ""))

    decision = "hold"
    reason = "scheduler_blocked"

    if project_direction_verdict == "reject":
        decision = "handoff"
        reason = "project_direction_rejected"
    elif escalation_required and (
        hold_streak >= max(1, int(max_hold_streak_before_handoff))
        or failure_streak >= max(1, int(max_failure_streak_before_handoff))
        or escalation_reason in {"execution_errors_detected", "critical_manual_review_required"}
    ):
        decision = "handoff"
        reason = "operator_handoff_required"
    elif scheduler_status != "apply":
        decision = "hold"
        reason = "scheduler_blocked"
    elif cadence_status != "allow":
        decision = "hold"
        reason = "cadence_blocked"
    elif project_direction_verdict == "accept_with_risk":
        decision = "hold"
        reason = "project_direction_risk"
    elif cycle_mode == "apply":
        decision = "allow"
        reason = "cycle_apply_executed"
    else:
        decision = "allow"
        reason = "eligible_waiting_apply"

    return {
        "ok": True,
        "decision": decision,
        "reason": reason,
        "inputs": {
            "cycle_mode": cycle_mode,
            "scheduler_status": scheduler_status,
            "scheduler_reason": scheduler_reason,
            "cadence_status": cadence_status,
            "cadence_reason": cadence_reason,
            "escalation_required": escalation_required,
            "escalation_reason": escalation_reason,
            "hold_streak": hold_streak,
            "failure_streak": failure_streak,
            "project_direction_verdict": project_direction_verdict,
            "project_direction_reason": project_direction_reason,
        },
    }

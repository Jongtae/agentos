from __future__ import annotations

from datetime import datetime, timezone


def build_operator_handoff_payload(
    *,
    workspace: str,
    governance: dict,
    cycle_payload: dict,
    run_id: str,
) -> dict:
    gov = governance or {}
    cycle = cycle_payload or {}

    decision = str(gov.get("decision", "hold"))
    reason = str(gov.get("reason", "unknown"))
    inputs = gov.get("inputs", {}) or {}

    escalation = cycle.get("escalation", {}) or {}
    escalation_event = escalation.get("event", {}) or {}
    cadence = cycle.get("cadence", {}) or {}
    scheduler = cycle.get("scheduler", {}) or {}
    scheduler_decision = scheduler.get("decision", {}) or {}

    handoff_required = decision == "handoff"

    summary = {
        "decision": decision,
        "reason": reason,
        "scheduler_status": str(inputs.get("scheduler_status", scheduler_decision.get("status", ""))),
        "scheduler_reason": str(inputs.get("scheduler_reason", scheduler_decision.get("reason", ""))),
        "cadence_status": str(inputs.get("cadence_status", cadence.get("status", ""))),
        "cadence_reason": str(inputs.get("cadence_reason", cadence.get("reason", ""))),
        "escalation_reason": str(inputs.get("escalation_reason", escalation.get("reason", ""))),
        "hold_streak": int(inputs.get("hold_streak", escalation_event.get("hold_streak", 0)) or 0),
        "failure_streak": int(inputs.get("failure_streak", escalation_event.get("failure_streak", 0)) or 0),
    }

    actions = _recommended_actions(summary)

    return {
        "ok": True,
        "handoff_required": handoff_required,
        "run_id": str(run_id),
        "workspace": str(workspace),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "escalation_event": escalation_event,
        "recommended_actions": actions,
    }


def _recommended_actions(summary: dict) -> list[str]:
    reason = str(summary.get("reason", ""))
    escalation_reason = str(summary.get("escalation_reason", ""))
    actions: list[str] = []

    if reason == "operator_handoff_required":
        actions.append("review latest diagnostics manifest and governance summary")

    if escalation_reason in {"execution_errors_detected", "critical_manual_review_required"}:
        actions.append("pause autonomous apply mode and require manual approval")
        actions.append("inspect remediation execution results and rollback candidates")
    elif escalation_reason in {"persistent_cadence_hold", "budget_guardrail_saturated"}:
        actions.append("review cadence limits and recent apply history")

    if not actions:
        actions.append("no immediate operator action required")

    return actions

from __future__ import annotations


def autoremediation_forced_resume_report(
    *,
    resume_gate: dict,
    override_window: dict,
) -> dict:
    gate = resume_gate or {}
    override = override_window or {}

    decision = gate.get("decision", {}) or {}
    gate_status = str(decision.get("status", "hold"))
    gate_reason = str(decision.get("reason", "unknown"))
    gate_next_check = int(decision.get("next_check_epoch", 0) or 0)
    override_status = str(override.get("status", "inactive"))
    override_reason = str(override.get("reason", "no_override_window"))
    override_active = override_status == "active"

    status = gate_status
    reason = gate_reason
    forced = False
    operator_action = "none"

    if gate_status == "allow":
        status = "allow"
        reason = "resume_gate_allow"
    elif gate_status == "block" and gate_reason == "rollback_budget_exhausted":
        status = "block"
        reason = "rollback_budget_exhausted"
        operator_action = "manual_handoff"
    elif override_active and gate_status in {"hold", "block"}:
        status = "allow"
        reason = "operator_override_active"
        forced = True
    elif gate_status == "block":
        status = "block"
        reason = gate_reason
        operator_action = "manual_handoff"
    else:
        status = "hold"
        reason = gate_reason
        operator_action = "request_override"

    return {
        "ok": True,
        "decision": {
            "status": status,
            "reason": reason,
            "forced": bool(forced),
            "operator_action": operator_action,
            "next_check_epoch": gate_next_check,
        },
        "inputs": {
            "resume_gate_status": gate_status,
            "resume_gate_reason": gate_reason,
            "override_status": override_status,
            "override_reason": override_reason,
        },
    }

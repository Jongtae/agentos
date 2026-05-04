from __future__ import annotations


def autoremediation_batch_governance_report(
    *,
    campaign_payload: dict,
    max_handoff_rate: float = 0.30,
    max_error_runs: int = 1,
    max_blocked_runs: int = 1,
) -> dict:
    payload = campaign_payload or {}
    campaign_governance = payload.get("campaign_governance", {}) or {}
    run_results = list(payload.get("run_results", []) or [])
    total_runs = len(run_results)

    if total_runs <= 0:
        return {
            "ok": True,
            "decision": "hold",
            "reason": "no_runs",
            "totals": {
                "runs": 0,
                "failed_runs": 0,
                "handoff_runs": 0,
                "blocked_runs": 0,
                "eligible_runs": 0,
            },
            "handoff_rate": 0.0,
            "eligible_run_indexes": [],
        }

    campaign_decision = str(campaign_governance.get("decision", "hold"))
    campaign_reason = str(campaign_governance.get("reason", "unknown"))

    failed_runs = sum(1 for item in run_results if int(item.get("exit_code", 0) or 0) != 0)
    handoff_runs = sum(1 for item in run_results if str(item.get("decision", "")) == "handoff")
    blocked_runs = sum(1 for item in run_results if int(item.get("cycle_exit_code", 0) or 0) == 3)
    eligible_run_indexes = [
        idx
        for idx, item in enumerate(run_results, start=1)
        if int(item.get("exit_code", 0) or 0) == 0 and str(item.get("decision", "")) == "allow"
    ]
    eligible_runs = len(eligible_run_indexes)
    handoff_rate = float(handoff_runs / total_runs)

    decision = "allow"
    reason = "batch_ready"

    if campaign_decision == "handoff":
        decision = "handoff"
        reason = "campaign_requires_handoff"
    elif failed_runs > max(0, int(max_error_runs)):
        decision = "handoff"
        reason = "batch_error_runs_high"
    elif handoff_rate > float(max_handoff_rate):
        decision = "handoff"
        reason = "batch_handoff_rate_high"
    elif blocked_runs > max(0, int(max_blocked_runs)):
        decision = "hold"
        reason = "batch_blocked_runs_high"
    elif eligible_runs <= 0:
        decision = "hold"
        reason = "no_eligible_runs"

    return {
        "ok": True,
        "decision": decision,
        "reason": reason,
        "campaign_decision": campaign_decision,
        "campaign_reason": campaign_reason,
        "totals": {
            "runs": total_runs,
            "failed_runs": failed_runs,
            "handoff_runs": handoff_runs,
            "blocked_runs": blocked_runs,
            "eligible_runs": eligible_runs,
        },
        "handoff_rate": round(handoff_rate, 4),
        "eligible_run_indexes": eligible_run_indexes,
    }

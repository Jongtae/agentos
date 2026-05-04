from __future__ import annotations


def autoremediation_campaign_governance_report(
    *,
    run_results: list[dict],
    max_handoff_rate: float = 0.30,
    max_error_runs: int = 1,
) -> dict:
    runs = list(run_results or [])
    total = len(runs)
    if total <= 0:
        return {
            "ok": True,
            "decision": "hold",
            "reason": "no_runs",
            "totals": {
                "runs": 0,
                "allow": 0,
                "hold": 0,
                "handoff": 0,
                "error_runs": 0,
            },
            "handoff_rate": 0.0,
        }

    allow = sum(1 for r in runs if str(r.get("decision", "")) == "allow")
    hold = sum(1 for r in runs if str(r.get("decision", "")) == "hold")
    handoff = sum(1 for r in runs if str(r.get("decision", "")) == "handoff")
    error_runs = sum(1 for r in runs if int(r.get("exit_code", 0) or 0) != 0)

    handoff_rate = float(handoff / total)

    decision = "allow"
    reason = "campaign_healthy"

    if error_runs > max(0, int(max_error_runs)):
        decision = "handoff"
        reason = "campaign_error_rate_high"
    elif handoff_rate > float(max_handoff_rate):
        decision = "handoff"
        reason = "campaign_handoff_rate_high"
    elif hold >= max(2, total // 2 + 1):
        decision = "hold"
        reason = "campaign_mostly_hold"

    return {
        "ok": True,
        "decision": decision,
        "reason": reason,
        "totals": {
            "runs": total,
            "allow": allow,
            "hold": hold,
            "handoff": handoff,
            "error_runs": error_runs,
        },
        "handoff_rate": round(handoff_rate, 4),
    }

from __future__ import annotations


def autoremediation_rollback_budget_report(
    *,
    run_results: list[dict],
    rollback_budget: int = 2,
    window_size: int = 5,
    max_failures_per_window: int = 1,
) -> dict:
    results = list(run_results or [])
    budget_total = max(0, int(rollback_budget))
    lookback = max(1, int(window_size))
    recent = results[-lookback:]

    failure_indexes: list[int] = []
    for idx, item in enumerate(recent, start=max(1, len(results) - len(recent) + 1)):
        exit_code = int(item.get("exit_code", 0) or 0)
        decision = str(item.get("decision", ""))
        if exit_code != 0 or decision == "handoff":
            failure_indexes.append(idx)

    failures = len(failure_indexes)
    consumed = min(budget_total, failures)
    remaining = max(0, budget_total - consumed)

    status = "allow"
    reason = "rollback_budget_healthy"
    if remaining <= 0 and failures > 0:
        status = "handoff"
        reason = "rollback_budget_exhausted"
    elif failures > max(0, int(max_failures_per_window)):
        status = "hold"
        reason = "rollback_failure_pressure_high"

    return {
        "ok": True,
        "status": status,
        "reason": reason,
        "budget": {
            "total": budget_total,
            "consumed": consumed,
            "remaining": remaining,
        },
        "window": {
            "size": lookback,
            "evaluated_runs": len(recent),
            "failures": failures,
            "failure_run_indexes": failure_indexes,
            "max_failures_per_window": int(max_failures_per_window),
        },
    }

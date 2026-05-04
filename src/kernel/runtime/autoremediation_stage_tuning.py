from __future__ import annotations


def autoremediation_stage_tuning_report(
    *,
    stage_governance: dict,
    rollback_budget: dict,
    min_window_size: int = 1,
    max_window_size: int = 4,
) -> dict:
    governance = stage_governance or {}
    budget = rollback_budget or {}

    window = governance.get("stage_window", {}) or {}
    totals = governance.get("totals", {}) or {}
    decision = str(governance.get("decision", "hold"))
    budget_status = str(budget.get("status", "allow"))

    current_size = max(1, int(window.get("size", 1) or 1))
    current_cursor = max(0, int(window.get("next_cursor", 0) or 0))
    hotspots = max(0, int(totals.get("hotspots", 0) or 0))
    selected_runs = max(0, int(totals.get("selected_runs", 0) or 0))
    failures = max(0, int(((budget.get("window", {}) or {}).get("failures", 0) or 0)))

    min_size = max(1, int(min_window_size))
    max_size = max(min_size, int(max_window_size))

    target_size = current_size
    action = "maintain"
    reason = "stable_stage_window"

    if budget_status == "handoff":
        target_size = min_size
        action = "shrink"
        reason = "rollback_budget_exhausted"
    elif decision == "handoff":
        target_size = min_size
        action = "shrink"
        reason = "stage_handoff_pressure"
    elif hotspots > 0 or failures > 0:
        target_size = max(min_size, current_size - 1)
        action = "shrink" if target_size < current_size else "maintain"
        reason = "stability_pressure_detected"
    elif decision == "allow" and selected_runs > 0:
        target_size = min(max_size, current_size + 1)
        action = "expand" if target_size > current_size else "maintain"
        reason = "stable_progress_expand_window"

    return {
        "ok": True,
        "action": action,
        "reason": reason,
        "current": {
            "window_size": current_size,
            "cursor": current_cursor,
        },
        "next": {
            "window_size": target_size,
            "cursor": current_cursor,
            "min_window_size": min_size,
            "max_window_size": max_size,
        },
    }

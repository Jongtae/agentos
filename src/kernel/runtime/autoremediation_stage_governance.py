from __future__ import annotations


def autoremediation_stage_governance_report(
    *,
    batch_payload: dict,
    max_stage_actions: int = 2,
    max_hotspots_for_allow: int = 1,
    critical_hotspots_for_handoff: int = 3,
    stage_cursor: int = 0,
) -> dict:
    payload = batch_payload or {}
    batch_governance = payload.get("batch_governance", {}) or {}
    batch_review = payload.get("batch_review", {}) or {}

    batch_decision = str(batch_governance.get("decision", "hold"))
    batch_reason = str(batch_governance.get("reason", "unknown"))
    eligible = list(batch_governance.get("eligible_run_indexes", []) or [])
    hotspots = list(batch_review.get("hotspots", []) or [])

    stage_size = max(1, int(max_stage_actions))
    cursor = max(0, int(stage_cursor))
    selected = eligible[cursor : cursor + stage_size]
    next_cursor = cursor + len(selected)
    has_remaining = next_cursor < len(eligible)

    decision = "allow"
    reason = "stage_ready"

    if batch_decision == "handoff":
        decision = "handoff"
        reason = "batch_requires_handoff"
    elif len(hotspots) >= max(1, int(critical_hotspots_for_handoff)):
        decision = "handoff"
        reason = "stage_hotspots_critical"
    elif len(eligible) <= 0:
        decision = "hold"
        reason = "no_stage_candidates"
    elif len(hotspots) > max(0, int(max_hotspots_for_allow)):
        decision = "hold"
        reason = "stage_hotspots_high"
    elif len(selected) <= 0:
        decision = "hold"
        reason = "stage_window_exhausted"

    return {
        "ok": True,
        "decision": decision,
        "reason": reason,
        "batch_decision": batch_decision,
        "batch_reason": batch_reason,
        "totals": {
            "eligible_runs": len(eligible),
            "hotspots": len(hotspots),
            "selected_runs": len(selected),
        },
        "stage_window": {
            "cursor": cursor,
            "size": stage_size,
            "selected_run_indexes": selected,
            "next_cursor": next_cursor if has_remaining else 0,
            "has_remaining": has_remaining,
        },
    }

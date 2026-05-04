from __future__ import annotations


def build_campaign_review_payload(
    *,
    workspace: str,
    campaign_governance: dict,
    run_results: list[dict],
    run_id: str,
) -> dict:
    governance = campaign_governance or {}
    results = list(run_results or [])
    decision = str(governance.get("decision", "hold"))
    reason = str(governance.get("reason", "unknown"))

    hotspots: list[dict] = []
    for idx, item in enumerate(results, start=1):
        exit_code = int(item.get("exit_code", 0) or 0)
        run_decision = str(item.get("decision", ""))
        if exit_code != 0 or run_decision == "handoff":
            hotspots.append(
                {
                    "run_index": idx,
                    "decision": run_decision,
                    "exit_code": exit_code,
                    "reason": str(item.get("reason", "")),
                }
            )

    checklist = _checklist_for(decision=decision, reason=reason, hotspots=hotspots)

    return {
        "ok": True,
        "run_id": str(run_id),
        "workspace": str(workspace),
        "campaign_decision": decision,
        "campaign_reason": reason,
        "run_count": len(results),
        "hotspots": hotspots,
        "checklist": checklist,
    }


def _checklist_for(*, decision: str, reason: str, hotspots: list[dict]) -> list[str]:
    items: list[str] = []
    if decision == "handoff":
        items.append("review campaign governance and escalation trends")
        items.append("pause autonomous apply mode for affected workspace")
    elif decision == "hold":
        items.append("review cadence and scheduler blockers")
    else:
        items.append("no immediate campaign action required")

    if hotspots:
        items.append("inspect hotspot runs and remediation outputs")
    if reason == "campaign_error_rate_high":
        items.append("investigate failing runs and rollback candidates")
    return items

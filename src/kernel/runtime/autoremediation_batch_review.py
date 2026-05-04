from __future__ import annotations


def build_batch_review_payload(
    *,
    workspace: str,
    batch_governance: dict,
    campaign_payload: dict,
    run_id: str,
) -> dict:
    governance = batch_governance or {}
    payload = campaign_payload or {}
    run_results = list(payload.get("run_results", []) or [])

    decision = str(governance.get("decision", "hold"))
    reason = str(governance.get("reason", "unknown"))

    hotspots: list[dict] = []
    for idx, item in enumerate(run_results, start=1):
        exit_code = int(item.get("exit_code", 0) or 0)
        run_decision = str(item.get("decision", ""))
        cycle_exit_code = int(item.get("cycle_exit_code", 0) or 0)
        if exit_code != 0 or run_decision == "handoff" or cycle_exit_code == 3:
            hotspots.append(
                {
                    "run_index": idx,
                    "decision": run_decision,
                    "exit_code": exit_code,
                    "cycle_exit_code": cycle_exit_code,
                    "reason": str(item.get("reason", "")),
                }
            )

    checklist = _checklist_for(decision=decision, reason=reason, hotspots=hotspots)
    eligible_run_indexes = list(governance.get("eligible_run_indexes", []) or [])

    return {
        "ok": True,
        "run_id": str(run_id),
        "workspace": str(workspace),
        "batch_decision": decision,
        "batch_reason": reason,
        "run_count": len(run_results),
        "eligible_run_indexes": eligible_run_indexes,
        "hotspots": hotspots,
        "checklist": checklist,
    }


def _checklist_for(*, decision: str, reason: str, hotspots: list[dict]) -> list[str]:
    items: list[str] = []
    if decision == "handoff":
        items.append("escalate batch execution to operator")
        items.append("disable autonomous batch apply mode")
    elif decision == "hold":
        items.append("review blocked runs and governance thresholds")
    else:
        items.append("batch execution ready for auto-safe actions")

    if hotspots:
        items.append("inspect hotspot runs before batch apply")
    if reason in ["batch_error_runs_high", "batch_handoff_rate_high"]:
        items.append("audit unstable runs and rollback options")
    return items

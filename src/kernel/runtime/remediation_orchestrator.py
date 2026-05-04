from __future__ import annotations

from pathlib import Path

from kernel.runtime.policy_actions import policy_actions_report
from kernel.runtime.policy_executor import execute_policy_actions


def remediation_orchestration_report(
    workspace_dir: Path,
    trace_file: Path | None = None,
    apply: bool = False,
    max_actions: int = 10,
) -> dict:
    actions_report = policy_actions_report(workspace_dir=workspace_dir, trace_file=trace_file)
    actions = actions_report.get("actions", [])
    plan = _build_plan(actions)
    execution = execute_policy_actions(
        actions=actions,
        workspace_dir=workspace_dir,
        apply=apply,
        max_actions=max_actions,
    )
    rollback = _build_rollback_plan(actions, execution)
    return {
        "ok": True,
        "workspace": str(Path(workspace_dir).resolve()),
        "mode": "apply" if apply else "dry-run",
        "plan": plan,
        "execution": execution,
        "rollback": rollback,
    }


def _build_plan(actions: list[dict]) -> dict:
    high_risk = sum(1 for a in actions if str(a.get("severity", "")) == "critical")
    auto_safe = sum(1 for a in actions if bool(a.get("auto_safe", False)))
    manual = max(0, len(actions) - auto_safe)
    return {
        "action_total": len(actions),
        "auto_safe_count": auto_safe,
        "manual_review_count": manual,
        "critical_count": high_risk,
        "sequence": [str(a.get("id", "")) for a in actions],
    }


def _build_rollback_plan(actions: list[dict], execution: dict) -> dict:
    executed_ids = {
        str(item.get("action_id", ""))
        for item in execution.get("results", [])
        if str(item.get("status", "")) == "executed"
    }
    candidates: list[dict] = []
    for action in actions:
        aid = str(action.get("id", ""))
        if aid not in executed_ids:
            continue
        candidates.append(
            {
                "action_id": aid,
                "rollback_hint": f"re-run diagnostics and revert side effects for {aid}",
                "verification_command": "python3 scripts/runtime_governance_report.py --workspace ./workspaces/default",
            }
        )
    return {
        "required": bool(execution.get("errors", 0) or candidates),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }

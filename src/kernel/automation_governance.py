from __future__ import annotations

from pathlib import Path

from kernel.event_fabric.report import query_events

AUTOMATION_GOVERNANCE_SCHEMA_VERSION = "agentos-automation-governance.v1"


def _scheduled_tasks() -> list[dict]:
    return [
        {
            "automation_id": "review_bundle_history_archive",
            "category": "scheduled_task",
            "trigger": "cron_like",
            "default_action": "review_bundle_history",
            "governance_requirement": "approval_gated",
            "override_rule": "operator_override_allowed",
            "rollback_rule": "report_dir_restore",
        },
        {
            "automation_id": "validation_window_snapshot",
            "category": "scheduled_task",
            "trigger": "cron_like",
            "default_action": "validation_window",
            "governance_requirement": "approval_gated",
            "override_rule": "operator_override_allowed",
            "rollback_rule": "snapshot_revert",
        },
        {
            "automation_id": "review_bundle_export",
            "category": "scheduled_task",
            "trigger": "operator_scheduled_export",
            "default_action": "review_bundle",
            "governance_requirement": "approval_gated",
            "override_rule": "operator_override_allowed",
            "rollback_rule": "latest_manifest_restore",
        },
    ]


def _background_agents() -> list[dict]:
    return [
        {
            "agent_id": "runtime_autoremediation_loop",
            "category": "background_agent",
            "trigger": "continuous_loop",
            "default_action": "autoremediation_cycle",
            "governance_requirement": "observe_only",
            "override_rule": "pause_or_budget_override",
            "rollback_rule": "resume_gate_or_pause_state",
        },
        {
            "agent_id": "runtime_autoremediation_campaign",
            "category": "background_agent",
            "trigger": "campaign_window",
            "default_action": "campaign_governance_review",
            "governance_requirement": "approval_gated",
            "override_rule": "operator_override_allowed",
            "rollback_rule": "campaign_handoff",
        },
        {
            "agent_id": "runtime_autoremediation_stage_orchestrator",
            "category": "background_agent",
            "trigger": "stage_window",
            "default_action": "stage_orchestrator",
            "governance_requirement": "approval_gated",
            "override_rule": "forced_resume_override",
            "rollback_rule": "rollback_budget_handoff",
        },
    ]


def _override_and_rollback_rules() -> list[dict]:
    return [
        {
            "rule_id": "operator_override_allowed",
            "applies_to": ["scheduled_task", "background_agent"],
            "when": "explicit operator override with evidence trail",
            "effect": "allow execution while emitting override evidence",
        },
        {
            "rule_id": "pause_or_budget_override",
            "applies_to": ["background_agent"],
            "when": "autoremediation loop is paused or override budget is consumed",
            "effect": "hold or bypass apply path until cooldown or manual intervention",
        },
        {
            "rule_id": "snapshot_revert",
            "applies_to": ["scheduled_task"],
            "when": "scheduled validation/export produces bad state or stale artifact",
            "effect": "revert to prior snapshot or latest known-good manifest",
        },
        {
            "rule_id": "rollback_budget_handoff",
            "applies_to": ["background_agent"],
            "when": "stage or campaign automation exceeds rollback or failure budget",
            "effect": "handoff to operator review instead of further unattended execution",
        },
    ]


def build_automation_governance_report(workspace: str | Path) -> dict:
    workspace_path = Path(workspace).resolve()
    scheduled = _scheduled_tasks()
    background = _background_agents()
    rules = _override_and_rollback_rules()
    broker_events = query_events(workspace_path, source="broker", limit=200)
    operator_control = []
    override_actions = []
    for event in broker_events.get("events", []):
        decision = event.get("decision") or {}
        request_kind = str(decision.get("request_kind", ""))
        action = str(event.get("action", ""))
        item = {
            "timestamp_utc": event.get("timestamp_utc", ""),
            "action": action,
            "state": decision.get("state", ""),
            "request_kind": request_kind,
            "reason": decision.get("reason", ""),
        }
        if request_kind == "operator_control":
            operator_control.append(item)
        if request_kind == "override" or str(decision.get("state", "")) == "override":
            override_actions.append(item)

    summary = {
        "scheduled_task_count": len(scheduled),
        "background_agent_count": len(background),
        "approval_gated_items": sorted(
            [item["automation_id"] for item in scheduled if item["governance_requirement"] == "approval_gated"]
            + [item["agent_id"] for item in background if item["governance_requirement"] == "approval_gated"]
        ),
        "observe_only_agents": sorted([item["agent_id"] for item in background if item["governance_requirement"] == "observe_only"]),
        "operator_control_events": len(operator_control),
        "override_events": len(override_actions),
    }
    return {
        "schema_version": AUTOMATION_GOVERNANCE_SCHEMA_VERSION,
        "workspace": str(workspace_path),
        "scheduled_tasks": scheduled,
        "background_agents": background,
        "override_and_rollback_rules": rules,
        "evidence": {
            "operator_control_events": operator_control[-20:],
            "override_events": override_actions[-20:],
        },
        "summary": summary,
    }

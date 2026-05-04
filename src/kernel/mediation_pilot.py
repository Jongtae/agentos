from __future__ import annotations

from pathlib import Path

from kernel.broker.daemon import brokerd_report
from kernel.mediation_taxonomy import build_mediation_taxonomy
from kernel.policy_maturity import build_policy_maturity_report
from scripts.kernel_approval_forensics import build_approval_forensics

SCHEMA_VERSION = "agentos-mediation-pilot.v1"


def build_mediation_pilot_report(*, workspace: str) -> dict:
    workspace_path = Path(workspace).resolve()
    taxonomy = build_mediation_taxonomy(workspace=str(workspace_path))
    maturity = build_policy_maturity_report(str(workspace_path), parser_cmd="python3")
    approval = build_approval_forensics(str(workspace_path), limit=20)
    broker = brokerd_report(workspace_path)

    maturity_by_target = {item["policy_target"]: item for item in maturity.get("targets", [])}
    execution_by_name = {item["class_name"]: item for item in taxonomy.get("execution_classes", [])}
    approval_summary = approval.get("summary", {}) or {}
    broker_activity = broker.get("activity", {}) or {}

    selected_targets = [
        {
            "pilot_target": "interactive_user_destructive",
            "policy_target": "destructive_action_approval",
            "mandatory_state": execution_by_name.get("interactive_user_destructive", {}).get("target_state", "mandatory_broker"),
            "current_requirement": execution_by_name.get("interactive_user_destructive", {}).get("mediation_requirement", "approval_gated"),
            "coverage_summary": {
                "approval_requested": int(approval_summary.get("approval_requested", 0)),
                "approval_denied": int(approval_summary.get("approval_denied", 0)),
                "broker_override_count": int(approval_summary.get("broker_override_count", 0)),
            },
            "false_deny_tracking": (maturity_by_target.get("destructive_action_approval", {}) or {}).get("false_deny_tracking", {}),
            "recovery_tracking": {
                "forensic_status": str(approval_summary.get("forensic_status", "unknown")),
                "recovery_hints": list((approval.get("recovery") or {}).get("recovery_hints", [])),
            },
        },
        {
            "pilot_target": "operator_control_change",
            "policy_target": "operator_control",
            "mandatory_state": execution_by_name.get("operator_control_change", {}).get("target_state", "mandatory_broker"),
            "current_requirement": execution_by_name.get("operator_control_change", {}).get("mediation_requirement", "mandatory_broker"),
            "coverage_summary": {
                "operator_control_events": int((broker_activity.get("request_kind_counts") or {}).get("operator_control", 0)),
                "recent_high_risk": len(broker_activity.get("high_risk_recent", []) or []),
                "recent_actions": len(broker_activity.get("recent_actions", []) or []),
            },
            "false_deny_tracking": {
                "count": 0,
                "status": "monitor",
                "summary": "Operator-control mandatory paths currently track denied transitions through broker state and recovery logs.",
            },
            "recovery_tracking": {
                "recovery_hints": [
                    "AGENTOS_BROKER_BYPASS=1",
                    "AGENTOS_BROKER_OVERRIDE=1",
                    "scripts/agentos-kernelctl broker-status --workspace ./workspaces/default --json",
                ],
                "recent_actions": list(broker_activity.get("recent_actions", []) or [])[:5],
            },
        },
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "workspace": str(workspace_path),
        "selected_targets": selected_targets,
        "summary": {
            "pilot_target_count": len(selected_targets),
            "mandatory_targets": [item["pilot_target"] for item in selected_targets if item["mandatory_state"] == "mandatory_broker"],
            "false_deny_attention_targets": [
                item["pilot_target"]
                for item in selected_targets
                if int((item.get("false_deny_tracking") or {}).get("count", 0)) > 0
            ],
            "recovery_ready_targets": [
                item["pilot_target"]
                for item in selected_targets
                if (item.get("recovery_tracking") or {}).get("recovery_hints")
            ],
        },
    }

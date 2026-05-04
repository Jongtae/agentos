from __future__ import annotations

from pathlib import Path

SCHEMA_VERSION = "agentos-mediation-taxonomy.v1"


def mediation_classes() -> list[dict]:
    return [
        {
            "class_id": "allow_direct",
            "description": "Action may execute directly without broker mediation.",
            "intended_use": "low-risk local actions with no policy target pressure",
        },
        {
            "class_id": "observe_only",
            "description": "Action remains outside mandatory mediation but must emit evidence.",
            "intended_use": "early coverage where event fabric visibility matters more than control",
        },
        {
            "class_id": "approval_gated",
            "description": "Action may proceed only after explicit approval when triggered conditions match.",
            "intended_use": "high-impact user actions and sensitive operator workflows",
        },
        {
            "class_id": "guarded_enforce",
            "description": "Action is mediated and constrained by active policy guardrails.",
            "intended_use": "policy-backed control paths in shadow-to-enforce transition",
        },
        {
            "class_id": "mandatory_broker",
            "description": "Action must enter through the broker control plane and cannot bypass mediation in the default path.",
            "intended_use": "core sovereignty targets and critical system changes",
        },
    ]


def build_mediation_taxonomy(*, workspace: str) -> dict:
    workspace_path = str(Path(workspace).resolve())
    execution_classes = [
        {
            "class_name": "interactive_user_destructive",
            "origin_model": "user_intent",
            "examples": ["destructive_shell_exec", "file_overwrite"],
            "mediation_requirement": "approval_gated",
            "target_state": "mandatory_broker",
        },
        {
            "class_name": "interactive_user_network_sensitive",
            "origin_model": "user_intent",
            "examples": ["network_sensitive_exec", "browser_cross_domain_navigation"],
            "mediation_requirement": "approval_gated",
            "target_state": "guarded_enforce",
        },
        {
            "class_name": "operator_control_change",
            "origin_model": "user_intent",
            "examples": ["operator_control_change", "install_and_boot_integration"],
            "mediation_requirement": "mandatory_broker",
            "target_state": "mandatory_broker",
        },
        {
            "class_name": "service_background_system_action",
            "origin_model": "system_originated",
            "examples": ["service_and_background_governance"],
            "mediation_requirement": "observe_only",
            "target_state": "approval_gated",
        },
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "workspace": workspace_path,
        "origin_models": {
            "user_intent": {
                "description": "Action originates from an explicit user or operator request.",
                "default_expectation": "mediation becomes stronger as impact increases",
            },
            "system_originated": {
                "description": "Action originates from services, automation, background agents, or unattended lifecycle paths.",
                "default_expectation": "evidence must exist before mandatory mediation expands",
            },
        },
        "mediation_classes": mediation_classes(),
        "execution_classes": execution_classes,
        "summary": {
            "mediation_class_count": len(mediation_classes()),
            "execution_class_count": len(execution_classes),
            "user_intent_class_count": sum(1 for item in execution_classes if item["origin_model"] == "user_intent"),
            "system_originated_class_count": sum(1 for item in execution_classes if item["origin_model"] == "system_originated"),
            "mandatory_broker_targets": sorted(
                item["class_name"] for item in execution_classes if item["target_state"] == "mandatory_broker"
            ),
        },
    }

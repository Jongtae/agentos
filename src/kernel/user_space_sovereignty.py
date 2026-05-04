from __future__ import annotations

USER_SPACE_SOVEREIGNTY_SCHEMA_VERSION = "agentos-user-space-sovereignty.v1"


def launcher_semantics() -> dict:
    return {
        "primary_model": "intent_task_centric",
        "fallback_model": "app_shell_passthrough",
        "entry_contract": {
            "default_entry": "setup_or_ai_shell",
            "interactive_prompt": "ai>",
            "agentos_first": True,
        },
        "rules": [
            {
                "semantic_action": "open_workspace",
                "legacy_surface": "shell_cd_or_file_manager",
                "agentos_surface": "ai_shell",
                "intent": "move into a working context before tool execution",
            },
            {
                "semantic_action": "run_command",
                "legacy_surface": "terminal_command",
                "agentos_surface": "broker_mediated_tool_execution",
                "intent": "execute a controlled tool or command",
            },
            {
                "semantic_action": "inspect_system_state",
                "legacy_surface": "shell_status_commands",
                "agentos_surface": "kernelctl_status_or_evidence",
                "intent": "inspect runtime, policy, broker, and session state",
            },
            {
                "semantic_action": "change_system_behavior",
                "legacy_surface": "systemctl_or_manual_config_edit",
                "agentos_surface": "brokered_operator_control",
                "intent": "apply an operator-visible state transition",
            },
            {
                "semantic_action": "handoff_or_review",
                "legacy_surface": "manual_log_collection",
                "agentos_surface": "review_bundle",
                "intent": "export a portable operator handoff artifact",
            },
        ],
    }


def prioritized_actions() -> list[dict]:
    return [
        {
            "action_id": "inspect_runtime_state",
            "priority": "p0",
            "current_surface": "status/evidence",
            "target_surface": "agentos-kernelctl status|evidence",
            "coverage_state": "agentos_managed",
            "notes": "Primary read path for user and operator state inspection.",
        },
        {
            "action_id": "execute_high_impact_command",
            "priority": "p0",
            "current_surface": "tool_node_adapter + broker",
            "target_surface": "ai_shell broker mediation",
            "coverage_state": "agentos_managed",
            "notes": "High-impact execution should stay inside mediated intent semantics.",
        },
        {
            "action_id": "review_or_handoff_session",
            "priority": "p0",
            "current_surface": "review_bundle",
            "target_surface": "review_bundle default handoff",
            "coverage_state": "agentos_managed",
            "notes": "Portable operator review is already an AgentOS-native path.",
        },
        {
            "action_id": "change_service_or_policy_state",
            "priority": "p1",
            "current_surface": "service_governance + policy surfaces",
            "target_surface": "brokered operator control",
            "coverage_state": "agentos_guided",
            "notes": "Governed but not yet universal mandatory mediation.",
        },
        {
            "action_id": "launch_general_app_flow",
            "priority": "p2",
            "current_surface": "desktop/shell passthrough",
            "target_surface": "future intent launcher",
            "coverage_state": "passthrough",
            "notes": "Still outside AgentOS-first semantics and intentionally deferred.",
        },
    ]


def build_user_space_sovereignty_report(*, session_origin: dict, setup_state: dict, runtime_entry: dict, operator_mode: dict) -> dict:
    semantics = launcher_semantics()
    actions = prioritized_actions()
    managed = [item for item in actions if item["coverage_state"] == "agentos_managed"]
    guided = [item for item in actions if item["coverage_state"] == "agentos_guided"]
    passthrough = [item for item in actions if item["coverage_state"] == "passthrough"]
    return {
        "schema_version": USER_SPACE_SOVEREIGNTY_SCHEMA_VERSION,
        "session_origin": str(session_origin.get("category", "noninteractive") or "noninteractive"),
        "setup_status": str(setup_state.get("status", "pending") or "pending"),
        "launcher_semantics": semantics,
        "default_user_actions": actions,
        "status": {
            "agentos_first_entry": bool(runtime_entry.get("agentos_first", False)),
            "effective_target": str(runtime_entry.get("effective_target", "")),
            "fallback_target": str(runtime_entry.get("fallback_target", "")),
            "current_mode": str(operator_mode.get("current_mode", "user_mode")),
        },
        "summary": {
            "managed_action_count": len(managed),
            "guided_action_count": len(guided),
            "passthrough_action_count": len(passthrough),
            "agentos_first_entry": bool(runtime_entry.get("agentos_first", False)),
            "default_interaction_model": semantics["primary_model"],
            "priority_actions": [item["action_id"] for item in actions if item["priority"] == "p0"],
        },
    }

from __future__ import annotations

from kernel.appliance_platform import appliance_platform_state

RUNTIME_ENTRY_SCHEMA_VERSION = "agentos-runtime-entry.v1"


def runtime_entry_rules() -> list[dict]:
    return [
        {
            "rule_id": "live_appliance_boot",
            "origin": "live_appliance_boot",
            "behavior": "agentos_appliance",
            "target": "setup_or_ai_shell",
            "fallback_target": "agentos_recovery_shell",
            "notes": "preferred AgentOS-first live appliance boot path",
        },
        {
            "rule_id": "installed_appliance_boot",
            "origin": "installed_appliance_boot",
            "behavior": "agentos_appliance_installed",
            "target": "setup_or_ai_shell",
            "fallback_target": "agentos_recovery_shell",
            "notes": "preferred installed appliance persistence path after install-later",
        },
        {
            "rule_id": "local_managed_tty1",
            "origin": "local_managed_tty1",
            "behavior": "agentos_first",
            "target": "setup_or_ai_shell",
            "fallback_target": "normal_tty_shell",
            "notes": "default managed local tty1 path",
        },
        {
            "rule_id": "ssh_passthrough",
            "origin": "ssh",
            "behavior": "passthrough",
            "target": "login_shell",
            "fallback_target": "login_shell",
            "notes": "ssh sessions skip managed local autostart",
        },
        {
            "rule_id": "root_tty_recovery",
            "origin": "root_tty_recovery",
            "behavior": "recovery_passthrough",
            "target": "root_tty_shell",
            "fallback_target": "root_tty_shell",
            "notes": "root tty stays outside managed session entry",
        },
        {
            "rule_id": "noninteractive_passthrough",
            "origin": "noninteractive",
            "behavior": "passthrough",
            "target": "noninteractive_shell",
            "fallback_target": "noninteractive_shell",
            "notes": "noninteractive sessions must not trigger managed entry",
        },
        {
            "rule_id": "local_unmanaged_tty",
            "origin": "local_tty_unmanaged",
            "behavior": "passthrough",
            "target": "login_shell",
            "fallback_target": "login_shell",
            "notes": "local tty without managed entry remains a normal shell",
        },
    ]


def build_runtime_entry_contract(*, session_origin: dict, setup_state: dict) -> dict:
    origin = str(session_origin.get("category", "noninteractive") or "noninteractive")
    next_managed_entry = str(setup_state.get("next_managed_entry", "setup_session") or "setup_session")
    setup_status = str(setup_state.get("status", "pending") or "pending")
    platform_state = appliance_platform_state()

    rules = runtime_entry_rules()
    rule = next((item for item in rules if item["origin"] == origin), rules[-1])

    effective_target = rule["target"]
    if origin in {"local_managed_tty1", "live_appliance_boot", "installed_appliance_boot"}:
        effective_target = next_managed_entry

    return {
        "schema_version": RUNTIME_ENTRY_SCHEMA_VERSION,
        "primary_runtime": "codex_cli",
        "primary_runtime_provider": "codex",
        "managed_runtime_target": "codex_cli_managed_session",
        "launch_path_summary": [
            "Continue to AgentOS",
            "AgentOS Setup",
            "Codex CLI Managed Session",
            "ai>",
        ],
        "installed_launch_path_summary": [
            "Installed AgentOS Boot",
            "AgentOS Setup",
            "Codex CLI Managed Session",
            "ai>",
        ],
        "recovery_return_path_summary": [
            "AgentOS Recovery",
            "Return to AgentOS",
            "Codex CLI Managed Session",
            "ai>",
        ],
        "default_origin": "local_managed_tty1",
        "preferred_origin": "live_appliance_boot",
        "preferred_installed_origin": "installed_appliance_boot",
        "recovery_label": "AgentOS Recovery",
        "platform_model": platform_state["platform_model"],
        "update_model": platform_state["update_model"],
        "transitional_origin_vocabulary": True,
        "target_platform_states": [
            "live_appliance",
            "installed_slot_a",
            "installed_slot_b",
            "recovery_mode",
        ],
        "slot_aware_runtime": True,
        "current_origin": origin,
        "current_rule_id": rule["rule_id"],
        "behavior": rule["behavior"],
        "effective_target": effective_target,
        "fallback_target": rule["fallback_target"],
        "agentos_first": origin in {"local_managed_tty1", "live_appliance_boot", "installed_appliance_boot"},
        "appliance_boot": origin in {"live_appliance_boot", "installed_appliance_boot"},
        "installed_appliance_boot": origin == "installed_appliance_boot",
        "setup_status": setup_status,
        "next_managed_entry": next_managed_entry,
        "safe_mode_supported": True,
        "recovery_mode_supported": True,
        "bypass_mode_supported": True,
        "recovery_entry_points": [
            "AGENTOS_BOOT_AUTOSTART=0",
            "AGENTOS_BROKER_BYPASS=1",
            "AGENTOS_BROKER_OVERRIDE=1",
            "sudo scripts/uninstall_kernel_boot_integration.sh",
        ],
        "entry_rules": rules,
    }

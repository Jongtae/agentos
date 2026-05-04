from __future__ import annotations

import os

from kernel.appliance_platform import appliance_platform_state


SESSION_PHASES = (
    "boot_entry",
    "setup_session",
    "ai_shell",
    "guide_mode",
    "recovery_bypass",
)

SESSION_ORIGINS = (
    "live_appliance_boot",
    "installed_appliance_boot",
    "local_managed_tty1",
    "local_tty_unmanaged",
    "ssh",
    "root_tty_recovery",
    "noninteractive",
)

MANAGED_ENTRY_MODES = (
    "setup_session",
    "ai_shell",
    "guide_mode",
    "normal_shell",
)

SESSION_GATE_STATES = (
    "pass",
    "warn",
    "fail",
)


def session_correlation_contract() -> dict:
    return {
        "stable_keys": [
            "session_id",
            "request_id",
            "approval_id",
            "trace_id",
            "run_id",
            "boot_id",
        ],
        "session_phases": list(SESSION_PHASES),
        "session_origins": list(SESSION_ORIGINS),
        "managed_entry_modes": list(MANAGED_ENTRY_MODES),
        "transition_contract": {
            "setup_pending": {"phase": "setup_session", "next_managed_entry": "setup_session"},
            "setup_configured": {"phase": "ai_shell", "next_managed_entry": "ai_shell"},
            "guide_mode": {"phase": "guide_mode", "next_managed_entry": "guide_mode"},
            "autostart_disabled": {"phase": "recovery_bypass", "next_managed_entry": "normal_shell"},
        },
        "notes": [
            "session_id is the primary join key for boot/setup/session timelines",
            "boot_id groups events produced during the same managed boot window when available",
            "session_phase and next_managed_entry should use the locked vocabulary from this contract",
            "request_id and approval_id remain the preferred link back to runtime and broker decisions",
        ],
    }


def session_start_contract() -> dict:
    platform_state = appliance_platform_state()
    return {
        "schema_version": "agentos-session-contract.v1",
        "entry_path": ["boot_entry", "setup_session", "ai_shell"],
        "codex_primary_runtime_contract": {
            "primary_runtime": "codex_cli",
            "managed_runtime_target": "codex_cli_managed_session",
            "launch_path": [
                "Continue to AgentOS",
                "AgentOS Setup",
                "Codex CLI Managed Session",
                "ai>",
            ],
            "installed_launch_path": [
                "Installed AgentOS Boot",
                "AgentOS Setup",
                "Codex CLI Managed Session",
                "ai>",
            ],
            "recovery_return_path": [
                "AgentOS Recovery",
                "Return to AgentOS",
                "Codex CLI Managed Session",
                "ai>",
            ],
        },
        "codex_runtime_contract_ref": {
            "schema_version": "agentos-codex-runtime-contract.v1",
            "required_fields": [
                "provider_contract",
                "launch_contract",
                "env_contract",
                "workspace_contract",
                "state_contract",
                "continuity_contract",
            ],
            "runtime_owner": "codex_cli_managed_session",
        },
        "codex_persistent_state_contract": {
            "schema_version": "agentos-codex-persistent-state.v1",
            "runtime_owner": "codex_cli_managed_session",
            "required_paths": [
                "codex_runtime",
                "codex_session",
                "codex_logs",
                "codex_evidence",
            ],
            "continuity_flag": "runtime_continuity",
        },
        "codex_launch_supervision_contract": {
            "schema_version": "agentos-codex-launch-supervision.v1",
            "restart_policy": "on_failure",
            "rejoin_target": "codex_cli_managed_session",
            "recovery_target": "codex_runtime_recovery",
        },
        "codex_recovery_contract": {
            "schema_version": "agentos-codex-recovery-to-codex.v1",
            "return_label": "Return to AgentOS",
            "runtime_rejoin_target": "codex_cli_managed_session",
            "detailed_rejoin_path": [
                "AgentOS Recovery",
                "AgentOS Setup",
                "Codex CLI Managed Session",
                "ai>",
            ],
        },
        "codex_slot_transition_contract": {
            "schema_version": "agentos-codex-slot-transition-compatibility.v1",
            "runtime_return_target": "codex_cli_managed_session",
            "rollback_candidate_required": True,
            "continuity_goal": "rejoin managed Codex CLI session after slot transition or recovery",
        },
        "preferred_entry_origin": "live_appliance_boot",
        "preferred_installed_origin": "installed_appliance_boot",
        "install_later_contract": {
            "source_origin": "live_appliance_boot",
            "install_action_label": "Install AgentOS",
            "persistence_goal": "make_this_appliance_persistent",
            "target_origin": "installed_appliance_boot",
            "post_install_identity_path": [
                "AgentOS Setup",
                "AgentOS Managed Session",
                "ai>",
            ],
            "operator_note": "installed_appliance_boot is the intended persistence origin for appliance-first installs",
            "compatibility_note": "legacy tty1-installed compatibility remains available during migration but is no longer the preferred installed identity",
        },
        "installed_appliance_contract": {
            "origin": "installed_appliance_boot",
            "identity_path": [
                "AgentOS Setup",
                "AgentOS Managed Session",
                "ai>",
            ],
            "runtime_target": "codex_cli_managed_session",
            "managed_session_reachability_required": True,
            "replaces_legacy_compatibility_path": True,
            "legacy_origin": "local_managed_tty1",
            "notes": [
                "installed appliance boot keeps the same AgentOS-first identity promised by install-later",
                "legacy tty1 compatibility remains valid for migration and recovery diagnostics",
            ],
        },
        "platform_reset_contract": {
            "platform_model": platform_state["platform_model"],
            "update_model": platform_state["update_model"],
            "system_images_read_only": platform_state["system_images_read_only"],
            "state_partition_required": True,
            "recovery_mode_label": "Recovery",
            "target_platform_states": [
                "live_appliance",
                "installed_slot_a",
                "installed_slot_b",
                "recovery_mode",
            ],
            "migration_note": (
                "live_appliance_boot, installed_appliance_boot, and local_managed_tty1 remain transitional "
                "origin labels while AgentOS moves to slot-aware appliance platform states."
            ),
        },
        "recovery_contract": {
            "label": "AgentOS Recovery",
            "purpose": "beginner-safe path for falling back to a safe shell or temporarily relaxing managed entry controls",
            "default_shell_target": "normal_shell",
            "recovery_summary_path": [
                "AgentOS Recovery",
                "Return to AgentOS",
                "ai>",
            ],
            "recovery_identity_path": [
                "AgentOS Recovery",
                "AgentOS Setup",
                "AgentOS Managed Session",
                "ai>",
            ],
            "ladder": [
                {
                    "level": 1,
                    "label": "Keep a normal shell",
                    "trigger_env": "AGENTOS_BOOT_AUTOSTART=0",
                    "resulting_entry": "normal_shell",
                },
                {
                    "level": 2,
                    "label": "Keep AgentOS entry but bypass broker mediation",
                    "trigger_env": "AGENTOS_BROKER_BYPASS=1",
                    "resulting_entry": "managed_shell_with_broker_bypass",
                },
                {
                    "level": 3,
                    "label": "Keep AgentOS entry and emit override evidence",
                    "trigger_env": "AGENTOS_BROKER_OVERRIDE=1",
                    "resulting_entry": "managed_shell_with_override_events",
                },
                {
                    "level": 4,
                    "label": "Remove managed entry assets entirely",
                    "trigger_cmd": "sudo scripts/uninstall_kernel_boot_integration.sh",
                    "resulting_entry": "no_managed_entry_assets",
                },
            ],
        },
        "managed_entry_requirements": {
            "interactive_login_shell": True,
            "local_tty1_only": True,
            "live_appliance_allowed": True,
            "installed_appliance_allowed": True,
            "root_disabled": True,
            "ssh_disabled": True,
            "boot_autostart_env": "AGENTOS_BOOT_AUTOSTART",
            "managed_session_env": "AGENTOS_SESSION_MANAGED",
        },
        "readiness_gates": {
            "health": "runtime health check must be available",
            "engine": "kernel engine health must pass before managed ai_shell entry",
            "policy": "kernel policy readiness should be pass for hardened managed entry",
            "broker": "broker control plane artifacts should be available for mediated entry",
        },
        "mode_contract": {
            "managed_mode": {
                "resulting_entry": "setup_session_or_ai_shell",
                "required_env": ["AGENTOS_SESSION_MANAGED=1"],
                "supported_session_entries": [
                    "local_tty1",
                    "live_appliance",
                    "installed_appliance",
                ],
            },
            "safe_mode": {
                "resulting_entry": "guide_mode",
                "trigger": "provider none or deferred setup path",
            },
            "recovery_mode": {
                "resulting_entry": "normal_shell",
                "trigger_env": "AGENTOS_BOOT_AUTOSTART=0",
            },
            "bypass_mode": {
                "resulting_entry": "managed_shell_with_broker_bypass",
                "trigger_env": "AGENTOS_BROKER_BYPASS=1",
            },
            "override_mode": {
                "resulting_entry": "managed_shell_with_override_events",
                "trigger_env": "AGENTOS_BROKER_OVERRIDE=1",
            },
        },
        "recovery_ladder": [
            {
                "level": 1,
                "name": "normal_shell_fallback",
                "trigger_env": "AGENTOS_BOOT_AUTOSTART=0",
                "resulting_entry": "normal_shell",
            },
            {
                "level": 2,
                "name": "managed_entry_broker_bypass",
                "trigger_env": "AGENTOS_BROKER_BYPASS=1",
                "resulting_entry": "managed_shell_with_broker_bypass",
            },
            {
                "level": 3,
                "name": "managed_entry_override",
                "trigger_env": "AGENTOS_BROKER_OVERRIDE=1",
                "resulting_entry": "managed_shell_with_override_events",
            },
            {
                "level": 4,
                "name": "full_uninstall",
                "trigger_cmd": "sudo scripts/uninstall_kernel_boot_integration.sh",
                "resulting_entry": "no_managed_entry_assets",
            },
        ],
        "fallback_contract": {
            "managed_entry_failure_target": "normal_shell",
            "setup_pending_target": "setup_session",
            "setup_configured_target": "ai_shell",
            "guide_mode_target": "guide_mode",
        },
    }


def build_session_ownership_summary(
    *,
    session_origin: str,
    setup_status: str,
    next_managed_entry: str,
    session_id: str = "",
    boot_id: str = "",
    banner_version: str = "",
) -> dict:
    phase = "setup_session"
    if next_managed_entry == "ai_shell":
        phase = "ai_shell"
    elif next_managed_entry == "guide_mode":
        phase = "guide_mode"
    elif next_managed_entry == "normal_shell":
        phase = "recovery_bypass"

    managed = session_origin in {"local_managed_tty1", "live_appliance_boot", "installed_appliance_boot"}
    return {
        "managed": managed,
        "session_origin": session_origin,
        "setup_status": setup_status,
        "session_phase": phase,
        "next_managed_entry": next_managed_entry,
        "session_id": session_id,
        "boot_id": boot_id,
        "banner_version": banner_version,
    }


def evaluate_session_contract(
    *,
    runtime_ok: bool,
    engine_status: str,
    policy_status: str,
    broker_ok: bool,
    broker_artifacts_ready: bool,
    session_origin: dict,
    setup_state: dict,
) -> dict:
    gate_health = "pass" if runtime_ok else "fail"
    gate_engine = "pass" if str(engine_status).upper() == "PASS" else "fail"
    gate_policy = "pass" if str(policy_status).lower() == "pass" else "warn"
    gate_broker = "pass" if broker_ok and broker_artifacts_ready else "warn"

    gates = {
        "health": gate_health,
        "engine": gate_engine,
        "policy": gate_policy,
        "broker": gate_broker,
    }

    mode = "managed_mode"
    if os.environ.get("AGENTOS_BOOT_AUTOSTART", "1") != "1":
        mode = "recovery_mode"
    elif os.environ.get("AGENTOS_BROKER_BYPASS", "0") == "1":
        mode = "bypass_mode"
    elif os.environ.get("AGENTOS_BROKER_OVERRIDE", "0") == "1":
        mode = "override_mode"
    elif str(setup_state.get("next_managed_entry", "")) == "guide_mode":
        mode = "safe_mode"

    eligible = bool(
        session_origin.get("interactive", False)
        and not session_origin.get("ssh_active", False)
        and str(session_origin.get("session_entry", "")) in {"local_tty1", "live_appliance", "installed_appliance"}
        and str(session_origin.get("category", "")) != "root_tty_recovery"
    )

    overall = "pass"
    if "fail" in gates.values():
        overall = "fail"
    elif "warn" in gates.values():
        overall = "warn"

    return {
        "overall_status": overall,
        "managed_entry_eligible": eligible,
        "active_mode": mode,
        "gates": gates,
        "expected_next_entry": str(setup_state.get("next_managed_entry", "")),
        "fallback_target": "normal_shell" if mode == "recovery_mode" else str(setup_state.get("next_managed_entry", "")),
    }

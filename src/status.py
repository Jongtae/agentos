from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from io_utils import scrub_payload, scrub_sensitive_text, write_json_file
from kernel.engine import (
    CodexCliEngine,
    ClaudeEngineStub,
    EngineRouter,
    GeminiEngineStub,
    OllamaEngine,
    SetupGuideEngine,
)
from kernel.memory.store import MemoryStore
from kernel.policies.approval_rules import PolicyEngine, browser_policy_config_from_env
from kernel.runtime.trace import (
    approval_anomaly_from_counters,
    approval_counters_from_trace,
    resolve_runtime_trace_path,
)
from kernel.event_fabric.session_contract import (
    build_session_ownership_summary,
    evaluate_session_contract,
    session_correlation_contract,
    session_start_contract,
)
from kernel.appliance_platform import (
    appliance_platform_state,
    build_image_release_identity,
    build_recovery_mode_contract,
    build_slot_recovery_summary,
    build_slot_update_contract,
    build_state_partition_contract,
    build_state_root_usage_summary,
    build_system_image_layout_contract,
)
from kernel.codex_primary_runtime import build_codex_primary_runtime_summary
from kernel.codex_persistent_state import build_codex_persistent_state_summary
from kernel.codex_runtime_contract import build_codex_runtime_contract
from kernel.codex_launch_supervision import build_codex_launch_supervision_summary
from kernel.codex_recovery_to_codex import build_codex_recovery_to_codex_summary
from kernel.codex_slot_transition_compatibility import build_codex_slot_transition_compatibility_summary
from kernel.installed_boot_to_codex import build_installed_boot_to_codex_summary
from kernel.broker.daemon import brokerd_report
from kernel.runtime_entry import build_runtime_entry_contract
from kernel.operator_mode import operator_mode_contract
from kernel.user_space_sovereignty import build_user_space_sovereignty_report
from kernel.capability_substrate import (
    build_inbox_capability_report,
    build_inbox_normalized_intake_report,
    build_telegram_status_report,
    capability_vocabulary_contract,
    build_intake_surface_report,
)
from kernel.service_permission_capability import (
    build_permission_capability_report,
    build_service_capability_report,
)
from kernel.control_plane_capabilities import (
    build_execution_ownership_report,
)
from kernel.tools.browser_tool import (
    is_browser_tool_enabled,
    browser_worker_timeout_sec,
    resolve_browser_backend,
)


def _setup_state_summary() -> dict:
    env_file = Path(os.environ.get("AGENTOS_ENV_FILE", Path.home() / ".config" / "agentos" / "env"))
    exists = env_file.exists()
    return {
        "env_file": str(env_file),
        "env_file_exists": exists,
        "status": "configured" if exists else "pending",
        "next_managed_entry": "ai_shell" if exists else "setup_session",
    }


def _resolve_tty_path() -> str:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "isatty") and stream.isatty():
                return os.ttyname(stream.fileno())
        except Exception:
            continue
    return ""


def _session_origin_summary() -> dict:
    tty_path = _resolve_tty_path()
    interactive = bool(
        getattr(sys.stdin, "isatty", lambda: False)() and getattr(sys.stdout, "isatty", lambda: False)()
    )
    ssh_active = bool(os.environ.get("SSH_TTY") or os.environ.get("SSH_CONNECTION"))
    managed = os.environ.get("AGENTOS_SESSION_MANAGED", "") == "1"
    session_entry = str(os.environ.get("AGENTOS_SESSION_ENTRY", "")).strip()
    live_appliance = os.environ.get("AGENTOS_LIVE_APPLIANCE", "0") == "1" or session_entry == "live_appliance"
    installed_appliance = (
        os.environ.get("AGENTOS_INSTALLED_APPLIANCE", "0") == "1" or session_entry == "installed_appliance"
    )
    banner_version = str(os.environ.get("AGENTOS_SESSION_BANNER_VERSION", "")).strip()
    session_id = str(os.environ.get("AGENTOS_SESSION_ID", "")).strip()
    boot_id = str(os.environ.get("AGENTOS_BOOT_ID", "")).strip()

    category = "noninteractive"
    if managed and live_appliance:
        category = "live_appliance_boot"
    elif managed and installed_appliance:
        category = "installed_appliance_boot"
    elif managed and session_entry == "local_tty1":
        category = "local_managed_tty1"
    elif ssh_active:
        category = "ssh"
    elif tty_path and os.geteuid() == 0:
        category = "root_tty_recovery"
    elif tty_path:
        category = "local_tty_unmanaged"

    return {
        "category": category,
        "interactive": interactive,
        "managed": managed,
        "live_appliance": live_appliance,
        "installed_appliance": installed_appliance,
        "session_entry": session_entry,
        "banner_version": banner_version,
        "session_id": session_id,
        "boot_id": boot_id,
        "tty_path": tty_path,
        "ssh_active": ssh_active,
    }


def _session_origin_compatibility_summary(session_origin: dict) -> dict:
    category = str(session_origin.get("category", "")).strip()
    session_entry = str(session_origin.get("session_entry", "")).strip()

    if category == "live_appliance_boot":
        return {
            "path_family": "appliance_first",
            "compatibility_path": False,
            "label": "live_appliance",
            "description": "AgentOS-first live appliance session path.",
        }
    if category == "installed_appliance_boot":
        return {
            "path_family": "appliance_first",
            "compatibility_path": False,
            "label": "installed_appliance",
            "description": "Installed appliance persistence path that preserves the same AgentOS-first identity.",
        }
    if category == "local_managed_tty1":
        return {
            "path_family": "legacy_compatibility",
            "compatibility_path": True,
            "label": "legacy_tty1_installed",
            "description": "Legacy installed tty1 managed-session compatibility path.",
        }
    if category in {"local_tty_unmanaged", "root_tty_recovery", "ssh", "noninteractive"}:
        return {
            "path_family": "fallback_or_unmanaged",
            "compatibility_path": False,
            "label": session_entry or category or "unmanaged",
            "description": "Fallback, unmanaged, or operator-only session path.",
        }
    return {
        "path_family": "unknown",
        "compatibility_path": False,
        "label": session_entry or category or "unknown",
        "description": "Unknown or unclassified session origin.",
    }


def _install_later_summary(session_origin: dict, setup_state: dict) -> dict:
    category = str(session_origin.get("category", "")).strip()
    available = category == "live_appliance_boot"
    current_path = "legacy_tty1_compatibility"
    description = "Install-later is defined for live appliance sessions; current session is not on that path."
    if category == "live_appliance_boot":
        current_path = "live_appliance_to_installed_appliance_transition"
        description = (
            "Live appliance sessions should offer Install AgentOS as a persistence action while preserving the same AgentOS identity after reboot."
        )
    elif category == "installed_appliance_boot":
        current_path = "installed_appliance_boot"
        description = (
            "This session is already running on the installed appliance persistence path and should preserve the same AgentOS identity without re-entering the legacy tty1 route."
        )
    return {
        "available": available,
        "source_origin": category or "unknown",
        "install_action_label": "Install AgentOS",
        "persistence_goal": "make_this_appliance_persistent",
        "target_origin": "installed_appliance_boot",
        "current_install_path": current_path,
        "post_install_identity_path": [
            "AgentOS Setup",
            "AgentOS Managed Session",
            "ai>",
        ],
        "next_managed_entry": str(setup_state.get("next_managed_entry", "")),
        "description": description,
    }


def _recovery_path_summary(session_origin: dict, setup_state: dict) -> dict:
    category = str(session_origin.get("category", "")).strip() or "unknown"
    session_entry = str(session_origin.get("session_entry", "")).strip() or "unknown"
    next_managed_entry = str(setup_state.get("next_managed_entry", "")).strip() or "setup_session"
    recommended_rejoin_summary = [
        "AgentOS Recovery",
        "Return to AgentOS",
        "ai>",
    ]
    return {
        "label": "AgentOS Recovery",
        "current_origin": category,
        "session_entry": session_entry,
        "default_shell_target": "normal_shell",
        "runtime_rejoin_target": "codex_cli_managed_session",
        "recommended_rejoin_summary": recommended_rejoin_summary,
        "recommended_rejoin_path": [
            "AgentOS Recovery",
            "AgentOS Setup",
            "Codex CLI Managed Session",
            "ai>",
        ],
        "entry_points": [
            {
                "level": 1,
                "label": "Keep a normal shell",
                "trigger": "AGENTOS_BOOT_AUTOSTART=0",
                "resulting_entry": "normal_shell",
            },
            {
                "level": 2,
                "label": "Keep AgentOS entry but bypass broker mediation",
                "trigger": "AGENTOS_BROKER_BYPASS=1",
                "resulting_entry": "managed_shell_with_broker_bypass",
            },
            {
                "level": 3,
                "label": "Keep AgentOS entry and emit override evidence",
                "trigger": "AGENTOS_BROKER_OVERRIDE=1",
                "resulting_entry": "managed_shell_with_override_events",
            },
            {
                "level": 4,
                "label": "Remove managed entry assets entirely",
                "trigger": "sudo scripts/uninstall_kernel_boot_integration.sh",
                "resulting_entry": "no_managed_entry_assets",
            },
        ],
        "description": (
            "Use AgentOS Recovery when you need a safe shell. When you are ready, return to AgentOS and continue to the Codex CLI managed session."
        ),
        "rejoin_target": next_managed_entry,
    }






def _installed_boot_summary(session_origin: dict, setup_state: dict) -> dict:
    category = str(session_origin.get("category", "")).strip() or "unknown"
    boot_file = Path(os.environ.get("AGENTOS_INSTALLED_BOOT_FILE", "/tmp/agentos-installed-boot.env"))
    next_managed_entry = str(setup_state.get("next_managed_entry", "ai_shell")).strip() or "ai_shell"
    manifest_values: dict[str, str] = {}
    if boot_file.exists():
        for line in boot_file.read_text(encoding="utf-8").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            manifest_values[key.strip()] = value.strip()
    return {
        "available": category == "installed_appliance_boot",
        "origin": "installed_appliance_boot",
        "manifest_path": str(boot_file),
        "manifest_exists": boot_file.exists(),
        "identity_label": "Installed AgentOS Boot",
        "identity_path": ["AgentOS Setup", "AgentOS Managed Session", "ai>"],
        "recovery_path": ["AgentOS Recovery", "Return to AgentOS", "ai>"],
        "next_managed_entry": next_managed_entry,
        "runtime_owner": manifest_values.get("runtime_owner", "codex_cli_managed_session"),
        "runtime_target": manifest_values.get("runtime_target", "codex_cli_managed_session"),
        "runtime_continuity": manifest_values.get("runtime_continuity", "").lower() == "true",
        "description": "Installed appliance boot should return directly to the same AgentOS-owned setup and ai path without Ubuntu-first framing.",
    }

def _state_root_usage_summary() -> dict:
    usage = build_state_root_usage_summary()
    usage["summary"] = (
        "initialized" if usage.get("initialized") else "pending_initialization"
    )
    return usage

def _appliance_platform_summary() -> dict:
    state = appliance_platform_state()
    slot_update_contract = build_slot_update_contract()
    slot_recovery = build_slot_recovery_summary()
    effective_update_status = slot_update_contract.get("update_status", state["update_status"])
    return {
        **state,
        "active_slot": slot_update_contract["active_slot"],
        "inactive_slot": slot_update_contract["inactive_slot"],
        "rollback_slot": slot_update_contract["rollback_slot"],
        "next_slot": slot_update_contract["next_slot"],
        "metadata_file": slot_update_contract["metadata_file"],
        "metadata_exists": slot_update_contract["metadata_exists"],
        "next_boot_file": slot_update_contract["next_boot_file"],
        "next_boot_exists": slot_update_contract["next_boot_exists"],
        "next_boot_target": slot_update_contract["next_boot_target"],
        "staged_payload_file": slot_update_contract["staged_payload_file"],
        "staged_payload_exists": slot_update_contract["staged_payload_exists"],
        "update_status": effective_update_status,
        "slot_recovery": slot_recovery,
        "target_platform_states": [
            "live_appliance",
            "installed_slot_a",
            "installed_slot_b",
            "recovery_mode",
        ],
        "system_image_layout_contract": build_system_image_layout_contract(),
        "slot_update_contract": slot_update_contract,
        "recovery_mode_contract": build_recovery_mode_contract(),
        "state_partition_contract": build_state_partition_contract(),
        "image_release_identity": build_image_release_identity(),
    }


def _kernel_policy_ready_summary(wm) -> dict:
    parser_cmd = os.environ.get("AGENTOS_POLICY_PARSER_CMD", "apparmor_parser")
    policy_dir_raw = os.environ.get("AGENTOS_POLICY_DIR", "artifacts/kernel-policy")
    policy_dir = Path(policy_dir_raw)
    if not policy_dir.is_absolute():
        policy_dir = (wm.workspace_dir / policy_dir).resolve()

    profile_path = policy_dir / "agentos-kernel-policy.profile"
    state_path = policy_dir / "bridge-state.json"
    parser_path = shutil.which(parser_cmd) or ""
    parser_available = bool(parser_path)
    ready_for_enforced_pilot = parser_available and profile_path.exists() and state_path.exists()
    overall_status = "pass" if ready_for_enforced_pilot else "warn"
    workspace_root = ""
    expected_workspace_root = ""
    workspace_root_matches_runtime = False
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            workspace_root = str(state.get("workspace_root", ""))
        except Exception:
            workspace_root = ""
    root = Path(wm.workspace_root)
    if not root.is_absolute():
        root = (wm.workspace_dir / root).resolve()
    expected_workspace_root = str(root)
    workspace_root_matches_runtime = bool(workspace_root and workspace_root == expected_workspace_root)
    ready_for_enforced_pilot = ready_for_enforced_pilot and workspace_root_matches_runtime
    overall_status = "pass" if ready_for_enforced_pilot else "warn"

    return {
        "overall_status": overall_status,
        "policy_dir": str(policy_dir),
        "parser_cmd": parser_cmd,
        "parser_path": parser_path,
        "parser_available": parser_available,
        "profile_exists": profile_path.exists(),
        "state_exists": state_path.exists(),
        "workspace_root": workspace_root,
        "expected_workspace_root": expected_workspace_root,
        "workspace_root_matches_runtime": workspace_root_matches_runtime,
        "ready_for_enforced_pilot": ready_for_enforced_pilot,
    }


def status_report(wm) -> dict:
    tool_cfg = wm.spec.get("tools", {})
    enabled_tools = [name for name, enabled in tool_cfg.items() if bool(enabled)]
    browser_configured = bool(tool_cfg.get("browser", False))
    browser_flag = is_browser_tool_enabled()
    browser_runtime_enabled = browser_configured and browser_flag
    backend = resolve_browser_backend()
    policy = PolicyEngine(require_approval=wm.require_approval)
    policy.begin_run()
    policy_cfg = browser_policy_config_from_env()
    browser_runtime = {
        "configured": browser_configured,
        "feature_flag_enabled": browser_flag,
        "runtime_enabled": browser_runtime_enabled,
        "backend_requested": backend.requested,
        "backend_selected": backend.selected,
        "backend_fallback_reason": backend.fallback_reason,
        "policy_allowlist": policy_cfg["allowlist"],
        "policy_denylist": policy_cfg["denylist"],
        "policy_current_url": policy.browser_current_url,
        "worker_timeout_sec": browser_worker_timeout_sec(),
        "last_policy_decision": policy.last_browser_decision.state,
        "last_policy_reason": policy.last_browser_decision.reason,
    }
    trace_path = resolve_runtime_trace_path(wm.workspace_dir)
    approval_counters = approval_counters_from_trace(trace_path)
    approval_anomaly = approval_anomaly_from_counters(approval_counters)
    approval_counters["trace_file"] = str(trace_path)
    approval_counters.update(approval_anomaly)
    kernel_policy_ready = _kernel_policy_ready_summary(wm)
    setup_state = _setup_state_summary()
    session_origin = _session_origin_summary()
    origin_compatibility = _session_origin_compatibility_summary(session_origin)
    session_contract = session_correlation_contract()
    session_start = session_start_contract()
    session_ownership = build_session_ownership_summary(
        session_origin=session_origin["category"],
        setup_status=setup_state["status"],
        next_managed_entry=setup_state["next_managed_entry"],
        session_id=session_origin.get("session_id", ""),
        boot_id=session_origin.get("boot_id", ""),
        banner_version=session_origin.get("banner_version", ""),
    )
    broker_status = brokerd_report(Path(wm.workspace_dir))
    runtime_entry = build_runtime_entry_contract(session_origin=session_origin, setup_state=setup_state)
    operator_mode = operator_mode_contract(session_origin=session_origin, setup_state=setup_state)
    install_later = _install_later_summary(session_origin, setup_state)
    recovery_path = _recovery_path_summary(session_origin, setup_state)
    installed_boot = _installed_boot_summary(session_origin, setup_state)
    appliance_platform = _appliance_platform_summary()
    state_root_usage = _state_root_usage_summary()
    user_space_sovereignty = build_user_space_sovereignty_report(
        session_origin=session_origin,
        setup_state=setup_state,
        runtime_entry=runtime_entry,
        operator_mode=operator_mode,
    )
    capability_substrate = capability_vocabulary_contract()
    intake_surface = build_intake_surface_report(wm.workspace_dir, limit=10, write_manifest=False)
    inbox_capability = build_inbox_capability_report(wm.workspace_dir, session_id="", write_manifest=False)
    inbox_normalized_intake = build_inbox_normalized_intake_report(wm.workspace_dir, session_id="", write_manifest=False)
    telegram_ingress = build_telegram_status_report(wm.workspace_dir, session_id="", write_manifest=False)
    service_capability = build_service_capability_report(wm.workspace_dir, write_manifest=False)
    permission_capability = build_permission_capability_report(wm.workspace_dir, write_manifest=False)
    execution_ownership = build_execution_ownership_report(wm.workspace_dir, samples=[], write_manifest=False)

    memory = MemoryStore(wm.memory_store_path)
    memory_count = memory.count()

    router = EngineRouter(
        mode=wm.kernel_engine_mode,
        engines={
            "codex": CodexCliEngine(
                workspace_dir=wm.workspace_dir,
                command=wm.codex_command,
                timeout_sec=wm.codex_timeout_sec,
                model=wm.codex_model,
            ),
            "ollama": OllamaEngine(
                workspace_dir=wm.workspace_dir,
                command=wm.ollama_command,
                timeout_sec=wm.ollama_timeout_sec,
                model=wm.ollama_model,
            ),
            "none": SetupGuideEngine(),
            "claude": ClaudeEngineStub(),
            "gemini": GeminiEngineStub(),
        },
    )

    provider = wm.kernel_engine_provider or "ollama"
    engine_command = ""
    engine_timeout_sec = 0
    engine_model = ""
    if provider == "codex":
        engine_command = wm.codex_command
        engine_timeout_sec = wm.codex_timeout_sec
        engine_model = wm.codex_model
    elif provider == "ollama":
        engine_command = wm.ollama_command
        engine_timeout_sec = wm.ollama_timeout_sec
        engine_model = wm.ollama_model

    try:
        engine = router.get_engine(provider)
    except ValueError as e:
        codex_primary_runtime = build_codex_primary_runtime_summary(
            provider=provider,
            command=wm.codex_command,
            model=wm.codex_model,
            engine_status="FAIL",
            session_origin=session_origin,
            setup_state=setup_state,
            install_later=install_later,
            recovery_path=recovery_path,
            installed_boot=installed_boot,
        )
        codex_runtime_contract = build_codex_runtime_contract(
            workspace_dir=str(wm.workspace_dir),
            workspace_root=wm.workspace_root,
            provider=provider,
            command=wm.codex_command,
            timeout_sec=wm.codex_timeout_sec,
            model=wm.codex_model,
            engine_status="FAIL",
            session_origin=session_origin,
            setup_state=setup_state,
            install_later=install_later,
            recovery_path=recovery_path,
            installed_boot=installed_boot,
        )
        codex_launch_supervision = build_codex_launch_supervision_summary(
            state_root=state_root_usage["state_root"],
            provider=provider,
            engine_status="FAIL",
            restart_policy=wm.codex_restart_policy,
            max_attempts=wm.codex_max_attempts,
            cooldown_sec=wm.codex_cooldown_sec,
        )
        codex_persistent_state = build_codex_persistent_state_summary(
            state_root_usage=state_root_usage,
            runtime_contract=codex_runtime_contract,
            install_later=install_later,
            installed_boot=installed_boot,
        )
        codex_recovery_to_codex = build_codex_recovery_to_codex_summary(
            recovery_path=recovery_path,
            runtime_contract=codex_runtime_contract,
            launch_supervision=codex_launch_supervision,
            slot_recovery=appliance_platform["slot_recovery"],
        )
        installed_boot_to_codex = build_installed_boot_to_codex_summary(
            installed_boot=installed_boot,
            primary_runtime=codex_primary_runtime,
            runtime_contract=codex_runtime_contract,
            next_boot_target=appliance_platform["next_boot_target"],
        )
        codex_slot_transition_compatibility = build_codex_slot_transition_compatibility_summary(
            slot_update_contract=appliance_platform["slot_update_contract"],
            next_boot_target=appliance_platform["next_boot_target"],
            slot_recovery=appliance_platform["slot_recovery"],
            installed_boot_to_codex=installed_boot_to_codex,
            recovery_to_codex=codex_recovery_to_codex,
        )
        session_contract_validation = evaluate_session_contract(
            runtime_ok=False,
            engine_status="FAIL",
            policy_status=kernel_policy_ready["overall_status"],
            broker_ok=bool(broker_status.get("ok", False)),
            broker_artifacts_ready=bool(broker_status.get("artifacts_ready", False)),
            session_origin=session_origin,
            setup_state=setup_state,
        )
        return {
            "ok": False,
            "exit_code": 1,
            "workspace": str(wm.workspace_dir),
            "workspace_name": wm.name,
            "tools_enabled": enabled_tools,
            "approval_required": wm.require_approval,
            "max_steps": wm.max_steps,
            "memory_db": wm.memory_store_path,
            "memory_items": memory_count,
            "kernel_engine_mode": wm.kernel_engine_mode,
            "kernel_engine_provider": wm.kernel_engine_provider or "",
            "checked_provider": provider,
            "engine_status": "FAIL",
            "engine_reason": "invalid_provider",
            "engine_detail": scrub_sensitive_text(str(e)),
            "engine_command": engine_command,
            "engine_timeout_sec": engine_timeout_sec,
            "engine_model": engine_model,
            "web_allowlist": wm.web_allowlist,
            "browser_runtime": browser_runtime,
            "capability_substrate": capability_substrate,
            "intake_surface": intake_surface,
            "inbox_capability": inbox_capability,
            "inbox_normalized_intake": inbox_normalized_intake,
            "telegram_ingress": telegram_ingress,
            "service_capability": service_capability,
            "permission_capability": permission_capability,
            "execution_ownership": execution_ownership,
            "approval_counters": approval_counters,
            "kernel_policy_ready": kernel_policy_ready,
            "setup_state": setup_state,
            "session_origin": session_origin,
            "session_origin_compatibility": origin_compatibility,
            "session_contract": session_contract,
            "session_start_contract": session_start,
            "install_later": install_later,
            "recovery_path": recovery_path,
            "installed_boot": installed_boot,
            "session_ownership": session_ownership,
            "runtime_entry": runtime_entry,
            "operator_mode": operator_mode,
            "appliance_platform": appliance_platform,
            "state_root_usage": state_root_usage,
            "codex_primary_runtime": codex_primary_runtime,
            "codex_persistent_state": codex_persistent_state,
            "codex_runtime_contract": codex_runtime_contract,
            "codex_launch_supervision": codex_launch_supervision,
            "codex_recovery_to_codex": codex_recovery_to_codex,
            "installed_boot_to_codex": installed_boot_to_codex,
            "codex_slot_transition_compatibility": codex_slot_transition_compatibility,
            "user_space_sovereignty": user_space_sovereignty,
            "session_contract_validation": session_contract_validation,
        }

    health = engine.health_check()
    codex_primary_runtime = build_codex_primary_runtime_summary(
        provider=provider,
        command=wm.codex_command,
        model=wm.codex_model,
        engine_status="PASS" if health.ok else "FAIL",
        session_origin=session_origin,
        setup_state=setup_state,
        install_later=install_later,
        recovery_path=recovery_path,
        installed_boot=installed_boot,
    )
    codex_runtime_contract = build_codex_runtime_contract(
        workspace_dir=str(wm.workspace_dir),
        workspace_root=wm.workspace_root,
        provider=provider,
        command=wm.codex_command,
        timeout_sec=wm.codex_timeout_sec,
        model=wm.codex_model,
        engine_status="PASS" if health.ok else "FAIL",
        session_origin=session_origin,
        setup_state=setup_state,
        install_later=install_later,
        recovery_path=recovery_path,
        installed_boot=installed_boot,
    )
    codex_launch_supervision = build_codex_launch_supervision_summary(
        state_root=state_root_usage["state_root"],
        provider=provider,
        engine_status="PASS" if health.ok else "FAIL",
        restart_policy=wm.codex_restart_policy,
        max_attempts=wm.codex_max_attempts,
        cooldown_sec=wm.codex_cooldown_sec,
    )
    codex_persistent_state = build_codex_persistent_state_summary(
        state_root_usage=state_root_usage,
        runtime_contract=codex_runtime_contract,
        install_later=install_later,
        installed_boot=installed_boot,
    )
    codex_recovery_to_codex = build_codex_recovery_to_codex_summary(
        recovery_path=recovery_path,
        runtime_contract=codex_runtime_contract,
        launch_supervision=codex_launch_supervision,
        slot_recovery=appliance_platform["slot_recovery"],
    )
    installed_boot_to_codex = build_installed_boot_to_codex_summary(
        installed_boot=installed_boot,
        primary_runtime=codex_primary_runtime,
        runtime_contract=codex_runtime_contract,
        next_boot_target=appliance_platform["next_boot_target"],
    )
    codex_slot_transition_compatibility = build_codex_slot_transition_compatibility_summary(
        slot_update_contract=appliance_platform["slot_update_contract"],
        next_boot_target=appliance_platform["next_boot_target"],
        slot_recovery=appliance_platform["slot_recovery"],
        installed_boot_to_codex=installed_boot_to_codex,
        recovery_to_codex=codex_recovery_to_codex,
    )
    session_contract_validation = evaluate_session_contract(
        runtime_ok=bool(health.ok),
        engine_status="PASS" if health.ok else "FAIL",
        policy_status=kernel_policy_ready["overall_status"],
        broker_ok=bool(broker_status.get("ok", False)),
        broker_artifacts_ready=bool(broker_status.get("artifacts_ready", False)),
        session_origin=session_origin,
        setup_state=setup_state,
    )
    return {
        "ok": bool(health.ok),
        "exit_code": 0 if health.ok else 1,
        "workspace": str(wm.workspace_dir),
        "workspace_name": wm.name,
        "tools_enabled": enabled_tools,
        "approval_required": wm.require_approval,
        "max_steps": wm.max_steps,
        "memory_db": wm.memory_store_path,
        "memory_items": memory_count,
        "kernel_engine_mode": wm.kernel_engine_mode,
        "kernel_engine_provider": wm.kernel_engine_provider or "",
        "checked_provider": provider,
        "engine_status": "PASS" if health.ok else "FAIL",
        "engine_reason": health.reason,
        "engine_detail": health.detail,
        "engine_command": engine_command,
        "engine_timeout_sec": engine_timeout_sec,
        "engine_model": engine_model,
        "web_allowlist": wm.web_allowlist,
        "browser_runtime": browser_runtime,
        "capability_substrate": capability_substrate,
        "intake_surface": intake_surface,
        "inbox_capability": inbox_capability,
        "inbox_normalized_intake": inbox_normalized_intake,
        "telegram_ingress": telegram_ingress,
        "service_capability": service_capability,
        "permission_capability": permission_capability,
        "execution_ownership": execution_ownership,
        "approval_counters": approval_counters,
        "kernel_policy_ready": kernel_policy_ready,
        "setup_state": setup_state,
        "session_origin": session_origin,
        "session_origin_compatibility": origin_compatibility,
        "session_contract": session_contract,
        "session_start_contract": session_start,
        "install_later": install_later,
        "recovery_path": recovery_path,
        "installed_boot": installed_boot,
        "session_ownership": session_ownership,
        "runtime_entry": runtime_entry,
        "operator_mode": operator_mode,
        "appliance_platform": appliance_platform,
        "state_root_usage": state_root_usage,
        "codex_primary_runtime": codex_primary_runtime,
        "codex_persistent_state": codex_persistent_state,
        "codex_runtime_contract": codex_runtime_contract,
        "codex_launch_supervision": codex_launch_supervision,
        "codex_recovery_to_codex": codex_recovery_to_codex,
        "installed_boot_to_codex": installed_boot_to_codex,
        "codex_slot_transition_compatibility": codex_slot_transition_compatibility,
        "user_space_sovereignty": user_space_sovereignty,
        "session_contract_validation": session_contract_validation,
    }


def run_status(wm, as_json: bool = False, output_file: str = "") -> int:
    """Print effective runtime status. Returns 0 when healthy, 1 when unhealthy."""
    report = status_report(wm)
    if output_file:
        write_json_file(output_file, report)
    if as_json:
        print(json.dumps(scrub_payload(report), ensure_ascii=True))
        return int(report["exit_code"])

    print("AgentOS Status")
    print("=============")
    print(f"Workspace: {report['workspace']}")
    print(f"Workspace name: {report['workspace_name']}")
    print(f"Tools enabled: {', '.join(report['tools_enabled']) if report['tools_enabled'] else '(none)'}")
    print(f"Approval required: {report['approval_required']}")
    print(f"Max steps: {report['max_steps']}")
    print(f"Memory DB: {report['memory_db']}")
    print(f"Memory items: {report['memory_items']}")
    print(f"Kernel engine mode: {report['kernel_engine_mode']}")
    print(f"Kernel engine provider: {report['kernel_engine_provider'] or '(not selected -> ollama default for health check)'}")
    setup = report["setup_state"]
    session_origin = report["session_origin"]
    origin_compatibility = report["session_origin_compatibility"]
    install_later = report["install_later"]
    recovery_path = report["recovery_path"]
    installed_boot = report["installed_boot"]
    appliance_platform = report["appliance_platform"]
    state_root_usage = report["state_root_usage"]
    codex_primary_runtime = report["codex_primary_runtime"]
    codex_persistent_state = report["codex_persistent_state"]
    codex_runtime_contract = report["codex_runtime_contract"]
    codex_launch_supervision = report["codex_launch_supervision"]
    codex_recovery_to_codex = report["codex_recovery_to_codex"]
    installed_boot_to_codex = report["installed_boot_to_codex"]
    codex_slot_transition_compatibility = report["codex_slot_transition_compatibility"]
    capability_substrate = report["capability_substrate"]
    intake_surface = report["intake_surface"]
    inbox_capability = report["inbox_capability"]
    inbox_normalized_intake = report["inbox_normalized_intake"]
    telegram_ingress = report["telegram_ingress"]
    service_capability = report["service_capability"]
    permission_capability = report["permission_capability"]
    execution_ownership = report["execution_ownership"]
    print(
        "Setup status: "
        f"{setup['status']} "
        f"(next_managed_entry={setup['next_managed_entry']}, env_file={setup['env_file']})"
    )
    print(
        "Session origin: "
        f"{session_origin['category']} "
        f"(managed={session_origin['managed']}, "
        f"interactive={session_origin['interactive']}, "
        f"entry={session_origin['session_entry'] or 'none'}, "
        f"tty={session_origin['tty_path'] or 'none'})"
    )
    print(
        "Session path family: "
        f"{origin_compatibility['path_family']} "
        f"(label={origin_compatibility['label']}, "
        f"compatibility_path={origin_compatibility['compatibility_path']})"
    )
    print(
        "Install-later path: "
        f"available={install_later['available']} "
        f"(source={install_later['source_origin']}, "
        f"target={install_later['target_origin']}, "
        f"identity={' -> '.join(install_later['post_install_identity_path'])})"
    )
    print(
        "Recovery path: "
        f"{recovery_path['label']} "
        f"(origin={recovery_path['current_origin']}, "
        f"default_shell={recovery_path['default_shell_target']}, "
        f"summary={' -> '.join(recovery_path['recommended_rejoin_summary'])}, "
        f"rejoin={' -> '.join(recovery_path['recommended_rejoin_path'])})"
    )
    print(
        "Installed boot: "
        f"available={installed_boot['available']}, "
        f"manifest={installed_boot['manifest_exists']}, "
        f"identity={' -> '.join(installed_boot['identity_path'])}, "
        f"recovery={' -> '.join(installed_boot['recovery_path'])}"
    )
    print(
        "Codex primary runtime: "
        f"provider={codex_primary_runtime['configured_provider'] or 'none'}, "
        f"matches_primary={codex_primary_runtime['provider_matches_primary']}, "
        f"command_available={codex_primary_runtime['command_available']}, "
        f"target={codex_primary_runtime['managed_runtime_target']}, "
        f"proof={codex_primary_runtime['proof_status']}"
    )
    print(
        "Codex persistent state: "
        f"owner={codex_persistent_state['runtime_owner']}, "
        f"continuity_ready={codex_persistent_state['continuity_ready']}, "
        f"manifest={codex_persistent_state['manifest_exists']}, "
        f"paths_ready={codex_persistent_state['runtime_state_paths_ready']}, "
        f"proof={codex_persistent_state['proof_status']}"
    )
    print(
        "Codex runtime contract: "
        f"workspace={codex_runtime_contract['workspace_contract']['workspace_dir']}, "
        f"state={codex_runtime_contract['state_contract']['state_root']}, "
        f"rejoin={codex_runtime_contract['continuity_contract']['rejoin_target']}, "
        f"proof={codex_runtime_contract['proof_status']}"
    )
    print(
        "Codex launch supervision: "
        f"policy={codex_launch_supervision['restart_policy']}, "
        f"attempts={codex_launch_supervision['attempt_count']}, "
        f"restarts={codex_launch_supervision['restart_count']}, "
        f"next={codex_launch_supervision['next_action']}"
    )
    print(
        "Recovery to Codex: "
        f"target={codex_recovery_to_codex['runtime_rejoin_target']}, "
        f"ready={codex_recovery_to_codex['recovery_ready']}, "
        f"return={codex_recovery_to_codex['return_label']}"
    )
    print(
        "Installed boot to Codex: "
        f"target={installed_boot_to_codex['runtime_target']}, "
        f"reachable={installed_boot_to_codex['managed_session_reachable']}, "
        f"slot={installed_boot_to_codex['target_slot'] or 'none'}, "
        f"proof={installed_boot_to_codex['proof_status']}"
    )
    print(
        "Codex slot transition: "
        f"target_slot={codex_slot_transition_compatibility['target_slot'] or 'none'}, "
        f"next_action={codex_slot_transition_compatibility['next_action']}, "
        f"continuity_ready={codex_slot_transition_compatibility['continuity_ready']}, "
        f"proof={codex_slot_transition_compatibility['proof_status']}"
    )
    print(
        "Appliance platform: "
        f"{appliance_platform['platform_model']} "
        f"(update_model={appliance_platform['update_model']}, "
        f"base_delivery={appliance_platform['base_delivery_model']}, "
        f"read_only_system={appliance_platform['system_images_read_only']})"
    )
    print(
        "Appliance slots: "
        f"active={appliance_platform['active_slot']}, "
        f"inactive={appliance_platform['inactive_slot']}, "
        f"rollback={appliance_platform['rollback_slot']}, "
        f"next={appliance_platform.get('next_slot', "")}, "
        f"slot_metadata={appliance_platform.get('metadata_exists', False)}, "
        f"next_boot={appliance_platform.get('next_boot_exists', False)}, "
        f"update_status={appliance_platform['update_status']}"
    )
    next_boot_target = appliance_platform.get("next_boot_target", {})
    print(
        "Next boot target: "
        f"staged={next_boot_target.get('staged', False)}, "
        f"slot={next_boot_target.get('target_slot', '')}, "
        f"role={next_boot_target.get('target_role', '')}, "
        f"transition={next_boot_target.get('transition_kind', '')}, "
        f"version={next_boot_target.get('payload_version', '') or 'none'}"
    )
    print(
        "Appliance recovery/update: "
        f"recovery_available={appliance_platform['recovery_available']}, "
        f"recovery_mode={appliance_platform['recovery_mode']}, "
        f"welcome_shell={appliance_platform['welcome_shell_included']}, "
        f"installer_hidden={appliance_platform['installer_hidden_default_path']}"
    )
    slot_recovery = appliance_platform.get("slot_recovery", {})
    print(
        "Appliance rollback: "
        f"candidate={slot_recovery.get('rollback_candidate', '')}, "
        f"failed_gate={slot_recovery.get('failed_health_gate', False)}, "
        f"recovery_required={slot_recovery.get('recovery_required', False)}, "
        f"next_action={slot_recovery.get('next_action', '')}"
    )
    print(
        "State root: "
        f"path={state_root_usage['state_root']}, "
        f"initialized={state_root_usage['initialized']}, "
        f"manifest={state_root_usage['manifest_exists']}, "
        f"present={','.join(state_root_usage['present_paths']) or 'none'}"
    )
    if session_origin["banner_version"]:
        print(f"Session banner contract: {session_origin['banner_version']}")
    ownership = report["session_ownership"]
    print(
        "Session ownership: "
        f"phase={ownership['session_phase']}, "
        f"next_managed_entry={ownership['next_managed_entry']}, "
        f"session_id={ownership['session_id'] or 'none'}, "
        f"boot_id={ownership['boot_id'] or 'none'}"
    )
    session_validation = report["session_contract_validation"]
    sovereignty = report["user_space_sovereignty"]
    print(
        "Session contract: "
        f"status={session_validation['overall_status']}, "
        f"eligible={session_validation['managed_entry_eligible']}, "
        f"mode={session_validation['active_mode']}, "
        f"fallback={session_validation['fallback_target'] or 'none'}"
    )
    print(
        "User-space sovereignty: "
        f"model={sovereignty['summary']['default_interaction_model']}, "
        f"managed={sovereignty['summary']['managed_action_count']}, "
        f"guided={sovereignty['summary']['guided_action_count']}, "
        f"passthrough={sovereignty['summary']['passthrough_action_count']}"
    )
    print(f"Engine status: {report['engine_status']}")
    print(f"Engine reason: {report['engine_reason']}")
    if report["engine_command"]:
        print(f"Engine command: {report['engine_command']}")
        print(f"Engine timeout sec: {report['engine_timeout_sec']}")
        print(f"Engine model: {report['engine_model'] or '(default)'}")
    if report["web_allowlist"]:
        print(f"Web allowlist: {', '.join(report['web_allowlist'])}")
    browser = report["browser_runtime"]
    print(
        "Browser runtime: "
        f"configured={browser['configured']}, "
        f"feature_flag={browser['feature_flag_enabled']}, "
        f"enabled={browser['runtime_enabled']}, "
        f"backend={browser['backend_selected']}, "
        f"worker_timeout={browser['worker_timeout_sec']}s, "
        f"last_decision={browser['last_policy_decision']}"
    )
    if browser["backend_fallback_reason"]:
        print(
            "Browser backend fallback: "
            f"requested={browser['backend_requested']} -> "
            f"selected={browser['backend_selected']} "
            f"reason={browser['backend_fallback_reason']}"
        )
    print(
        "Capability substrate: "
        f"rule={capability_substrate['native_first_rule']}, "
        f"document_classes={','.join(capability_substrate['document_defaults']['native_document_classes'])}, "
        f"browser_path={capability_substrate['web_defaults']['browser_path']}"
    )
    print(
        "Intake surface: "
        f"total={intake_surface['summary']['total_items']}, "
        f"native={intake_surface['summary']['native_intake_items']}, "
        f"escalated={intake_surface['summary']['escalated_intake_items']}, "
        f"session_correlated={intake_surface['summary']['visible_session_correlated_items']}"
    )
    print(
        "Inbox capability: "
        f"messages={inbox_capability['summary']['message_count']}, "
        f"threads={inbox_capability['summary']['thread_count']}, "
        f"native={inbox_capability['summary']['native_inbox_handled']}, "
        f"adapter_required={inbox_capability['summary']['inbox_adapter_required']}"
    )
    print(
        "Inbox intake: "
        f"path={inbox_normalized_intake['summary']['selected_path']}, "
        f"messages={inbox_normalized_intake['summary']['message_intake_count']}, "
        f"session_correlated={inbox_normalized_intake['summary']['session_correlated']}, "
        f"request_correlated={inbox_normalized_intake['summary']['request_correlated']}, "
        f"approval_correlated={inbox_normalized_intake['summary']['approval_correlated']}"
    )
    print(
        "Telegram ingress: "
        f"status={telegram_ingress['status']}, "
        f"polling_enabled={telegram_ingress['polling']['enabled']}, "
        f"interval_sec={telegram_ingress['polling']['interval_sec']}, "
        f"chat_policy={telegram_ingress['chat_policy']['mode']}, "
        f"token_configured={telegram_ingress['bot_token']['configured']}"
    )
    print(
        "Service capability: "
        f"native_status={service_capability['native_status_visibility']}, "
        f"brokered_units={service_capability['summary']['broker_mediated_control_units']}, "
        f"approval_gated={service_capability['summary']['escalated_control_units']}"
    )
    print(
        "Permission capability: "
        f"native_signal={permission_capability['native_policy_signal_supported']}, "
        f"approval_requested={permission_capability['summary']['approval_requested']}, "
        f"escalated={permission_capability['summary']['escalated_permission_events']}"
    )
    print(
        "Execution ownership: "
        f"native={execution_ownership['summary']['native_capability_handler_count']}, "
        f"brokered={execution_ownership['summary']['broker_mediated_count']}, "
        f"external={execution_ownership['summary']['external_adapter_count']}"
    )
    counters = report["approval_counters"]
    print(
        "Approval counters: "
        f"requested={counters['requested']}, "
        f"approved={counters['approved']}, "
        f"denied={counters['denied']}, "
        f"blocked={counters['blocked']} "
        f"(events={counters['trace_events']})"
    )
    policy_ready = report["kernel_policy_ready"]
    print(
        "Kernel policy readiness: "
        f"status={policy_ready['overall_status']}, "
        f"ready_for_enforced_pilot={policy_ready['ready_for_enforced_pilot']}, "
        f"parser={policy_ready['parser_cmd']}"
    )
    if report["engine_detail"]:
        print(f"Engine detail: {report['engine_detail']}")

    return int(report["exit_code"])

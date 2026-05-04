from __future__ import annotations

import os
import shlex
import shutil
from pathlib import Path


CODEX_PRIMARY_RUNTIME_SCHEMA_VERSION = "agentos-codex-primary-runtime.v1"


def _resolve_command_path(command: str) -> str:
    command = str(command or "").strip()
    if not command:
        return ""
    try:
        first = shlex.split(command)[0]
    except Exception:
        first = command.split()[0]
    if not first:
        return ""
    if os.path.isabs(first):
        return first if Path(first).exists() else ""
    if Path(first).exists():
        return str(Path(first).resolve())
    return shutil.which(first) or ""


def build_codex_primary_runtime_summary(
    *,
    provider: str,
    command: str,
    model: str,
    engine_status: str,
    session_origin: dict,
    setup_state: dict,
    install_later: dict,
    recovery_path: dict,
    installed_boot: dict,
) -> dict:
    current_origin = str((session_origin or {}).get("category", "") or "unknown")
    next_managed_entry = str((setup_state or {}).get("next_managed_entry", "") or "unknown")
    provider = str(provider or "")
    command = str(command or "")
    model = str(model or "")
    command_path = _resolve_command_path(command)
    command_available = bool(command_path)
    engine_status = str(engine_status or "")
    provider_matches_primary = provider == "codex"
    managed_origins = {"live_appliance_boot", "installed_appliance_boot", "local_managed_tty1"}
    current_origin_managed = current_origin in managed_origins
    launch_path = [
        "Continue to AgentOS",
        "AgentOS Setup",
        "Codex CLI Managed Session",
        "ai>",
    ]
    installed_path = [
        "Installed AgentOS Boot",
        "AgentOS Setup",
        "Codex CLI Managed Session",
        "ai>",
    ]
    recovery_return_path = [
        "AgentOS Recovery",
        "Return to AgentOS",
        "Codex CLI Managed Session",
        "ai>",
    ]
    proof_status = "ready" if provider_matches_primary and command_available and engine_status == "PASS" else "attention"
    return {
        "schema_version": CODEX_PRIMARY_RUNTIME_SCHEMA_VERSION,
        "primary_runtime": "codex_cli",
        "expected_provider": "codex",
        "configured_provider": provider,
        "provider_matches_primary": provider_matches_primary,
        "configured_command": command,
        "resolved_command_path": command_path,
        "command_available": command_available,
        "configured_model": model,
        "engine_status": engine_status,
        "current_origin": current_origin,
        "current_origin_managed": current_origin_managed,
        "next_managed_entry": next_managed_entry,
        "managed_runtime_target": "codex_cli_managed_session",
        "launch_path": launch_path,
        "installed_launch_path": installed_path,
        "recovery_return_path": recovery_return_path,
        "install_action_label": str((install_later or {}).get("install_action_label", "Install AgentOS")),
        "install_target_origin": str((install_later or {}).get("target_origin", "installed_appliance_boot")),
        "recovery_label": str((recovery_path or {}).get("label", "AgentOS Recovery")),
        "installed_boot_available": bool((installed_boot or {}).get("available", False)),
        "runtime_continuity_supported": current_origin_managed and provider_matches_primary,
        "proof_status": proof_status,
    }

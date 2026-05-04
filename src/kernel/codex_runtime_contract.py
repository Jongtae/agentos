from __future__ import annotations

from pathlib import Path

from kernel.appliance_platform import build_state_root_usage_summary
from kernel.codex_primary_runtime import build_codex_primary_runtime_summary


CODEX_RUNTIME_CONTRACT_SCHEMA_VERSION = "agentos-codex-runtime-contract.v1"


def build_codex_runtime_contract(
    *,
    workspace_dir: str,
    workspace_root: str,
    provider: str,
    command: str,
    timeout_sec: int,
    model: str,
    engine_status: str,
    session_origin: dict,
    setup_state: dict,
    install_later: dict,
    recovery_path: dict,
    installed_boot: dict,
) -> dict:
    workspace_dir_path = Path(workspace_dir).resolve()
    workspace_root_path = (workspace_dir_path / workspace_root).resolve()
    state_root_usage = build_state_root_usage_summary()
    primary_runtime = build_codex_primary_runtime_summary(
        provider=provider,
        command=command,
        model=model,
        engine_status=engine_status,
        session_origin=session_origin,
        setup_state=setup_state,
        install_later=install_later,
        recovery_path=recovery_path,
        installed_boot=installed_boot,
    )
    return {
        "schema_version": CODEX_RUNTIME_CONTRACT_SCHEMA_VERSION,
        "primary_runtime": "codex_cli",
        "managed_runtime_target": "codex_cli_managed_session",
        "provider_contract": {
            "expected_provider": "codex",
            "configured_provider": str(provider or ""),
            "provider_matches_primary": bool(primary_runtime["provider_matches_primary"]),
        },
        "launch_contract": {
            "command": str(command or ""),
            "resolved_command_path": primary_runtime["resolved_command_path"],
            "command_available": bool(primary_runtime["command_available"]),
            "timeout_sec": max(1, int(timeout_sec)),
            "model": str(model or ""),
            "engine_status": str(engine_status or ""),
            "launch_path": list(primary_runtime["launch_path"]),
            "installed_launch_path": list(primary_runtime["installed_launch_path"]),
        },
        "env_contract": {
            "required_runtime_env": [
                "AGENTOS_SESSION_MANAGED=1",
                "AGENTOS_SESSION_ENTRY=<local_tty1|live_appliance|installed_appliance>",
            ],
            "required_provider_env": ["OPENAI_API_KEY"],
            "optional_runtime_env": [
                "AGENTOS_ENV_FILE",
                "AGENTOS_STATE_ROOT",
                "AGENTOS_SESSION_ID",
                "AGENTOS_BOOT_ID",
            ],
        },
        "workspace_contract": {
            "workspace_dir": str(workspace_dir_path),
            "workspace_root_runtime": str(workspace_root_path),
            "spec_file": str(workspace_dir_path / "spec.yaml"),
            "workspace_root_declared": str(workspace_root or "./"),
            "workspace_state_path": state_root_usage["paths"]["workspaces"]["path"],
        },
        "state_contract": {
            "state_root": state_root_usage["state_root"],
            "manifest_path": state_root_usage["manifest_path"],
            "initialized": bool(state_root_usage["initialized"]),
            "preserved_across_updates": bool(state_root_usage["preserved_across_updates"]),
            "mutable_paths": {key: value["path"] for key, value in state_root_usage["paths"].items()},
        },
        "continuity_contract": {
            "next_managed_entry": str(setup_state.get("next_managed_entry", "") or ""),
            "install_action_label": str(install_later.get("install_action_label", "Install AgentOS")),
            "install_target_origin": str(install_later.get("target_origin", "installed_appliance_boot")),
            "installed_boot_available": bool(installed_boot.get("available", False)),
            "recovery_label": str(recovery_path.get("label", "AgentOS Recovery")),
            "recovery_return_path": list(primary_runtime["recovery_return_path"]),
            "rejoin_target": "codex_cli_managed_session",
        },
        "proof_status": primary_runtime["proof_status"],
    }

from __future__ import annotations


CODEX_RECOVERY_TO_CODEX_SCHEMA_VERSION = "agentos-codex-recovery-to-codex.v1"


def build_codex_recovery_to_codex_summary(
    *,
    recovery_path: dict,
    runtime_contract: dict,
    launch_supervision: dict,
    slot_recovery: dict,
) -> dict:
    recommended_summary = list(recovery_path.get("recommended_rejoin_summary", []))
    detailed_path = list(recovery_path.get("recommended_rejoin_path", []))
    runtime_target = str(recovery_path.get("runtime_rejoin_target", "") or "")
    runtime_contract_ok = (
        (runtime_contract.get("continuity_contract") or {}).get("rejoin_target") == "codex_cli_managed_session"
    )
    slot_recovery_required = bool(slot_recovery.get("recovery_required", False))
    return {
        "schema_version": CODEX_RECOVERY_TO_CODEX_SCHEMA_VERSION,
        "recovery_label": str(recovery_path.get("label", "AgentOS Recovery")),
        "return_label": "Return to AgentOS",
        "recommended_summary": recommended_summary,
        "detailed_rejoin_path": detailed_path,
        "runtime_rejoin_target": runtime_target or "codex_cli_managed_session",
        "runtime_contract_ok": runtime_contract_ok,
        "launch_supervision_next_action": str(launch_supervision.get("next_action", "") or ""),
        "slot_recovery_required": slot_recovery_required,
        "slot_return_action": str(slot_recovery.get("return_action", "") or ""),
        "recovery_ready": (
            bool(recommended_summary == ["AgentOS Recovery", "Return to AgentOS", "ai>"])
            and "Codex CLI Managed Session" in detailed_path
            and (runtime_target or "codex_cli_managed_session") == "codex_cli_managed_session"
            and runtime_contract_ok
        ),
    }

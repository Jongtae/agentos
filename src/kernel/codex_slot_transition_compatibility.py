from __future__ import annotations


CODEX_SLOT_TRANSITION_COMPATIBILITY_SCHEMA_VERSION = "agentos-codex-slot-transition-compatibility.v1"


def build_codex_slot_transition_compatibility_summary(
    *,
    slot_update_contract: dict,
    next_boot_target: dict,
    slot_recovery: dict,
    installed_boot_to_codex: dict,
    recovery_to_codex: dict,
) -> dict:
    staged = bool(next_boot_target.get("staged", False))
    target_slot = str(next_boot_target.get("target_slot", "") or slot_update_contract.get("next_slot", ""))
    rollback_candidate = str(slot_recovery.get("rollback_candidate", "") or slot_update_contract.get("rollback_slot", ""))
    recovery_target_ok = str(slot_recovery.get("runtime_return_target", "")) == "codex_cli_managed_session"
    installed_target_ok = str(installed_boot_to_codex.get("runtime_target", "")) == "codex_cli_managed_session"
    recovery_ready = bool(recovery_to_codex.get("recovery_ready", False))
    continuity_ready = all((installed_target_ok, recovery_target_ok, recovery_ready))
    return {
        "schema_version": CODEX_SLOT_TRANSITION_COMPATIBILITY_SCHEMA_VERSION,
        "target_slot": target_slot,
        "active_slot": str(slot_update_contract.get("active_slot", "")),
        "inactive_slot": str(slot_update_contract.get("inactive_slot", "")),
        "rollback_candidate": rollback_candidate,
        "staged_transition": staged,
        "transition_kind": str(next_boot_target.get("transition_kind", "stay_on_active_slot")),
        "next_action": str(slot_recovery.get("next_action", "")),
        "recovery_required": bool(slot_recovery.get("recovery_required", False)),
        "runtime_return_target": str(slot_recovery.get("runtime_return_target", "codex_cli_managed_session")),
        "installed_runtime_target": str(installed_boot_to_codex.get("runtime_target", "")),
        "managed_session_reachable": bool(installed_boot_to_codex.get("managed_session_reachable", False)),
        "recovery_ready": recovery_ready,
        "continuity_ready": continuity_ready,
        "proof_status": "ready" if continuity_ready else "attention",
    }

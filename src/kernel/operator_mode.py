from __future__ import annotations

OPERATOR_MODE_SCHEMA_VERSION = "agentos-operator-mode.v1"


def operator_mode_contract(*, session_origin: dict, setup_state: dict) -> dict:
    origin = str(session_origin.get("category", "noninteractive") or "noninteractive")
    setup_status = str(setup_state.get("status", "pending") or "pending")

    recovery_active = any(
        str(session_origin.get(flag, "")) == "1"
        for flag in ()
    )

    boot_autostart_disabled = str(__import__("os").environ.get("AGENTOS_BOOT_AUTOSTART", "")) == "0"
    broker_bypass = str(__import__("os").environ.get("AGENTOS_BROKER_BYPASS", "")) == "1"
    policy_disable = str(__import__("os").environ.get("AGENTOS_KERNEL_POLICY_DISABLE", "")) == "1"
    operator_override = str(__import__("os").environ.get("AGENTOS_OPERATOR_MODE", "")) == "1"

    current_mode = "user_mode"
    reason = "managed_session_default"
    if origin == "root_tty_recovery" or boot_autostart_disabled or broker_bypass or policy_disable or recovery_active:
        current_mode = "recovery_mode"
        reason = "recovery_controls_active"
    elif operator_override:
        current_mode = "operator_mode"
        reason = "explicit_operator_override"

    surfaces = {
        "user_mode": [
            "ai_shell",
            "session_contract",
            "runtime_entry",
        ],
        "operator_mode": [
            "status",
            "evidence",
            "replay",
            "approval_forensics",
            "review_bundle",
            "review_bundle_history",
            "case_export",
        ],
        "recovery_mode": [
            "status",
            "health",
            "audit",
            "repair",
            "firstrun_reset",
            "policy_bridge",
            "policy_enforce",
        ],
    }

    return {
        "schema_version": OPERATOR_MODE_SCHEMA_VERSION,
        "current_mode": current_mode,
        "reason": reason,
        "setup_status": setup_status,
        "session_origin": origin,
        "controls": {
            "boot_autostart_disabled": boot_autostart_disabled,
            "broker_bypass": broker_bypass,
            "policy_disable": policy_disable,
            "operator_override": operator_override,
        },
        "surfaces": surfaces,
        "recommended_surface": surfaces[current_mode][0],
    }

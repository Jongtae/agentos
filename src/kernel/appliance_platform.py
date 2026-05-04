from __future__ import annotations

import os
from pathlib import Path

SYSTEM_IMAGE_LAYOUT_SCHEMA_VERSION = "agentos-system-image-layout.v1"
SLOT_UPDATE_SCHEMA_VERSION = "agentos-slot-update-contract.v1"
RECOVERY_MODE_SCHEMA_VERSION = "agentos-recovery-mode-contract.v1"
STATE_PARTITION_SCHEMA_VERSION = "agentos-state-partition-contract.v1"
IMAGE_RELEASE_IDENTITY_SCHEMA_VERSION = "agentos-image-release-identity.v1"

PLATFORM_MODEL = "agentos_managed_appliance_os"
UPDATE_MODEL = "image_based_ab_updates"
BASE_DELIVERY_MODEL = "migration_compatibility_server_iso"


def appliance_platform_state() -> dict:
    active_slot = str(os.environ.get("AGENTOS_ACTIVE_SLOT", "A")).strip() or "A"
    inactive_slot = str(os.environ.get("AGENTOS_INACTIVE_SLOT", "B")).strip() or ("B" if active_slot == "A" else "A")
    rollback_slot = str(os.environ.get("AGENTOS_ROLLBACK_SLOT", active_slot)).strip() or active_slot
    update_channel = str(os.environ.get("AGENTOS_UPDATE_CHANNEL", "preview")).strip() or "preview"
    update_status = str(os.environ.get("AGENTOS_UPDATE_STATUS", "idle")).strip() or "idle"
    recovery_available = os.environ.get("AGENTOS_RECOVERY_AVAILABLE", "1") == "1"
    recovery_mode = os.environ.get("AGENTOS_RECOVERY_MODE", "0") == "1"
    installer_hidden_default_path = os.environ.get("AGENTOS_INSTALLER_HIDDEN_DEFAULT_PATH", "0") == "1"
    welcome_shell_included = os.environ.get("AGENTOS_WELCOME_SHELL_INCLUDED", "0") == "1"
    system_root = str(os.environ.get("AGENTOS_SYSTEM_ROOT", "/sysroot/agentos")).strip() or "/sysroot/agentos"
    state_root = str(os.environ.get("AGENTOS_STATE_ROOT", "/var/lib/agentos")).strip() or "/var/lib/agentos"
    recovery_root = str(os.environ.get("AGENTOS_RECOVERY_ROOT", "/recovery/agentos")).strip() or "/recovery/agentos"
    return {
        "platform_model": PLATFORM_MODEL,
        "update_model": UPDATE_MODEL,
        "base_delivery_model": BASE_DELIVERY_MODEL,
        "active_slot": active_slot,
        "inactive_slot": inactive_slot,
        "rollback_slot": rollback_slot,
        "update_channel": update_channel,
        "update_status": update_status,
        "recovery_available": recovery_available,
        "recovery_mode": recovery_mode,
        "installer_hidden_default_path": installer_hidden_default_path,
        "welcome_shell_included": welcome_shell_included,
        "system_root": system_root,
        "state_root": state_root,
        "recovery_root": recovery_root,
        "system_images_read_only": True,
    }




def build_slot_state_summary() -> dict:
    state = appliance_platform_state()
    state_root = Path(state["state_root"])
    slots_dir = Path(os.environ.get("AGENTOS_SLOTS_DIR", state_root / "slots"))
    metadata_file = Path(os.environ.get("AGENTOS_SLOT_METADATA_FILE", slots_dir / "slot-state.env"))
    next_boot_file = Path(os.environ.get("AGENTOS_NEXT_BOOT_FILE", slots_dir / "next-boot.env"))
    values = {
        "active_slot": state["active_slot"],
        "inactive_slot": state["inactive_slot"],
        "rollback_slot": state["rollback_slot"],
        "next_slot": state["inactive_slot"],
        "health_state": "unknown",
    }
    next_boot_values = {
        "bootable_slot": "",
        "staged_from_slot": "",
        "payload_file": "",
        "payload_version": "",
        "payload_channel": "",
        "payload_digest": "",
    }
    if metadata_file.exists():
        for line in metadata_file.read_text(encoding="utf-8").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key in values:
                values[key] = value
    if next_boot_file.exists():
        for line in next_boot_file.read_text(encoding="utf-8").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key in next_boot_values:
                next_boot_values[key] = value
        if next_boot_values["bootable_slot"]:
            values["next_slot"] = next_boot_values["bootable_slot"]
    return {
        "slots_dir": str(slots_dir),
        "metadata_file": str(metadata_file),
        "metadata_exists": metadata_file.exists(),
        "next_boot_file": str(next_boot_file),
        "next_boot_exists": next_boot_file.exists(),
        "staged_payload_file": str(slots_dir / str(values["next_slot"]) / "update-payload.json"),
        "staged_payload_exists": (slots_dir / str(values["next_slot"]) / "update-payload.json").exists(),
        "active_slot_dir_exists": (slots_dir / str(values["active_slot"])).exists(),
        "inactive_slot_dir_exists": (slots_dir / str(values["inactive_slot"])).exists(),
        "next_boot_target_slot": next_boot_values["bootable_slot"] or values["next_slot"],
        "next_boot_staged_from_slot": next_boot_values["staged_from_slot"],
        "next_boot_payload_version": next_boot_values["payload_version"],
        "next_boot_payload_channel": next_boot_values["payload_channel"],
        "next_boot_payload_digest": next_boot_values["payload_digest"],
        "next_boot_payload_file": next_boot_values["payload_file"] or str(slots_dir / str(values["next_slot"]) / "update-payload.json"),
        **values,
    }


def build_next_boot_target_summary() -> dict:
    slot_state = build_slot_state_summary()
    target_slot = str(slot_state.get("next_boot_target_slot", slot_state.get("next_slot", "")) or slot_state.get("next_slot", ""))
    active_slot = str(slot_state.get("active_slot", "A") or "A")
    staged = bool(slot_state.get("next_boot_exists")) and bool(target_slot)
    target_role = f"installed_slot_{target_slot.lower()}" if target_slot else ""
    transition_kind = "stay_on_active_slot"
    if staged and target_slot and target_slot != active_slot:
        transition_kind = "switch_to_inactive_slot"
    elif staged and target_slot == active_slot:
        transition_kind = "reaffirm_active_slot"
    return {
        "staged": staged,
        "target_slot": target_slot,
        "active_slot": active_slot,
        "target_role": target_role,
        "target_origin": "installed_appliance_boot" if staged else "",
        "identity_path": ["Installed AgentOS Boot", "AgentOS Setup", "AgentOS Managed Session", "ai>"] if staged else [],
        "transition_kind": transition_kind,
        "payload_version": str(slot_state.get("next_boot_payload_version", "") or ""),
        "payload_channel": str(slot_state.get("next_boot_payload_channel", "") or ""),
        "payload_digest": str(slot_state.get("next_boot_payload_digest", "") or ""),
        "next_boot_file": slot_state["next_boot_file"],
        "next_boot_exists": slot_state["next_boot_exists"],
        "payload_file": str(slot_state.get("next_boot_payload_file", "") or slot_state.get("staged_payload_file", "")),
    }


def build_slot_recovery_summary() -> dict:
    state = appliance_platform_state()
    slot_state = build_slot_state_summary()
    health_state = str(slot_state.get("health_state", "unknown") or "unknown")
    failed_health_gate = health_state in {"boot_failed", "health_gate_failed", "rollback_required"}
    staged_update = bool(slot_state.get("next_boot_exists")) and bool(slot_state.get("staged_payload_exists"))
    rollback_candidate = str(slot_state.get("rollback_slot", slot_state.get("active_slot", "A")) or "A")
    recovery_required = failed_health_gate
    next_action = "stay_on_active_slot"
    if failed_health_gate:
        next_action = f"rollback_to_slot_{rollback_candidate.lower()}"
    elif staged_update:
        next_action = f"boot_staged_slot_{str(slot_state.get('next_slot', '')).lower()}"
    return {
        "health_state": health_state,
        "failed_health_gate": failed_health_gate,
        "staged_update": staged_update,
        "rollback_candidate": rollback_candidate,
        "recovery_required": recovery_required,
        "recovery_available": state["recovery_available"],
        "next_action": next_action,
        "return_action": "Return to AgentOS",
        "runtime_return_target": "codex_cli_managed_session",
        "rejoin_path": ["Recovery", "Return to AgentOS", "ai>"],
    }

def build_system_image_layout_contract() -> dict:
    state = appliance_platform_state()
    slot_state = build_slot_state_summary()
    return {
        "schema_version": SYSTEM_IMAGE_LAYOUT_SCHEMA_VERSION,
        "platform_model": PLATFORM_MODEL,
        "partition_contract": [
            {"id": "efi", "mountpoint": "/boot/efi", "writable": True, "purpose": "bootloader_and_slot_metadata"},
            {"id": "system_a", "mountpoint": f"{state['system_root']}/slot-a", "writable": False, "purpose": "read_only_system_image_a"},
            {"id": "system_b", "mountpoint": f"{state['system_root']}/slot-b", "writable": False, "purpose": "read_only_system_image_b"},
            {"id": "state", "mountpoint": state["state_root"], "writable": True, "purpose": "workspace_agent_logs_models_and_caches"},
            {"id": "recovery", "mountpoint": state["recovery_root"], "writable": False, "purpose": "bootable_recovery_mode"},
        ],
        "default_boot_path": ["boot", "agentos_splash", "agentos_welcome", "continue_to_agentos", "ai_shell"],
        "install_path_role": "make_persistent_not_install_ubuntu",
        "installer_hidden_default_path": state["installer_hidden_default_path"],
    }


def build_slot_update_contract() -> dict:
    state = appliance_platform_state()
    slot_state = build_slot_state_summary()
    slot_recovery = build_slot_recovery_summary()
    next_boot_target = build_next_boot_target_summary()
    stage_status = "staged" if slot_state["next_boot_exists"] and slot_state["staged_payload_exists"] else "idle"
    return {
        "schema_version": SLOT_UPDATE_SCHEMA_VERSION,
        "platform_model": PLATFORM_MODEL,
        "update_model": UPDATE_MODEL,
        "active_slot": slot_state["active_slot"],
        "inactive_slot": slot_state["inactive_slot"],
        "rollback_slot": slot_state["rollback_slot"],
        "next_slot": slot_state["next_slot"],
        "metadata_file": slot_state["metadata_file"],
        "metadata_exists": slot_state["metadata_exists"],
        "next_boot_file": slot_state["next_boot_file"],
        "next_boot_exists": slot_state["next_boot_exists"],
        "staged_payload_file": slot_state["staged_payload_file"],
        "staged_payload_exists": slot_state["staged_payload_exists"],
        "stage_status": stage_status,
        "next_boot_target": next_boot_target,
        "health_state": slot_recovery["health_state"],
        "failed_health_gate": slot_recovery["failed_health_gate"],
        "rollback_candidate": slot_recovery["rollback_candidate"],
        "recovery_required": slot_recovery["recovery_required"],
        "next_action": slot_recovery["next_action"],
        "update_channel": state["update_channel"],
        "update_status": "staged" if stage_status == "staged" and state["update_status"] == "idle" else state["update_status"],
        "slot_roles": {
            "active": f"installed_slot_{slot_state['active_slot'].lower()}",
            "inactive": f"installed_slot_{slot_state['inactive_slot'].lower()}",
            "rollback": f"installed_slot_{slot_state['rollback_slot'].lower()}",
        },
        "boot_health_contract": [
            "boot_attempt_counter",
            "slot_health_gate",
            "rollback_on_failed_health_gate",
            "explicit_recovery_override",
        ],
    }


def build_recovery_mode_contract() -> dict:
    state = appliance_platform_state()
    slot_recovery = build_slot_recovery_summary()
    return {
        "schema_version": RECOVERY_MODE_SCHEMA_VERSION,
        "platform_model": PLATFORM_MODEL,
        "recovery_available": state["recovery_available"],
        "recovery_mode": state["recovery_mode"],
        "label": "Recovery",
        "recovery_label": "Recovery",
        "primary_return_action": "Return to AgentOS",
        "entry_modes": [
            "boot_menu_recovery",
            "rollback_after_failed_slot_health_gate",
            "operator_forced_recovery",
        ],
        "capabilities": [
            "inspect_slots",
            "rollback_to_last_known_good_slot",
            "repair_boot_metadata",
            "return_to_agentos",
        ],
        "default_rejoin_path": ["Recovery", "Return to AgentOS", "ai>"],
        "slot_recovery": slot_recovery,
    }




def _state_root_paths(state_root: str) -> dict:
    root = Path(state_root)
    return {
        "workspaces": str(root / "workspaces"),
        "logs": str(root / "logs"),
        "evidence": str(root / "evidence"),
        "models": str(root / "models"),
        "update_metadata": str(root / "updates"),
        "rollback_markers": str(root / "rollback"),
        "runtime": str(root / "runtime"),
        "codex_runtime": str(root / "runtime" / "codex"),
        "codex_session": str(root / "runtime" / "codex" / "session"),
        "codex_logs": str(root / "runtime" / "codex" / "logs"),
        "codex_evidence": str(root / "runtime" / "codex" / "evidence"),
    }


def build_state_root_usage_summary() -> dict:
    state = appliance_platform_state()
    state_root = Path(state["state_root"])
    manifest_path = Path(os.environ.get("AGENTOS_STATE_MANIFEST_FILE", state_root / "state-layout.env"))
    mutable_paths = _state_root_paths(str(state_root))
    path_status = {
        key: {
            "path": value,
            "exists": Path(value).exists(),
        }
        for key, value in mutable_paths.items()
    }
    initialized = state_root.exists() and manifest_path.exists() and all(item["exists"] for item in path_status.values())
    return {
        "state_root": str(state_root),
        "manifest_path": str(manifest_path),
        "state_root_exists": state_root.exists(),
        "manifest_exists": manifest_path.exists(),
        "initialized": initialized,
        "runtime_owner": "codex_cli_managed_session",
        "paths": path_status,
        "missing_paths": [key for key, item in path_status.items() if not item["exists"]],
        "present_paths": [key for key, item in path_status.items() if item["exists"]],
        "system_root_mutable": False,
        "preserved_across_updates": True,
        "codex_runtime_paths_present": all(
            path_status[key]["exists"]
            for key in ("codex_runtime", "codex_session", "codex_logs", "codex_evidence")
        ),
    }

def build_state_partition_contract() -> dict:
    state = appliance_platform_state()
    state_root = Path(state["state_root"])
    return {
        "schema_version": STATE_PARTITION_SCHEMA_VERSION,
        "platform_model": PLATFORM_MODEL,
        "state_root": str(state_root),
        "mutable_contract": {
            "workspace_state": str(state_root / "workspaces"),
            "logs_and_evidence": str(state_root / "evidence"),
            "models_and_caches": str(state_root / "models"),
            "update_metadata": str(state_root / "updates"),
            "rollback_markers": str(state_root / "rollback"),
        },
        "mutable_paths": _state_root_paths(str(state_root)),
        "preserved_across_updates": True,
        "system_root_mutable": False,
    }


def build_image_release_identity(*, version: str = "development", channel: str = "preview") -> dict:
    state = appliance_platform_state()
    slot_state = build_slot_state_summary()
    next_boot_target = build_next_boot_target_summary()
    return {
        "schema_version": IMAGE_RELEASE_IDENTITY_SCHEMA_VERSION,
        "platform_model": PLATFORM_MODEL,
        "version": version,
        "channel": channel,
        "update_model": UPDATE_MODEL,
        "system_image_digest_contract": "required",
        "active_slot": slot_state["active_slot"],
        "inactive_slot": slot_state["inactive_slot"],
        "next_slot": slot_state["next_slot"],
        "slot_metadata_file": slot_state["metadata_file"],
        "slot_metadata_exists": slot_state["metadata_exists"],
        "next_boot_file": slot_state["next_boot_file"],
        "next_boot_exists": slot_state["next_boot_exists"],
        "next_boot_target_role": next_boot_target["target_role"],
        "next_boot_target_origin": next_boot_target["target_origin"],
        "next_boot_payload_version": next_boot_target["payload_version"],
        "recovery_present": state["recovery_available"],
        "welcome_shell_included": state["welcome_shell_included"],
        "installer_hidden_default_path": state["installer_hidden_default_path"],
        "base_delivery_model": BASE_DELIVERY_MODEL,
    }

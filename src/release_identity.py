from __future__ import annotations

from pathlib import Path


RELEASE_IDENTITY_SCHEMA_VERSION = "agentos-release-identity.v1"
RELEASE_DISTRIBUTION_CONTRACT = "agentos_managed_session"
RELEASE_PRIMARY_ENTRY_CONTRACT = "agentos_setup_to_ai_shell"
RELEASE_BOOT_EXPERIENCE_CONTRACT = "agentos_direct_ai_boot"
ISO_DEFAULT_BOOT_PATH = "continue_to_agentos_default_path"
ISO_FALLBACK_BOOT_PATH = "installer_heavy_compatibility"
GRUB_THEME_CONTRACT = "agentos_minimal_appliance_grub.v1"
SPLASH_THEME_CONTRACT = "agentos_minimal_appliance_splash.v1"
BASE_IMAGE_TYPE = "desktop-live-iso"
HEADLESS_BASE_IMAGE_TYPE = "headless-live-server-iso"
BASE_IMAGE_TYPES = {BASE_IMAGE_TYPE, HEADLESS_BASE_IMAGE_TYPE}
REMASTER_MODE = "required_for_product_path"
WELCOME_SHELL_CONTRACT = "agentos_welcome_shell.v1"
RECOVERY_SHELL_CONTRACT = "agentos_recovery_shell.v1"
BOOT_FLOW_PROOF_CONTRACT = "agentos-remastered-boot-flow-proof.v1"
DEFAULT_BOOT_TARGET_CONTRACT = "agentos_continue_boot_target.v1"
DEFAULT_BOOT_TARGET_LABEL = "Continue to AgentOS"
VM_FIRST_SCREEN_EVIDENCE_CONTRACT = "agentos_vm_first_screen_evidence.v1"
LIVE_GUEST_AGENT_REACHABILITY_PATHS = {"prestaged", "runtime_apt_install", "unstaged"}

REQUIRED_FIELDS = {
    "schema_version",
    "artifact_type",
    "agentos_version",
    "package_version",
    "arch",
    "distribution_contract",
    "primary_entry_contract",
    "boot_experience_contract",
    "output_path",
    "sha256sums_path",
    "build_manifest_path",
    "base_image_path",
    "asset_bundle_path",
    "asset_manifest_path",
    "install_root",
    "default_workspace",
}

ARTIFACT_TYPES = {"iso", "deb"}


def build_release_identity_payload(
    *,
    artifact_type: str,
    agentos_version: str,
    package_version: str = "",
    arch: str = "amd64",
    output_path: str = "",
    sha256sums_path: str = "",
    build_manifest_path: str = "",
    base_image_path: str = "",
    asset_bundle_path: str = "",
    asset_manifest_path: str = "",
    install_root: str = "",
    default_workspace: str = "",
    boot_experience_contract: str = RELEASE_BOOT_EXPERIENCE_CONTRACT,
    iso_default_boot_path: str = ISO_DEFAULT_BOOT_PATH,
    iso_fallback_boot_path: str = ISO_FALLBACK_BOOT_PATH,
    grub_theme_contract: str = GRUB_THEME_CONTRACT,
    splash_theme_contract: str = SPLASH_THEME_CONTRACT,
    base_image_type: str = BASE_IMAGE_TYPE,
    remaster_mode: str = REMASTER_MODE,
    welcome_shell_contract: str = WELCOME_SHELL_CONTRACT,
    recovery_shell_contract: str = RECOVERY_SHELL_CONTRACT,
    boot_flow_proof_contract: str = BOOT_FLOW_PROOF_CONTRACT,
    boot_flow_proof_included: bool = False,
    default_boot_target_contract: str = DEFAULT_BOOT_TARGET_CONTRACT,
    default_boot_target_label: str = DEFAULT_BOOT_TARGET_LABEL,
    boot_target_activated: bool = False,
    vm_first_screen_evidence_contract: str = VM_FIRST_SCREEN_EVIDENCE_CONTRACT,
    vm_first_screen_evidence_included: bool = False,
    installer_hidden_default_path: bool = False,
    ubuntu_installer_masked: bool = False,
    agentos_welcome_assets_staged: bool = False,
    agentos_welcome_runtime_observed: bool = False,
    agentos_welcome_owns_first_screen: bool = False,
    live_guest_agent_bootstrap_staged: bool = False,
    live_guest_agent_prestaged: bool = False,
    live_guest_agent_reachability_path: str = "unstaged",
    bundled_local_provider_staged: bool = False,
    bundled_local_model_staged: bool = False,
    bundled_local_service_staged: bool = False,
    bundled_local_firstrun_service_staged: bool = False,
) -> dict:
    payload = {
        "schema_version": RELEASE_IDENTITY_SCHEMA_VERSION,
        "artifact_type": artifact_type,
        "agentos_version": agentos_version,
        "package_version": package_version,
        "arch": arch,
        "distribution_contract": RELEASE_DISTRIBUTION_CONTRACT,
        "primary_entry_contract": RELEASE_PRIMARY_ENTRY_CONTRACT,
        "boot_experience_contract": boot_experience_contract,
        "output_path": output_path,
        "sha256sums_path": sha256sums_path,
        "build_manifest_path": build_manifest_path,
        "base_image_path": base_image_path,
        "asset_bundle_path": asset_bundle_path,
        "asset_manifest_path": asset_manifest_path,
        "install_root": install_root,
        "default_workspace": default_workspace,
    }
    if artifact_type == "iso":
        payload["iso_default_boot_path"] = iso_default_boot_path
        payload["iso_fallback_boot_path"] = iso_fallback_boot_path
        payload["grub_theme_contract"] = grub_theme_contract
        payload["splash_theme_contract"] = splash_theme_contract
        payload["base_image_type"] = base_image_type
        payload["remaster_mode"] = remaster_mode
        payload["welcome_shell_contract"] = welcome_shell_contract
        payload["recovery_shell_contract"] = recovery_shell_contract
        payload["boot_flow_proof_contract"] = boot_flow_proof_contract
        payload["boot_flow_proof_included"] = boot_flow_proof_included
        payload["default_boot_target_contract"] = default_boot_target_contract
        payload["default_boot_target_label"] = default_boot_target_label
        payload["boot_target_activated"] = boot_target_activated
        payload["vm_first_screen_evidence_contract"] = vm_first_screen_evidence_contract
        payload["vm_first_screen_evidence_included"] = vm_first_screen_evidence_included
        payload["installer_hidden_default_path"] = installer_hidden_default_path
        payload["ubuntu_installer_masked"] = ubuntu_installer_masked
        payload["agentos_welcome_assets_staged"] = agentos_welcome_assets_staged
        payload["agentos_welcome_runtime_observed"] = agentos_welcome_runtime_observed
        payload["agentos_welcome_owns_first_screen"] = bool(
            agentos_welcome_owns_first_screen or agentos_welcome_runtime_observed
        )
        payload["live_guest_agent_bootstrap_staged"] = live_guest_agent_bootstrap_staged
        payload["live_guest_agent_prestaged"] = live_guest_agent_prestaged
        payload["live_guest_agent_reachability_path"] = live_guest_agent_reachability_path
        payload["bundled_local_provider_staged"] = bundled_local_provider_staged
        payload["bundled_local_model_staged"] = bundled_local_model_staged
        payload["bundled_local_service_staged"] = bundled_local_service_staged
        payload["bundled_local_firstrun_service_staged"] = bundled_local_firstrun_service_staged
    return payload


def validate_release_identity_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["payload must be an object"]

    missing = sorted(REQUIRED_FIELDS - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")

    schema_version = str(payload.get("schema_version", "")).strip()
    if schema_version != RELEASE_IDENTITY_SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {RELEASE_IDENTITY_SCHEMA_VERSION}, got {schema_version or '(empty)'}"
        )

    artifact_type = str(payload.get("artifact_type", "")).strip()
    if artifact_type not in ARTIFACT_TYPES:
        errors.append(f"artifact_type must be one of {sorted(ARTIFACT_TYPES)}, got {artifact_type or '(empty)'}")

    if str(payload.get("distribution_contract", "")).strip() != RELEASE_DISTRIBUTION_CONTRACT:
        errors.append(
            "distribution_contract must be "
            f"{RELEASE_DISTRIBUTION_CONTRACT}"
        )

    if str(payload.get("primary_entry_contract", "")).strip() != RELEASE_PRIMARY_ENTRY_CONTRACT:
        errors.append(
            "primary_entry_contract must be "
            f"{RELEASE_PRIMARY_ENTRY_CONTRACT}"
        )

    if str(payload.get("boot_experience_contract", "")).strip() != RELEASE_BOOT_EXPERIENCE_CONTRACT:
        errors.append(
            "boot_experience_contract must be "
            f"{RELEASE_BOOT_EXPERIENCE_CONTRACT}"
        )

    for key in ("agentos_version", "arch", "output_path", "sha256sums_path"):
        if not str(payload.get(key, "")).strip():
            errors.append(f"{key} must be non-empty")

    if artifact_type == "iso":
        for key in ("build_manifest_path", "base_image_path", "asset_bundle_path", "asset_manifest_path"):
            if not str(payload.get(key, "")).strip():
                errors.append(f"{key} must be non-empty for iso artifacts")
        if str(payload.get("iso_default_boot_path", "")).strip() != ISO_DEFAULT_BOOT_PATH:
            errors.append(f"iso_default_boot_path must be {ISO_DEFAULT_BOOT_PATH}")
        if str(payload.get("iso_fallback_boot_path", "")).strip() != ISO_FALLBACK_BOOT_PATH:
            errors.append(f"iso_fallback_boot_path must be {ISO_FALLBACK_BOOT_PATH}")
        if str(payload.get("grub_theme_contract", "")).strip() != GRUB_THEME_CONTRACT:
            errors.append(f"grub_theme_contract must be {GRUB_THEME_CONTRACT}")
        if str(payload.get("splash_theme_contract", "")).strip() != SPLASH_THEME_CONTRACT:
            errors.append(f"splash_theme_contract must be {SPLASH_THEME_CONTRACT}")
        base_image_type = str(payload.get("base_image_type", "")).strip()
        if base_image_type not in BASE_IMAGE_TYPES:
            errors.append(
                f"base_image_type must be one of {sorted(BASE_IMAGE_TYPES)}, "
                f"got {base_image_type or '(empty)'}"
            )
        if str(payload.get("remaster_mode", "")).strip() != REMASTER_MODE:
            errors.append(f"remaster_mode must be {REMASTER_MODE}")
        if str(payload.get("welcome_shell_contract", "")).strip() != WELCOME_SHELL_CONTRACT:
            errors.append(f"welcome_shell_contract must be {WELCOME_SHELL_CONTRACT}")
        if str(payload.get("recovery_shell_contract", "")).strip() != RECOVERY_SHELL_CONTRACT:
            errors.append(f"recovery_shell_contract must be {RECOVERY_SHELL_CONTRACT}")
        if str(payload.get("boot_flow_proof_contract", "")).strip() != BOOT_FLOW_PROOF_CONTRACT:
            errors.append(f"boot_flow_proof_contract must be {BOOT_FLOW_PROOF_CONTRACT}")
        if not isinstance(payload.get("boot_flow_proof_included"), bool):
            errors.append("boot_flow_proof_included must be a boolean")
        if str(payload.get("default_boot_target_contract", "")).strip() != DEFAULT_BOOT_TARGET_CONTRACT:
            errors.append(f"default_boot_target_contract must be {DEFAULT_BOOT_TARGET_CONTRACT}")
        if str(payload.get("default_boot_target_label", "")).strip() != DEFAULT_BOOT_TARGET_LABEL:
            errors.append(f"default_boot_target_label must be {DEFAULT_BOOT_TARGET_LABEL}")
        if not isinstance(payload.get("boot_target_activated"), bool):
            errors.append("boot_target_activated must be a boolean")
        if str(payload.get("vm_first_screen_evidence_contract", "")).strip() != VM_FIRST_SCREEN_EVIDENCE_CONTRACT:
            errors.append(f"vm_first_screen_evidence_contract must be {VM_FIRST_SCREEN_EVIDENCE_CONTRACT}")
        if not isinstance(payload.get("vm_first_screen_evidence_included"), bool):
            errors.append("vm_first_screen_evidence_included must be a boolean")
        if not isinstance(payload.get("installer_hidden_default_path"), bool):
            errors.append("installer_hidden_default_path must be a boolean")
        for bool_key in (
            "ubuntu_installer_masked",
            "agentos_welcome_assets_staged",
            "agentos_welcome_runtime_observed",
            "agentos_welcome_owns_first_screen",
            "live_guest_agent_bootstrap_staged",
            "live_guest_agent_prestaged",
            "bundled_local_provider_staged",
            "bundled_local_model_staged",
            "bundled_local_service_staged",
            "bundled_local_firstrun_service_staged",
        ):
            if bool_key in payload and not isinstance(payload.get(bool_key), bool):
                errors.append(f"{bool_key} must be a boolean")
        if "live_guest_agent_reachability_path" in payload:
            reach = str(payload.get("live_guest_agent_reachability_path", "")).strip()
            if reach not in LIVE_GUEST_AGENT_REACHABILITY_PATHS:
                errors.append(
                    "live_guest_agent_reachability_path must be one of "
                    f"{sorted(LIVE_GUEST_AGENT_REACHABILITY_PATHS)}, got {reach or '(empty)'}"
                )
    if artifact_type == "deb":
        for key in ("install_root", "default_workspace"):
            if not str(payload.get(key, "")).strip():
                errors.append(f"{key} must be non-empty for deb artifacts")

    return errors


def payload_paths(payload: dict) -> dict[str, Path]:
    return {
        key: Path(str(payload.get(key, "")))
        for key in (
            "output_path",
            "sha256sums_path",
            "build_manifest_path",
            "base_image_path",
            "asset_bundle_path",
            "asset_manifest_path",
        )
        if str(payload.get(key, "")).strip()
    }

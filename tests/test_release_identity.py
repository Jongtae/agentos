from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from release_identity import (
    RELEASE_DISTRIBUTION_CONTRACT,
    RELEASE_BOOT_EXPERIENCE_CONTRACT,
    RELEASE_IDENTITY_SCHEMA_VERSION,
    ISO_DEFAULT_BOOT_PATH,
    ISO_FALLBACK_BOOT_PATH,
    GRUB_THEME_CONTRACT,
    RELEASE_PRIMARY_ENTRY_CONTRACT,
    SPLASH_THEME_CONTRACT,
    BASE_IMAGE_TYPE,
    HEADLESS_BASE_IMAGE_TYPE,
    REMASTER_MODE,
    WELCOME_SHELL_CONTRACT,
    RECOVERY_SHELL_CONTRACT,
    BOOT_FLOW_PROOF_CONTRACT,
    DEFAULT_BOOT_TARGET_CONTRACT,
    DEFAULT_BOOT_TARGET_LABEL,
    VM_FIRST_SCREEN_EVIDENCE_CONTRACT,
    build_release_identity_payload,
    validate_release_identity_payload,
)


class ReleaseIdentityTests(unittest.TestCase):
    def test_build_iso_payload_uses_shared_contract(self):
        payload = build_release_identity_payload(
            artifact_type="iso",
            agentos_version="v0.50.0",
            arch="amd64",
            output_path="/tmp/agentos.iso",
            sha256sums_path="/tmp/SHA256SUMS",
            build_manifest_path="/tmp/manifest.txt",
            base_image_path="/tmp/base.iso",
            asset_bundle_path="/tmp/assets.tar.gz",
            asset_manifest_path="/tmp/asset-manifest.txt",
        )

        self.assertEqual(payload["schema_version"], RELEASE_IDENTITY_SCHEMA_VERSION)
        self.assertEqual(payload["distribution_contract"], RELEASE_DISTRIBUTION_CONTRACT)
        self.assertEqual(payload["primary_entry_contract"], RELEASE_PRIMARY_ENTRY_CONTRACT)
        self.assertEqual(payload["boot_experience_contract"], RELEASE_BOOT_EXPERIENCE_CONTRACT)
        self.assertEqual(payload["iso_default_boot_path"], ISO_DEFAULT_BOOT_PATH)
        self.assertEqual(payload["iso_fallback_boot_path"], ISO_FALLBACK_BOOT_PATH)
        self.assertEqual(payload["grub_theme_contract"], GRUB_THEME_CONTRACT)
        self.assertEqual(payload["splash_theme_contract"], SPLASH_THEME_CONTRACT)
        self.assertEqual(payload["base_image_type"], BASE_IMAGE_TYPE)
        self.assertEqual(payload["remaster_mode"], REMASTER_MODE)
        self.assertEqual(payload["welcome_shell_contract"], WELCOME_SHELL_CONTRACT)
        self.assertEqual(payload["recovery_shell_contract"], RECOVERY_SHELL_CONTRACT)
        self.assertEqual(payload["boot_flow_proof_contract"], BOOT_FLOW_PROOF_CONTRACT)
        self.assertFalse(payload["boot_flow_proof_included"])
        self.assertEqual(payload["default_boot_target_contract"], DEFAULT_BOOT_TARGET_CONTRACT)
        self.assertEqual(payload["default_boot_target_label"], DEFAULT_BOOT_TARGET_LABEL)
        self.assertFalse(payload["boot_target_activated"])
        self.assertEqual(payload["vm_first_screen_evidence_contract"], VM_FIRST_SCREEN_EVIDENCE_CONTRACT)
        self.assertFalse(payload["vm_first_screen_evidence_included"])
        self.assertFalse(payload["installer_hidden_default_path"])
        self.assertFalse(payload["agentos_welcome_assets_staged"])
        self.assertFalse(payload["agentos_welcome_runtime_observed"])
        self.assertFalse(payload["agentos_welcome_owns_first_screen"])
        self.assertFalse(payload["bundled_local_provider_staged"])
        self.assertFalse(payload["bundled_local_model_staged"])
        self.assertFalse(payload["bundled_local_service_staged"])
        self.assertFalse(payload["bundled_local_firstrun_service_staged"])
        self.assertEqual(validate_release_identity_payload(payload), [])

    def test_build_deb_payload_requires_install_fields(self):
        payload = build_release_identity_payload(
            artifact_type="deb",
            agentos_version="v0.50.0",
            package_version="0.50.0",
            arch="amd64",
            output_path="/tmp/agentos.deb",
            sha256sums_path="/tmp/SHA256SUMS",
            install_root="/usr/lib/agentos",
            default_workspace="/var/lib/agentos/workspaces/default",
        )

        self.assertEqual(validate_release_identity_payload(payload), [])

    def test_validate_accepts_headless_live_server_base_contract(self):
        payload = build_release_identity_payload(
            artifact_type="iso",
            agentos_version="v0.50.0",
            arch="amd64",
            output_path="/tmp/agentos.iso",
            sha256sums_path="/tmp/SHA256SUMS",
            build_manifest_path="/tmp/manifest.txt",
            base_image_path="/tmp/ubuntu-24.04.4-live-server-amd64.iso",
            asset_bundle_path="/tmp/assets.tar.gz",
            asset_manifest_path="/tmp/asset-manifest.txt",
            base_image_type=HEADLESS_BASE_IMAGE_TYPE,
        )

        self.assertEqual(payload["base_image_type"], HEADLESS_BASE_IMAGE_TYPE)
        self.assertEqual(validate_release_identity_payload(payload), [])

    def test_validate_rejects_unknown_base_contract(self):
        payload = build_release_identity_payload(
            artifact_type="iso",
            agentos_version="v0.50.0",
            arch="amd64",
            output_path="/tmp/agentos.iso",
            sha256sums_path="/tmp/SHA256SUMS",
            build_manifest_path="/tmp/manifest.txt",
            base_image_path="/tmp/base.iso",
            asset_bundle_path="/tmp/assets.tar.gz",
            asset_manifest_path="/tmp/asset-manifest.txt",
            base_image_type="live-server-iso",
        )

        errors = validate_release_identity_payload(payload)
        self.assertTrue(any("base_image_type must be one of" in e for e in errors))

    def test_validate_rejects_missing_iso_fields(self):
        payload = build_release_identity_payload(
            artifact_type="iso",
            agentos_version="v0.50.0",
            output_path="/tmp/agentos.iso",
            sha256sums_path="/tmp/SHA256SUMS",
        )

        errors = validate_release_identity_payload(payload)
        self.assertTrue(any("build_manifest_path must be non-empty for iso artifacts" in e for e in errors))
        self.assertTrue(any("asset_manifest_path must be non-empty for iso artifacts" in e for e in errors))

    def test_script_roundtrip_validate(self):
        payload = build_release_identity_payload(
            artifact_type="deb",
            agentos_version="v0.50.0",
            package_version="0.50.0",
            output_path="/tmp/agentos.deb",
            sha256sums_path="/tmp/SHA256SUMS",
            install_root="/usr/lib/agentos",
            default_workspace="/var/lib/agentos/workspaces/default",
        )

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "agentos-release-metadata.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            stored = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(validate_release_identity_payload(stored), [])


if __name__ == "__main__":
    unittest.main()


class ReleaseIdentityRemasterTests(unittest.TestCase):
    def test_validate_rejects_non_boolean_installer_hidden_flag(self):
        payload = build_release_identity_payload(
            artifact_type="iso",
            agentos_version="v0.50.0",
            output_path="/tmp/agentos.iso",
            sha256sums_path="/tmp/SHA256SUMS",
            build_manifest_path="/tmp/manifest.txt",
            base_image_path="/tmp/base.iso",
            asset_bundle_path="/tmp/assets.tar.gz",
            asset_manifest_path="/tmp/asset-manifest.txt",
        )
        payload["installer_hidden_default_path"] = "false"
        errors = validate_release_identity_payload(payload)
        self.assertTrue(any("installer_hidden_default_path must be a boolean" in e for e in errors))

    def test_validate_rejects_non_boolean_boot_flow_proof_flag(self):
        payload = build_release_identity_payload(
            artifact_type="iso",
            agentos_version="v0.50.0",
            output_path="/tmp/agentos.iso",
            sha256sums_path="/tmp/SHA256SUMS",
            build_manifest_path="/tmp/manifest.txt",
            base_image_path="/tmp/base.iso",
            asset_bundle_path="/tmp/assets.tar.gz",
            asset_manifest_path="/tmp/asset-manifest.txt",
        )
        payload["boot_flow_proof_included"] = "true"
        errors = validate_release_identity_payload(payload)
        self.assertTrue(any("boot_flow_proof_included must be a boolean" in e for e in errors))

    def test_validate_rejects_non_boolean_boot_target_activated(self):
        payload = build_release_identity_payload(
            artifact_type="iso",
            agentos_version="v0.50.0",
            output_path="/tmp/agentos.iso",
            sha256sums_path="/tmp/SHA256SUMS",
            build_manifest_path="/tmp/manifest.txt",
            base_image_path="/tmp/base.iso",
            asset_bundle_path="/tmp/assets.tar.gz",
            asset_manifest_path="/tmp/asset-manifest.txt",
        )
        payload["boot_target_activated"] = "true"
        errors = validate_release_identity_payload(payload)
        self.assertTrue(any("boot_target_activated must be a boolean" in e for e in errors))

    def test_validate_rejects_non_boolean_vm_first_screen_evidence_flag(self):
        payload = build_release_identity_payload(
            artifact_type="iso",
            agentos_version="v0.50.0",
            output_path="/tmp/agentos.iso",
            sha256sums_path="/tmp/SHA256SUMS",
            build_manifest_path="/tmp/manifest.txt",
            base_image_path="/tmp/base.iso",
            asset_bundle_path="/tmp/assets.tar.gz",
            asset_manifest_path="/tmp/asset-manifest.txt",
        )
        payload["vm_first_screen_evidence_included"] = "true"
        errors = validate_release_identity_payload(payload)
        self.assertTrue(any("vm_first_screen_evidence_included must be a boolean" in e for e in errors))

    def test_iso_payload_carries_welcome_and_guest_agent_signals_when_supplied(self):
        payload = build_release_identity_payload(
            artifact_type="iso",
            agentos_version="v0.50.0",
            output_path="/tmp/agentos.iso",
            sha256sums_path="/tmp/SHA256SUMS",
            build_manifest_path="/tmp/manifest.txt",
            base_image_path="/tmp/base.iso",
            asset_bundle_path="/tmp/assets.tar.gz",
            asset_manifest_path="/tmp/asset-manifest.txt",
            agentos_welcome_assets_staged=True,
            agentos_welcome_runtime_observed=False,
            ubuntu_installer_masked=True,
            live_guest_agent_bootstrap_staged=True,
            live_guest_agent_prestaged=False,
            live_guest_agent_reachability_path="runtime_apt_install",
            bundled_local_provider_staged=True,
            bundled_local_model_staged=True,
            bundled_local_service_staged=True,
            bundled_local_firstrun_service_staged=True,
        )
        self.assertTrue(payload["ubuntu_installer_masked"])
        self.assertTrue(payload["agentos_welcome_assets_staged"])
        self.assertFalse(payload["agentos_welcome_runtime_observed"])
        self.assertFalse(payload["agentos_welcome_owns_first_screen"])
        self.assertTrue(payload["live_guest_agent_bootstrap_staged"])
        self.assertFalse(payload["live_guest_agent_prestaged"])
        self.assertEqual(payload["live_guest_agent_reachability_path"], "runtime_apt_install")
        self.assertTrue(payload["bundled_local_provider_staged"])
        self.assertTrue(payload["bundled_local_model_staged"])
        self.assertTrue(payload["bundled_local_service_staged"])
        self.assertTrue(payload["bundled_local_firstrun_service_staged"])
        self.assertEqual(validate_release_identity_payload(payload), [])

    def test_iso_payload_sets_runtime_observed_first_screen_truth(self):
        payload = build_release_identity_payload(
            artifact_type="iso",
            agentos_version="v0.50.0",
            output_path="/tmp/agentos.iso",
            sha256sums_path="/tmp/SHA256SUMS",
            build_manifest_path="/tmp/manifest.txt",
            base_image_path="/tmp/base.iso",
            asset_bundle_path="/tmp/assets.tar.gz",
            asset_manifest_path="/tmp/asset-manifest.txt",
            agentos_welcome_assets_staged=True,
            agentos_welcome_runtime_observed=True,
        )
        self.assertTrue(payload["agentos_welcome_owns_first_screen"])
        self.assertEqual(validate_release_identity_payload(payload), [])

    def test_validate_rejects_unknown_live_guest_agent_reachability_path(self):
        payload = build_release_identity_payload(
            artifact_type="iso",
            agentos_version="v0.50.0",
            output_path="/tmp/agentos.iso",
            sha256sums_path="/tmp/SHA256SUMS",
            build_manifest_path="/tmp/manifest.txt",
            base_image_path="/tmp/base.iso",
            asset_bundle_path="/tmp/assets.tar.gz",
            asset_manifest_path="/tmp/asset-manifest.txt",
        )
        payload["live_guest_agent_reachability_path"] = "mystery"
        errors = validate_release_identity_payload(payload)
        self.assertTrue(any("live_guest_agent_reachability_path must be one of" in e for e in errors))

    def test_validate_rejects_non_boolean_ubuntu_installer_masked(self):
        payload = build_release_identity_payload(
            artifact_type="iso",
            agentos_version="v0.50.0",
            output_path="/tmp/agentos.iso",
            sha256sums_path="/tmp/SHA256SUMS",
            build_manifest_path="/tmp/manifest.txt",
            base_image_path="/tmp/base.iso",
            asset_bundle_path="/tmp/assets.tar.gz",
            asset_manifest_path="/tmp/asset-manifest.txt",
        )
        payload["ubuntu_installer_masked"] = "yes"
        errors = validate_release_identity_payload(payload)
        self.assertTrue(any("ubuntu_installer_masked must be a boolean" in e for e in errors))

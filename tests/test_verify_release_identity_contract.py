from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from release_identity import build_release_identity_payload


ROOT_DIR = Path(__file__).resolve().parent.parent


class VerifyReleaseIdentityContractTests(unittest.TestCase):
    def test_verify_iso_contract_accepts_arm64_layout(self):
        script_path = ROOT_DIR / "scripts" / "verify_release_identity_contract.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            iso = root / "agentos-v0.50.0-arm64.iso"
            sha = root / "SHA256SUMS"
            manifest = root / "manifest-v0.50.0.txt"
            base = root / "base.iso"
            bundle = root / "assets.tar.gz"
            asset_manifest = root / "asset-manifest.txt"
            iso.write_text("iso", encoding="utf-8")
            sha.write_text(f"deadbeef  {iso.name}\n", encoding="utf-8")
            manifest.write_text("agentos_version=v0.50.0\narch=arm64\n", encoding="utf-8")
            base.write_text("base", encoding="utf-8")
            bundle.write_text("bundle", encoding="utf-8")
            asset_manifest.write_text("manifest", encoding="utf-8")

            payload = build_release_identity_payload(
                artifact_type="iso",
                agentos_version="v0.50.0",
                arch="arm64",
                output_path=str(iso),
                sha256sums_path=str(sha),
                build_manifest_path=str(manifest),
                base_image_path=str(base),
                asset_bundle_path=str(bundle),
                asset_manifest_path=str(asset_manifest),
            )
            metadata = root / "agentos-release-metadata.json"
            metadata.write_text(json.dumps(payload), encoding="utf-8")

            proc = __import__("subprocess").run(
                ["python3", str(script_path), "--metadata", str(metadata), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            report = json.loads(proc.stdout)
            self.assertTrue(report["ok"], report)

    def test_verify_iso_contract_passes_for_expected_layout(self):
        script_path = ROOT_DIR / "scripts" / "verify_release_identity_contract.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            iso = root / "agentos-v0.50.0-amd64.iso"
            sha = root / "SHA256SUMS"
            manifest = root / "manifest-v0.50.0.txt"
            base = root / "base.iso"
            bundle = root / "assets.tar.gz"
            asset_manifest = root / "asset-manifest.txt"
            iso.write_text("iso", encoding="utf-8")
            sha.write_text(f"deadbeef  {iso.name}\n", encoding="utf-8")
            manifest.write_text(
                "\n".join(
                    [
                        "agentos_version=v0.50.0",
                        f"output_iso={iso}",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            base.write_text("base", encoding="utf-8")
            bundle.write_text("bundle", encoding="utf-8")
            asset_manifest.write_text("manifest", encoding="utf-8")

            payload = build_release_identity_payload(
                artifact_type="iso",
                agentos_version="v0.50.0",
                output_path=str(iso),
                sha256sums_path=str(sha),
                build_manifest_path=str(manifest),
                base_image_path=str(base),
                asset_bundle_path=str(bundle),
                asset_manifest_path=str(asset_manifest),
            )
            metadata = root / "agentos-release-metadata.json"
            metadata.write_text(json.dumps(payload), encoding="utf-8")

            proc = __import__("subprocess").run(
                ["python3", str(script_path), "--metadata", str(metadata), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            report = json.loads(proc.stdout)
            self.assertTrue(report["ok"])

    def test_verify_iso_contract_rejects_missing_boot_visual_contracts(self):
        script_path = ROOT_DIR / "scripts" / "verify_release_identity_contract.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            iso = root / "agentos-v0.50.0-amd64.iso"
            sha = root / "SHA256SUMS"
            manifest = root / "manifest-v0.50.0.txt"
            base = root / "base.iso"
            bundle = root / "assets.tar.gz"
            asset_manifest = root / "asset-manifest.txt"
            iso.write_text("iso", encoding="utf-8")
            sha.write_text(f"deadbeef  {iso.name}\n", encoding="utf-8")
            manifest.write_text("agentos_version=v0.50.0\n", encoding="utf-8")
            base.write_text("base", encoding="utf-8")
            bundle.write_text("bundle", encoding="utf-8")
            asset_manifest.write_text("manifest", encoding="utf-8")

            payload = build_release_identity_payload(
                artifact_type="iso",
                agentos_version="v0.50.0",
                output_path=str(iso),
                sha256sums_path=str(sha),
                build_manifest_path=str(manifest),
                base_image_path=str(base),
                asset_bundle_path=str(bundle),
                asset_manifest_path=str(asset_manifest),
            )
            payload["grub_theme_contract"] = ""
            metadata = root / "agentos-release-metadata.json"
            metadata.write_text(json.dumps(payload), encoding="utf-8")

            proc = __import__("subprocess").run(
                ["python3", str(script_path), "--metadata", str(metadata), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            report = json.loads(proc.stdout)
            self.assertFalse(report["ok"])
            self.assertTrue(any("grub_theme_contract" in e for e in report["errors"]))

    def test_verify_iso_contract_rejects_missing_boot_flow_proof_contract(self):
        script_path = ROOT_DIR / "scripts" / "verify_release_identity_contract.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            iso = root / "agentos-v0.50.0-amd64.iso"
            sha = root / "SHA256SUMS"
            manifest = root / "manifest-v0.50.0.txt"
            base = root / "base.iso"
            bundle = root / "assets.tar.gz"
            asset_manifest = root / "asset-manifest.txt"
            iso.write_text("iso", encoding="utf-8")
            sha.write_text(f"deadbeef  {iso.name}\n", encoding="utf-8")
            manifest.write_text("agentos_version=v0.50.0\n", encoding="utf-8")
            base.write_text("base", encoding="utf-8")
            bundle.write_text("bundle", encoding="utf-8")
            asset_manifest.write_text("manifest", encoding="utf-8")
            payload = build_release_identity_payload(
                artifact_type="iso",
                agentos_version="v0.50.0",
                output_path=str(iso),
                sha256sums_path=str(sha),
                build_manifest_path=str(manifest),
                base_image_path=str(base),
                asset_bundle_path=str(bundle),
                asset_manifest_path=str(asset_manifest),
            )
            payload["boot_flow_proof_contract"] = ""
            metadata = root / "agentos-release-metadata.json"
            metadata.write_text(json.dumps(payload), encoding="utf-8")
            proc = __import__("subprocess").run(
                ["python3", str(script_path), "--metadata", str(metadata), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            report = json.loads(proc.stdout)
            self.assertFalse(report["ok"])
            self.assertTrue(any("boot_flow_proof_contract" in e for e in report["errors"]))

    def test_verify_iso_contract_rejects_missing_default_boot_target_contract(self):
        script_path = ROOT_DIR / "scripts" / "verify_release_identity_contract.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            iso = root / "agentos-v0.50.0-amd64.iso"
            sha = root / "SHA256SUMS"
            manifest = root / "manifest-v0.50.0.txt"
            base = root / "base.iso"
            bundle = root / "assets.tar.gz"
            asset_manifest = root / "asset-manifest.txt"
            iso.write_text("iso", encoding="utf-8")
            sha.write_text(f"deadbeef  {iso.name}\n", encoding="utf-8")
            manifest.write_text("agentos_version=v0.50.0\n", encoding="utf-8")
            base.write_text("base", encoding="utf-8")
            bundle.write_text("bundle", encoding="utf-8")
            asset_manifest.write_text("manifest", encoding="utf-8")
            payload = build_release_identity_payload(
                artifact_type="iso",
                agentos_version="v0.50.0",
                output_path=str(iso),
                sha256sums_path=str(sha),
                build_manifest_path=str(manifest),
                base_image_path=str(base),
                asset_bundle_path=str(bundle),
                asset_manifest_path=str(asset_manifest),
            )
            payload["default_boot_target_contract"] = ""
            metadata = root / "agentos-release-metadata.json"
            metadata.write_text(json.dumps(payload), encoding="utf-8")
            proc = __import__("subprocess").run(
                ["python3", str(script_path), "--metadata", str(metadata), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            report = json.loads(proc.stdout)
            self.assertFalse(report["ok"])
            self.assertTrue(any("default_boot_target_contract" in e for e in report["errors"]))

    def test_verify_iso_contract_rejects_missing_vm_first_screen_evidence_contract(self):
        script_path = ROOT_DIR / "scripts" / "verify_release_identity_contract.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            iso = root / "agentos-v0.50.0-amd64.iso"
            sha = root / "SHA256SUMS"
            manifest = root / "manifest-v0.50.0.txt"
            base = root / "base.iso"
            bundle = root / "assets.tar.gz"
            asset_manifest = root / "asset-manifest.txt"
            iso.write_text("iso", encoding="utf-8")
            sha.write_text(f"deadbeef  {iso.name}\n", encoding="utf-8")
            manifest.write_text("agentos_version=v0.50.0\n", encoding="utf-8")
            base.write_text("base", encoding="utf-8")
            bundle.write_text("bundle", encoding="utf-8")
            asset_manifest.write_text("manifest", encoding="utf-8")
            payload = build_release_identity_payload(
                artifact_type="iso",
                agentos_version="v0.50.0",
                output_path=str(iso),
                sha256sums_path=str(sha),
                build_manifest_path=str(manifest),
                base_image_path=str(base),
                asset_bundle_path=str(bundle),
                asset_manifest_path=str(asset_manifest),
            )
            payload["vm_first_screen_evidence_contract"] = ""
            metadata = root / "agentos-release-metadata.json"
            metadata.write_text(json.dumps(payload), encoding="utf-8")
            proc = __import__("subprocess").run(
                ["python3", str(script_path), "--metadata", str(metadata), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            report = json.loads(proc.stdout)
            self.assertFalse(report["ok"])
            self.assertTrue(any("vm_first_screen_evidence_contract" in e for e in report["errors"]))

    def test_verify_deb_contract_rejects_wrong_install_root(self):
        script_path = ROOT_DIR / "scripts" / "verify_release_identity_contract.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            deb = root / "agentos_0.50.0_amd64.deb"
            sha = root / "SHA256SUMS"
            deb.write_text("deb", encoding="utf-8")
            sha.write_text(f"deadbeef  {deb.name}\n", encoding="utf-8")

            payload = build_release_identity_payload(
                artifact_type="deb",
                agentos_version="v0.50.0",
                package_version="0.50.0",
                output_path=str(deb),
                sha256sums_path=str(sha),
                install_root="/tmp/agentos",
                default_workspace="/var/lib/agentos/workspaces/default",
            )
            metadata = root / "agentos-release-metadata.json"
            metadata.write_text(json.dumps(payload), encoding="utf-8")

            proc = __import__("subprocess").run(
                ["python3", str(script_path), "--metadata", str(metadata), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            report = json.loads(proc.stdout)
            self.assertFalse(report["ok"])
            self.assertTrue(any("install_root does not match deb contract" in e for e in report["errors"]))


class VerifyReleaseIdentityRemasterTests(unittest.TestCase):
    def test_verify_iso_contract_accepts_headless_base_image_type(self):
        script_path = ROOT_DIR / "scripts" / "verify_release_identity_contract.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            iso = root / "agentos-v0.50.0-amd64.iso"
            sha = root / "SHA256SUMS"
            manifest = root / "manifest-v0.50.0.txt"
            base = root / "ubuntu-24.04.4-live-server-amd64.iso"
            bundle = root / "assets.tar.gz"
            asset_manifest = root / "asset-manifest.txt"
            iso.write_text("iso", encoding="utf-8")
            sha.write_text(f"deadbeef  {iso.name}\n", encoding="utf-8")
            manifest.write_text("agentos_version=v0.50.0\n", encoding="utf-8")
            base.write_text("base", encoding="utf-8")
            bundle.write_text("bundle", encoding="utf-8")
            asset_manifest.write_text("manifest", encoding="utf-8")
            payload = build_release_identity_payload(
                artifact_type="iso",
                agentos_version="v0.50.0",
                output_path=str(iso),
                sha256sums_path=str(sha),
                build_manifest_path=str(manifest),
                base_image_path=str(base),
                asset_bundle_path=str(bundle),
                asset_manifest_path=str(asset_manifest),
                base_image_type="headless-live-server-iso",
            )
            metadata = root / "agentos-release-metadata.json"
            metadata.write_text(json.dumps(payload), encoding="utf-8")
            proc = __import__("subprocess").run(
                ["python3", str(script_path), "--metadata", str(metadata), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            report = json.loads(proc.stdout)
            self.assertTrue(report["ok"], report["errors"])

    def test_verify_iso_contract_rejects_wrong_base_image_type(self):
        script_path = ROOT_DIR / "scripts" / "verify_release_identity_contract.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            iso = root / "agentos-v0.50.0-amd64.iso"
            sha = root / "SHA256SUMS"
            manifest = root / "manifest-v0.50.0.txt"
            base = root / "base.iso"
            bundle = root / "assets.tar.gz"
            asset_manifest = root / "asset-manifest.txt"
            iso.write_text("iso", encoding="utf-8")
            sha.write_text(f"deadbeef  {iso.name}\n", encoding="utf-8")
            manifest.write_text("agentos_version=v0.50.0\n", encoding="utf-8")
            base.write_text("base", encoding="utf-8")
            bundle.write_text("bundle", encoding="utf-8")
            asset_manifest.write_text("manifest", encoding="utf-8")
            payload = build_release_identity_payload(artifact_type="iso", agentos_version="v0.50.0", output_path=str(iso), sha256sums_path=str(sha), build_manifest_path=str(manifest), base_image_path=str(base), asset_bundle_path=str(bundle), asset_manifest_path=str(asset_manifest))
            payload["base_image_type"] = "unknown-iso"
            metadata = root / "agentos-release-metadata.json"
            metadata.write_text(json.dumps(payload), encoding="utf-8")
            proc = __import__("subprocess").run(["python3", str(script_path), "--metadata", str(metadata), "--json"], capture_output=True, text=True, check=False)
            report = json.loads(proc.stdout)
            self.assertFalse(report["ok"])
            self.assertTrue(any("base_image_type" in e for e in report["errors"]))

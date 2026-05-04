from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
EXPORT_SCRIPT = ROOT_DIR / "scripts" / "export_install_verification_manifest.py"
INSTALL_SCRIPT = ROOT_DIR / "scripts" / "install_kernel_boot_integration.sh"


class InstallVerificationManifestTests(unittest.TestCase):
    def test_export_manifest_passes_validation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            metadata = root / "agentos-release-metadata.json"
            install_root = root / "install-root"
            metadata.write_text(
                json.dumps(
                    {
                        "artifact_type": "iso",
                        "distribution_contract": "agentos_managed_session",
                        "primary_entry_contract": "agentos_setup_to_ai_shell",
                    }
                ),
                encoding="utf-8",
            )
            install_root.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env.update(
                {
                    "AGENTOS_INSTALL_ROOT": str(install_root),
                    "AGENTOS_ENABLE_SYSTEMD": "0",
                    "AGENTOS_BROKER_BYPASS": "1",
                }
            )
            proc = subprocess.run(
                ["bash", str(INSTALL_SCRIPT)],
                cwd=ROOT_DIR,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            out = root / "install-verification.json"
            proc = subprocess.run(
                [
                    "python3",
                    str(EXPORT_SCRIPT),
                    "--metadata",
                    str(metadata),
                    "--install-root",
                    str(install_root),
                    "--workspace",
                    "./workspaces/default",
                    "--output",
                    str(out),
                ],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "agentos-install-verification.v1")
            self.assertTrue(payload["summary"]["ok"])
            self.assertEqual(payload["summary"]["artifact_type"], "iso")
            self.assertIn("health_commands", payload["summary"])

            proc = subprocess.run(
                ["python3", str(EXPORT_SCRIPT), "--validate", str(out), "--json"],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout)
            report = json.loads(proc.stdout)
            self.assertTrue(report["ok"])

    def test_validate_rejects_failed_summary(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "install-verification.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": "agentos-install-verification.v1",
                        "generated_at_utc": "2026-01-01T00:00:00Z",
                        "distribution_contract": "agentos_managed_session",
                        "primary_entry_contract": "agentos_setup_to_ai_shell",
                        "install_validation": {"ok": False, "recovery_controls": {}},
                        "appliance_manifest": {
                            "schema_version": "agentos-vm-appliance.v1",
                            "appliance_contract": "agentos_vm_demo",
                            "platform": "ubuntu-24.04",
                            "workspace": "./workspaces/default",
                            "snapshot_label": "agentos-demo-clean",
                            "recommended_hypervisors": ["qemu"],
                            "primary_entry_contract": "agentos_setup_to_ai_shell",
                            "launch_helper": "scripts/vm_demo_flow.sh",
                            "reset_helper": "scripts/vm_demo_reset.sh",
                            "health_commands": ["scripts/agentos-kernelctl health"],
                            "recovery_commands": ["export AGENTOS_BOOT_AUTOSTART=0"],
                        },
                        "summary": {
                            "ok": False,
                            "health_commands": ["scripts/agentos-kernelctl health"],
                            "recovery_commands": ["export AGENTOS_BOOT_AUTOSTART=0"],
                            "recovery_controls": {"boot_autostart_bypass": "AGENTOS_BOOT_AUTOSTART=0"},
                        },
                        "errors": [],
                    }
                ),
                encoding="utf-8",
            )
            proc = subprocess.run(
                ["python3", str(EXPORT_SCRIPT), "--validate", str(manifest), "--json"],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            self.assertTrue(any("install_validation.ok must be true" in e for e in report["errors"]))

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPT = ROOT_DIR / "scripts" / "vm_appliance_manifest.py"


class VmApplianceManifestTests(unittest.TestCase):
    def test_build_manifest_contains_launch_and_reset_helpers(self):
        proc = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--workspace",
                "./workspaces/default",
                "--snapshot-label",
                "agentos-demo-clean",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], "agentos-vm-appliance.v1")
        self.assertEqual(payload["appliance_contract"], "agentos_vm_demo")
        self.assertIn("qemu", payload["recommended_hypervisors"])
        self.assertTrue(payload["launch_helper"].endswith("scripts/vm_demo_flow.sh"))
        self.assertTrue(payload["reset_helper"].endswith("scripts/vm_demo_reset.sh"))

    def test_validate_rejects_missing_health_commands(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "vm-appliance.json"
            payload = {
                "schema_version": "agentos-vm-appliance.v1",
                "appliance_contract": "agentos_vm_demo",
                "platform": "ubuntu-24.04",
                "workspace": "./workspaces/default",
                "snapshot_label": "agentos-demo-clean",
                "recommended_hypervisors": ["qemu"],
                "primary_entry_contract": "agentos_setup_to_ai_shell",
                "launch_helper": "scripts/vm_demo_flow.sh",
                "reset_helper": "scripts/vm_demo_reset.sh",
                "health_commands": [],
                "recovery_commands": ["export AGENTOS_BOOT_AUTOSTART=0"],
            }
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            proc = subprocess.run(
                ["python3", str(SCRIPT), "--validate", str(manifest), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            self.assertTrue(any("health_commands must be a non-empty list" in e for e in report["errors"]))

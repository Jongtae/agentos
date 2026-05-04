from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPT = ROOT_DIR / "scripts" / "verify_boot_target_activation.py"


class VerifyBootTargetActivationTests(unittest.TestCase):
    def test_generate_and_validate_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            iso_root = root / "iso-root"
            (iso_root / "agentos").mkdir(parents=True, exist_ok=True)
            patch_report = root / "boot-entry-patch-report.json"
            patch_report.write_text(
                json.dumps(
                    {
                        "continue_present": True,
                        "install_present": False,
                        "install_path_available": True,
                        "recovery_present": True,
                        "installer_hidden_default_path": True,
                        "default_boot_target_label": "Continue to AgentOS",
                        "default_boot_target_entry_index": 0,
                        "grub_default_target_configured": True,
                        "default_boot_target_configured": True,
                    }
                ),
                encoding="utf-8",
            )
            report = root / "boot-target-activation.json"
            proc = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--iso-root",
                    str(iso_root),
                    "--boot-patch-report",
                    str(patch_report),
                    "--output",
                    str(report),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "agentos-boot-target-activation.v1")
            self.assertEqual(payload["boot_target_contract"], "agentos_continue_boot_target.v1")
            self.assertTrue(payload["boot_target_activated"])
            validate = subprocess.run(
                ["python3", str(SCRIPT), "--validate", str(report), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(validate.returncode, 0)
            result = json.loads(validate.stdout)
            self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()

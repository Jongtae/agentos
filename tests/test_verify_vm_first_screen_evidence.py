from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPT = ROOT_DIR / "scripts" / "verify_vm_first_screen_evidence.py"


class VerifyVmFirstScreenEvidenceTests(unittest.TestCase):
    def test_generate_and_validate_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            iso_root = root / "iso-root"
            (iso_root / "agentos").mkdir(parents=True, exist_ok=True)
            boot_flow = root / "boot-flow-proof.json"
            boot_target = root / "boot-target-activation.json"
            boot_flow.write_text(
                json.dumps(
                    {
                        "welcome_autostart_included": True,
                        "welcome_shell_included": True,
                    }
                ),
                encoding="utf-8",
            )
            boot_target.write_text(
                json.dumps(
                    {
                        "default_boot_target_label": "Continue to AgentOS",
                        "boot_target_activated": True,
                    }
                ),
                encoding="utf-8",
            )
            out = root / "vm-first-screen-evidence.json"
            proc = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--iso-root",
                    str(iso_root),
                    "--boot-flow-proof",
                    str(boot_flow),
                    "--boot-target-activation",
                    str(boot_target),
                    "--output",
                    str(out),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "agentos-vm-first-screen-evidence.v1")
            self.assertEqual(payload["expected_first_screen"], "AgentOS Welcome")
            self.assertEqual(payload["evidence_status"], "ready")
            validate = subprocess.run(
                ["python3", str(SCRIPT), "--validate", str(out), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(validate.returncode, 0)
            result = json.loads(validate.stdout)
            self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "kernel_installed_reboot_slot_proof.py"


class KernelInstalledRebootSlotProofTests(unittest.TestCase):
    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            next_boot = tmp_path / "next.json"
            switch = tmp_path / "switch.json"
            out = tmp_path / "proof.json"
            next_boot.write_text(json.dumps({
                "schema_version": "agentos-next-boot-target-integration.v1",
                "target_slot": "B",
            }) + "\n", encoding="utf-8")
            switch.write_text(json.dumps({
                "schema_version": "agentos-installed-slot-switch-evidence.v1",
                "observed_slot": "B",
                "switch_confirmed": True,
                "identity_path": "Installed AgentOS Boot -> AgentOS Setup -> AgentOS Managed Session -> ai>",
            }) + "\n", encoding="utf-8")

            subprocess.run([
                str(SCRIPT),
                "--report-dir", str(tmp_path / "reports"),
                "--next-boot-target", str(next_boot),
                "--installed-slot-switch-evidence", str(switch),
                "--output", str(out),
            ], check=True)

            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "agentos-installed-reboot-slot-proof.v1")
            self.assertTrue(payload["summary"]["ok"])

            validate = subprocess.run([
                str(SCRIPT),
                "--validate", str(out),
                "--json",
            ], check=True, capture_output=True, text=True)
            result = json.loads(validate.stdout)
            self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()

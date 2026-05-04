from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.appliance_platform import build_recovery_mode_contract
from scripts.kernel_recovery_mode_contract import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_recovery_mode_contract.py"


class KernelRecoveryModeContractTests(unittest.TestCase):
    def test_contract_exposes_return_to_agentos(self) -> None:
        payload = build_recovery_mode_contract()
        self.assertEqual(payload["schema_version"], "agentos-recovery-mode-contract.v1")
        self.assertEqual(payload["label"], "Recovery")
        self.assertEqual(payload["primary_return_action"], "Return to AgentOS")
        self.assertIn("slot_recovery", payload)
        self.assertEqual(validate_payload(payload), [])

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "recovery-mode.json"
            subprocess.run(["python3", str(SCRIPT), "--output", str(out)], cwd=ROOT_DIR, check=True)
            result = subprocess.run(
                ["python3", str(SCRIPT), "--validate", str(out), "--json"],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.operator_mode import operator_mode_contract
from scripts.kernel_operator_mode import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_operator_mode.py"


class KernelOperatorModeTests(unittest.TestCase):
    def test_default_managed_session_is_user_mode(self) -> None:
        payload = operator_mode_contract(
            session_origin={"category": "local_managed_tty1"},
            setup_state={"status": "configured"},
        )
        self.assertEqual(payload["current_mode"], "user_mode")
        self.assertEqual(payload["recommended_surface"], "ai_shell")
        self.assertEqual(validate_payload(payload), [])

    def test_recovery_controls_force_recovery_mode(self) -> None:
        old = os.environ.get("AGENTOS_BROKER_BYPASS")
        os.environ["AGENTOS_BROKER_BYPASS"] = "1"
        try:
            payload = operator_mode_contract(
                session_origin={"category": "local_managed_tty1"},
                setup_state={"status": "configured"},
            )
        finally:
            if old is None:
                os.environ.pop("AGENTOS_BROKER_BYPASS", None)
            else:
                os.environ["AGENTOS_BROKER_BYPASS"] = old
        self.assertEqual(payload["current_mode"], "recovery_mode")
        self.assertIn("repair", payload["surfaces"]["recovery_mode"])

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "operator-mode.json"
            subprocess.run(
                ["python3", str(SCRIPT), "--session-origin", "local_managed_tty1", "--setup-status", "configured", "--output", str(out)],
                cwd=ROOT_DIR,
                check=True,
            )
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

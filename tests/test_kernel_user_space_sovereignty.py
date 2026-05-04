from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.operator_mode import operator_mode_contract
from kernel.runtime_entry import build_runtime_entry_contract
from kernel.user_space_sovereignty import build_user_space_sovereignty_report
from scripts.kernel_user_space_sovereignty import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_user_space_sovereignty.py"


class KernelUserSpaceSovereigntyTests(unittest.TestCase):
    def test_contract_contains_prioritized_actions(self) -> None:
        session_origin = {"category": "local_managed_tty1"}
        setup_state = {"status": "configured", "next_managed_entry": "ai_shell"}
        runtime_entry = build_runtime_entry_contract(session_origin=session_origin, setup_state=setup_state)
        operator_mode = operator_mode_contract(session_origin=session_origin, setup_state=setup_state)
        payload = build_user_space_sovereignty_report(
            session_origin=session_origin,
            setup_state=setup_state,
            runtime_entry=runtime_entry,
            operator_mode=operator_mode,
        )
        self.assertEqual(validate_payload(payload), [])
        self.assertGreaterEqual(payload["summary"]["managed_action_count"], 1)
        self.assertIn("execute_high_impact_command", payload["summary"]["priority_actions"])

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "user-space-sovereignty.json"
            subprocess.run(["python3", str(SCRIPT), "--output", str(out)], cwd=ROOT_DIR, check=True)
            result = subprocess.run(["python3", str(SCRIPT), "--validate", str(out), "--json"], cwd=ROOT_DIR, check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()

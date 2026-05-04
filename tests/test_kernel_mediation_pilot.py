from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.mediation_pilot import build_mediation_pilot_report
from scripts.kernel_mediation_pilot import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_mediation_pilot.py"


class KernelMediationPilotTests(unittest.TestCase):
    def test_report_contains_selected_targets(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            (workspace / "artifacts" / "kernel-policy").mkdir(parents=True)
            payload = build_mediation_pilot_report(workspace=str(workspace))
            self.assertEqual(validate_payload(payload), [])
            targets = {item["pilot_target"] for item in payload["selected_targets"]}
            self.assertIn("interactive_user_destructive", targets)
            self.assertIn("operator_control_change", targets)

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            (workspace / "artifacts" / "kernel-policy").mkdir(parents=True)
            out = Path(td) / "mediation-pilot.json"
            subprocess.run(["python3", str(SCRIPT), "--workspace", str(workspace), "--output", str(out)], cwd=ROOT_DIR, check=True)
            result = subprocess.run(["python3", str(SCRIPT), "--validate", str(out), "--json"], cwd=ROOT_DIR, check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()

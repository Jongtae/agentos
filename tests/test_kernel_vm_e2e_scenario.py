from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.vm_e2e_scenario import run_vm_e2e_scenario

ROOT_DIR = Path(__file__).resolve().parents[1]
SCENARIO_SCRIPT = ROOT_DIR / "scripts" / "kernel_vm_e2e_scenario.py"


class VmE2EScenarioTests(unittest.TestCase):
    def test_scenario_refreshes_required_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            payload = run_vm_e2e_scenario(workspace)

            self.assertTrue(payload["summary"]["document_native_handled"])
            self.assertTrue(payload["summary"]["web_handled"])
            self.assertTrue(payload["summary"]["intake_ok"])
            self.assertGreaterEqual(payload["summary"]["execution_samples"], 1)
            self.assertTrue((workspace / "artifacts" / "capability-substrate" / "latest-document-access.json").exists())
            self.assertTrue((workspace / "artifacts" / "capability-substrate" / "latest-web-access.json").exists())
            self.assertTrue((workspace / "artifacts" / "capability-substrate" / "latest-intake-surface.json").exists())

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            out = Path(td) / "scenario.json"
            subprocess.run(
                ["python3", str(SCENARIO_SCRIPT), "--workspace", str(workspace), "--output", str(out)],
                cwd=ROOT_DIR,
                check=True,
            )
            result = subprocess.run(
                ["python3", str(SCENARIO_SCRIPT), "--validate", str(out), "--json"],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()

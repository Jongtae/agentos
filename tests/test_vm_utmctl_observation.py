from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "vm_utmctl_observation.py"


class VmUtmctlObservationTests(unittest.TestCase):
    def test_dry_run_json_includes_utmctl_and_proof_commands(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True)
            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--vm-name",
                    "AgentOS Preview",
                    "--workspace",
                    str(workspace),
                    "--dry-run",
                    "--json",
                ],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
                check=True,
            )
            payload = json.loads(result.stdout)

        self.assertEqual(payload["schema_version"], "agentos-utmctl-vm-observation.v1")
        self.assertEqual(payload["summary"]["observation_mode"], "dry_run")
        self.assertTrue(any("utmctl status" in command and "AgentOS Preview" in command for command in payload["planned_commands"]))
        self.assertTrue(any("utmctl start" in command and "AgentOS Preview" in command for command in payload["planned_commands"]))
        self.assertTrue(any("kernel_vm_e2e_scenario.py" in command for command in payload["planned_commands"]))
        self.assertTrue(any("--use-existing-manifests" in command for command in payload["planned_commands"]))


if __name__ == "__main__":
    unittest.main()

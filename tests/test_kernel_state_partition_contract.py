from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.appliance_platform import build_state_partition_contract, build_state_root_usage_summary
from scripts.kernel_state_partition_contract import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_state_partition_contract.py"
STATE_ROOT_INIT = ROOT_DIR / "image-assets" / "live" / "bin" / "agentos-state-root-init"


class KernelStatePartitionContractTests(unittest.TestCase):
    def test_contract_describes_mutable_roots(self) -> None:
        payload = build_state_partition_contract()
        self.assertEqual(payload["schema_version"], "agentos-state-partition-contract.v1")
        self.assertEqual(payload["state_root"], "/var/lib/agentos")
        self.assertIn("workspace_state", payload["mutable_contract"])
        self.assertEqual(validate_payload(payload), [])

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "state-partition.json"
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

    def test_state_root_usage_summary_reports_initialized_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env = dict(os.environ)
            env["AGENTOS_STATE_ROOT"] = td
            subprocess.run(["bash", str(STATE_ROOT_INIT)], check=True, env=env, capture_output=True, text=True)
            old = os.environ.get("AGENTOS_STATE_ROOT")
            os.environ["AGENTOS_STATE_ROOT"] = td
            self.addCleanup(
                lambda: os.environ.pop("AGENTOS_STATE_ROOT", None)
                if old is None
                else os.environ.__setitem__("AGENTOS_STATE_ROOT", old)
            )
            usage = build_state_root_usage_summary()
        self.assertTrue(usage["initialized"])
        self.assertTrue(usage["manifest_exists"])
        self.assertIn("workspaces", usage["present_paths"])
        self.assertEqual(usage["missing_paths"], [])


if __name__ == "__main__":
    unittest.main()

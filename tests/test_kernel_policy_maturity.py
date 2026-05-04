from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.policy_maturity import build_policy_maturity_report
from scripts.kernel_policy_maturity import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_policy_maturity.py"


class KernelPolicyMaturityTests(unittest.TestCase):
    def test_contract_contains_expected_targets(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            (workspace / "artifacts" / "kernel-policy").mkdir(parents=True)
            payload = build_policy_maturity_report(str(workspace), parser_cmd="python3")
            self.assertEqual(validate_payload(payload), [])
            targets = {item["policy_target"] for item in payload["targets"]}
            self.assertEqual(
                targets,
                {"fs_workspace_boundary", "network_allowlist", "destructive_action_approval"},
            )

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            (workspace / "artifacts" / "kernel-policy").mkdir(parents=True)
            out = Path(td) / "policy-maturity.json"
            subprocess.run(
                ["python3", str(SCRIPT), "--workspace", str(workspace), "--parser-cmd", "python3", "--output", str(out)],
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

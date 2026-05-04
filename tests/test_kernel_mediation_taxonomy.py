from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.mediation_taxonomy import build_mediation_taxonomy
from scripts.kernel_mediation_taxonomy import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_mediation_taxonomy.py"


class KernelMediationTaxonomyTests(unittest.TestCase):
    def test_build_taxonomy_contains_user_and_system_models(self) -> None:
        payload = build_mediation_taxonomy(workspace="./workspaces/default")
        self.assertEqual(payload["schema_version"], "agentos-mediation-taxonomy.v1")
        self.assertIn("user_intent", payload["origin_models"])
        self.assertIn("system_originated", payload["origin_models"])
        self.assertEqual(validate_payload(payload), [])

    def test_mandatory_broker_targets_include_operator_control(self) -> None:
        payload = build_mediation_taxonomy(workspace="./workspaces/default")
        self.assertIn("operator_control_change", payload["summary"]["mandatory_broker_targets"])

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "taxonomy.json"
            subprocess.run(
                ["python3", str(SCRIPT), "--workspace", "./workspaces/default", "--output", str(out)],
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

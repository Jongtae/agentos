from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.appliance_platform import build_system_image_layout_contract
from scripts.kernel_system_image_layout import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_system_image_layout.py"


class KernelSystemImageLayoutTests(unittest.TestCase):
    def test_contract_has_expected_partitions(self) -> None:
        payload = build_system_image_layout_contract()
        names = [entry["id"] for entry in payload["partition_contract"]]
        self.assertEqual(payload["schema_version"], "agentos-system-image-layout.v1")
        self.assertIn("system_a", names)
        self.assertIn("system_b", names)
        self.assertIn("state", names)
        self.assertIn("recovery", names)
        self.assertEqual(validate_payload(payload), [])

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "layout.json"
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

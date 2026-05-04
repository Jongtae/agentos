from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.unified_event_schema import unified_event_schema_contract
from scripts.kernel_unified_event_schema import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_unified_event_schema.py"


class KernelUnifiedEventSchemaTests(unittest.TestCase):
    def test_contract_contains_required_families(self) -> None:
        payload = unified_event_schema_contract()
        families = {item["family"] for item in payload["event_families"]}
        self.assertTrue({"process", "approval", "policy", "recovery", "service", "session"}.issubset(families))
        self.assertEqual(validate_payload(payload), [])

    def test_causal_chain_includes_stable_linkage(self) -> None:
        payload = unified_event_schema_contract()
        causal = payload["causal_chain"]
        self.assertIn("request_id", causal["stable_fields"])
        self.assertIn("approval_id", causal["stable_fields"])
        self.assertIn("parent_event_id", causal["phase_fields"])

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "unified-event-schema.json"
            subprocess.run(["python3", str(SCRIPT), "--output", str(out)], cwd=ROOT_DIR, check=True)
            result = subprocess.run(["python3", str(SCRIPT), "--validate", str(out), "--json"], cwd=ROOT_DIR, check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()

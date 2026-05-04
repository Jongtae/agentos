from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.kernel_mediation_coverage import build_mediation_coverage_report


class KernelMediationCoverageTests(unittest.TestCase):
    def test_build_mediation_coverage_report_exposes_targets_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            payload = build_mediation_coverage_report(workspace=str(Path(td) / "workspace"))
            self.assertEqual(payload["schema_version"], "agentos-mediation-coverage.v1")
            self.assertGreaterEqual(payload["summary"]["target_count"], 6)
            self.assertIn("destructive_action_approval", payload["summary"]["policy_targets"])
            target_ids = {item["path_id"] for item in payload["targets"]}
            self.assertIn("destructive_shell_exec", target_ids)
            self.assertIn("network_sensitive_exec", target_ids)


if __name__ == "__main__":
    unittest.main()

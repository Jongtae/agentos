from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.kernel_repair_report_status import build_report_status


class KernelRepairReportStatusTests(unittest.TestCase):
    def test_report_status_surfaces_shadow_and_alignment_summaries(self):
        with tempfile.TemporaryDirectory() as td:
            report_dir = Path(td)
            payload = {
                "ok": True,
                "mode": "apply",
                "needs_repair": False,
                "after": {
                    "shadow_mode": {
                        "available": True,
                        "aligned": True,
                        "delta": 0,
                        "user_space_blocked_count": 1,
                        "shadow_detected_count": 1,
                        "coverage_summary": {
                            "policy_target_count": 3,
                            "aligned_count": 2,
                            "divergent_count": 1,
                        },
                        "policy_targets": [
                            {
                                "policy_target": "fs_workspace_boundary",
                                "comparison": {"status": "aligned", "delta": 0},
                            },
                            {
                                "policy_target": "network_allowlist",
                                "comparison": {"status": "divergent", "delta": -1},
                            },
                            {
                                "policy_target": "destructive_action_approval",
                                "comparison": {"status": "aligned", "delta": 0},
                            },
                        ],
                    },
                    "event_fabric": {
                        "available": True,
                        "overall_aligned": False,
                        "total_events": 3,
                        "recent_kinds": ["file.outside_workspace_candidate", "network.connect_candidate"],
                        "enforced_pilot": {
                            "configured_enabled": True,
                            "effective_enabled": True,
                            "policy_target": "fs_workspace_boundary",
                        },
                        "supported_policy_targets": ["fs_workspace_boundary", "network_allowlist", "destructive_action_approval"],
                        "next_policy_target": "destructive_action_approval",
                        "policy_targets": [
                            {
                                "policy_target": "fs_workspace_boundary",
                                "status": "aligned",
                                "aligned": True,
                                "delta": 0,
                            },
                            {
                                "policy_target": "destructive_action_approval",
                                "status": "aligned",
                                "aligned": True,
                                "delta": 0,
                            },
                        ],
                    },
                },
            }
            path = report_dir / "kernel-repair-20260414T000000000000Z.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            report = build_report_status(str(report_dir))

            self.assertTrue(report["ok"])
            self.assertTrue(report["shadow_summary"]["available"])
            self.assertTrue(report["shadow_summary"]["aligned"])
            self.assertEqual(report["shadow_summary"]["coverage_summary"]["policy_target_count"], 3)
            self.assertEqual(len(report["shadow_summary"]["policy_targets"]), 3)
            self.assertTrue(report["alignment_summary"]["available"])
            self.assertFalse(report["alignment_summary"]["overall_aligned"])
            self.assertEqual(report["alignment_summary"]["total_events"], 3)
            self.assertTrue(report["alignment_summary"]["enforced_pilot"]["configured_enabled"])
            self.assertIn("destructive_action_approval", report["alignment_summary"]["supported_policy_targets"])
            self.assertEqual(report["alignment_summary"]["next_policy_target"], "destructive_action_approval")


if __name__ == "__main__":
    unittest.main()

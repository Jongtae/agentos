from __future__ import annotations

import unittest

from kernel.runtime.autoremediation_stage_governance import (
    autoremediation_stage_governance_report,
)


class RuntimeAutoremediationStageGovernanceTests(unittest.TestCase):
    def test_handoff_when_batch_handoff(self):
        report = autoremediation_stage_governance_report(
            batch_payload={
                "batch_governance": {"decision": "handoff", "reason": "batch_error_runs_high", "eligible_run_indexes": [1, 2]},
                "batch_review": {"hotspots": []},
            }
        )
        self.assertEqual(report.get("decision"), "handoff")
        self.assertEqual(report.get("reason"), "batch_requires_handoff")

    def test_hold_when_no_candidates(self):
        report = autoremediation_stage_governance_report(
            batch_payload={
                "batch_governance": {"decision": "hold", "reason": "no_eligible_runs", "eligible_run_indexes": []},
                "batch_review": {"hotspots": []},
            }
        )
        self.assertEqual(report.get("decision"), "hold")
        self.assertEqual(report.get("reason"), "no_stage_candidates")

    def test_hold_when_hotspots_high(self):
        report = autoremediation_stage_governance_report(
            batch_payload={
                "batch_governance": {"decision": "allow", "reason": "batch_ready", "eligible_run_indexes": [1, 2, 3]},
                "batch_review": {"hotspots": [{"run_index": 2}, {"run_index": 3}]},
            },
            max_hotspots_for_allow=1,
            critical_hotspots_for_handoff=5,
        )
        self.assertEqual(report.get("decision"), "hold")
        self.assertEqual(report.get("reason"), "stage_hotspots_high")

    def test_allow_with_window_and_cursor(self):
        report = autoremediation_stage_governance_report(
            batch_payload={
                "batch_governance": {"decision": "allow", "reason": "batch_ready", "eligible_run_indexes": [1, 2, 3, 4]},
                "batch_review": {"hotspots": []},
            },
            max_stage_actions=2,
            stage_cursor=1,
        )
        self.assertEqual(report.get("decision"), "allow")
        window = report.get("stage_window", {})
        self.assertEqual(window.get("selected_run_indexes"), [2, 3])
        self.assertEqual(window.get("next_cursor"), 3)
        self.assertTrue(bool(window.get("has_remaining", False)))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from kernel.runtime.autoremediation_auto_pause import (
    autoremediation_auto_pause_report,
)


class RuntimeAutoremediationAutoPauseTests(unittest.TestCase):
    def test_no_pause_when_healthy(self):
        report = autoremediation_auto_pause_report(
            rollback_budget={"status": "allow", "reason": "rollback_budget_healthy"},
            stage_governance={"decision": "allow", "reason": "stage_ready"},
            consecutive_holds=0,
            hold_pause_threshold=3,
        )
        self.assertFalse(bool(report.get("should_pause", True)))
        self.assertEqual(report.get("reason"), "pause_not_required")

    def test_pause_when_budget_exhausted(self):
        report = autoremediation_auto_pause_report(
            rollback_budget={"status": "handoff", "reason": "rollback_budget_exhausted"},
            stage_governance={"decision": "hold", "reason": "stage_hotspots_high"},
            consecutive_holds=1,
            hold_pause_threshold=3,
        )
        self.assertTrue(bool(report.get("should_pause", False)))
        self.assertEqual(report.get("reason"), "rollback_budget_exhausted")
        self.assertEqual(report.get("severity"), "critical")

    def test_pause_when_persistent_hold(self):
        report = autoremediation_auto_pause_report(
            rollback_budget={"status": "allow", "reason": "rollback_budget_healthy"},
            stage_governance={"decision": "hold", "reason": "stage_window_exhausted"},
            consecutive_holds=3,
            hold_pause_threshold=3,
        )
        self.assertTrue(bool(report.get("should_pause", False)))
        self.assertEqual(report.get("reason"), "persistent_stage_hold")


if __name__ == "__main__":
    unittest.main()

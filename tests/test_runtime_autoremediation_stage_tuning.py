from __future__ import annotations

import unittest

from kernel.runtime.autoremediation_stage_tuning import (
    autoremediation_stage_tuning_report,
)


class RuntimeAutoremediationStageTuningTests(unittest.TestCase):
    def test_expand_when_stable_allow(self):
        report = autoremediation_stage_tuning_report(
            stage_governance={
                "decision": "allow",
                "totals": {"hotspots": 0, "selected_runs": 2},
                "stage_window": {"size": 2, "next_cursor": 2},
            },
            rollback_budget={"status": "allow", "window": {"failures": 0}},
            min_window_size=1,
            max_window_size=4,
        )
        self.assertEqual(report.get("action"), "expand")
        self.assertEqual((report.get("next", {}) or {}).get("window_size"), 3)

    def test_shrink_when_pressure(self):
        report = autoremediation_stage_tuning_report(
            stage_governance={
                "decision": "hold",
                "totals": {"hotspots": 2, "selected_runs": 1},
                "stage_window": {"size": 3, "next_cursor": 3},
            },
            rollback_budget={"status": "allow", "window": {"failures": 0}},
            min_window_size=1,
            max_window_size=4,
        )
        self.assertEqual(report.get("action"), "shrink")
        self.assertEqual((report.get("next", {}) or {}).get("window_size"), 2)

    def test_shrink_to_min_when_budget_exhausted(self):
        report = autoremediation_stage_tuning_report(
            stage_governance={
                "decision": "allow",
                "totals": {"hotspots": 0, "selected_runs": 2},
                "stage_window": {"size": 4, "next_cursor": 4},
            },
            rollback_budget={"status": "handoff", "window": {"failures": 3}},
            min_window_size=1,
            max_window_size=4,
        )
        self.assertEqual(report.get("action"), "shrink")
        self.assertEqual((report.get("next", {}) or {}).get("window_size"), 1)
        self.assertEqual(report.get("reason"), "rollback_budget_exhausted")


if __name__ == "__main__":
    unittest.main()

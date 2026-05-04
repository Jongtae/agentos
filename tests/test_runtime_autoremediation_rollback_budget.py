from __future__ import annotations

import unittest

from kernel.runtime.autoremediation_rollback_budget import (
    autoremediation_rollback_budget_report,
)


class RuntimeAutoremediationRollbackBudgetTests(unittest.TestCase):
    def test_healthy_budget_allows(self):
        report = autoremediation_rollback_budget_report(
            run_results=[
                {"decision": "allow", "exit_code": 0},
                {"decision": "allow", "exit_code": 0},
            ],
            rollback_budget=2,
            window_size=3,
            max_failures_per_window=1,
        )
        self.assertEqual(report.get("status"), "allow")
        self.assertEqual(report.get("reason"), "rollback_budget_healthy")
        self.assertEqual((report.get("budget", {}) or {}).get("remaining"), 2)

    def test_failure_pressure_holds(self):
        report = autoremediation_rollback_budget_report(
            run_results=[
                {"decision": "allow", "exit_code": 0},
                {"decision": "allow", "exit_code": 4},
                {"decision": "handoff", "exit_code": 0},
            ],
            rollback_budget=5,
            window_size=3,
            max_failures_per_window=1,
        )
        self.assertEqual(report.get("status"), "hold")
        self.assertEqual(report.get("reason"), "rollback_failure_pressure_high")
        self.assertEqual((report.get("window", {}) or {}).get("failures"), 2)

    def test_budget_exhausted_handoff(self):
        report = autoremediation_rollback_budget_report(
            run_results=[
                {"decision": "allow", "exit_code": 5},
                {"decision": "handoff", "exit_code": 0},
                {"decision": "allow", "exit_code": 4},
            ],
            rollback_budget=2,
            window_size=5,
            max_failures_per_window=5,
        )
        self.assertEqual(report.get("status"), "handoff")
        self.assertEqual(report.get("reason"), "rollback_budget_exhausted")
        self.assertEqual((report.get("budget", {}) or {}).get("remaining"), 0)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from kernel.runtime.autoremediation_batch_governance import (
    autoremediation_batch_governance_report,
)


class RuntimeAutoremediationBatchGovernanceTests(unittest.TestCase):
    def test_no_runs_holds(self):
        report = autoremediation_batch_governance_report(campaign_payload={"run_results": []})
        self.assertEqual(report.get("decision"), "hold")
        self.assertEqual(report.get("reason"), "no_runs")

    def test_campaign_handoff_forces_handoff(self):
        report = autoremediation_batch_governance_report(
            campaign_payload={
                "campaign_governance": {"decision": "handoff", "reason": "campaign_handoff_rate_high"},
                "run_results": [{"decision": "allow", "exit_code": 0, "cycle_exit_code": 0}],
            }
        )
        self.assertEqual(report.get("decision"), "handoff")
        self.assertEqual(report.get("reason"), "campaign_requires_handoff")

    def test_error_runs_handoff(self):
        report = autoremediation_batch_governance_report(
            campaign_payload={
                "campaign_governance": {"decision": "allow", "reason": "campaign_healthy"},
                "run_results": [
                    {"decision": "allow", "exit_code": 0, "cycle_exit_code": 0},
                    {"decision": "allow", "exit_code": 4, "cycle_exit_code": 4},
                    {"decision": "allow", "exit_code": 5, "cycle_exit_code": 5},
                ],
            },
            max_error_runs=1,
        )
        self.assertEqual(report.get("decision"), "handoff")
        self.assertEqual(report.get("reason"), "batch_error_runs_high")

    def test_blocked_runs_hold(self):
        report = autoremediation_batch_governance_report(
            campaign_payload={
                "campaign_governance": {"decision": "allow", "reason": "campaign_healthy"},
                "run_results": [
                    {"decision": "hold", "exit_code": 0, "cycle_exit_code": 3},
                    {"decision": "allow", "exit_code": 0, "cycle_exit_code": 0},
                    {"decision": "hold", "exit_code": 0, "cycle_exit_code": 3},
                ],
            },
            max_error_runs=10,
            max_handoff_rate=0.8,
            max_blocked_runs=1,
        )
        self.assertEqual(report.get("decision"), "hold")
        self.assertEqual(report.get("reason"), "batch_blocked_runs_high")

    def test_healthy_allow(self):
        report = autoremediation_batch_governance_report(
            campaign_payload={
                "campaign_governance": {"decision": "allow", "reason": "campaign_healthy"},
                "run_results": [
                    {"decision": "allow", "exit_code": 0, "cycle_exit_code": 0},
                    {"decision": "allow", "exit_code": 0, "cycle_exit_code": 0},
                    {"decision": "hold", "exit_code": 0, "cycle_exit_code": 0},
                ],
            },
            max_handoff_rate=0.8,
            max_error_runs=1,
            max_blocked_runs=2,
        )
        self.assertEqual(report.get("decision"), "allow")
        self.assertEqual(report.get("reason"), "batch_ready")
        self.assertEqual(report.get("eligible_run_indexes"), [1, 2])


if __name__ == "__main__":
    unittest.main()

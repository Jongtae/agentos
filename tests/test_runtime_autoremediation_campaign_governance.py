from __future__ import annotations

import unittest

from kernel.runtime.autoremediation_campaign_governance import (
    autoremediation_campaign_governance_report,
)


class RuntimeAutoremediationCampaignGovernanceTests(unittest.TestCase):
    def test_no_runs_holds(self):
        report = autoremediation_campaign_governance_report(run_results=[])
        self.assertEqual(report.get("decision"), "hold")
        self.assertEqual(report.get("reason"), "no_runs")

    def test_error_rate_handoff(self):
        report = autoremediation_campaign_governance_report(
            run_results=[
                {"decision": "allow", "exit_code": 0},
                {"decision": "hold", "exit_code": 4},
                {"decision": "allow", "exit_code": 5},
            ],
            max_error_runs=1,
        )
        self.assertEqual(report.get("decision"), "handoff")
        self.assertEqual(report.get("reason"), "campaign_error_rate_high")

    def test_handoff_rate_handoff(self):
        report = autoremediation_campaign_governance_report(
            run_results=[
                {"decision": "handoff", "exit_code": 0},
                {"decision": "handoff", "exit_code": 0},
                {"decision": "allow", "exit_code": 0},
            ],
            max_handoff_rate=0.3,
            max_error_runs=10,
        )
        self.assertEqual(report.get("decision"), "handoff")
        self.assertEqual(report.get("reason"), "campaign_handoff_rate_high")

    def test_mostly_hold(self):
        report = autoremediation_campaign_governance_report(
            run_results=[
                {"decision": "hold", "exit_code": 0},
                {"decision": "hold", "exit_code": 0},
                {"decision": "allow", "exit_code": 0},
            ],
            max_handoff_rate=0.9,
            max_error_runs=10,
        )
        self.assertEqual(report.get("decision"), "hold")
        self.assertEqual(report.get("reason"), "campaign_mostly_hold")

    def test_healthy_allow(self):
        report = autoremediation_campaign_governance_report(
            run_results=[
                {"decision": "allow", "exit_code": 0},
                {"decision": "allow", "exit_code": 0},
                {"decision": "hold", "exit_code": 0},
            ],
            max_handoff_rate=0.8,
            max_error_runs=1,
        )
        self.assertEqual(report.get("decision"), "allow")
        self.assertEqual(report.get("reason"), "campaign_healthy")


if __name__ == "__main__":
    unittest.main()

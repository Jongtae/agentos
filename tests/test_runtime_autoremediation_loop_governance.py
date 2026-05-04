from __future__ import annotations

import unittest

from kernel.runtime.autoremediation_loop_governance import autoremediation_loop_governance_report


class RuntimeAutoremediationLoopGovernanceTests(unittest.TestCase):
    def test_scheduler_blocked_results_hold(self):
        report = autoremediation_loop_governance_report(
            cycle_payload={
                "execution_mode": "dry-run",
                "scheduler": {"decision": {"status": "skip", "reason": "cooldown_active"}},
                "cadence": {"status": "hold", "reason": "scheduler_not_eligible"},
                "escalation": {"should_escalate": False, "reason": "no_escalation", "event": {}},
            }
        )
        self.assertEqual(report.get("decision"), "hold")
        self.assertEqual(report.get("reason"), "scheduler_blocked")

    def test_cadence_blocked_results_hold(self):
        report = autoremediation_loop_governance_report(
            cycle_payload={
                "execution_mode": "dry-run",
                "scheduler": {"decision": {"status": "apply", "reason": "eligible"}},
                "cadence": {"status": "hold", "reason": "min_interval_not_elapsed"},
                "escalation": {"should_escalate": False, "reason": "no_escalation", "event": {}},
            }
        )
        self.assertEqual(report.get("decision"), "hold")
        self.assertEqual(report.get("reason"), "cadence_blocked")

    def test_allow_when_apply_executed(self):
        report = autoremediation_loop_governance_report(
            cycle_payload={
                "execution_mode": "apply",
                "scheduler": {"decision": {"status": "apply", "reason": "eligible"}},
                "cadence": {"status": "allow", "reason": "eligible"},
                "escalation": {"should_escalate": False, "reason": "no_escalation", "event": {}},
            }
        )
        self.assertEqual(report.get("decision"), "allow")
        self.assertEqual(report.get("reason"), "cycle_apply_executed")

    def test_handoff_when_escalation_with_failure(self):
        report = autoremediation_loop_governance_report(
            cycle_payload={
                "execution_mode": "dry-run",
                "scheduler": {"decision": {"status": "apply", "reason": "eligible"}},
                "cadence": {"status": "allow", "reason": "eligible"},
                "escalation": {
                    "should_escalate": True,
                    "reason": "execution_errors_detected",
                    "event": {"hold_streak": 1, "failure_streak": 2},
                },
            }
        )
        self.assertEqual(report.get("decision"), "handoff")
        self.assertEqual(report.get("reason"), "operator_handoff_required")


if __name__ == "__main__":
    unittest.main()

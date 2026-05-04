from __future__ import annotations

import unittest

from kernel.runtime.autoremediation_forced_resume import (
    autoremediation_forced_resume_report,
)


class RuntimeAutoremediationForcedResumeTests(unittest.TestCase):
    def test_allow_when_resume_gate_allows(self):
        report = autoremediation_forced_resume_report(
            resume_gate={"decision": {"status": "allow", "reason": "resume_eligible", "next_check_epoch": 1000}},
            override_window={"status": "inactive", "reason": "no_override_window"},
        )
        decision = report.get("decision", {}) or {}
        self.assertEqual(decision.get("status"), "allow")
        self.assertEqual(decision.get("reason"), "resume_gate_allow")
        self.assertFalse(bool(decision.get("forced", True)))

    def test_block_when_budget_exhausted_even_with_override(self):
        report = autoremediation_forced_resume_report(
            resume_gate={"decision": {"status": "block", "reason": "rollback_budget_exhausted", "next_check_epoch": 0}},
            override_window={"status": "active", "reason": "operator_override_requested"},
        )
        decision = report.get("decision", {}) or {}
        self.assertEqual(decision.get("status"), "block")
        self.assertEqual(decision.get("reason"), "rollback_budget_exhausted")
        self.assertEqual(decision.get("operator_action"), "manual_handoff")

    def test_override_forces_allow_from_hold(self):
        report = autoremediation_forced_resume_report(
            resume_gate={"decision": {"status": "hold", "reason": "pause_cooldown_active", "next_check_epoch": 1200}},
            override_window={"status": "active", "reason": "override_window_active"},
        )
        decision = report.get("decision", {}) or {}
        self.assertEqual(decision.get("status"), "allow")
        self.assertEqual(decision.get("reason"), "operator_override_active")
        self.assertTrue(bool(decision.get("forced", False)))

    def test_hold_without_override_requests_operator_override(self):
        report = autoremediation_forced_resume_report(
            resume_gate={"decision": {"status": "hold", "reason": "resume_interval_not_elapsed", "next_check_epoch": 1500}},
            override_window={"status": "inactive", "reason": "no_override_window"},
        )
        decision = report.get("decision", {}) or {}
        self.assertEqual(decision.get("status"), "hold")
        self.assertEqual(decision.get("operator_action"), "request_override")

    def test_block_without_override_requires_manual_handoff(self):
        report = autoremediation_forced_resume_report(
            resume_gate={"decision": {"status": "block", "reason": "max_resume_attempts_reached", "next_check_epoch": 0}},
            override_window={"status": "inactive", "reason": "no_override_window"},
        )
        decision = report.get("decision", {}) or {}
        self.assertEqual(decision.get("status"), "block")
        self.assertEqual(decision.get("operator_action"), "manual_handoff")


if __name__ == "__main__":
    unittest.main()

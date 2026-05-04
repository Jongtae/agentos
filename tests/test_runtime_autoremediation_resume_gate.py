from __future__ import annotations

import unittest

from kernel.runtime.autoremediation_resume_gate import (
    autoremediation_resume_gate_report,
)


class RuntimeAutoremediationResumeGateTests(unittest.TestCase):
    def test_allow_when_not_paused(self):
        report = autoremediation_resume_gate_report(
            now_epoch=1000,
            pause_state={"is_paused": False},
            rollback_budget={"status": "allow"},
            stage_governance={"decision": "allow"},
        )
        self.assertEqual((report.get("decision", {}) or {}).get("status"), "allow")
        self.assertEqual((report.get("decision", {}) or {}).get("reason"), "not_paused")

    def test_hold_when_cooldown_active(self):
        report = autoremediation_resume_gate_report(
            now_epoch=1000,
            pause_state={"is_paused": True, "cooldown_until_epoch": 1200},
            rollback_budget={"status": "allow"},
            stage_governance={"decision": "allow"},
        )
        self.assertEqual((report.get("decision", {}) or {}).get("status"), "hold")
        self.assertEqual((report.get("decision", {}) or {}).get("reason"), "pause_cooldown_active")
        self.assertEqual(int((report.get("decision", {}) or {}).get("next_check_epoch", 0)), 1200)

    def test_block_when_budget_exhausted(self):
        report = autoremediation_resume_gate_report(
            now_epoch=1300,
            pause_state={"is_paused": True, "cooldown_until_epoch": 1200},
            rollback_budget={"status": "handoff"},
            stage_governance={"decision": "allow"},
        )
        self.assertEqual((report.get("decision", {}) or {}).get("status"), "block")
        self.assertEqual((report.get("decision", {}) or {}).get("reason"), "rollback_budget_exhausted")

    def test_hold_when_stage_handoff(self):
        report = autoremediation_resume_gate_report(
            now_epoch=1300,
            pause_state={"is_paused": True, "cooldown_until_epoch": 1200},
            rollback_budget={"status": "allow"},
            stage_governance={"decision": "handoff"},
        )
        self.assertEqual((report.get("decision", {}) or {}).get("status"), "hold")
        self.assertEqual((report.get("decision", {}) or {}).get("reason"), "stage_handoff_required")

    def test_block_when_resume_attempts_exceeded(self):
        report = autoremediation_resume_gate_report(
            now_epoch=1300,
            pause_state={
                "is_paused": True,
                "cooldown_until_epoch": 1200,
                "resume_attempt_count": 5,
            },
            rollback_budget={"status": "allow"},
            stage_governance={"decision": "allow"},
            max_resume_attempts=5,
        )
        self.assertEqual((report.get("decision", {}) or {}).get("status"), "block")
        self.assertEqual((report.get("decision", {}) or {}).get("reason"), "max_resume_attempts_reached")

    def test_hold_when_resume_interval_not_elapsed(self):
        report = autoremediation_resume_gate_report(
            now_epoch=1300,
            pause_state={
                "is_paused": True,
                "cooldown_until_epoch": 1200,
                "resume_attempt_count": 1,
                "last_resume_attempt_epoch": 1205,
            },
            rollback_budget={"status": "allow"},
            stage_governance={"decision": "allow"},
            min_resume_interval_sec=300,
        )
        self.assertEqual((report.get("decision", {}) or {}).get("status"), "hold")
        self.assertEqual((report.get("decision", {}) or {}).get("reason"), "resume_interval_not_elapsed")
        self.assertEqual(int((report.get("decision", {}) or {}).get("next_check_epoch", 0)), 1505)

    def test_allow_when_resume_eligible(self):
        report = autoremediation_resume_gate_report(
            now_epoch=1800,
            pause_state={
                "is_paused": True,
                "cooldown_until_epoch": 1200,
                "resume_attempt_count": 1,
                "last_resume_attempt_epoch": 1400,
            },
            rollback_budget={"status": "allow"},
            stage_governance={"decision": "allow"},
            min_resume_interval_sec=300,
            max_resume_attempts=5,
        )
        self.assertEqual((report.get("decision", {}) or {}).get("status"), "allow")
        self.assertEqual((report.get("decision", {}) or {}).get("reason"), "resume_eligible")
        self.assertTrue(bool((report.get("decision", {}) or {}).get("eligible_resume", False)))


if __name__ == "__main__":
    unittest.main()

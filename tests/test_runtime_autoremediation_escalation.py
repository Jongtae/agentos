from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel.runtime.autoremediation_escalation import (
    autoremediation_escalation_report,
    load_autoremediation_escalation_state,
    save_autoremediation_escalation_state,
)


class RuntimeAutoremediationEscalationTests(unittest.TestCase):
    def test_cooldown_blocks_escalation(self):
        report = autoremediation_escalation_report(
            now_epoch=1200,
            cadence_status="hold",
            cadence_reason="min_interval_not_elapsed",
            scheduler_reason="eligible",
            execution_errors=1,
            hold_streak=5,
            failure_streak=2,
            last_escalation_epoch=1100,
            min_escalation_interval_sec=300,
        )
        self.assertFalse(bool(report.get("should_escalate", True)))
        self.assertEqual(report.get("reason"), "escalation_cooldown_active")

    def test_execution_error_escalates(self):
        report = autoremediation_escalation_report(
            now_epoch=2000,
            cadence_status="allow",
            cadence_reason="eligible",
            scheduler_reason="eligible",
            execution_errors=2,
            hold_streak=0,
            failure_streak=1,
            last_escalation_epoch=0,
        )
        self.assertTrue(bool(report.get("should_escalate", False)))
        self.assertEqual(report.get("reason"), "execution_errors_detected")

    def test_critical_manual_review_escalates(self):
        report = autoremediation_escalation_report(
            now_epoch=2000,
            cadence_status="hold",
            cadence_reason="scheduler_not_eligible",
            scheduler_reason="critical_manual_review_required",
            execution_errors=0,
            hold_streak=1,
            failure_streak=0,
            last_escalation_epoch=0,
        )
        self.assertTrue(bool(report.get("should_escalate", False)))
        self.assertEqual(report.get("reason"), "critical_manual_review_required")

    def test_persistent_hold_escalates(self):
        report = autoremediation_escalation_report(
            now_epoch=2000,
            cadence_status="hold",
            cadence_reason="min_interval_not_elapsed",
            scheduler_reason="eligible",
            execution_errors=0,
            hold_streak=3,
            failure_streak=0,
            last_escalation_epoch=0,
        )
        self.assertTrue(bool(report.get("should_escalate", False)))
        self.assertEqual(report.get("reason"), "persistent_cadence_hold")

    def test_budget_saturation_escalates(self):
        report = autoremediation_escalation_report(
            now_epoch=2000,
            cadence_status="hold",
            cadence_reason="hourly_budget_exceeded",
            scheduler_reason="eligible",
            execution_errors=0,
            hold_streak=1,
            failure_streak=0,
            last_escalation_epoch=0,
        )
        self.assertTrue(bool(report.get("should_escalate", False)))
        self.assertEqual(report.get("reason"), "budget_guardrail_saturated")

    def test_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            save_autoremediation_escalation_state(
                workspace,
                last_escalation_epoch=123,
                hold_streak=2,
                failure_streak=1,
            )
            state = load_autoremediation_escalation_state(workspace)
            self.assertEqual(int(state.get("last_escalation_epoch", 0)), 123)
            self.assertEqual(int(state.get("hold_streak", 0)), 2)
            self.assertEqual(int(state.get("failure_streak", 0)), 1)


if __name__ == "__main__":
    unittest.main()

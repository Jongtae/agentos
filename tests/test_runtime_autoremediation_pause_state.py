from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel.runtime.autoremediation_pause_state import (
    autoremediation_pause_state_report,
    load_autoremediation_pause_state,
    save_autoremediation_pause_state,
)


class RuntimeAutoremediationPauseStateTests(unittest.TestCase):
    def test_load_missing_returns_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            state = load_autoremediation_pause_state(Path(td))
            self.assertFalse(state.get("is_paused"))
            self.assertEqual(int(state.get("cooldown_until_epoch", -1)), 0)
            self.assertEqual(str(state.get("pause_reason")), "none")

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            save_autoremediation_pause_state(
                workspace,
                state={
                    "is_paused": True,
                    "paused_since_epoch": 100,
                    "cooldown_until_epoch": 700,
                    "pause_reason": "rollback_budget_exhausted",
                    "pause_severity": "critical",
                    "resume_attempt_count": 2,
                    "last_resume_attempt_epoch": 650,
                },
            )
            loaded = load_autoremediation_pause_state(workspace)
            self.assertTrue(bool(loaded.get("is_paused")))
            self.assertEqual(int(loaded.get("paused_since_epoch", 0)), 100)
            self.assertEqual(int(loaded.get("resume_attempt_count", 0)), 2)

    def test_pause_activation_sets_cooldown(self):
        report = autoremediation_pause_state_report(
            now_epoch=1000,
            current_state={"is_paused": False},
            auto_pause={
                "should_pause": True,
                "reason": "rollback_budget_exhausted",
                "severity": "critical",
                "cooldown_sec": 900,
            },
        )
        self.assertEqual(report.get("event"), "pause_activated")
        self.assertEqual(report.get("status"), "paused")
        state = report.get("state", {})
        self.assertTrue(bool(state.get("is_paused")))
        self.assertEqual(int(state.get("cooldown_until_epoch", 0)), 1900)

    def test_resume_blocked_by_cooldown(self):
        report = autoremediation_pause_state_report(
            now_epoch=1100,
            current_state={
                "is_paused": True,
                "paused_since_epoch": 1000,
                "cooldown_until_epoch": 1900,
                "pause_reason": "rollback_budget_exhausted",
                "pause_severity": "critical",
            },
            resume_requested=True,
        )
        self.assertEqual(report.get("event"), "resume_blocked_by_cooldown")
        self.assertEqual(report.get("status"), "paused")
        self.assertEqual(report.get("reason"), "cooldown_active")
        self.assertEqual(int((report.get("state", {}) or {}).get("resume_attempt_count", 0)), 1)

    def test_resume_released_after_cooldown(self):
        report = autoremediation_pause_state_report(
            now_epoch=2100,
            current_state={
                "is_paused": True,
                "paused_since_epoch": 1000,
                "cooldown_until_epoch": 1900,
                "pause_reason": "rollback_budget_exhausted",
                "pause_severity": "critical",
            },
            resume_requested=True,
        )
        self.assertEqual(report.get("event"), "resume_released")
        self.assertEqual(report.get("status"), "active")
        self.assertEqual(report.get("reason"), "resumed")
        state = report.get("state", {})
        self.assertFalse(bool(state.get("is_paused")))
        self.assertEqual(int(state.get("cooldown_until_epoch", -1)), 0)


if __name__ == "__main__":
    unittest.main()

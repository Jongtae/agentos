from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel.runtime.autoremediation_cadence import (
    append_apply_history,
    autoremediation_cadence_report,
    load_autoremediation_cadence_state,
    save_autoremediation_cadence_state,
)


class RuntimeAutoremediationCadenceTests(unittest.TestCase):
    def test_scheduler_not_eligible_holds(self):
        report = autoremediation_cadence_report(
            now_epoch=1000,
            scheduler_status="skip",
            last_apply_epoch=0,
            apply_history_epochs=[],
        )
        self.assertEqual(report.get("status"), "hold")
        self.assertEqual(report.get("reason"), "scheduler_not_eligible")

    def test_min_interval_holds(self):
        report = autoremediation_cadence_report(
            now_epoch=1100,
            scheduler_status="apply",
            last_apply_epoch=1000,
            apply_history_epochs=[1000],
            min_interval_sec=300,
        )
        self.assertEqual(report.get("status"), "hold")
        self.assertEqual(report.get("reason"), "min_interval_not_elapsed")
        self.assertEqual(int(report.get("next_allowed_epoch", 0)), 1300)

    def test_hourly_budget_holds(self):
        report = autoremediation_cadence_report(
            now_epoch=2000,
            scheduler_status="apply",
            last_apply_epoch=100,
            apply_history_epochs=[1700, 1800, 1900],
            max_applies_per_hour=3,
        )
        self.assertEqual(report.get("status"), "hold")
        self.assertEqual(report.get("reason"), "hourly_budget_exceeded")

    def test_daily_budget_holds(self):
        report = autoremediation_cadence_report(
            now_epoch=100000,
            scheduler_status="apply",
            last_apply_epoch=100,
            apply_history_epochs=list(range(90000, 90000 + 12)),
            max_applies_per_hour=20,
            max_applies_per_day=12,
        )
        self.assertEqual(report.get("status"), "hold")
        self.assertEqual(report.get("reason"), "daily_budget_exceeded")

    def test_eligible_allows(self):
        report = autoremediation_cadence_report(
            now_epoch=5000,
            scheduler_status="apply",
            last_apply_epoch=1000,
            apply_history_epochs=[1000, 2000],
            min_interval_sec=300,
            max_applies_per_hour=3,
            max_applies_per_day=12,
        )
        self.assertEqual(report.get("status"), "allow")
        self.assertEqual(report.get("reason"), "eligible")

    def test_state_roundtrip_and_append_history(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            save_autoremediation_cadence_state(
                workspace,
                last_apply_epoch=123,
                apply_history_epochs=[10, 20, 30],
            )
            state = load_autoremediation_cadence_state(workspace)
            self.assertEqual(int(state.get("last_apply_epoch", 0)), 123)
            self.assertEqual(state.get("apply_history_epochs"), [10, 20, 30])

            history = append_apply_history([1, 2], applied_epoch=100, now_epoch=200, retention_sec=150)
            self.assertEqual(history, [100])


if __name__ == "__main__":
    unittest.main()

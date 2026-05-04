from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel.runtime.autoremediation_override_budget import (
    append_override_budget_event,
    autoremediation_override_budget_report,
    load_autoremediation_override_budget_state,
    save_autoremediation_override_budget_state,
)


class RuntimeAutoremediationOverrideBudgetTests(unittest.TestCase):
    def test_load_missing_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            state = load_autoremediation_override_budget_state(Path(td))
            self.assertEqual(state.get("override_applied_epochs"), [])

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            save_autoremediation_override_budget_state(
                ws,
                state={"override_applied_epochs": [100, 200]},
            )
            loaded = load_autoremediation_override_budget_state(ws)
            self.assertEqual(loaded.get("override_applied_epochs"), [100, 200])

    def test_budget_allow_with_remaining(self):
        report = autoremediation_override_budget_report(
            now_epoch=2000,
            state={"override_applied_epochs": [1500]},
            window_size_sec=1000,
            max_overrides_per_window=3,
        )
        self.assertEqual(report.get("status"), "allow")
        self.assertEqual((report.get("budget", {}) or {}).get("remaining"), 2)

    def test_budget_block_when_exhausted(self):
        report = autoremediation_override_budget_report(
            now_epoch=2000,
            state={"override_applied_epochs": [1200, 1300, 1400]},
            window_size_sec=1000,
            max_overrides_per_window=3,
        )
        self.assertEqual(report.get("status"), "block")
        self.assertEqual(report.get("reason"), "override_budget_exhausted")
        self.assertEqual(int((report.get("budget", {}) or {}).get("remaining", -1)), 0)

    def test_append_event(self):
        updated = append_override_budget_event({"override_applied_epochs": [100]}, applied_epoch=200)
        self.assertEqual(updated.get("override_applied_epochs"), [100, 200])


if __name__ == "__main__":
    unittest.main()

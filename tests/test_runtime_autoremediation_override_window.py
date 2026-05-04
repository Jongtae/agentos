from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel.runtime.autoremediation_override_window import (
    autoremediation_override_window_report,
    load_autoremediation_override_window_state,
    save_autoremediation_override_window_state,
)


class RuntimeAutoremediationOverrideWindowTests(unittest.TestCase):
    def test_load_missing_returns_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            state = load_autoremediation_override_window_state(Path(td))
            self.assertEqual(int(state.get("override_until_epoch", -1)), 0)
            self.assertEqual(int(state.get("request_count", -1)), 0)

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            save_autoremediation_override_window_state(
                workspace,
                state={
                    "override_until_epoch": 2000,
                    "activated_at_epoch": 1000,
                    "request_count": 2,
                    "last_requested_epoch": 1200,
                },
            )
            loaded = load_autoremediation_override_window_state(workspace)
            self.assertEqual(int(loaded.get("override_until_epoch", 0)), 2000)
            self.assertEqual(int(loaded.get("request_count", 0)), 2)

    def test_override_request_activates_window(self):
        report = autoremediation_override_window_report(
            now_epoch=1000,
            current_state={},
            override_requested=True,
            override_duration_sec=600,
        )
        self.assertEqual(report.get("status"), "active")
        self.assertEqual(report.get("reason"), "operator_override_requested")
        self.assertEqual(report.get("event"), "override_activated")
        self.assertEqual(int((report.get("state", {}) or {}).get("override_until_epoch", 0)), 1600)
        self.assertEqual(int((report.get("state", {}) or {}).get("request_count", 0)), 1)

    def test_active_window_without_new_request(self):
        report = autoremediation_override_window_report(
            now_epoch=1100,
            current_state={
                "override_until_epoch": 1600,
                "activated_at_epoch": 1000,
                "request_count": 1,
                "last_requested_epoch": 1000,
            },
            override_requested=False,
        )
        self.assertEqual(report.get("status"), "active")
        self.assertEqual(report.get("reason"), "override_window_active")
        self.assertEqual(int(report.get("remaining_sec", -1)), 500)

    def test_window_expires(self):
        report = autoremediation_override_window_report(
            now_epoch=1700,
            current_state={
                "override_until_epoch": 1600,
                "activated_at_epoch": 1000,
                "request_count": 1,
                "last_requested_epoch": 1000,
            },
            override_requested=False,
        )
        self.assertEqual(report.get("status"), "inactive")
        self.assertEqual(report.get("reason"), "override_window_expired")
        self.assertEqual(report.get("event"), "window_expired")
        self.assertEqual(int((report.get("state", {}) or {}).get("override_until_epoch", -1)), 0)


if __name__ == "__main__":
    unittest.main()

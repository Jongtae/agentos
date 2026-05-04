from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel.broker.daemon import broker_activity_summary, brokerd_report, run_brokerd_loop
from kernel.broker.event_bridge import append_broker_transition


class BrokerDaemonTests(unittest.TestCase):
    def test_brokerd_report_exposes_service_contract(self):
        with tempfile.TemporaryDirectory() as td:
            payload = brokerd_report(Path(td), loop_interval_sec=15)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["mode"], "skeleton")
            self.assertEqual(payload["service"]["name"], "agentos-brokerd.service")
            self.assertFalse(payload["service"]["enabled_by_default"])
            self.assertEqual(payload["loop_interval_sec"], 15)
            self.assertGreaterEqual(len(payload["managed_paths"]), 5)

    def test_run_brokerd_loop_run_once_prepares_artifacts_dir(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            rc = run_brokerd_loop(workspace, loop_interval_sec=1, run_once=True)
            self.assertEqual(rc, 0)
            self.assertTrue((workspace / "artifacts").exists())

    def test_broker_activity_summary_counts_recent_events(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            append_broker_transition(
                workspace,
                kind="operator_control",
                action="policy_enforce_enable",
                state="override",
                reason="operator override active",
                actor={"component": "test"},
            )
            summary = broker_activity_summary(workspace, limit=5)
            self.assertTrue(summary["available"])
            self.assertGreaterEqual(summary["counts"]["broker.exec_request"], 1)
            self.assertEqual(summary["request_kind_counts"]["operator_control"], 2)
            self.assertEqual(summary["decision_state_counts"]["requested"], 1)
            self.assertEqual(summary["decision_state_counts"]["override"], 1)
            self.assertIn("policy_enforce_enable", summary["recent_actions"])
            self.assertEqual(len(summary["high_risk_recent"]), 2)
            self.assertGreaterEqual(len(summary["recent_events"]), 1)


if __name__ == "__main__":
    unittest.main()

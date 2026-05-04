from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel.event_fabric.daemon import eventd_report, run_eventd_loop


class EventFabricDaemonTests(unittest.TestCase):
    def test_eventd_report_exposes_service_contract(self):
        with tempfile.TemporaryDirectory() as td:
            payload = eventd_report(Path(td), loop_interval_sec=12)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["mode"], "skeleton")
            self.assertEqual(payload["service"]["name"], "agentos-eventd.service")
            self.assertFalse(payload["service"]["enabled_by_default"])
            self.assertEqual(payload["loop_interval_sec"], 12)
            self.assertGreaterEqual(len(payload["collectors"]), 5)

    def test_run_eventd_loop_run_once_prepares_artifacts_dir(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            rc = run_eventd_loop(workspace, loop_interval_sec=1, run_once=True)
            self.assertEqual(rc, 0)
            self.assertTrue((workspace / "artifacts").exists())


if __name__ == "__main__":
    unittest.main()

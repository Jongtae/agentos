from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from kernel.runtime.trace import approval_counters_from_trace


class RuntimeTraceSummaryTests(unittest.TestCase):
    def test_counters_from_trace_events(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "trace.jsonl"
            rows = [
                {"event": "run_start", "payload": {}},
                {"event": "approval_requested", "payload": {}},
                {"event": "approval_decision", "payload": {"approved": True}},
                {"event": "approval_requested", "payload": {}},
                {"event": "approval_decision", "payload": {"approved": False}},
                {"event": "step_blocked", "payload": {}},
            ]
            p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

            c = approval_counters_from_trace(p)
            self.assertEqual(c["requested"], 2)
            self.assertEqual(c["approved"], 1)
            self.assertEqual(c["denied"], 1)
            self.assertEqual(c["blocked"], 1)
            self.assertEqual(c["trace_events"], 6)

    def test_missing_trace_file_returns_zero_counters(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "missing.jsonl"
            c = approval_counters_from_trace(p)
            self.assertEqual(c["requested"], 0)
            self.assertEqual(c["approved"], 0)
            self.assertEqual(c["denied"], 0)
            self.assertEqual(c["blocked"], 0)


if __name__ == "__main__":
    unittest.main()

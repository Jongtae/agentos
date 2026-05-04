from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel.runtime.autoremediation_override_audit import (
    append_override_audit_event,
    override_audit_report,
)


class RuntimeAutoremediationOverrideAuditTests(unittest.TestCase):
    def test_empty_report_when_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            report = override_audit_report(workspace_dir=Path(td))
            self.assertEqual(int(report.get("event_count", -1)), 0)
            self.assertEqual(int(report.get("parse_errors", -1)), 0)

    def test_append_and_report(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            append_override_audit_event(
                ws,
                event="operator_override_requested",
                decision_status="allow",
                reason="operator_override_active",
                forced=True,
            )
            append_override_audit_event(
                ws,
                event="operator_override_expired",
                decision_status="hold",
                reason="override_window_expired",
                forced=False,
            )
            report = override_audit_report(workspace_dir=ws, max_recent=1)
            self.assertEqual(int(report.get("event_count", -1)), 2)
            recent = report.get("recent_events", [])
            self.assertEqual(len(recent), 1)
            self.assertEqual(str((recent[0] or {}).get("event", "")), "operator_override_expired")

    def test_parse_error_counted(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            p = ws / "artifacts" / "autoremediation_override_audit.jsonl"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('{"event":"ok"}\nnot-json\n', encoding="utf-8")
            report = override_audit_report(workspace_dir=ws)
            self.assertEqual(int(report.get("event_count", -1)), 1)
            self.assertEqual(int(report.get("parse_errors", -1)), 1)


if __name__ == "__main__":
    unittest.main()

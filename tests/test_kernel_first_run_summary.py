from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from kernel.first_run_summary import FIRST_RUN_SUMMARY_SCHEMA, build_first_run_summary_report


class FirstRunSummaryTests(unittest.TestCase):
    def test_build_first_run_summary_report_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            payload = build_first_run_summary_report(workspace)
            self.assertEqual(payload["schema_version"], FIRST_RUN_SUMMARY_SCHEMA)
            self.assertTrue(payload["summary"]["document_native_handled"])
            self.assertTrue(payload["summary"]["web_handled"])
            self.assertTrue(payload["summary"]["capability_proof_ready"])
            manifest = Path(payload["artifacts"]["latest_first_run_summary_manifest_json"])
            self.assertTrue(manifest.is_file())
            saved = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(saved["schema_version"], FIRST_RUN_SUMMARY_SCHEMA)
            self.assertEqual(saved["summary"]["document_path"], "documents/agentos-first-run.md")


if __name__ == "__main__":
    unittest.main()

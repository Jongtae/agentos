from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_inbox_workflow.py"


class InboxWorkflowTests(unittest.TestCase):
    def test_exports_valid_inbox_workflow_payload(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            out = Path(td) / "inbox-workflow.json"
            subprocess.run(
                [str(SCRIPT), "--workspace", str(workspace), "--output", str(out)],
                check=True,
                text=True,
                capture_output=True,
            )
            payload = json.loads(out.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], "agentos-inbox-triage-summary-response-workflow.v1")
        self.assertEqual(payload["capability"], "inbox_triage_summary_response_workflow")
        self.assertEqual(payload["workflow_id"], "inbox_triage_summary_response")
        self.assertEqual(
            [step["id"] for step in payload["steps"]],
            ["inbox_intake", "inbox_proof", "first_run_summary"],
        )
        self.assertTrue(payload["workflow_ready"])
        self.assertTrue(payload["summary"]["inbox_execution_ready"])
        self.assertTrue(payload["summary"]["summary_response_ready"])
        self.assertEqual(payload["entry_surface"], "guided_operator.review_inbox")
        self.assertEqual(payload["links"]["runtime"], "agentos-kernelctl inbox-intake --json")
        self.assertIn("latest_inbox_triage_summary_response_workflow_manifest_json", payload["artifacts"])

    def test_validate_reports_success(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            out = Path(td) / "inbox-workflow.json"
            subprocess.run(
                [str(SCRIPT), "--workspace", str(workspace), "--output", str(out)],
                check=True,
                text=True,
                capture_output=True,
            )
            proc = subprocess.run(
                [str(SCRIPT), "--validate", str(out), "--json"],
                check=True,
                text=True,
                capture_output=True,
            )
            result = json.loads(proc.stdout)

        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()

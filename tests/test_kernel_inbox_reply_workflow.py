from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
KERNELCTL = ROOT_DIR / "scripts" / "agentos-kernelctl"
SCRIPT = ROOT_DIR / "scripts" / "kernel_inbox_reply_workflow.py"


class InboxReplyWorkflowTests(unittest.TestCase):
    def test_inbox_reply_workflow_exports_reply_ready_payload(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            proc = subprocess.run(
                [str(KERNELCTL), "inbox-reply-workflow", "--workspace", str(workspace), "--json"],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], "agentos-inbox-reply-workflow.v1")
        self.assertEqual(payload["workflow_id"], "inbox_reply_workflow")
        self.assertTrue(payload["inbox_reply_workflow_ready"])
        self.assertTrue(payload["reply_draft_ready"])
        self.assertTrue(payload["summary"]["native_vs_adapter_split_recorded"])
        self.assertIn("imap_adapter_ready", payload["source_status"])

    def test_validate_reports_success(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            out = Path(td) / "inbox-reply.json"
            subprocess.run(
                [str(SCRIPT), "--workspace", str(workspace), "--output", str(out)],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            validate = subprocess.run(
                [str(SCRIPT), "--validate", str(out), "--json"],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
        self.assertTrue(json.loads(validate.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()

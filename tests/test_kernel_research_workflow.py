from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
KERNELCTL = ROOT_DIR / "scripts" / "agentos-kernelctl"


class KernelResearchWorkflowTests(unittest.TestCase):
    def _workspace(self) -> str:
        td = tempfile.TemporaryDirectory()
        workspace = Path(td.name)
        (workspace / "spec.yaml").write_text("name: research-workflow-test\n", encoding="utf-8")
        self.addCleanup(td.cleanup)
        return td.name

    def _run_workflow(self) -> dict:
        workspace = self._workspace()
        result = subprocess.run(
            [
                str(KERNELCTL),
                "research-workflow",
                "--workspace",
                workspace,
                "--message-text",
                "search agentos roadmap",
                "--chat-id",
                "1001",
                "--json",
            ],
            cwd=ROOT_DIR,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self.fail(
                f"research workflow command failed with code {result.returncode}:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        return json.loads(result.stdout)

    def test_workflow_schema_and_identity(self) -> None:
        payload = self._run_workflow()
        self.assertEqual(payload["schema_version"], "agentos-research-request-response-workflow.v1")
        self.assertEqual(payload["capability"], "research_request_response_workflow")
        self.assertEqual(payload["workflow_id"], "research_request_response")

    def test_workflow_contains_expected_steps(self) -> None:
        payload = self._run_workflow()
        self.assertEqual(
            [step["id"] for step in payload["steps"]],
            ["telegram_request_routing", "internal_web_execution", "telegram_reply"],
        )

    def test_workflow_summary_and_links_are_present(self) -> None:
        payload = self._run_workflow()
        self.assertIn("summary", payload)
        self.assertIn("links", payload)
        self.assertIn("proof", payload["links"])
        self.assertIn("runtime", payload["links"])
        self.assertIn("reply", payload["links"])
        self.assertFalse(payload["browser_escalation_used"])


if __name__ == "__main__":
    unittest.main()

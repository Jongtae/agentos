from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
KERNELCTL = ROOT_DIR / "scripts" / "agentos-kernelctl"


class KernelWorkflowContractTests(unittest.TestCase):
    SUBCOMMAND = "workflow-contract"
    REQUIRED_WORKFLOW_IDS = {
        "research_request_response",
        "inbox_triage_summary_response",
    }

    def _workspace(self) -> str:
        td = tempfile.TemporaryDirectory()
        workspace = Path(td.name)
        (workspace / "spec.yaml").write_text("name: workflow-contract-test\n", encoding="utf-8")
        self.addCleanup(td.cleanup)
        return td.name

    def _run_contract(self) -> dict:
        workspace = self._workspace()
        result = subprocess.run(
            [
                str(KERNELCTL),
                self.SUBCOMMAND,
                "--workspace",
                workspace,
                "--json",
            ],
            cwd=ROOT_DIR,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self.fail(
                f"workflow contract command failed with code {result.returncode}:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"workflow contract did not emit JSON: {exc}\nstdout={result.stdout}\nstderr={result.stderr}")

    @staticmethod
    def _workflow_id(workflow: dict) -> str:
        workflow_id = workflow.get("workflow_id") or workflow.get("id") or workflow.get("workflow")
        return "" if workflow_id is None else str(workflow_id)

    @staticmethod
    def _workflow_links(workflow: dict) -> dict[str, str]:
        links = workflow.get("links") if isinstance(workflow.get("links"), dict) else None
        proof_link = links.get("proof_link") if isinstance(links, dict) else None
        task_link = links.get("task_link") if isinstance(links, dict) else None
        runtime_link = links.get("runtime_link") if isinstance(links, dict) else None
        if proof_link is None:
            proof_link = links.get("proof") if isinstance(links, dict) else None
        if task_link is None:
            task_link = links.get("task") if isinstance(links, dict) else None
        if runtime_link is None:
            runtime_link = links.get("runtime") if isinstance(links, dict) else None

        if proof_link is None and not isinstance(links, dict):
            proof_link = workflow.get("proof_link")
        if task_link is None and not isinstance(links, dict):
            task_link = workflow.get("task_link")
        if runtime_link is None and not isinstance(links, dict):
            runtime_link = workflow.get("runtime_link")

        if proof_link is None and not isinstance(links, dict):
            proof_link = workflow.get("proof")
        if task_link is None and not isinstance(links, dict):
            task_link = workflow.get("task")
        if runtime_link is None and not isinstance(links, dict):
            runtime_link = workflow.get("runtime")

        return {
            "proof": proof_link or "",
            "task": task_link or "",
            "runtime": runtime_link or "",
        }

    def test_workflow_contract_schema_shape(self) -> None:
        payload = self._run_contract()

        self.assertEqual(type(payload), dict)
        self.assertEqual(payload["schema_version"], "agentos-built-in-workflow-contract.v1")
        self.assertIn("schema_version", payload)
        self.assertIn("workflows", payload)
        self.assertIsInstance(payload["workflows"], list)
        self.assertGreater(len(payload["workflows"]), 0, "workflow contract should include workflows")

        for workflow in payload["workflows"]:
            self.assertIsInstance(workflow, dict)
            workflow_id = self._workflow_id(workflow)
            self.assertTrue(workflow_id, "each workflow should expose a workflow_id")
            links = self._workflow_links(workflow)
            self.assertIsInstance(links["proof"], str)
            self.assertIsInstance(links["task"], str)
            self.assertIsInstance(links["runtime"], str)
            self.assertTrue(links["proof"].strip(), f"proof link missing for workflow={workflow_id}")
            self.assertTrue(links["task"].strip(), f"task link missing for workflow={workflow_id}")
            self.assertTrue(links["runtime"].strip(), f"runtime link missing for workflow={workflow_id}")

    def test_workflow_contract_includes_required_workflow_ids(self) -> None:
        payload = self._run_contract()
        ids = {self._workflow_id(workflow) for workflow in payload["workflows"]}
        missing = self.REQUIRED_WORKFLOW_IDS - ids
        self.assertFalse(missing, f"missing required workflows: {sorted(missing)}")

    def test_workflow_contract_required_workflows_include_proof_task_runtime_links(self) -> None:
        payload = self._run_contract()
        workflows = {self._workflow_id(workflow): workflow for workflow in payload["workflows"]}
        for workflow_id in self.REQUIRED_WORKFLOW_IDS:
            self.assertIn(workflow_id, workflows)
            links = self._workflow_links(workflows[workflow_id])
            self.assertNotEqual(links["proof"], "")
            self.assertNotEqual(links["task"], "")
            self.assertNotEqual(links["runtime"], "")
            self.assertIn("agentos-kernelctl", links["proof"] or links["runtime"])

    def test_kernelctl_workflow_contract_cli_invocation(self) -> None:
        payload = self._run_contract()
        workflow_ids = {
            self._workflow_id(item) for item in payload["workflows"]
        }
        self.assertTrue(self.REQUIRED_WORKFLOW_IDS.issubset(workflow_ids))
        self.assertIn("schema_version", payload)
        self.assertIsInstance(payload["schema_version"], str)
        self.assertIn("workflows", payload)
        self.assertTrue(payload["workflows"])


if __name__ == "__main__":
    unittest.main()

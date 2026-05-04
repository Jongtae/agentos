from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel.planner.planner import Step
from kernel.policies.approval_rules import PolicyEngine
from kernel.runtime.tool_node_adapter import ToolNodeAdapter
from kernel.tools.bash_tool import BashTool
from kernel.tools.file_tool import FileReadTool, FileWriteTool, FileListTool
from kernel.tools.web_tool import WebTool


class ToolNodeAdapterTests(unittest.TestCase):
    def _adapter(self, root: Path) -> ToolNodeAdapter:
        tools = [
            BashTool(root),
            FileReadTool(root),
            FileWriteTool(root),
            FileListTool(root),
            WebTool(),
        ]
        return ToolNodeAdapter(tools=tools, policy=PolicyEngine(require_approval=True), workspace_dir=root)

    def test_policy_state_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            adapter = self._adapter(Path(td))
            step = Step(tool_name="bash", description="danger", args={"command": "rm -rf tmp"})
            self.assertEqual(adapter.policy_state(step), "blocked")

    def test_policy_state_approval_required(self):
        with tempfile.TemporaryDirectory() as td:
            adapter = self._adapter(Path(td))
            step = Step(tool_name="bash", description="risky", args={"command": "rm file.txt"})
            self.assertEqual(adapter.policy_state(step), "approval_required")

    def test_policy_state_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            adapter = self._adapter(Path(td))
            step = Step(tool_name="bash", description="safe", args={"command": "echo hello"})
            self.assertEqual(adapter.policy_state(step), "allowed")

    def test_run_step_respects_sandbox(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            adapter = self._adapter(root)
            step = Step(
                tool_name="file_write",
                description="write outside",
                args={"path": "../outside.txt", "content": "x", "overwrite": False},
            )
            result = adapter.run_step(step)
            self.assertEqual(result["state"], "allowed")
            self.assertIn("[error]", result["output"])
            self.assertEqual(result["broker"]["decision"]["state"], "allowed")
            self.assertEqual(result["broker"]["request"]["kind"], "exec")
            self.assertIn("execution", result)
            self.assertEqual(result["execution"]["capability_selected_path"], "broker_mediated_privileged_path")
            event_log = root / "artifacts" / "os_events.jsonl"
            self.assertTrue(event_log.exists())

    def test_run_step_blocked_returns_blocked_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            adapter = self._adapter(root)
            step = Step(tool_name="bash", description="danger", args={"command": "sudo ls"})
            result = adapter.run_step(step)
            self.assertEqual(result["state"], "blocked")
            self.assertIn("[blocked]", result["output"])
            self.assertEqual(result["broker"]["decision"]["state"], "blocked")
            self.assertEqual(result["broker"]["request"]["kind"], "exec")
            self.assertEqual(result["execution"]["permission_state"], "temporarily_blocked")
            self.assertTrue((root / "artifacts" / "os_events.jsonl").exists())

    def test_run_step_approval_required_includes_broker_contract(self):
        with tempfile.TemporaryDirectory() as td:
            adapter = self._adapter(Path(td))
            step = Step(tool_name="bash", description="risky", args={"command": "rm file.txt"})
            result = adapter.run_step(step)
            self.assertEqual(result["state"], "approval_required")
            self.assertEqual(result["broker"]["decision"]["state"], "approval_required")
            self.assertEqual(result["broker"]["request"]["kind"], "approval")
            self.assertIn("approval_request", result["broker"])
            self.assertEqual(result["execution"]["permission_state"], "approval_required")


if __name__ == "__main__":
    unittest.main()

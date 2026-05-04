from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel.memory.store import MemoryStore
from kernel.planner.planner import Plan, Step
from kernel.policies.approval_rules import PolicyEngine
from kernel.runtime.executor import Executor
from kernel.runtime.loop import KernelRuntime


class _FixedPlanner:
    def __init__(self, steps: list[Step]):
        self._steps = steps

    def plan(self, intent: str, context: str = "") -> Plan:
        _ = (intent, context)
        return Plan(summary="browser plan", steps=self._steps)


class _NoopSelector:
    def select(self, user_input: str, memory: MemoryStore) -> str:
        _ = (user_input, memory)
        return ""


class _FakeBrowserTool:
    name = "browser_run"

    def run(self, args: dict) -> str:
        return f"ok navigate {args.get('url', '')}"


class BrowserApprovalRuntimeTests(unittest.TestCase):
    def _runtime(self, approver, steps: list[Step]) -> KernelRuntime:
        self._tmpdir = tempfile.TemporaryDirectory()
        root = Path(self._tmpdir.name)
        memory = MemoryStore(root / "memory.sqlite")
        return KernelRuntime(
            planner=_FixedPlanner(steps),
            executor=Executor([_FakeBrowserTool()]),
            context_selector=_NoopSelector(),
            policy=PolicyEngine(require_approval=True),
            approver_fn=approver,
            memory=memory,
            max_steps=5,
        )

    def tearDown(self):
        td = getattr(self, "_tmpdir", None)
        if td is not None:
            td.cleanup()
            self._tmpdir = None

    def test_cross_domain_navigation_requests_approval_and_can_be_denied(self):
        requests = []

        def _deny(request):
            requests.append(request)
            return False

        steps = [
            Step(
                tool_name="browser_run",
                description="navigate first",
                args={"action": "navigate", "url": "https://example.com"},
            ),
            Step(
                tool_name="browser_run",
                description="navigate second",
                args={"action": "navigate", "url": "https://openai.com"},
            ),
        ]

        runtime = self._runtime(_deny, steps)
        output = runtime.run("browse")

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].tool_name, "browser_run")
        self.assertIn("cross-domain", requests[0].risk_reason)
        self.assertIn("[aborted] step 2: navigate second", output)
        self.assertNotIn("approval_required", output)

    def test_cross_domain_navigation_executes_after_approval(self):
        requests = []

        def _approve(request):
            requests.append(request)
            return True

        steps = [
            Step(
                tool_name="browser_run",
                description="navigate first",
                args={"action": "navigate", "url": "https://example.com"},
            ),
            Step(
                tool_name="browser_run",
                description="navigate second",
                args={"action": "navigate", "url": "https://openai.com"},
            ),
        ]

        runtime = self._runtime(_approve, steps)
        output = runtime.run("browse")

        self.assertEqual(len(requests), 1)
        self.assertIn("[1] ok navigate https://example.com", output)
        self.assertIn("[2] ok navigate https://openai.com", output)


if __name__ == "__main__":
    unittest.main()

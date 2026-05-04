from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from kernel.memory.store import MemoryStore
from kernel.planner.planner import Plan, Step
from kernel.policies.approval_rules import PolicyEngine
from kernel.event_fabric.report import query_events
from kernel.runtime.executor import Executor
from kernel.runtime.loop import KernelRuntime
from kernel.runtime.trace import RuntimeTraceWriter


class _FixedPlanner:
    def __init__(self, steps: list[Step]):
        self._steps = steps

    def plan(self, intent: str, context: str = "") -> Plan:
        _ = (intent, context)
        return Plan(summary="trace-test", steps=self._steps)


class _NoopSelector:
    def select(self, user_input: str, memory: MemoryStore) -> str:
        _ = (user_input, memory)
        return ""


class _EchoTool:
    name = "echo_tool"

    def run(self, args: dict) -> str:
        return f"ok:{args.get('value', '')}"


class _FileWriteToolFake:
    name = "file_write"

    def run(self, args: dict) -> str:
        _ = args
        return "should-not-run"


class RuntimeTraceTests(unittest.TestCase):
    def _read_events(self, path: Path) -> list[dict]:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def test_emits_core_trace_events(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            trace_file = root / "runtime_trace.jsonl"
            runtime = KernelRuntime(
                planner=_FixedPlanner([
                    Step(tool_name="echo_tool", description="echo", args={"value": "x"}),
                ]),
                executor=Executor([_EchoTool()]),
                context_selector=_NoopSelector(),
                policy=PolicyEngine(require_approval=True),
                approver_fn=lambda _: True,
                memory=MemoryStore(root / "memory.sqlite"),
                trace_writer=RuntimeTraceWriter(trace_file),
                max_steps=3,
                workspace_dir=root,
            )

            out = runtime.run("hello")
            self.assertIn("ok:x", out)

            events = self._read_events(trace_file)
            names = [e["event"] for e in events]
            self.assertIn("run_start", names)
            self.assertIn("plan_generated", names)
            self.assertIn("step_started", names)
            self.assertIn("step_completed", names)
            self.assertIn("run_end", names)

    def test_emits_approval_events_when_denied(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            trace_file = root / "runtime_trace.jsonl"
            runtime = KernelRuntime(
                planner=_FixedPlanner([
                    Step(
                        tool_name="file_write",
                        description="write file",
                        args={"path": "a.txt", "content": "x", "overwrite": True},
                    ),
                ]),
                executor=Executor([_FileWriteToolFake()]),
                context_selector=_NoopSelector(),
                policy=PolicyEngine(require_approval=True),
                approver_fn=lambda _: False,
                memory=MemoryStore(root / "memory.sqlite"),
                trace_writer=RuntimeTraceWriter(trace_file),
                max_steps=3,
                workspace_dir=root,
            )

            out = runtime.run("write")
            self.assertIn("[aborted]", out)

            events = self._read_events(trace_file)
            names = [e["event"] for e in events]
            self.assertIn("approval_requested", names)
            self.assertIn("approval_decision", names)
            self.assertIn("run_end", names)
            self.assertNotIn("step_completed", names)
            approval_requested = next(e for e in events if e["event"] == "approval_requested")
            approval_decision = next(e for e in events if e["event"] == "approval_decision")
            self.assertEqual(
                approval_requested["payload"]["broker"]["kind"],
                "approval",
            )
            self.assertEqual(
                approval_decision["payload"]["broker"]["state"],
                "denied",
            )
            os_events = query_events(root, kind="broker.approval_decision", limit=5)
            self.assertEqual(os_events["returned_events"], 1)


if __name__ == "__main__":
    unittest.main()

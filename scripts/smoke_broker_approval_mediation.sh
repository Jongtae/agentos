#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT_DIR/src"

python3 - <<'PY'
import json
import tempfile
from pathlib import Path

from kernel.memory.store import MemoryStore
from kernel.planner.planner import Plan, Step
from kernel.policies.approval_rules import PolicyEngine
from kernel.runtime.executor import Executor
from kernel.runtime.loop import KernelRuntime
from kernel.runtime.trace import RuntimeTraceWriter


class _Planner:
    def plan(self, intent: str, context: str = "") -> Plan:
        _ = (intent, context)
        return Plan(
            summary="approval path",
            steps=[Step(tool_name="file_write", description="overwrite file", args={"path": "a.txt", "content": "x", "overwrite": True})],
        )


class _Selector:
    def select(self, user_input: str, memory: MemoryStore) -> str:
        _ = (user_input, memory)
        return ""


class _Tool:
    name = "file_write"

    def run(self, args: dict) -> str:
        return f"write:{args['path']}"


with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    trace_file = root / "runtime_trace.jsonl"
    runtime = KernelRuntime(
        planner=_Planner(),
        executor=Executor([_Tool()]),
        context_selector=_Selector(),
        policy=PolicyEngine(require_approval=True),
        approver_fn=lambda _: False,
        memory=MemoryStore(root / "memory.sqlite"),
        trace_writer=RuntimeTraceWriter(trace_file),
        max_steps=3,
    )
    output = runtime.run("overwrite")
    if "[aborted]" not in output:
        raise SystemExit("expected aborted output for denied approval")

    events = [json.loads(line) for line in trace_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    req = next(item for item in events if item["event"] == "approval_requested")
    decision = next(item for item in events if item["event"] == "approval_decision")
    if req["payload"]["broker"]["kind"] != "approval":
        raise SystemExit("expected broker approval request")
    if decision["payload"]["broker"]["state"] != "denied":
        raise SystemExit("expected denied broker decision")

print("broker approval mediation smoke ok")
PY

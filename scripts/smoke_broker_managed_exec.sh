#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT_DIR/src"

python3 - <<'PY'
from kernel.planner.planner import Step
from kernel.policies.approval_rules import PolicyEngine
from kernel.runtime.tool_node_adapter import ToolNodeAdapter
from kernel.tools.bash_tool import BashTool
from kernel.tools.file_tool import FileListTool, FileReadTool, FileWriteTool
from kernel.tools.web_tool import WebTool
from pathlib import Path
import tempfile

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    adapter = ToolNodeAdapter(
        tools=[
            BashTool(root),
            FileReadTool(root),
            FileWriteTool(root),
            FileListTool(root),
            WebTool(),
        ],
        policy=PolicyEngine(require_approval=True),
    )

    allowed = adapter.run_step(Step(tool_name="bash", description="safe", args={"command": "echo hello"}))
    if allowed["broker"]["decision"]["state"] != "allowed":
        raise SystemExit("expected allowed broker decision")

    approval = adapter.run_step(Step(tool_name="bash", description="risky", args={"command": "rm file.txt"}))
    if approval["broker"]["decision"]["state"] != "approval_required":
        raise SystemExit("expected approval_required broker decision")
    if approval["broker"]["request"]["kind"] != "approval":
        raise SystemExit("expected approval request kind")

    blocked = adapter.run_step(Step(tool_name="bash", description="danger", args={"command": "sudo ls"}))
    if blocked["broker"]["decision"]["state"] != "blocked":
        raise SystemExit("expected blocked broker decision")

print("broker managed exec smoke ok")
PY

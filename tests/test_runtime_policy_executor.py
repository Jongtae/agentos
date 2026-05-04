from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.runtime.policy_executor import execute_policy_actions


class RuntimePolicyExecutorTests(unittest.TestCase):
    def test_dry_run_reports_would_execute(self):
        with tempfile.TemporaryDirectory() as td:
            actions = [
                {
                    "id": "run_retention_apply",
                    "auto_safe": True,
                    "recommended_command": "python3 scripts/runtime_trace_retention.py --workspace ./workspaces/default --apply",
                }
            ]
            out = execute_policy_actions(actions=actions, workspace_dir=Path(td), apply=False, max_actions=5)
            self.assertEqual(out["would_execute"], 1)
            self.assertEqual(out["executed"], 0)

    def test_apply_skips_not_auto_safe(self):
        with tempfile.TemporaryDirectory() as td:
            actions = [
                {"id": "unsafe", "auto_safe": False, "recommended_command": "python3 scripts/runtime_governance_report.py"}
            ]
            out = execute_policy_actions(actions=actions, workspace_dir=Path(td), apply=True, max_actions=5)
            self.assertEqual(out["skipped"], 1)
            self.assertEqual(out["executed"], 0)

    def test_apply_rejects_non_allowlisted(self):
        with tempfile.TemporaryDirectory() as td:
            actions = [{"id": "x", "auto_safe": True, "recommended_command": "python3 -c 'print(1)'"}]
            out = execute_policy_actions(actions=actions, workspace_dir=Path(td), apply=True, max_actions=5)
            self.assertEqual(out["skipped"], 1)
            self.assertEqual(out["errors"], 0)

    def test_cli_outputs_execution_summary(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            trace = artifacts / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")
            proc = subprocess.run(
                [
                    "python3",
                    "scripts/runtime_policy_actions_execute.py",
                    "--workspace",
                    str(workspace),
                    "--trace-file",
                    str(trace),
                    "--dry-run",
                ],
                cwd=str(Path(__file__).resolve().parents[1]),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0)
            payload = json.loads(proc.stdout.strip())
            self.assertIn("execution", payload)
            self.assertIn("policy_actions", payload)


if __name__ == "__main__":
    unittest.main()

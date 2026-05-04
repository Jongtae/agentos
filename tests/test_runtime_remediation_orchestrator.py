from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.runtime.remediation_orchestrator import remediation_orchestration_report


class RuntimeRemediationOrchestratorTests(unittest.TestCase):
    def test_orchestration_report_has_plan_execution_rollback(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            trace = artifacts / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")

            payload = remediation_orchestration_report(workspace_dir=workspace, trace_file=trace, apply=False)
            self.assertIn("plan", payload)
            self.assertIn("execution", payload)
            self.assertIn("rollback", payload)
            self.assertEqual(payload["mode"], "dry-run")

    def test_apply_mode_executes_auto_safe(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            trace = artifacts / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")

            payload = remediation_orchestration_report(workspace_dir=workspace, trace_file=trace, apply=True)
            exec_ = payload.get("execution", {})
            self.assertGreaterEqual(int(exec_.get("executed", 0)), 1)

    def test_cli_outputs_json(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            trace = artifacts / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")

            proc = subprocess.run(
                [
                    "python3",
                    "scripts/runtime_remediation_orchestrate.py",
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
            self.assertIn("plan", payload)
            self.assertIn("execution", payload)
            self.assertIn("rollback", payload)


if __name__ == "__main__":
    unittest.main()

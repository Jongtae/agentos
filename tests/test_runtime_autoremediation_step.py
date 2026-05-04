from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class RuntimeAutoremediationStepTests(unittest.TestCase):
    def test_dry_run_outputs_json(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            trace = artifacts / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")

            proc = subprocess.run(
                [
                    "python3",
                    "scripts/runtime_autoremediation_step.py",
                    "--workspace",
                    str(workspace),
                    "--trace-file",
                    str(trace),
                    "--dry-run",
                    "--now-epoch",
                    "1000",
                ],
                cwd=str(Path(__file__).resolve().parents[1]),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0)
            payload = json.loads(proc.stdout.strip())
            self.assertEqual(payload.get("requested_mode"), "dry-run")
            self.assertIn("scheduler", payload)
            self.assertIn("orchestration", payload)

    def test_apply_blocked_returns_non_zero(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            trace = artifacts / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")
            (artifacts / "autoremediation_scheduler_state.json").write_text(
                json.dumps({"last_apply_epoch": 1000, "consecutive_applies": 1}),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    "python3",
                    "scripts/runtime_autoremediation_step.py",
                    "--workspace",
                    str(workspace),
                    "--trace-file",
                    str(trace),
                    "--apply",
                    "--now-epoch",
                    "1100",
                    "--cooldown-sec",
                    "300",
                ],
                cwd=str(Path(__file__).resolve().parents[1]),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 3)
            payload = json.loads(proc.stdout.strip())
            self.assertEqual(payload.get("execution_mode"), "dry-run")
            self.assertFalse(bool(payload.get("state_update", {}).get("written", True)))

    def test_apply_eligible_writes_state(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            trace = artifacts / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")
            archive = artifacts / "runtime_trace.jsonl.1"
            archive.write_text("old\n", encoding="utf-8")

            proc = subprocess.run(
                [
                    "python3",
                    "scripts/runtime_autoremediation_step.py",
                    "--workspace",
                    str(workspace),
                    "--trace-file",
                    str(trace),
                    "--apply",
                    "--now-epoch",
                    "2000",
                    "--cooldown-sec",
                    "10",
                ],
                cwd=str(Path(__file__).resolve().parents[1]),
                env={
                    **dict(os.environ),
                    "AGENTOS_SLO_MAX_RETENTION_PENDING": "0",
                    "AGENTOS_TRACE_KEEP_ARCHIVES": "0",
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0)
            payload = json.loads(proc.stdout.strip())
            self.assertEqual(payload.get("execution_mode"), "apply")
            self.assertTrue(bool(payload.get("state_update", {}).get("written", False)))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class RuntimeAutoremediationCycleTests(unittest.TestCase):
    def test_dry_run_outputs_required_fields(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            trace = artifacts / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")

            proc = subprocess.run(
                [
                    "python3",
                    "scripts/runtime_autoremediation_cycle.py",
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
            for field in ["scheduler", "cadence", "orchestration", "escalation", "state_updates"]:
                self.assertIn(field, payload)

    def test_apply_blocked_by_cadence_returns_non_zero(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            trace = artifacts / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")
            (artifacts / "runtime_trace.jsonl.1").write_text("old\n", encoding="utf-8")
            (artifacts / "autoremediation_cadence_state.json").write_text(
                json.dumps({"last_apply_epoch": 1000, "apply_history_epochs": [1000]}),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    "python3",
                    "scripts/runtime_autoremediation_cycle.py",
                    "--workspace",
                    str(workspace),
                    "--trace-file",
                    str(trace),
                    "--apply",
                    "--now-epoch",
                    "1100",
                    "--cadence-min-interval-sec",
                    "300",
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
            self.assertEqual(proc.returncode, 3)
            payload = json.loads(proc.stdout.strip())
            self.assertEqual(payload.get("execution_mode"), "dry-run")
            self.assertEqual((payload.get("cadence", {}) or {}).get("reason"), "min_interval_not_elapsed")

    def test_apply_eligible_runs_and_writes_state(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            trace = artifacts / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")
            (artifacts / "runtime_trace.jsonl.1").write_text("old\n", encoding="utf-8")

            proc = subprocess.run(
                [
                    "python3",
                    "scripts/runtime_autoremediation_cycle.py",
                    "--workspace",
                    str(workspace),
                    "--trace-file",
                    str(trace),
                    "--apply",
                    "--now-epoch",
                    "2000",
                    "--scheduler-cooldown-sec",
                    "10",
                    "--cadence-min-interval-sec",
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
            state_updates = payload.get("state_updates", {}) or {}
            self.assertTrue(bool((state_updates.get("scheduler", {}) or {}).get("written", False)))
            self.assertTrue(bool((state_updates.get("cadence", {}) or {}).get("written", False)))
            self.assertTrue(bool((state_updates.get("escalation", {}) or {}).get("written", False)))


if __name__ == "__main__":
    unittest.main()

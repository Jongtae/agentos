from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class RuntimeAutoremediationSupervisorTests(unittest.TestCase):
    def test_dry_run_outputs_sections(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "workspace"
            (ws / "artifacts").mkdir(parents=True, exist_ok=True)
            trace = ws / "artifacts" / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")
            proc = subprocess.run(
                [
                    "python3",
                    "scripts/runtime_autoremediation_supervisor.py",
                    "--workspace",
                    str(ws),
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
            for field in ["cycle", "governance", "handoff", "run_id"]:
                self.assertIn(field, payload)

    def test_apply_returns_cycle_exit_when_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "workspace"
            artifacts = ws / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            trace = artifacts / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")
            (artifacts / "autoremediation_cadence_state.json").write_text(
                json.dumps({"last_apply_epoch": 1000, "apply_history_epochs": [1000]}),
                encoding="utf-8",
            )
            (artifacts / "runtime_trace.jsonl.1").write_text("old\n", encoding="utf-8")

            proc = subprocess.run(
                [
                    "python3",
                    "scripts/runtime_autoremediation_supervisor.py",
                    "--workspace",
                    str(ws),
                    "--trace-file",
                    str(trace),
                    "--apply",
                    "--now-epoch",
                    "1100",
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
            self.assertEqual(int(payload.get("cycle_exit_code", 0)), 3)


if __name__ == "__main__":
    unittest.main()

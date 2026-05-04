from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class RuntimeAutoremediationBatchTests(unittest.TestCase):
    def test_dry_run_outputs_batch_sections(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "workspace"
            artifacts = ws / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            trace = artifacts / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")

            proc = subprocess.run(
                [
                    "python3",
                    "scripts/runtime_autoremediation_batch.py",
                    "--workspace",
                    str(ws),
                    "--trace-file",
                    str(trace),
                    "--runs",
                    "2",
                    "--dry-run",
                    "--now-epoch",
                    "1000",
                    "--run-interval-sec",
                    "300",
                ],
                cwd=str(Path(__file__).resolve().parents[1]),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0)
            payload = json.loads(proc.stdout.strip())
            for field in ["campaign", "batch_governance", "batch_review", "run_id"]:
                self.assertIn(field, payload)

    def test_apply_returns_nonzero_when_campaign_fails(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "workspace"
            artifacts = ws / "artifacts"
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
                    "scripts/runtime_autoremediation_batch.py",
                    "--workspace",
                    str(ws),
                    "--trace-file",
                    str(trace),
                    "--runs",
                    "2",
                    "--apply",
                    "--now-epoch",
                    "1100",
                    "--run-interval-sec",
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
            self.assertIn(proc.returncode, [4, 5])
            payload = json.loads(proc.stdout.strip())
            self.assertNotEqual(int(payload.get("campaign_exit_code", 0)), 0)


if __name__ == "__main__":
    unittest.main()

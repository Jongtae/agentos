from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class RuntimeAutoremediationCampaignTests(unittest.TestCase):
    def test_dry_run_outputs_campaign_sections(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "workspace"
            artifacts = ws / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            trace = artifacts / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")

            proc = subprocess.run(
                [
                    "python3",
                    "scripts/runtime_autoremediation_campaign.py",
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
            self.assertEqual(int(payload.get("runs_requested", 0)), 2)
            self.assertEqual(len(payload.get("run_results", [])), 2)
            self.assertIn("campaign_governance", payload)
            self.assertIn("campaign_review", payload)

    def test_apply_campaign_returns_nonzero_when_any_run_fails(self):
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
                    "scripts/runtime_autoremediation_campaign.py",
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
            self.assertEqual(proc.returncode, 4)
            payload = json.loads(proc.stdout.strip())
            run_results = payload.get("run_results", [])
            self.assertEqual(len(run_results), 2)
            self.assertGreaterEqual(sum(1 for item in run_results if int(item.get("exit_code", 0)) != 0), 1)


if __name__ == "__main__":
    unittest.main()

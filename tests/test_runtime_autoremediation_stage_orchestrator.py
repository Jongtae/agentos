from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class RuntimeAutoremediationStageOrchestratorTests(unittest.TestCase):
    def test_dry_run_outputs_orchestrator_sections(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "workspace"
            artifacts = ws / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            trace = artifacts / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")

            proc = subprocess.run(
                [
                    "python3",
                    "scripts/runtime_autoremediation_stage_orchestrator.py",
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
            for field in [
                "stage",
                "stage_tuning",
                "auto_pause",
                "pause_state",
                "resume_gate",
                "override_window",
                "override_budget",
                "forced_resume",
                "override_audit",
                "run_id",
            ]:
                self.assertIn(field, payload)
            self.assertIn("decision", (payload.get("resume_gate", {}) or {}))
            self.assertIn("decision", (payload.get("forced_resume", {}) or {}))

    def test_apply_returns_nonzero_when_stage_fails(self):
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
                    "scripts/runtime_autoremediation_stage_orchestrator.py",
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
            self.assertIn(proc.returncode, [4, 5, 6, 7, 8, 9])
            payload = json.loads(proc.stdout.strip())
            self.assertNotEqual(int(payload.get("stage_exit_code", 0)), 0)

    def test_override_allows_forced_resume(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "workspace"
            artifacts = ws / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            trace = artifacts / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")
            (artifacts / "autoremediation_pause_state.json").write_text(
                json.dumps(
                    {
                        "is_paused": True,
                        "paused_since_epoch": 900,
                        "cooldown_until_epoch": 1500,
                        "pause_reason": "rollback_budget_exhausted",
                        "pause_severity": "critical",
                        "resume_attempt_count": 1,
                        "last_resume_attempt_epoch": 950,
                    }
                ),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    "python3",
                    "scripts/runtime_autoremediation_stage_orchestrator.py",
                    "--workspace",
                    str(ws),
                    "--trace-file",
                    str(trace),
                    "--dry-run",
                    "--now-epoch",
                    "1000",
                    "--resume-requested",
                    "--operator-override-requested",
                ],
                cwd=str(Path(__file__).resolve().parents[1]),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0)
            payload = json.loads(proc.stdout.strip())
            decision = ((payload.get("forced_resume", {}) or {}).get("decision", {}) or {})
            self.assertEqual(str(decision.get("status", "")), "allow")
            self.assertTrue(bool(decision.get("forced", False)))

    def test_budget_exhausted_blocks_forced_resume(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "workspace"
            artifacts = ws / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            trace = artifacts / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")
            (artifacts / "autoremediation_pause_state.json").write_text(
                json.dumps(
                    {
                        "is_paused": True,
                        "paused_since_epoch": 900,
                        "cooldown_until_epoch": 1500,
                        "pause_reason": "rollback_budget_exhausted",
                        "pause_severity": "critical",
                        "resume_attempt_count": 1,
                        "last_resume_attempt_epoch": 950,
                    }
                ),
                encoding="utf-8",
            )
            (artifacts / "autoremediation_override_budget_state.json").write_text(
                json.dumps({"override_applied_epochs": [700, 800, 900]}),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    "python3",
                    "scripts/runtime_autoremediation_stage_orchestrator.py",
                    "--workspace",
                    str(ws),
                    "--trace-file",
                    str(trace),
                    "--dry-run",
                    "--now-epoch",
                    "1000",
                    "--resume-requested",
                    "--operator-override-requested",
                ],
                cwd=str(Path(__file__).resolve().parents[1]),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 9)
            payload = json.loads(proc.stdout.strip())
            decision = ((payload.get("forced_resume", {}) or {}).get("decision", {}) or {})
            self.assertEqual(str(decision.get("status", "")), "block")
            self.assertEqual(str(decision.get("reason", "")), "override_budget_exhausted")


if __name__ == "__main__":
    unittest.main()

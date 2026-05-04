from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kernel.runtime.governance import governance_report


class RuntimeGovernanceTests(unittest.TestCase):
    def test_governance_report_contains_stable_keys(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            trace_dir = workspace / "artifacts"
            trace_dir.mkdir(parents=True, exist_ok=True)
            trace = trace_dir / "runtime_trace.jsonl"
            trace.write_text(
                "\n".join(
                    [
                        '{"timestamp_utc":"2026-01-01T00:00:00+00:00","event":"approval_requested","payload":{}}',
                        '{"timestamp_utc":"2026-01-01T00:00:01+00:00","event":"approval_decision","payload":{"approved":false}}',
                        '{"timestamp_utc":"2026-01-01T00:00:02+00:00","event":"step_blocked","payload":{}}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            report = governance_report(workspace_dir=workspace, trace_file=trace)
            self.assertTrue(report["ok"])
            self.assertIn("policy_pressure", report)
            self.assertIn("retention_health", report)
            self.assertIn("slo", report)
            self.assertIn("overall_state", report)
            self.assertIn("checks", report["slo"])

    def test_slo_threshold_env_override(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            trace_dir = workspace / "artifacts"
            trace_dir.mkdir(parents=True, exist_ok=True)
            trace = trace_dir / "runtime_trace.jsonl"
            trace.write_text(
                "\n".join(
                    [
                        '{"timestamp_utc":"2026-01-01T00:00:00+00:00","event":"approval_requested","payload":{}}',
                        '{"timestamp_utc":"2026-01-01T00:00:01+00:00","event":"approval_decision","payload":{"approved":false}}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"AGENTOS_SLO_MAX_DENIED_RATE": "0.10"}, clear=False):
                report = governance_report(workspace_dir=workspace, trace_file=trace)
                self.assertFalse(report["slo"]["checks"]["denied_rate_ok"])

    def test_cli_outputs_json(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            trace_dir = workspace / "artifacts"
            trace_dir.mkdir(parents=True, exist_ok=True)
            trace = trace_dir / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")

            proc = subprocess.run(
                [
                    "python3",
                    "scripts/runtime_governance_report.py",
                    "--workspace",
                    str(workspace),
                    "--trace-file",
                    str(trace),
                ],
                cwd=str(Path(__file__).resolve().parents[1]),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0)
            payload = json.loads(proc.stdout.strip())
            self.assertIn("policy_pressure", payload)
            self.assertIn("slo", payload)


if __name__ == "__main__":
    unittest.main()

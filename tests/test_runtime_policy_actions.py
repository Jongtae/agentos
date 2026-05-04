from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.runtime.policy_actions import generate_policy_actions, policy_actions_report


class RuntimePolicyActionsTests(unittest.TestCase):
    def test_no_action_when_checks_pass(self):
        payload = {
            "policy_pressure": {"approval_anomaly": {"anomaly_detected": False}},
            "slo": {"checks": {"denied_rate_ok": True, "blocked_steps_ok": True, "retention_pending_ok": True}},
            "overall_state": "PASS",
            "workspace": "/tmp/ws",
        }
        actions = generate_policy_actions(payload)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["id"], "no_action_required")

    def test_actions_when_slo_or_anomaly_fail(self):
        payload = {
            "policy_pressure": {
                "approval_anomaly": {
                    "anomaly_detected": True,
                    "reason": "high_denied_rate",
                    "details": "denied_rate=0.90",
                }
            },
            "slo": {"checks": {"denied_rate_ok": False, "blocked_steps_ok": False, "retention_pending_ok": False}},
            "overall_state": "WARN",
            "workspace": "/tmp/ws",
        }
        actions = generate_policy_actions(payload)
        ids = {a["id"] for a in actions}
        self.assertIn("approval_anomaly_triage", ids)
        self.assertIn("reduce_denied_rate", ids)
        self.assertIn("reduce_blocked_steps", ids)
        self.assertIn("run_retention_apply", ids)

    def test_report_shape(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            trace_dir = workspace / "artifacts"
            trace_dir.mkdir(parents=True, exist_ok=True)
            trace = trace_dir / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")
            report = policy_actions_report(workspace_dir=workspace, trace_file=trace)
            self.assertIn("actions", report)
            self.assertIn("severity_counts", report)
            self.assertIn("action_count", report)

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
                    "scripts/runtime_policy_actions_report.py",
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
            self.assertIn("actions", payload)


if __name__ == "__main__":
    unittest.main()

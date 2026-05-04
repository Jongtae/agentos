from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel.runtime.autoremediation_scheduler import (
    autoremediation_scheduler_report,
    load_autoremediation_state,
    save_autoremediation_state,
)


class RuntimeAutoremediationSchedulerTests(unittest.TestCase):
    def test_no_auto_safe_actions_returns_skip(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            payload = autoremediation_scheduler_report(
                workspace_dir=workspace,
                now_epoch=100,
                actions=[
                    {
                        "id": "no_action_required",
                        "auto_safe": True,
                        "recommended_command": "python3 scripts/runtime_governance_report.py --workspace ./workspaces/default",
                        "severity": "info",
                    }
                ],
            )
            decision = payload.get("decision", {})
            self.assertEqual(decision.get("status"), "skip")
            self.assertEqual(decision.get("reason"), "no_auto_safe_actions")

    def test_cooldown_active_blocks_apply(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            save_autoremediation_state(workspace, last_apply_epoch=100, consecutive_applies=1)
            payload = autoremediation_scheduler_report(
                workspace_dir=workspace,
                now_epoch=200,
                cooldown_sec=150,
                actions=[
                    {
                        "id": "run_retention_apply",
                        "auto_safe": True,
                        "recommended_command": "python3 scripts/runtime_trace_retention.py --workspace ./workspaces/default --apply",
                        "severity": "warn",
                    }
                ],
            )
            decision = payload.get("decision", {})
            self.assertEqual(decision.get("status"), "skip")
            self.assertEqual(decision.get("reason"), "cooldown_active")
            self.assertEqual(int(decision.get("next_allowed_epoch", 0)), 250)

    def test_max_consecutive_applies_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            save_autoremediation_state(workspace, last_apply_epoch=0, consecutive_applies=3)
            payload = autoremediation_scheduler_report(
                workspace_dir=workspace,
                now_epoch=200,
                max_consecutive_applies=3,
                actions=[
                    {
                        "id": "run_retention_apply",
                        "auto_safe": True,
                        "recommended_command": "python3 scripts/runtime_trace_retention.py --workspace ./workspaces/default --apply",
                        "severity": "warn",
                    }
                ],
            )
            decision = payload.get("decision", {})
            self.assertEqual(decision.get("status"), "hold")
            self.assertEqual(decision.get("reason"), "max_consecutive_applies_reached")

    def test_critical_manual_review_forces_hold(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            payload = autoremediation_scheduler_report(
                workspace_dir=workspace,
                now_epoch=200,
                actions=[
                    {
                        "id": "approval_anomaly_triage",
                        "auto_safe": False,
                        "recommended_command": "python3 scripts/runtime_governance_report.py --workspace ./workspaces/default",
                        "severity": "critical",
                    },
                    {
                        "id": "run_retention_apply",
                        "auto_safe": True,
                        "recommended_command": "python3 scripts/runtime_trace_retention.py --workspace ./workspaces/default --apply",
                        "severity": "warn",
                    },
                ],
            )
            decision = payload.get("decision", {})
            self.assertEqual(decision.get("status"), "hold")
            self.assertEqual(decision.get("reason"), "critical_manual_review_required")

    def test_eligible_path_returns_apply(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            save_autoremediation_state(workspace, last_apply_epoch=100, consecutive_applies=1)
            payload = autoremediation_scheduler_report(
                workspace_dir=workspace,
                now_epoch=1200,
                cooldown_sec=300,
                max_consecutive_applies=3,
                actions=[
                    {
                        "id": "run_retention_apply",
                        "auto_safe": True,
                        "recommended_command": "python3 scripts/runtime_trace_retention.py --workspace ./workspaces/default --apply",
                        "severity": "warn",
                    }
                ],
            )
            decision = payload.get("decision", {})
            self.assertEqual(decision.get("status"), "apply")
            self.assertEqual(decision.get("reason"), "eligible")

    def test_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            save_autoremediation_state(workspace, last_apply_epoch=123, consecutive_applies=2)
            state = load_autoremediation_state(workspace)
            self.assertEqual(int(state.get("last_apply_epoch", 0)), 123)
            self.assertEqual(int(state.get("consecutive_applies", 0)), 2)


if __name__ == "__main__":
    unittest.main()

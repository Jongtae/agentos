from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.kernel_policy_shadow_report import build_shadow_report


class KernelPolicyShadowReportTests(unittest.TestCase):
    def _workspace(self) -> Path:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        ws = Path(td.name) / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "artifacts").mkdir(parents=True, exist_ok=True)
        (ws / "spec.yaml").write_text(
            yaml.dump(
                {
                    "name": "shadow-test",
                    "kernel_engine": {"provider": "none", "mode": "single"},
                    "runtime": {"workspace_root": "./"},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return ws

    def test_shadow_report_alignment(self):
        ws = self._workspace()
        trace = ws / "artifacts" / "runtime_trace.jsonl"
        shadow = ws / "artifacts" / "kernel-shadow-events.jsonl"
        trace.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "event": "step_blocked",
                            "payload": {"reason": "workspace_boundary", "detail": "../outside.txt"},
                        }
                    ),
                    json.dumps(
                        {
                            "event": "step_blocked",
                            "payload": {"reason": "workspace_boundary", "detail": "../outside2.txt"},
                        }
                    ),
                    json.dumps(
                        {
                            "event": "step_blocked",
                            "payload": {"reason": "network_allowlist", "detail": "blocked.example"},
                        }
                    ),
                    json.dumps(
                        {
                            "event": "approval_requested",
                            "payload": {"tool_name": "bash", "risk_reason": "destructive command"},
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        shadow.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "event": "kernel.shadow.fs_outside_workspace.v1",
                            "payload": {"policy_target": "fs_workspace_boundary", "path": "../outside.txt"},
                        }
                    ),
                    json.dumps(
                        {
                            "event": "kernel.shadow.fs_outside_workspace.v1",
                            "payload": {"policy_target": "fs_workspace_boundary", "path": "../outside2.txt"},
                        }
                    ),
                    json.dumps(
                        {
                            "event": "kernel.shadow.net_allowlist_violation.v1",
                            "payload": {"policy_target": "network_allowlist", "host": "blocked.example", "port": 443, "action": "connect"},
                        }
                    ),
                    json.dumps(
                        {
                            "event": "kernel.shadow.destructive_action.v1",
                            "payload": {"policy_target": "destructive_action_approval", "approval_id": "approval:1", "action": "approval_gate"},
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        report = build_shadow_report(str(ws))
        self.assertEqual(report["primary_policy_target"], "fs_workspace_boundary")
        self.assertEqual(report["next_policy_target"], "destructive_action_approval")
        self.assertEqual(report["user_space_blocked_count"], 2)
        self.assertEqual(report["shadow_detected_count"], 2)
        self.assertTrue(report["comparison"]["aligned"])
        self.assertEqual(report["comparison"]["delta"], 0)
        self.assertEqual(report["coverage_summary"]["policy_target_count"], 3)
        self.assertEqual(report["coverage_summary"]["aligned_count"], 3)
        self.assertEqual(report["coverage_summary"]["divergent_count"], 0)
        network_target = next(item for item in report["policy_targets"] if item["policy_target"] == "network_allowlist")
        self.assertEqual(network_target["user_space_blocked_count"], 1)
        self.assertEqual(network_target["shadow_detected_count"], 1)
        self.assertEqual(network_target["comparison"]["status"], "aligned")
        approval_target = next(
            item for item in report["policy_targets"] if item["policy_target"] == "destructive_action_approval"
        )
        self.assertEqual(approval_target["user_space_blocked_count"], 1)
        self.assertEqual(approval_target["shadow_detected_count"], 1)
        self.assertEqual(approval_target["comparison"]["status"], "aligned")
        self.assertTrue(report["overall_aligned"])


if __name__ == "__main__":
    unittest.main()

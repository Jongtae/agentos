from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.kernel_session_replay import build_session_replay


class KernelSessionReplayTests(unittest.TestCase):
    def test_build_session_replay_orders_runtime_broker_and_session_milestones(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
            (workspace / "spec.yaml").write_text(
                yaml.dump(
                    {
                        "name": "replay-test",
                        "kernel_engine": {"provider": "none", "mode": "single"},
                        "runtime": {"workspace_root": "./"},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            (workspace / "artifacts" / "runtime_trace.jsonl").write_text(
                "\n".join(
                    [
                        '{"timestamp_utc":"2026-04-14T00:00:00+00:00","event":"run_start","payload":{}}',
                        '{"timestamp_utc":"2026-04-14T00:00:01+00:00","event":"approval_requested","payload":{"tool_name":"bash"}}',
                        '{"timestamp_utc":"2026-04-14T00:00:02+00:00","event":"approval_decision","payload":{"approved":false}}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (workspace / "artifacts" / "os_events.jsonl").write_text(
                "\n".join(
                    [
                        '{"timestamp_utc":"2026-04-14T00:00:01+00:00","source":"broker","kind":"broker.approval_request","actor":{"component":"agentos-runtime"},"object":{"policy_target":"destructive_action_approval","tool_name":"bash"},"action":"approval_gate","decision":{"state":"requested","request_kind":"approval"},"correlation":{"approval_id":"approval:test","session_id":"agentos:tty1","boot_id":"boot-1"},"raw_ref":{"component":"broker"}}',
                        '{"timestamp_utc":"2026-04-14T00:00:03+00:00","source":"journald","kind":"session.login","actor":{"uid":1000},"object":{"session_id":"agentos:tty1"},"action":"login","decision":{"state":"observed"},"correlation":{"session_id":"agentos:tty1","boot_id":"boot-1","session_origin":"local_managed_tty1","next_managed_entry":"ai_shell"},"raw_ref":{"collector":"journald"}}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = build_session_replay(str(workspace), session_id="agentos:tty1")
            self.assertTrue(report["ok"])
            self.assertGreaterEqual(report["milestone_count"], 4)
            milestones = [item["milestone"] for item in report["milestones"]]
            self.assertIn("run_start", milestones)
            self.assertIn("broker.approval_request", milestones)
            self.assertIn("session.login", milestones)
            self.assertEqual(report["ownership_summary"]["session_phase"], "ai_shell")
            self.assertEqual(report["approval_forensics_summary"]["approval_requested"], 1)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel.event_fabric.collectors import append_events_jsonl, file_access_candidate_event, network_connect_candidate_event
from kernel.event_fabric.policy_evidence import policy_evidence_report


class EventFabricPolicyEvidenceTests(unittest.TestCase):
    def test_policy_evidence_report_marks_alignment_and_divergence(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir()
            trace_file = workspace / "artifacts" / "runtime_trace.jsonl"
            trace_file.parent.mkdir(parents=True, exist_ok=True)
            trace_file.write_text(
                "\n".join(
                    [
                        '{"timestamp_utc":"2026-04-14T00:00:01+00:00","event":"step_blocked","payload":{"reason":"workspace_boundary","detail":"../outside.txt"}}',
                        '{"timestamp_utc":"2026-04-14T00:00:02+00:00","event":"step_blocked","payload":{"reason":"network_allowlist","detail":"blocked.example"}}',
                        '{"timestamp_utc":"2026-04-14T00:00:03+00:00","event":"step_blocked","payload":{"reason":"network_allowlist","detail":"blocked-2.example"}}',
                        '{"timestamp_utc":"2026-04-14T00:00:04+00:00","event":"approval_requested","payload":{"tool_name":"bash","risk_reason":"destructive command"}}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            events = [
                file_access_candidate_event(
                    candidate_path="../outside.txt",
                    action="read",
                    workspace_root=str(workspace),
                    actor={"pid": 7, "comm": "bash"},
                ),
                network_connect_candidate_event(
                    host="blocked.example",
                    port=443,
                    allowlist=["openai.com"],
                    actor={"pid": 7, "comm": "curl"},
                ),
            ]
            append_events_jsonl(workspace / "artifacts" / "os_events.jsonl", [event for event in events if event is not None])
            with (workspace / "artifacts" / "os_events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(
                    '{"timestamp_utc":"2026-04-14T00:00:04+00:00","source":"broker","kind":"broker.approval_request","actor":{"component":"agentos-runtime"},"object":{"policy_target":"destructive_action_approval","tool_name":"bash"},"action":"approval_gate","decision":{"state":"requested","request_kind":"approval"},"correlation":{"approval_id":"approval:1"},"raw_ref":{"component":"broker"}}\n'
                )
            kernel_policy_dir = workspace / "artifacts" / "kernel-policy"
            kernel_policy_dir.mkdir(parents=True, exist_ok=True)
            (kernel_policy_dir / "enforced-pilot.json").write_text(
                '{"enabled": true, "policy_target": "fs_workspace_boundary", "updated_at_utc": "2026-04-14T00:00:05+00:00"}\n',
                encoding="utf-8",
            )

            report = policy_evidence_report(workspace, trace_file=trace_file)

            self.assertTrue(report["ok"])
            self.assertTrue(report["enforced_pilot"]["configured_enabled"])
            targets = {item["policy_target"]: item for item in report["policy_targets"]}
            self.assertEqual(targets["fs_workspace_boundary"]["comparison"]["status"], "aligned")
            self.assertTrue(targets["fs_workspace_boundary"]["enforced_pilot"]["effective"])
            self.assertEqual(targets["network_allowlist"]["comparison"]["status"], "divergent")
            self.assertEqual(targets["network_allowlist"]["comparison"]["delta"], -1)
            self.assertEqual(targets["destructive_action_approval"]["comparison"]["status"], "aligned")
            self.assertEqual(targets["destructive_action_approval"]["evidence_kind"], "broker.approval_request")


if __name__ == "__main__":
    unittest.main()

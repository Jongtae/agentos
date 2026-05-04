from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.kernel_operator_case_export import build_case_export


class KernelOperatorCaseExportTests(unittest.TestCase):
    def test_build_case_export_packages_evidence_replay_and_approval_forensics(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / 'workspace'
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / 'artifacts').mkdir(parents=True, exist_ok=True)
            (workspace / 'spec.yaml').write_text(
                yaml.dump(
                    {
                        'name': 'case-export-test',
                        'kernel_engine': {'provider': 'none', 'mode': 'single'},
                        'runtime': {'workspace_root': './'},
                    },
                    sort_keys=False,
                ),
                encoding='utf-8',
            )
            (workspace / 'artifacts' / 'runtime_trace.jsonl').write_text(
                '\n'.join([
                    json.dumps({'timestamp_utc': '2026-04-14T00:00:00+00:00', 'event': 'run_start', 'payload': {}}),
                    json.dumps({'timestamp_utc': '2026-04-14T00:00:01+00:00', 'event': 'approval_requested', 'payload': {'tool_name': 'bash', 'risk_reason': 'destructive command', 'broker': {'correlation': {'request_id': 'req-1', 'approval_id': 'approval:req-1'}}}}),
                    json.dumps({'timestamp_utc': '2026-04-14T00:00:02+00:00', 'event': 'approval_decision', 'payload': {'tool_name': 'bash', 'approved': False, 'broker': {'correlation': {'request_id': 'req-1', 'approval_id': 'approval:req-1'}}}}),
                ]) + '\n',
                encoding='utf-8',
            )
            (workspace / 'artifacts' / 'os_events.jsonl').write_text(
                '\n'.join([
                    json.dumps({'timestamp_utc': '2026-04-14T00:00:00+00:00', 'source': 'journald', 'kind': 'session.login', 'actor': {'uid': 1000}, 'object': {'session_id': 'agentos:tty1'}, 'action': 'login', 'decision': {'state': 'observed'}, 'correlation': {'session_id': 'agentos:tty1', 'boot_id': 'boot-1', 'session_origin': 'local_managed_tty1', 'next_managed_entry': 'ai_shell'}, 'raw_ref': {'collector': 'journald'}}),
                    json.dumps({'timestamp_utc': '2026-04-14T00:00:01+00:00', 'source': 'broker', 'kind': 'broker.approval_request', 'actor': {'component': 'agentos-runtime'}, 'object': {'tool_name': 'bash', 'policy_target': 'destructive_action_approval'}, 'action': 'approval_gate', 'decision': {'state': 'requested', 'request_kind': 'approval'}, 'correlation': {'approval_id': 'approval:req-1', 'request_id': 'req-1', 'session_id': 'agentos:tty1'}, 'raw_ref': {'component': 'broker'}}),
                    json.dumps({'timestamp_utc': '2026-04-14T00:00:02+00:00', 'source': 'broker', 'kind': 'broker.approval_decision', 'actor': {'component': 'agentos-runtime'}, 'object': {'tool_name': 'bash', 'policy_target': 'destructive_action_approval'}, 'action': 'decision', 'decision': {'state': 'denied', 'reason': 'approval denied by approver', 'request_kind': 'approval'}, 'correlation': {'approval_id': 'approval:req-1', 'request_id': 'req-1', 'session_id': 'agentos:tty1'}, 'raw_ref': {'component': 'broker'}}),
                ]) + '\n',
                encoding='utf-8',
            )
            payload = build_case_export(workspace=str(workspace), session_id='agentos:tty1')
            self.assertEqual(payload['schema_version'], 'agentos-operator-case.v1')
            self.assertEqual(payload['summary']['approval_requested'], 1)
            self.assertEqual(payload['summary']['approval_denied'], 1)
            self.assertGreaterEqual(payload['summary']['milestone_count'], 3)
            self.assertIn('evidence', payload)
            self.assertIn('replay', payload)
            self.assertIn('approval_forensics', payload)


if __name__ == '__main__':
    unittest.main()

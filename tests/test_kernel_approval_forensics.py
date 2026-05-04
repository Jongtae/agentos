from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.kernel_approval_forensics import build_approval_forensics


class KernelApprovalForensicsTests(unittest.TestCase):
    def test_build_approval_forensics_tracks_denials_overrides_and_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            artifacts = ws / 'artifacts'
            artifacts.mkdir()
            (artifacts / 'runtime_trace.jsonl').write_text(
                '\n'.join([
                    json.dumps({
                        'timestamp_utc': '2026-04-14T00:00:01+00:00',
                        'event': 'approval_requested',
                        'payload': {
                            'tool_name': 'bash',
                            'risk_reason': 'destructive command',
                            'broker': {'correlation': {'request_id': 'req-1', 'approval_id': 'approval:req-1'}},
                        },
                    }),
                    json.dumps({
                        'timestamp_utc': '2026-04-14T00:00:02+00:00',
                        'event': 'approval_decision',
                        'payload': {
                            'tool_name': 'bash',
                            'approved': False,
                            'broker': {'correlation': {'request_id': 'req-1', 'approval_id': 'approval:req-1'}},
                        },
                    }),
                ]) + '\n',
                encoding='utf-8',
            )
            (artifacts / 'os_events.jsonl').write_text(
                '\n'.join([
                    json.dumps({
                        'timestamp_utc': '2026-04-14T00:00:00+00:00',
                        'source': 'journald',
                        'kind': 'session.login',
                        'actor': {'component': 'logind'},
                        'object': {'session_id': 'tty1'},
                        'action': 'login',
                        'decision': {'state': 'observed'},
                        'correlation': {
                            'session_id': 'tty1',
                            'boot_id': 'boot-1',
                            'session_origin': 'local_managed_tty1',
                            'next_managed_entry': 'ai_shell',
                        },
                        'raw_ref': {'component': 'journald'},
                    }),
                    json.dumps({
                        'timestamp_utc': '2026-04-14T00:00:01+00:00',
                        'source': 'broker',
                        'kind': 'broker.approval_request',
                        'actor': {'component': 'agentos-runtime'},
                        'object': {'tool_name': 'bash', 'policy_target': 'destructive_action_approval'},
                        'action': 'approval_gate',
                        'decision': {'state': 'requested', 'request_kind': 'approval'},
                        'correlation': {'request_id': 'req-1', 'approval_id': 'approval:req-1', 'session_id': 'tty1'},
                        'raw_ref': {'component': 'broker'},
                    }),
                    json.dumps({
                        'timestamp_utc': '2026-04-14T00:00:02+00:00',
                        'source': 'broker',
                        'kind': 'broker.approval_decision',
                        'actor': {'component': 'agentos-runtime'},
                        'object': {'tool_name': 'bash', 'policy_target': 'destructive_action_approval'},
                        'action': 'decision',
                        'decision': {'state': 'denied', 'reason': 'approval denied by approver', 'request_kind': 'approval'},
                        'correlation': {'request_id': 'req-1', 'approval_id': 'approval:req-1', 'session_id': 'tty1'},
                        'raw_ref': {'component': 'broker'},
                    }),
                    json.dumps({
                        'timestamp_utc': '2026-04-14T00:00:03+00:00',
                        'source': 'broker',
                        'kind': 'broker.exec_decision',
                        'actor': {'component': 'install_kernel_boot_integration.sh'},
                        'object': {'status': 'override_active'},
                        'action': 'install_kernel_boot_integration',
                        'decision': {'state': 'override', 'reason': 'operator override active: install_kernel_boot_integration', 'request_kind': 'override'},
                        'correlation': {'request_id': 'req-override', 'session_id': 'tty1'},
                        'raw_ref': {'component': 'broker'},
                    }),
                ]) + '\n',
                encoding='utf-8',
            )
            report = build_approval_forensics(ws, limit=20)
            summary = report['summary']
            self.assertEqual(summary['approval_requested'], 1)
            self.assertEqual(summary['approval_denied'], 1)
            self.assertEqual(summary['broker_override_count'], 1)
            self.assertEqual(summary['forensic_status'], 'override_active')
            self.assertGreaterEqual(summary['approval_ids_observed'], 1)
            self.assertGreaterEqual(summary['request_ids_observed'], 1)
            self.assertEqual(report['recovery']['session_phase'], 'ai_shell')


if __name__ == '__main__':
    unittest.main()

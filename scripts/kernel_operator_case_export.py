#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / 'src'
SCRIPTS_DIR = ROOT_DIR / 'scripts'
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kernel_approval_forensics import build_approval_forensics
from kernel_operator_evidence import build_evidence_report
from kernel_session_replay import build_session_replay

SCHEMA_VERSION = 'agentos-operator-case.v1'


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def build_case_export(
    *,
    workspace: str,
    install_root: str = '',
    metadata: str = '',
    snapshot_label: str = 'agentos-demo-clean',
    session_id: str = '',
    limit: int = 50,
) -> dict:
    evidence = build_evidence_report(
        workspace=workspace,
        install_root=install_root,
        metadata=metadata,
        snapshot_label=snapshot_label,
    )
    replay = build_session_replay(workspace, session_id=session_id, limit=limit)
    approval = build_approval_forensics(workspace, session_id=session_id, limit=limit)

    summary = {
        'runtime_ok': bool((evidence.get('summary') or {}).get('runtime_ok', False)),
        'session_phase': str((evidence.get('summary') or {}).get('session_phase', '')),
        'session_origin': str((evidence.get('summary') or {}).get('session_origin', '')),
        'approval_forensic_status': str((approval.get('summary') or {}).get('forensic_status', '')),
        'approval_requested': int((approval.get('summary') or {}).get('approval_requested', 0) or 0),
        'approval_denied': int((approval.get('summary') or {}).get('approval_denied', 0) or 0),
        'broker_override_count': int((approval.get('summary') or {}).get('broker_override_count', 0) or 0),
        'milestone_count': int(replay.get('milestone_count', 0) or 0),
        'policy_targets': list((evidence.get('summary') or {}).get('policy_targets', [])),
        'install_validation_ok': (evidence.get('summary') or {}).get('install_validation_ok', None),
        'audit_ok': (evidence.get('summary') or {}).get('audit_ok', None),
    }

    return {
        'schema_version': SCHEMA_VERSION,
        'generated_at_utc': _utc_now(),
        'workspace': str(Path(workspace).resolve()),
        'session_filter': session_id,
        'summary': summary,
        'evidence': evidence,
        'replay': replay,
        'approval_forensics': approval,
        'references': {
            'primary_commands': [
                'scripts/agentos-kernelctl evidence --workspace ./workspaces/default --json',
                'scripts/agentos-kernelctl replay --workspace ./workspaces/default --json',
                'scripts/agentos-kernelctl approval-forensics --workspace ./workspaces/default --json',
            ],
            'diagnostics_bundle_hint': 'scripts/export_diagnostics_bundle.sh ./workspaces/default',
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Export AgentOS operator case artifact')
    parser.add_argument('--workspace', default='./workspaces/default')
    parser.add_argument('--install-root', default='')
    parser.add_argument('--metadata', default='')
    parser.add_argument('--snapshot-label', default='agentos-demo-clean')
    parser.add_argument('--session-id', default='')
    parser.add_argument('--limit', type=int, default=50)
    parser.add_argument('--output', default='')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    payload = build_case_export(
        workspace=args.workspace,
        install_root=args.install_root,
        metadata=args.metadata,
        snapshot_label=args.snapshot_label,
        session_id=args.session_id,
        limit=args.limit,
    )
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + '\n', encoding='utf-8')
    if args.json or not args.output:
        print(text)
        return 0

    summary = payload['summary']
    print('AgentOS Operator Case Export')
    print('============================')
    print(f"Workspace: {payload['workspace']}")
    print(
        'Summary: '
        f"phase={summary['session_phase'] or 'unknown'} origin={summary['session_origin'] or 'unknown'} "
        f"approvals={summary['approval_requested']} denied={summary['approval_denied']} "
        f"overrides={summary['broker_override_count']} milestones={summary['milestone_count']} "
        f"forensics={summary['approval_forensic_status'] or 'unknown'}"
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

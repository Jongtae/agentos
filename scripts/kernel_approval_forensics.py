#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / 'src'
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.event_fabric.report import query_events, query_session_timeline
from kernel.runtime.trace import resolve_runtime_trace_path


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        row = line.strip()
        if not row:
            continue
        try:
            payload = json.loads(row)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _runtime_approval_summary(rows: list[dict]) -> dict:
    requested = 0
    approved = 0
    denied = 0
    blocked = 0
    recent: list[dict] = []
    approval_ids: list[str] = []
    request_ids: list[str] = []
    for row in rows:
        event = str(row.get('event', '')).strip()
        payload = row.get('payload', {}) or {}
        broker = payload.get('broker', {}) or {}
        correlation = broker.get('correlation', {}) or {}
        approval_id = str(correlation.get('approval_id', '')).strip()
        request_id = str(correlation.get('request_id', '')).strip()
        if approval_id and approval_id not in approval_ids:
            approval_ids.append(approval_id)
        if request_id and request_id not in request_ids:
            request_ids.append(request_id)
        if event == 'approval_requested':
            requested += 1
            recent.append({
                'timestamp_utc': str(row.get('timestamp_utc', '')),
                'source': 'runtime_trace',
                'kind': event,
                'decision': 'requested',
                'tool_name': str(payload.get('tool_name', '')),
                'approval_id': approval_id,
                'request_id': request_id,
                'reason': str(payload.get('risk_reason', '')),
            })
        elif event == 'approval_decision':
            if bool(payload.get('approved', False)):
                approved += 1
                decision_state = 'approved'
            else:
                denied += 1
                decision_state = 'denied'
            recent.append({
                'timestamp_utc': str(row.get('timestamp_utc', '')),
                'source': 'runtime_trace',
                'kind': event,
                'decision': decision_state,
                'tool_name': str(payload.get('tool_name', '')),
                'approval_id': approval_id,
                'request_id': request_id,
                'reason': str(((payload.get('broker') or {}).get('reason', ''))),
            })
        elif event == 'step_blocked':
            reason = str(payload.get('reason', '')).lower()
            if 'approval' in reason or reason == 'approval_required':
                blocked += 1
    return {
        'requested': requested,
        'approved': approved,
        'denied': denied,
        'blocked': blocked,
        'approval_ids': approval_ids,
        'request_ids': request_ids,
        'recent': recent,
    }


def _collect_broker_events(workspace: Path, *, limit: int) -> list[dict]:
    rows: list[dict] = []
    for kind in ('broker.approval_request', 'broker.approval_decision', 'broker.exec_decision'):
        rows.extend((query_events(workspace, kind=kind, limit=limit).get('events') or []))
    rows.sort(key=lambda item: str(item.get('timestamp_utc', '')))
    return rows[-limit:]


def _broker_forensics_summary(workspace: Path, *, limit: int) -> dict:
    rows = _collect_broker_events(workspace, limit=limit)
    counts = {
        'approval_requests': 0,
        'approval_approved': 0,
        'approval_denied': 0,
        'overrides': 0,
        'operator_controls': 0,
        'install_controls': 0,
    }
    recent: list[dict] = []
    approval_ids: list[str] = []
    request_ids: list[str] = []
    for row in rows:
        kind = str(row.get('kind', '')).strip()
        decision = row.get('decision', {}) or {}
        request_kind = str(decision.get('request_kind', '')).strip()
        state = str(decision.get('state', '')).strip()
        correlation = row.get('correlation', {}) or {}
        approval_id = str(correlation.get('approval_id', '')).strip()
        request_id = str(correlation.get('request_id', '')).strip()
        if approval_id and approval_id not in approval_ids:
            approval_ids.append(approval_id)
        if request_id and request_id not in request_ids:
            request_ids.append(request_id)

        if kind == 'broker.approval_request' or request_kind == 'approval' and state == 'requested':
            counts['approval_requests'] += 1
        elif kind == 'broker.approval_decision' and state == 'approved':
            counts['approval_approved'] += 1
        elif kind == 'broker.approval_decision' and state == 'denied':
            counts['approval_denied'] += 1

        if request_kind == 'override' or state == 'override':
            counts['overrides'] += 1
        if request_kind == 'operator_control':
            counts['operator_controls'] += 1
        if request_kind == 'install_control':
            counts['install_controls'] += 1

        recent.append({
            'timestamp_utc': str(row.get('timestamp_utc', '')),
            'kind': kind,
            'request_kind': request_kind,
            'state': state,
            'action': str(row.get('action', '')),
            'approval_id': approval_id,
            'request_id': request_id,
            'reason': str(decision.get('reason', '')),
        })

    return {
        'counts': counts,
        'approval_ids': approval_ids,
        'request_ids': request_ids,
        'recent': recent,
    }


def _recovery_summary(session_report: dict) -> dict:
    ownership = session_report.get('ownership_summary', {}) or {}
    recovery_bypass = str(ownership.get('session_phase', '')).strip() == 'recovery_bypass'
    timeline = session_report.get('timeline', []) or []
    hints = []
    if recovery_bypass:
        hints.extend([
            'AGENTOS_BOOT_AUTOSTART=0',
            'AGENTOS_BROKER_BYPASS=1',
            'AGENTOS_BROKER_OVERRIDE=1',
        ])
    return {
        'recovery_bypass_active': recovery_bypass,
        'session_phase': str(ownership.get('session_phase', '')),
        'session_origin': str(ownership.get('session_origin', '')),
        'next_managed_entry': str(ownership.get('next_managed_entry', '')),
        'timeline_event_count': len(timeline),
        'recovery_hints': hints,
    }


def build_approval_forensics(workspace: str | Path, *, session_id: str = '', limit: int = 50) -> dict:
    workspace_path = Path(workspace).resolve()
    runtime_trace = resolve_runtime_trace_path(workspace_path)
    runtime_rows = _read_jsonl(runtime_trace)
    session_report = query_session_timeline(workspace_path, session_id=session_id, limit=limit)
    runtime = _runtime_approval_summary(runtime_rows)
    broker = _broker_forensics_summary(workspace_path, limit=limit)
    recovery = _recovery_summary(session_report)

    approval_ids = []
    request_ids = []
    for value in runtime.get('approval_ids', []) + broker.get('approval_ids', []) + list((session_report.get('correlation_evidence') or {}).get('approval_ids', [])):
        if value and value not in approval_ids:
            approval_ids.append(value)
    for value in runtime.get('request_ids', []) + broker.get('request_ids', []) + list((session_report.get('correlation_evidence') or {}).get('request_ids', [])):
        if value and value not in request_ids:
            request_ids.append(value)

    summary = {
        'approval_requested': int(runtime['requested']),
        'approval_approved': int(runtime['approved']),
        'approval_denied': int(runtime['denied']),
        'approval_blocked': int(runtime['blocked']),
        'broker_override_count': int((broker.get('counts') or {}).get('overrides', 0)),
        'operator_control_count': int((broker.get('counts') or {}).get('operator_controls', 0)),
        'install_control_count': int((broker.get('counts') or {}).get('install_controls', 0)),
        'recovery_bypass_active': bool(recovery['recovery_bypass_active']),
        'approval_ids_observed': len(approval_ids),
        'request_ids_observed': len(request_ids),
    }
    summary['forensic_status'] = (
        'override_active' if summary['broker_override_count'] > 0 else
        'approval_denied' if summary['approval_denied'] > 0 else
        'approval_heavy' if summary['approval_requested'] > 0 else
        'quiet'
    )

    recent = sorted(runtime['recent'] + broker['recent'], key=lambda item: str(item.get('timestamp_utc', '')))[-limit:]
    return {
        'ok': True,
        'exit_code': 0,
        'workspace': str(workspace_path),
        'runtime_trace_file': str(runtime_trace),
        'session_filter': session_id,
        'summary': summary,
        'runtime_trace': {
            'requested': runtime['requested'],
            'approved': runtime['approved'],
            'denied': runtime['denied'],
            'blocked': runtime['blocked'],
        },
        'broker': broker['counts'],
        'recovery': recovery,
        'correlation_evidence': {
            'approval_ids': approval_ids,
            'request_ids': request_ids,
            'session_ids': [str((session_report.get('correlation_evidence') or {}).get('session_id', ''))] if (session_report.get('correlation_evidence') or {}).get('session_id') else [],
            'boot_ids': list((session_report.get('correlation_evidence') or {}).get('boot_ids', [])),
        },
        'recent_events': recent,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Build AgentOS approval control forensics report')
    parser.add_argument('--workspace', default='./workspaces/default')
    parser.add_argument('--session-id', default='')
    parser.add_argument('--limit', type=int, default=50)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    payload = build_approval_forensics(args.workspace, session_id=args.session_id, limit=args.limit)
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
        return int(payload['exit_code'])

    print('AgentOS Approval Forensics')
    print('==========================')
    print(f"Workspace: {payload['workspace']}")
    summary = payload['summary']
    print(
        'Summary: '
        f"requested={summary['approval_requested']} approved={summary['approval_approved']} denied={summary['approval_denied']} "
        f"blocked={summary['approval_blocked']} overrides={summary['broker_override_count']} "
        f"recovery_bypass={summary['recovery_bypass_active']} status={summary['forensic_status']}"
    )
    print('Recent approval evidence:')
    for row in payload['recent_events']:
        print(f"- {row.get('timestamp_utc','')} [{row.get('kind', row.get('source',''))}] {row.get('state', row.get('decision',''))} {row.get('reason','')}")
    return int(payload['exit_code'])


if __name__ == '__main__':
    raise SystemExit(main())

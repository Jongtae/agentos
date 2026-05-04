#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(ROOT_DIR / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "scripts"))

from kernel.event_fabric.report import query_events, query_session_timeline
from kernel.runtime.trace import resolve_runtime_trace_path
from kernel_approval_forensics import build_approval_forensics


def _read_runtime_trace(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
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


def _runtime_replay_events(trace_rows: list[dict]) -> list[dict]:
    replay: list[dict] = []
    for row in trace_rows:
        event = str(row.get("event", "")).strip()
        payload = row.get("payload", {}) or {}
        timestamp = str(row.get("timestamp_utc", "")).strip()
        milestone = ""
        summary = ""
        if event == "approval_requested":
            milestone = "approval_requested"
            summary = f"Approval requested for {payload.get('tool_name', 'unknown')}"
        elif event == "approval_decision":
            milestone = "approval_decision"
            summary = "Approval granted" if bool(payload.get("approved", False)) else "Approval denied"
        elif event == "step_blocked":
            milestone = "step_blocked"
            summary = f"Step blocked: {payload.get('reason', 'policy')}"
        elif event == "step_completed":
            milestone = "step_completed"
            summary = f"Step completed: {payload.get('tool_name', 'unknown')}"
        elif event == "run_start":
            milestone = "run_start"
            summary = "Runtime loop started"
        elif event == "run_end":
            milestone = "run_end"
            summary = "Runtime loop ended"
        if milestone:
            replay.append(
                {
                    "timestamp_utc": timestamp,
                    "source": "runtime_trace",
                    "milestone": milestone,
                    "summary": summary,
                    "payload": payload,
                }
            )
    return replay


def _broker_replay_events(workspace: Path, *, limit: int) -> list[dict]:
    replay: list[dict] = []
    for kind in ("broker.exec_request", "broker.exec_decision", "broker.approval_request", "broker.approval_decision"):
        report = query_events(workspace, kind=kind, limit=limit)
        for row in report.get("events", []) or []:
            decision = row.get("decision", {}) or {}
            obj = row.get("object", {}) or {}
            replay.append(
                {
                    "timestamp_utc": str(row.get("timestamp_utc", "")),
                    "source": "broker",
                    "milestone": kind,
                    "summary": f"{kind}: {decision.get('state', '')} {obj.get('tool_name', '')}".strip(),
                    "payload": {
                        "decision": decision,
                        "object": obj,
                        "correlation": row.get("correlation") or {},
                    },
                }
            )
    return replay


def _session_replay_events(session_report: dict) -> list[dict]:
    replay: list[dict] = []
    for row in session_report.get("timeline", []) or []:
        replay.append(
            {
                "timestamp_utc": str(row.get("timestamp_utc", "")),
                "source": "session_timeline",
                "milestone": str(row.get("kind", "")),
                "summary": str(row.get("summary", "")),
                "payload": {
                    "session_id": row.get("session_id", ""),
                    "correlation": row.get("correlation") or {},
                    "object": row.get("object") or {},
                },
            }
        )
    return replay


def build_session_replay(workspace: str | Path, *, session_id: str = "", limit: int = 50) -> dict:
    workspace_path = Path(workspace).resolve()
    runtime_trace_path = resolve_runtime_trace_path(workspace_path)
    trace_rows = _read_runtime_trace(runtime_trace_path)
    session_report = query_session_timeline(workspace_path, session_id=session_id, limit=limit)
    approval_forensics = build_approval_forensics(workspace_path, session_id=session_id, limit=limit)

    replay = []
    replay.extend(_runtime_replay_events(trace_rows))
    replay.extend(_broker_replay_events(workspace_path, limit=limit))
    replay.extend(_session_replay_events(session_report))
    replay.sort(key=lambda item: item.get("timestamp_utc", ""))

    return {
        "ok": True,
        "exit_code": 0,
        "workspace": str(workspace_path),
        "runtime_trace_file": str(runtime_trace_path),
        "session_filter": session_id,
        "ownership_summary": session_report.get("ownership_summary", {}),
        "correlation_evidence": session_report.get("correlation_evidence", {}),
        "approval_forensics_summary": approval_forensics.get("summary", {}),
        "milestone_count": len(replay),
        "milestones": replay[-limit:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AgentOS session replay narrative")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_session_replay(args.workspace, session_id=args.session_id, limit=args.limit)
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
        return int(payload["exit_code"])

    print("AgentOS Session Replay")
    print("======================")
    print(f"Workspace: {payload['workspace']}")
    ownership = payload.get("ownership_summary", {}) or {}
    print(
        "Ownership: "
        f"phase={ownership.get('session_phase', '') or 'unknown'} "
        f"origin={ownership.get('session_origin', '') or 'unknown'} "
        f"next={ownership.get('next_managed_entry', '') or 'unknown'}"
    )
    approval_summary = payload.get("approval_forensics_summary", {}) or {}
    print(
        "Approvals: "
        f"requested={approval_summary.get('approval_requested', 0)} "
        f"denied={approval_summary.get('approval_denied', 0)} "
        f"overrides={approval_summary.get('broker_override_count', 0)} "
        f"status={approval_summary.get('forensic_status', 'unknown')}"
    )
    for row in payload.get("milestones", []):
        print(f"- {row['timestamp_utc']} [{row['source']}] {row['summary']}")
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())

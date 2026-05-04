from __future__ import annotations

import json
import time
from pathlib import Path

from kernel.broker.schema import broker_contract
from kernel.event_fabric.report import query_events


def broker_activity_summary(workspace_dir: Path, *, limit: int = 10) -> dict:
    workspace_dir = Path(workspace_dir).resolve()
    kinds = (
        "broker.exec_request",
        "broker.exec_decision",
        "broker.approval_request",
        "broker.approval_decision",
    )
    counts: dict[str, int] = {}
    request_kind_counts: dict[str, int] = {}
    decision_state_counts: dict[str, int] = {}
    recent: list[dict] = []
    for kind in kinds:
        report = query_events(workspace_dir, kind=kind, limit=limit)
        counts[kind] = int(report.get("matched_events", 0))
        rows = report.get("events", []) or []
        recent.extend(rows)
        for item in rows:
            decision = item.get("decision") or {}
            request_kind = str(decision.get("request_kind", "")).strip()
            if request_kind:
                request_kind_counts[request_kind] = request_kind_counts.get(request_kind, 0) + 1
            state = str(decision.get("state", "")).strip()
            if state:
                decision_state_counts[state] = decision_state_counts.get(state, 0) + 1
    recent.sort(key=lambda item: item.get("timestamp_utc", ""))
    recent_events = recent[-limit:]
    recent_actions = [str(item.get("action", "")) for item in recent_events if item.get("action")]
    high_risk_recent = [
        item
        for item in recent_events
        if str((item.get("decision") or {}).get("request_kind", "")) in {"approval", "override", "operator_control", "install_control"}
    ]
    return {
        "available": True,
        "counts": counts,
        "request_kind_counts": request_kind_counts,
        "decision_state_counts": decision_state_counts,
        "recent_actions": recent_actions,
        "recent_events": recent_events,
        "high_risk_recent": high_risk_recent,
    }


def brokerd_report(workspace_dir: Path, loop_interval_sec: int = 30) -> dict:
    workspace_dir = Path(workspace_dir).resolve()
    return {
        "ok": True,
        "exit_code": 0,
        "mode": "skeleton",
        "workspace": str(workspace_dir),
        "service": {
            "name": "agentos-brokerd.service",
            "exec_start": f"/usr/local/bin/agentos-brokerd --workspace {workspace_dir}",
            "enabled_by_default": False,
        },
        "loop_interval_sec": max(1, int(loop_interval_sec)),
        "managed_paths": [
            {"name": "exec", "status": "planned"},
            {"name": "approval", "status": "planned"},
            {"name": "session_entry", "status": "planned"},
            {"name": "firstrun", "status": "planned"},
            {"name": "override", "status": "planned"},
            {"name": "operator_control", "status": "active"},
            {"name": "install_control", "status": "active"},
        ],
        "contract": broker_contract(),
        "artifacts_ready": True,
        "activity": broker_activity_summary(workspace_dir),
    }


def run_brokerd_status(workspace_dir: Path, *, as_json: bool = False, loop_interval_sec: int = 30) -> int:
    report = brokerd_report(workspace_dir, loop_interval_sec=loop_interval_sec)
    if as_json:
        print(json.dumps(report, ensure_ascii=True))
        return int(report["exit_code"])

    print("AgentOS Broker Control Plane")
    print("============================")
    print(f"Mode: {report['mode']}")
    print(f"Workspace: {report['workspace']}")
    print(f"Service: {report['service']['name']}")
    print(f"Enabled by default: {report['service']['enabled_by_default']}")
    print(f"Loop interval: {report['loop_interval_sec']}s")
    print("Managed paths:")
    for item in report["managed_paths"]:
        print(f"- {item['name']}: {item['status']}")
    activity = report.get("activity", {}) or {}
    print("Recent broker activity:")
    for kind, count in (activity.get("counts", {}) or {}).items():
        print(f"- {kind}: {count}")
    if activity.get("request_kind_counts"):
        print("Request kinds:")
        for kind, count in sorted((activity.get("request_kind_counts", {}) or {}).items()):
            print(f"- {kind}: {count}")
    if activity.get("decision_state_counts"):
        print("Decision states:")
        for kind, count in sorted((activity.get("decision_state_counts", {}) or {}).items()):
            print(f"- {kind}: {count}")
    return int(report["exit_code"])


def run_brokerd_loop(workspace_dir: Path, *, loop_interval_sec: int = 30, run_once: bool = False) -> int:
    report = brokerd_report(workspace_dir, loop_interval_sec=loop_interval_sec)
    Path(report["workspace"]).joinpath("artifacts").mkdir(parents=True, exist_ok=True)
    if run_once:
        return 0

    interval = max(1, int(loop_interval_sec))
    while True:
        time.sleep(interval)

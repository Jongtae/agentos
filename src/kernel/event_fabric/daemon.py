from __future__ import annotations

import json
import time
from pathlib import Path

from kernel.event_fabric.schema import os_event_storage_contract


def eventd_report(workspace_dir: Path, loop_interval_sec: int = 30) -> dict:
    workspace_dir = Path(workspace_dir).resolve()
    storage = os_event_storage_contract(workspace_dir)
    return {
        "ok": True,
        "exit_code": 0,
        "mode": "skeleton",
        "workspace": str(workspace_dir),
        "service": {
            "name": "agentos-eventd.service",
            "exec_start": f"/usr/local/bin/agentos-eventd --workspace {workspace_dir}",
            "enabled_by_default": False,
        },
        "storage": storage,
        "loop_interval_sec": max(1, int(loop_interval_sec)),
        "collectors": [
            {"name": "process_exec_exit", "status": "planned"},
            {"name": "file_access_candidate", "status": "planned"},
            {"name": "network_connect_candidate", "status": "planned"},
            {"name": "journald_systemd_logind", "status": "planned"},
            {"name": "dbus_monitor", "status": "planned"},
        ],
        "artifacts_ready": True,
    }


def run_eventd_status(workspace_dir: Path, as_json: bool = False, loop_interval_sec: int = 30) -> int:
    report = eventd_report(workspace_dir, loop_interval_sec=loop_interval_sec)
    if as_json:
        print(json.dumps(report, ensure_ascii=True))
        return int(report["exit_code"])

    print("AgentOS Event Fabric")
    print("====================")
    print(f"Mode: {report['mode']}")
    print(f"Workspace: {report['workspace']}")
    print(f"Service: {report['service']['name']}")
    print(f"Enabled by default: {report['service']['enabled_by_default']}")
    print(f"Event log: {report['storage']['active_file']}")
    print(f"Archive log: {report['storage']['archive_file']}")
    print(f"Loop interval: {report['loop_interval_sec']}s")
    print("Collectors:")
    for item in report["collectors"]:
        print(f"- {item['name']}: {item['status']}")
    return int(report["exit_code"])


def run_eventd_loop(workspace_dir: Path, loop_interval_sec: int = 30, run_once: bool = False) -> int:
    report = eventd_report(workspace_dir, loop_interval_sec=loop_interval_sec)
    Path(report["storage"]["active_file"]).parent.mkdir(parents=True, exist_ok=True)
    if run_once:
        return 0

    interval = max(1, int(loop_interval_sec))
    while True:
        time.sleep(interval)

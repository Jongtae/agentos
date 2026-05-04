from __future__ import annotations

import json
from pathlib import Path

from io_utils import scrub_payload
from kernel.runtime.trace import (
    approval_anomaly_from_counters,
    approval_counters_from_trace,
    resolve_runtime_trace_path,
)


def trace_status_report(wm, recent_limit: int = 10) -> dict:
    trace_file = resolve_runtime_trace_path(wm.workspace_dir)
    counters = approval_counters_from_trace(trace_file)
    anomaly = approval_anomaly_from_counters(counters)
    recent_events: list[dict] = []

    if trace_file.exists():
        try:
            lines = trace_file.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in lines[-recent_limit:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                recent_events.append(
                    {
                        "timestamp_utc": row.get("timestamp_utc", ""),
                        "event": row.get("event", ""),
                    }
                )
        except Exception:
            pass

    exists = trace_file.exists()
    return {
        "ok": exists,
        "exit_code": 0 if exists else 1,
        "trace_file": str(trace_file),
        "trace_exists": exists,
        "event_count": counters["trace_events"],
        "approval_counters": {
            "requested": counters["requested"],
            "approved": counters["approved"],
            "denied": counters["denied"],
            "blocked": counters["blocked"],
        },
        "approval_anomaly": anomaly,
        "recent_events": recent_events,
    }


def run_trace_status(wm, as_json: bool = False) -> int:
    payload = trace_status_report(wm)
    if as_json:
        print(json.dumps(scrub_payload(payload), ensure_ascii=True))
        return int(payload["exit_code"])

    print("Runtime Trace Status")
    print("====================")
    print(f"Trace file: {payload['trace_file']}")
    print(f"Trace exists: {payload['trace_exists']}")
    print(f"Event count: {payload['event_count']}")
    c = payload["approval_counters"]
    print(
        "Approval counters: "
        f"requested={c['requested']}, approved={c['approved']}, denied={c['denied']}, blocked={c['blocked']}"
    )
    anomaly = payload["approval_anomaly"]
    if anomaly["anomaly_detected"]:
        print(f"Approval anomaly: {anomaly['reason']} ({anomaly['details']})")

    if not payload["trace_exists"]:
        print("No runtime trace file found.")
        return 1

    if payload["recent_events"]:
        print("Recent events:")
        for e in payload["recent_events"]:
            print(f"- {e['timestamp_utc']} {e['event']}")
    return 0

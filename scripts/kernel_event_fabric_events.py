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

from kernel.event_fabric.report import query_events, query_process_lineage


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentOS event fabric event query")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--source", default="")
    parser.add_argument("--kind", default="")
    parser.add_argument("--unit", default="")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--lineage", action="store_true")
    parser.add_argument("--correlation-key", default="")
    parser.add_argument("--correlation-value", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.lineage:
        report = query_process_lineage(
            Path(args.workspace),
            correlation_key=args.correlation_key,
            correlation_value=args.correlation_value,
            limit=args.limit,
        )
    else:
        report = query_events(
            Path(args.workspace),
            source=args.source,
            kind=args.kind,
            unit=args.unit,
            limit=args.limit,
        )
    if args.json:
        print(json.dumps(report, ensure_ascii=True))
        return int(report["exit_code"])

    if args.lineage:
        print("AgentOS Event Fabric Lineage")
        print("============================")
        print(f"Workspace: {report['workspace']}")
        print(f"Event file: {report['event_file']}")
        print(f"Correlation filter: {report['filter']['correlation_key'] or '(none)'}={report['filter']['correlation_value'] or '(none)'}")
        print(f"Matched process events: {report['matched_process_events']}")
        print(f"Returned process events: {report['returned_process_events']}")
        print(f"Root PIDs: {', '.join(str(pid) for pid in report['root_pids']) or '(none)'}")
        for node in report["nodes"]:
            child_text = ", ".join(str(pid) for pid in node["children"]) or "-"
            print(f"- pid={node['pid']} ppid={node['ppid']} comm={node['comm']} children={child_text}")
        return int(report["exit_code"])

    print("AgentOS Event Fabric Events")
    print("===========================")
    print(f"Workspace: {report['workspace']}")
    print(f"Event file: {report['event_file']}")
    print(f"Archive file: {report['archive_file']}")
    print(f"Event file exists: {report['event_file_exists']}")
    print(f"Archive file exists: {report['archive_file_exists']}")
    filter_source = report["filter"].get("source", "") or "(all)"
    filter_kind = report["filter"]["kind"] or "(all)"
    filter_unit = report["filter"].get("unit", "") or "(all)"
    retention = report.get("retention", {})
    remaining = retention.get("active_bytes_remaining", 0)
    print(f"Kind filter: {filter_kind}")
    print(f"Source filter: {filter_source}")
    print(f"Unit filter: {filter_unit}")
    print(f"Total events: {report['total_events']}")
    print(f"Matched events: {report['matched_events']}")
    print(f"Returned events: {report['returned_events']}")
    print(f"Retention: active={retention.get('active_size_bytes', 0)}B archive={retention.get('archive_size_bytes', 0)}B remaining={remaining}B")
    for event in report["events"]:
        print(f"- {event.get('timestamp_utc', '')} {event.get('kind', '')} {event.get('action', '')}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())

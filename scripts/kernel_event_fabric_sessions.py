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

from kernel.event_fabric.report import query_session_timeline


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentOS event fabric session timeline query")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = query_session_timeline(
        Path(args.workspace),
        session_id=args.session_id,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=True))
        return int(report["exit_code"])

    print("AgentOS Session Timeline")
    print("========================")
    print(f"Workspace: {report['workspace']}")
    print(f"Session filter: {report['filter']['session_id'] or '(all)'}")
    print(f"Matched events: {report['matched_events']}")
    print(f"Returned events: {report['returned_events']}")
    ownership = report.get("ownership_summary", {})
    if ownership:
        print(
            "Ownership: "
            f"phase={ownership.get('session_phase', '')} "
            f"origin={ownership.get('session_origin', '')} "
            f"next={ownership.get('next_managed_entry', '')} "
            f"session_id={ownership.get('session_id', '') or 'none'} "
            f"boot_id={ownership.get('boot_id', '') or 'none'}"
        )
    for item in report["timeline"]:
        print(f"- {item['timestamp_utc']} {item['summary']}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())

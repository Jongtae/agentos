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

from kernel.capability_substrate import build_intake_surface_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS unified intake surface report")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--report-dir", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_intake_surface_report(
        args.workspace,
        report_dir=args.report_dir,
        session_id=args.session_id,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print("AgentOS Intake Surface")
        print("======================")
        print(f"Workspace: {payload['workspace']}")
        print(f"Total items: {payload['summary']['total_items']}")
        print(f"Native intake items: {payload['summary']['native_intake_items']}")
        print(f"Escalated intake items: {payload['summary']['escalated_intake_items']}")
    return 0 if payload.get("summary", {}).get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())

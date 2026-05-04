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

from kernel.capability_substrate import build_inbox_routing_contract


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS inbox routing contract")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_inbox_routing_contract(args.workspace, session_id=args.session_id)
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print("AgentOS Inbox Routing Contract")
        print("==============================")
        print(f"Workspace: {payload['workspace']}")
        print(f"Default selected path: {payload['default_selected_path']}")
        for item in payload["paths"]:
            print(f"- {item['path_id']}: {item['source_kind']} ({item['mediation_cost']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

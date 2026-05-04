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

from kernel.capability_substrate import build_capability_proof_surface


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS capability proof surface")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_capability_proof_surface(args.workspace)
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print("AgentOS Capability Proof Surface")
        print("================================")
        print(f"Workspace: {payload['workspace']}")
        print(f"Document native handled: {payload['summary']['document_native_handled']}")
        print(f"Web native handled: {payload['summary']['web_native_handled']}")
        print(f"Web escalated handled: {payload['summary']['web_escalated_handled']}")
        print(f"Intake native items: {payload['summary']['intake_native_items']}")
        print(f"Intake escalated items: {payload['summary']['intake_escalated_items']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

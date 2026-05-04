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

from kernel.capability_substrate import build_document_access_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS native document access evidence")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--path", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_document_access_report(args.workspace, args.path)
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print("AgentOS Document Access")
        print("=======================")
        print(f"Workspace: {payload['workspace']}")
        print(f"Requested path: {payload['requested_path']}")
        print(f"Resolved path: {payload['resolved_path'] or '(unresolved)'}")
        print(f"Document class: {payload['document_class'] or '(unknown)'}")
        print(f"Native handled: {payload['native_handled']}")
        print(f"Unsupported/deferred: {payload['unsupported_or_deferred']}")
        print(f"Mediation cost: {payload['mediation_cost']}")
    return 0 if payload.get("proof", {}).get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())

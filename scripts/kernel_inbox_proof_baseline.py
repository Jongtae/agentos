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

from kernel.capability_substrate import build_inbox_proof_baseline_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS inbox proof baseline")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--maildir", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_inbox_proof_baseline_report(
        args.workspace,
        maildir_path=args.maildir,
        session_id=args.session_id,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print("AgentOS Inbox Proof Baseline")
        print("============================")
        print(f"Workspace: {payload['workspace']}")
        for key, value in payload["summary"].items():
            print(f"{key}: {value}")
    return 0 if payload.get("summary", {}).get("inbox_execution_ready", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())

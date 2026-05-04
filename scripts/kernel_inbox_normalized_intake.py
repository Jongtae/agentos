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

from kernel.capability_substrate import build_inbox_normalized_intake_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS adapter-normalized inbox intake")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--fixture-path", default="messages/inbox-fixture.json")
    parser.add_argument("--maildir", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_inbox_normalized_intake_report(
        args.workspace,
        fixture_path=args.fixture_path,
        maildir_path=args.maildir,
        session_id=args.session_id,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print("AgentOS Inbox Normalized Intake")
        print("===============================")
        print(f"Workspace: {payload['workspace']}")
        print(f"Selected path: {payload['selected_path']}")
        print(f"Path kind: {payload['path_kind']}")
        print(f"Source kind: {payload['source_kind']}")
        print(f"Message count: {payload.get('summary', {}).get('message_count', 0)}")
        print(f"Thread count: {payload.get('summary', {}).get('thread_count', 0)}")
        print(f"Attachment count: {payload.get('summary', {}).get('attachment_count', 0)}")
        print(f"Session correlated: {payload.get('summary', {}).get('session_correlated', False)}")
        print(f"Request correlated: {payload.get('summary', {}).get('request_correlated', False)}")
        print(f"Approval correlated: {payload.get('summary', {}).get('approval_correlated', False)}")
    return 0 if payload.get("proof", {}).get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())

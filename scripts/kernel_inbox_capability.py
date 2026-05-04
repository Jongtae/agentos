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

from kernel.capability_substrate import build_inbox_capability_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS inbox capability evidence")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--fixture-path", default="messages/inbox-fixture.json")
    parser.add_argument("--maildir", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_inbox_capability_report(
        args.workspace,
        fixture_path=args.fixture_path,
        maildir_path=args.maildir,
        session_id=args.session_id,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print("AgentOS Inbox Capability")
        print("========================")
        print(f"Workspace: {payload['workspace']}")
        print(f"Native inbox handled: {payload['native_inbox_handled']}")
        print(f"Inbox adapter required: {payload['inbox_adapter_required']}")
        print(f"Message thread correlated: {payload['message_thread_correlated']}")
        print(f"Attachment visibility ok: {payload['attachment_visibility_ok']}")
        print(f"Inbox execution ready: {payload['inbox_execution_ready']}")
        print(f"Message count: {payload.get('summary', {}).get('message_count', 0)}")
        print(f"Thread count: {payload.get('summary', {}).get('thread_count', 0)}")
        print(f"Message intake count: {payload.get('summary', {}).get('message_intake_count', 0)}")
    return 0 if payload.get("proof", {}).get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())

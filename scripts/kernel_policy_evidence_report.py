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

from kernel.event_fabric.policy_evidence import policy_evidence_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build runtime policy vs OS evidence comparison report")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--trace-file", default="")
    parser.add_argument("--event-file", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = policy_evidence_report(
        Path(args.workspace),
        trace_file=args.trace_file,
        event_file=args.event_file,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
        return int(payload["exit_code"])

    print("AgentOS Policy Evidence Report")
    print("==============================")
    print(f"Workspace: {payload['workspace']}")
    print(f"Runtime trace: {payload['runtime_trace_file']}")
    print(f"OS events: {payload['os_event_file']}")
    enforced = payload.get("enforced_pilot", {}) or {}
    print(
        "Enforced pilot: "
        f"configured={enforced.get('configured_enabled', False)} "
        f"effective={enforced.get('effective_enabled', False)} "
        f"target={enforced.get('policy_target', '') or '(none)'}"
    )
    for item in payload["policy_targets"]:
        print(
            f"- {item['policy_target']}: "
            f"user={item['user_space_count']} "
            f"os={item['os_evidence_count']} "
            f"enforced={item.get('enforced_pilot', {}).get('effective', False)} "
            f"status={item['comparison']['status']} "
            f"delta={item['comparison']['delta']}"
        )
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())

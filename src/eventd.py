from __future__ import annotations

import argparse
from pathlib import Path

from kernel.event_fabric.daemon import run_eventd_loop, run_eventd_status


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentOS OS event fabric daemon")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--run-once", action="store_true")
    parser.add_argument("--loop-interval-sec", type=int, default=30)
    args = parser.parse_args()

    workspace_dir = Path(args.workspace)
    if args.status:
        return run_eventd_status(workspace_dir, as_json=args.json, loop_interval_sec=args.loop_interval_sec)
    return run_eventd_loop(workspace_dir, loop_interval_sec=args.loop_interval_sec, run_once=args.run_once)


if __name__ == "__main__":
    raise SystemExit(main())

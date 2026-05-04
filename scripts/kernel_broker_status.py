#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.broker.daemon import run_brokerd_status


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentOS broker control plane status")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--loop-interval-sec", type=int, default=30)
    args = parser.parse_args()
    return run_brokerd_status(
        Path(args.workspace),
        as_json=bool(args.json),
        loop_interval_sec=args.loop_interval_sec,
    )


if __name__ == "__main__":
    raise SystemExit(main())

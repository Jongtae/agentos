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

from kernel.runtime.governance import governance_report


def main() -> int:
    args = _parse_args()
    workspace = Path(args.workspace).resolve()
    trace_file = Path(args.trace_file).resolve() if args.trace_file else None
    payload = governance_report(workspace_dir=workspace, trace_file=trace_file)
    print(json.dumps(payload, ensure_ascii=True))
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate runtime governance report (policy/SLO).")
    parser.add_argument("--workspace", default="./workspaces/default", help="Workspace directory path")
    parser.add_argument("--trace-file", default="", help="Optional runtime trace file override")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())

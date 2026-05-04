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

from kernel.runtime.remediation_orchestrator import remediation_orchestration_report


def main() -> int:
    args = _parse_args()
    workspace = Path(args.workspace).resolve()
    trace_file = Path(args.trace_file).resolve() if args.trace_file else None
    payload = remediation_orchestration_report(
        workspace_dir=workspace,
        trace_file=trace_file,
        apply=args.apply,
        max_actions=args.max_actions,
    )
    print(json.dumps(payload, ensure_ascii=True))
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run remediation orchestration with rollback-aware summary.")
    parser.add_argument("--workspace", default="./workspaces/default", help="Workspace directory path")
    parser.add_argument("--trace-file", default="", help="Optional runtime trace file override")
    parser.add_argument("--max-actions", type=int, default=10, help="Maximum actions to process")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Plan-only mode (default)")
    mode.add_argument("--apply", action="store_true", help="Execute allowlisted auto-safe actions")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        args.dry_run = True
    return args


if __name__ == "__main__":
    sys.exit(main())

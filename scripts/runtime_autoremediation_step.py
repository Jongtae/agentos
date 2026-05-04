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

from kernel.runtime.autoremediation_scheduler import (  # noqa: E402
    autoremediation_scheduler_report,
    save_autoremediation_state,
)
from kernel.runtime.remediation_orchestrator import remediation_orchestration_report  # noqa: E402


def main() -> int:
    args = _parse_args()
    workspace = Path(args.workspace).resolve()
    trace_file = Path(args.trace_file).resolve() if args.trace_file else None

    scheduler = autoremediation_scheduler_report(
        workspace_dir=workspace,
        trace_file=trace_file,
        now_epoch=args.now_epoch,
        cooldown_sec=args.cooldown_sec,
        max_consecutive_applies=args.max_consecutive_applies,
    )

    decision = scheduler.get("decision", {})
    decision_status = str(decision.get("status", "skip"))
    should_apply = bool(args.apply) and decision_status == "apply"

    orchestration = remediation_orchestration_report(
        workspace_dir=workspace,
        trace_file=trace_file,
        apply=should_apply,
        max_actions=args.max_actions,
    )

    state_update = {
        "written": False,
        "path": "",
        "last_apply_epoch": int(scheduler.get("state", {}).get("last_apply_epoch", 0) or 0),
        "consecutive_applies": int(scheduler.get("state", {}).get("consecutive_applies", 0) or 0),
    }

    if should_apply:
        execution = orchestration.get("execution", {})
        had_error = int(execution.get("errors", 0)) > 0
        if not had_error:
            next_consecutive = int(state_update["consecutive_applies"]) + 1
            state_file = save_autoremediation_state(
                workspace,
                last_apply_epoch=int(scheduler.get("now_epoch", 0) or 0),
                consecutive_applies=next_consecutive,
            )
            state_update = {
                "written": True,
                "path": str(state_file),
                "last_apply_epoch": int(scheduler.get("now_epoch", 0) or 0),
                "consecutive_applies": next_consecutive,
            }

    payload = {
        "ok": True,
        "workspace": str(workspace),
        "requested_mode": "apply" if args.apply else "dry-run",
        "execution_mode": "apply" if should_apply else "dry-run",
        "scheduler": scheduler,
        "orchestration": orchestration,
        "state_update": state_update,
    }
    print(json.dumps(payload, ensure_ascii=True))

    if args.apply and not should_apply:
        return 3
    errors = int(orchestration.get("execution", {}).get("errors", 0) or 0)
    if args.apply and should_apply and errors > 0:
        return 4
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one policy-safe autoremediation step.")
    parser.add_argument("--workspace", default="./workspaces/default", help="Workspace directory path")
    parser.add_argument("--trace-file", default="", help="Optional runtime trace file override")
    parser.add_argument("--cooldown-sec", type=int, default=900, help="Cooldown seconds between apply runs")
    parser.add_argument(
        "--max-consecutive-applies",
        type=int,
        default=3,
        help="Maximum consecutive apply runs before manual hold",
    )
    parser.add_argument("--max-actions", type=int, default=10, help="Maximum actions to process")
    parser.add_argument("--now-epoch", type=int, default=None, help="Optional scheduler timestamp override")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Plan-only mode (default)")
    mode.add_argument("--apply", action="store_true", help="Execute eligible auto-safe actions")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        args.dry_run = True
    return args


if __name__ == "__main__":
    sys.exit(main())

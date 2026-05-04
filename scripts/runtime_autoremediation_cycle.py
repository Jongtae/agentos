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

from kernel.runtime.autoremediation_cadence import (  # noqa: E402
    append_apply_history,
    autoremediation_cadence_report,
    load_autoremediation_cadence_state,
    save_autoremediation_cadence_state,
)
from kernel.runtime.autoremediation_escalation import (  # noqa: E402
    autoremediation_escalation_report,
    load_autoremediation_escalation_state,
    save_autoremediation_escalation_state,
)
from kernel.runtime.autoremediation_scheduler import (  # noqa: E402
    autoremediation_scheduler_report,
    load_autoremediation_state,
    save_autoremediation_state,
)
from kernel.runtime.remediation_orchestrator import remediation_orchestration_report  # noqa: E402


def main() -> int:
    args = _parse_args()
    workspace = Path(args.workspace).resolve()
    trace_file = Path(args.trace_file).resolve() if args.trace_file else None

    scheduler_state = load_autoremediation_state(workspace)
    cadence_state = load_autoremediation_cadence_state(workspace)
    escalation_state = load_autoremediation_escalation_state(workspace)

    scheduler = autoremediation_scheduler_report(
        workspace_dir=workspace,
        trace_file=trace_file,
        now_epoch=args.now_epoch,
        cooldown_sec=args.scheduler_cooldown_sec,
        max_consecutive_applies=args.scheduler_max_consecutive_applies,
    )

    now_epoch = int(scheduler.get("now_epoch", 0) or 0)
    scheduler_decision = scheduler.get("decision", {}) or {}
    scheduler_status = str(scheduler_decision.get("status", "skip"))

    cadence = autoremediation_cadence_report(
        now_epoch=now_epoch,
        scheduler_status=scheduler_status,
        last_apply_epoch=int(cadence_state.get("last_apply_epoch", 0) or 0),
        apply_history_epochs=list(cadence_state.get("apply_history_epochs", [])),
        min_interval_sec=args.cadence_min_interval_sec,
        max_applies_per_hour=args.cadence_max_applies_per_hour,
        max_applies_per_day=args.cadence_max_applies_per_day,
    )

    cadence_status = str(cadence.get("status", "hold"))
    should_apply = bool(args.apply) and scheduler_status == "apply" and cadence_status == "allow"

    orchestration = remediation_orchestration_report(
        workspace_dir=workspace,
        trace_file=trace_file,
        apply=should_apply,
        max_actions=args.max_actions,
    )
    execution = orchestration.get("execution", {}) or {}
    execution_errors = int(execution.get("errors", 0) or 0)

    state_updates = {
        "scheduler": {"written": False, "path": ""},
        "cadence": {"written": False, "path": ""},
        "escalation": {"written": False, "path": ""},
    }

    hold_streak_prev = int(escalation_state.get("hold_streak", 0) or 0)
    failure_streak_prev = int(escalation_state.get("failure_streak", 0) or 0)

    hold_detected = scheduler_status != "apply" or cadence_status == "hold"
    hold_streak = hold_streak_prev + 1 if hold_detected else 0

    failure_streak = failure_streak_prev
    if should_apply and execution_errors > 0:
        failure_streak += 1
    elif should_apply and execution_errors == 0:
        failure_streak = 0

    if should_apply and execution_errors == 0:
        next_scheduler_consecutive = int(scheduler_state.get("consecutive_applies", 0) or 0) + 1
        scheduler_path = save_autoremediation_state(
            workspace,
            last_apply_epoch=now_epoch,
            consecutive_applies=next_scheduler_consecutive,
        )
        state_updates["scheduler"] = {"written": True, "path": str(scheduler_path)}

        updated_history = append_apply_history(
            cadence_state.get("apply_history_epochs", []),
            applied_epoch=now_epoch,
            now_epoch=now_epoch,
            retention_sec=86400,
        )
        cadence_path = save_autoremediation_cadence_state(
            workspace,
            last_apply_epoch=now_epoch,
            apply_history_epochs=updated_history,
        )
        state_updates["cadence"] = {"written": True, "path": str(cadence_path)}

    escalation = autoremediation_escalation_report(
        now_epoch=now_epoch,
        cadence_status=cadence_status,
        cadence_reason=str(cadence.get("reason", "")),
        scheduler_reason=str(scheduler_decision.get("reason", "")),
        execution_errors=execution_errors,
        hold_streak=hold_streak,
        failure_streak=failure_streak,
        last_escalation_epoch=int(escalation_state.get("last_escalation_epoch", 0) or 0),
        min_escalation_interval_sec=args.escalation_min_interval_sec,
    )

    next_last_escalation = int(escalation_state.get("last_escalation_epoch", 0) or 0)
    if bool(escalation.get("should_escalate", False)):
        next_last_escalation = now_epoch
    escalation_path = save_autoremediation_escalation_state(
        workspace,
        last_escalation_epoch=next_last_escalation,
        hold_streak=hold_streak,
        failure_streak=failure_streak,
    )
    state_updates["escalation"] = {"written": True, "path": str(escalation_path)}

    payload = {
        "ok": True,
        "workspace": str(workspace),
        "requested_mode": "apply" if args.apply else "dry-run",
        "execution_mode": "apply" if should_apply else "dry-run",
        "scheduler": scheduler,
        "cadence": cadence,
        "orchestration": orchestration,
        "escalation": escalation,
        "state_updates": state_updates,
    }
    print(json.dumps(payload, ensure_ascii=True))

    if args.apply and not should_apply:
        return 3
    if args.apply and should_apply and execution_errors > 0:
        return 4
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one autoremediation cycle with cadence and escalation controls.")
    parser.add_argument("--workspace", default="./workspaces/default", help="Workspace directory path")
    parser.add_argument("--trace-file", default="", help="Optional runtime trace file override")
    parser.add_argument("--max-actions", type=int, default=10, help="Maximum actions to process")
    parser.add_argument("--now-epoch", type=int, default=None, help="Optional scheduler timestamp override")

    parser.add_argument("--scheduler-cooldown-sec", type=int, default=900)
    parser.add_argument("--scheduler-max-consecutive-applies", type=int, default=3)

    parser.add_argument("--cadence-min-interval-sec", type=int, default=300)
    parser.add_argument("--cadence-max-applies-per-hour", type=int, default=3)
    parser.add_argument("--cadence-max-applies-per-day", type=int, default=12)

    parser.add_argument("--escalation-min-interval-sec", type=int, default=900)

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Plan-only mode (default)")
    mode.add_argument("--apply", action="store_true", help="Execute eligible auto-safe actions")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        args.dry_run = True
    return args


if __name__ == "__main__":
    sys.exit(main())

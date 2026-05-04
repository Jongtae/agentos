#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.runtime.autoremediation_pause_state import (  # noqa: E402
    autoremediation_pause_state_report,
    load_autoremediation_pause_state,
    save_autoremediation_pause_state,
)
from kernel.runtime.autoremediation_override_window import (  # noqa: E402
    autoremediation_override_window_report,
    load_autoremediation_override_window_state,
    save_autoremediation_override_window_state,
)
from kernel.runtime.autoremediation_override_budget import (  # noqa: E402
    append_override_budget_event,
    autoremediation_override_budget_report,
    load_autoremediation_override_budget_state,
    save_autoremediation_override_budget_state,
)
from kernel.runtime.autoremediation_override_audit import (  # noqa: E402
    append_override_audit_event,
    override_audit_report,
)
from kernel.runtime.autoremediation_resume_gate import (  # noqa: E402
    autoremediation_resume_gate_report,
)
from kernel.runtime.autoremediation_forced_resume import (  # noqa: E402
    autoremediation_forced_resume_report,
)
from kernel.runtime.autoremediation_auto_pause import (  # noqa: E402
    autoremediation_auto_pause_report,
)
from kernel.runtime.autoremediation_stage_tuning import (  # noqa: E402
    autoremediation_stage_tuning_report,
)


def main() -> int:
    args = _parse_args()
    workspace_path = Path(args.workspace).resolve()
    workspace = str(workspace_path)
    now_epoch = int(time.time() if args.now_epoch is None else args.now_epoch)
    run_id = str(uuid.uuid4())

    stage_proc, stage_payload = _run_stage(
        workspace=workspace,
        trace_file=args.trace_file,
        runs=args.runs,
        run_interval_sec=args.run_interval_sec,
        now_epoch=args.now_epoch,
        apply=args.apply,
        max_stage_actions=args.max_stage_actions,
        max_hotspots_for_allow=args.max_hotspots_for_allow,
        critical_hotspots_for_handoff=args.critical_hotspots_for_handoff,
        stage_cursor=args.stage_cursor,
        rollback_budget=args.rollback_budget,
        rollback_window_size=args.rollback_window_size,
        rollback_max_failures_per_window=args.rollback_max_failures_per_window,
    )

    stage_governance = stage_payload.get("stage_governance", {}) or {}
    rollback_budget = stage_payload.get("rollback_budget", {}) or {}

    stage_tuning = autoremediation_stage_tuning_report(
        stage_governance=stage_governance,
        rollback_budget=rollback_budget,
        min_window_size=int(args.min_window_size),
        max_window_size=int(args.max_window_size),
    )
    auto_pause = autoremediation_auto_pause_report(
        rollback_budget=rollback_budget,
        stage_governance=stage_governance,
        consecutive_holds=int(args.consecutive_holds),
        hold_pause_threshold=int(args.hold_pause_threshold),
        pause_cooldown_sec=int(args.pause_cooldown_sec),
    )
    pause_state = load_autoremediation_pause_state(workspace_path)
    pause_state_report = autoremediation_pause_state_report(
        now_epoch=now_epoch,
        current_state=pause_state,
        auto_pause=auto_pause,
        resume_requested=False,
    )
    resume_gate = autoremediation_resume_gate_report(
        now_epoch=now_epoch,
        pause_state=(pause_state_report.get("state", {}) or {}),
        rollback_budget=rollback_budget,
        stage_governance=stage_governance,
        min_resume_interval_sec=int(args.min_resume_interval_sec),
        max_resume_attempts=int(args.max_resume_attempts),
    )
    override_window_state = load_autoremediation_override_window_state(workspace_path)
    override_window = autoremediation_override_window_report(
        now_epoch=now_epoch,
        current_state=override_window_state,
        override_requested=bool(args.operator_override_requested),
        override_duration_sec=int(args.override_duration_sec),
    )
    forced_resume = autoremediation_forced_resume_report(
        resume_gate=resume_gate,
        override_window=override_window,
    )
    override_budget_state = load_autoremediation_override_budget_state(workspace_path)
    override_budget = autoremediation_override_budget_report(
        now_epoch=now_epoch,
        state=override_budget_state,
        window_size_sec=int(args.override_budget_window_sec),
        max_overrides_per_window=int(args.max_overrides_per_window),
    )
    forced_resume = _apply_override_budget_to_forced_resume(
        forced_resume=forced_resume,
        override_budget=override_budget,
    )

    forced_status = str(((forced_resume or {}).get("decision", {}) or {}).get("status", "hold"))
    if bool(args.resume_requested) and str((forced_resume.get("decision", {}) or {}).get("status", "")) == "allow":
        pause_state_report = autoremediation_pause_state_report(
            now_epoch=now_epoch,
            current_state=(pause_state_report.get("state", {}) or {}),
            auto_pause={},
            resume_requested=True,
        )
        if bool((forced_resume.get("decision", {}) or {}).get("forced", False)):
            override_budget_state = append_override_budget_event(
                override_budget_state,
                applied_epoch=now_epoch,
            )
            override_budget = autoremediation_override_budget_report(
                now_epoch=now_epoch,
                state=override_budget_state,
                window_size_sec=int(args.override_budget_window_sec),
                max_overrides_per_window=int(args.max_overrides_per_window),
            )
    save_autoremediation_pause_state(
        workspace_path,
        state=(pause_state_report.get("state", {}) or {}),
    )
    save_autoremediation_override_window_state(
        workspace_path,
        state=(override_window.get("state", {}) or {}),
    )
    save_autoremediation_override_budget_state(
        workspace_path,
        state=(override_budget.get("state", {}) or {}),
    )
    if bool(args.resume_requested):
        append_override_audit_event(
            workspace_path,
            event="resume_requested",
            decision_status=forced_status,
            reason=str(((forced_resume or {}).get("decision", {}) or {}).get("reason", "")),
            forced=bool(((forced_resume or {}).get("decision", {}) or {}).get("forced", False)),
        )
    override_audit = override_audit_report(workspace_dir=workspace_path, max_recent=int(args.override_audit_recent))

    payload = {
        "ok": True,
        "run_id": run_id,
        "workspace": workspace,
        "requested_mode": "apply" if args.apply else "dry-run",
        "stage_exit_code": int(stage_proc.returncode),
        "stage": stage_payload,
        "stage_tuning": stage_tuning,
        "auto_pause": auto_pause,
        "pause_state": pause_state_report,
        "resume_gate": resume_gate,
        "override_window": override_window,
        "override_budget": override_budget,
        "forced_resume": forced_resume,
        "override_audit": override_audit,
    }
    print(json.dumps(payload, ensure_ascii=True))

    forced_status = str(((forced_resume or {}).get("decision", {}) or {}).get("status", "hold"))
    if bool(args.resume_requested):
        if forced_status == "block" and str(((forced_resume or {}).get("decision", {}) or {}).get("reason", "")) == "override_budget_exhausted":
            return 9
        if forced_status == "block":
            return 8
        if forced_status != "allow":
            return 7
    if bool((auto_pause or {}).get("should_pause", False)):
        return 6
    if int(stage_proc.returncode) == 5:
        return 5
    if args.apply and int(stage_proc.returncode) != 0:
        return 4
    return 0


def _run_stage(
    *,
    workspace: str,
    trace_file: str,
    runs: int,
    run_interval_sec: int,
    now_epoch: int | None,
    apply: bool,
    max_stage_actions: int,
    max_hotspots_for_allow: int,
    critical_hotspots_for_handoff: int,
    stage_cursor: int,
    rollback_budget: int,
    rollback_window_size: int,
    rollback_max_failures_per_window: int,
) -> tuple[subprocess.CompletedProcess, dict]:
    cmd = [
        "python3",
        "scripts/runtime_autoremediation_stage.py",
        "--workspace",
        workspace,
        "--runs",
        str(int(runs)),
        "--run-interval-sec",
        str(int(run_interval_sec)),
        "--max-stage-actions",
        str(int(max_stage_actions)),
        "--max-hotspots-for-allow",
        str(int(max_hotspots_for_allow)),
        "--critical-hotspots-for-handoff",
        str(int(critical_hotspots_for_handoff)),
        "--stage-cursor",
        str(int(stage_cursor)),
        "--rollback-budget",
        str(int(rollback_budget)),
        "--rollback-window-size",
        str(int(rollback_window_size)),
        "--rollback-max-failures-per-window",
        str(int(rollback_max_failures_per_window)),
    ]
    if trace_file:
        cmd.extend(["--trace-file", trace_file])
    if now_epoch is not None:
        cmd.extend(["--now-epoch", str(now_epoch)])
    if apply:
        cmd.append("--apply")
    else:
        cmd.append("--dry-run")

    proc = subprocess.run(cmd, cwd=str(ROOT_DIR), capture_output=True, text=True, check=False)
    return proc, _safe_parse_json(proc.stdout)


def _safe_parse_json(raw: str) -> dict:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if isinstance(obj, dict):
        return obj
    return {}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run stage orchestrator with adaptive tuning and budget-aware auto-pause.")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--trace-file", default="")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--run-interval-sec", type=int, default=300)
    parser.add_argument("--now-epoch", type=int, default=None)

    parser.add_argument("--max-stage-actions", type=int, default=2)
    parser.add_argument("--max-hotspots-for-allow", type=int, default=1)
    parser.add_argument("--critical-hotspots-for-handoff", type=int, default=3)
    parser.add_argument("--stage-cursor", type=int, default=0)

    parser.add_argument("--rollback-budget", type=int, default=2)
    parser.add_argument("--rollback-window-size", type=int, default=5)
    parser.add_argument("--rollback-max-failures-per-window", type=int, default=1)

    parser.add_argument("--min-window-size", type=int, default=1)
    parser.add_argument("--max-window-size", type=int, default=4)
    parser.add_argument("--consecutive-holds", type=int, default=0)
    parser.add_argument("--hold-pause-threshold", type=int, default=3)
    parser.add_argument("--pause-cooldown-sec", type=int, default=900)
    parser.add_argument("--resume-requested", action="store_true")
    parser.add_argument("--operator-override-requested", action="store_true")
    parser.add_argument("--override-duration-sec", type=int, default=900)
    parser.add_argument("--override-budget-window-sec", type=int, default=86400)
    parser.add_argument("--max-overrides-per-window", type=int, default=3)
    parser.add_argument("--override-audit-recent", type=int, default=5)
    parser.add_argument("--min-resume-interval-sec", type=int, default=300)
    parser.add_argument("--max-resume-attempts", type=int, default=5)

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if int(args.runs) <= 0:
        parser.error("--runs must be greater than 0")
    if not args.dry_run and not args.apply:
        args.dry_run = True
    return args


def _apply_override_budget_to_forced_resume(*, forced_resume: dict, override_budget: dict) -> dict:
    payload = dict(forced_resume or {})
    decision = dict((payload.get("decision", {}) or {}))
    budget_status = str((override_budget.get("status", "")))
    if (
        str(decision.get("status", "")) == "allow"
        and bool(decision.get("forced", False))
        and budget_status == "block"
    ):
        decision["status"] = "block"
        decision["reason"] = "override_budget_exhausted"
        decision["operator_action"] = "manual_handoff"
        decision["forced"] = False
    payload["decision"] = decision
    return payload


if __name__ == "__main__":
    raise SystemExit(main())

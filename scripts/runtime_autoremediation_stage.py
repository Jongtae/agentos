#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.runtime.autoremediation_rollback_budget import (  # noqa: E402
    autoremediation_rollback_budget_report,
)
from kernel.runtime.autoremediation_stage_governance import (  # noqa: E402
    autoremediation_stage_governance_report,
)


def main() -> int:
    args = _parse_args()
    workspace = str(Path(args.workspace).resolve())
    run_id = str(uuid.uuid4())

    batch_proc, batch_payload = _run_batch(
        workspace=workspace,
        trace_file=args.trace_file,
        runs=args.runs,
        run_interval_sec=args.run_interval_sec,
        now_epoch=args.now_epoch,
        apply=args.apply,
    )

    stage_governance = autoremediation_stage_governance_report(
        batch_payload=batch_payload,
        max_stage_actions=int(args.max_stage_actions),
        max_hotspots_for_allow=int(args.max_hotspots_for_allow),
        critical_hotspots_for_handoff=int(args.critical_hotspots_for_handoff),
        stage_cursor=int(args.stage_cursor),
    )
    run_results = list(((batch_payload.get("campaign", {}) or {}).get("run_results", []) or []))
    rollback_budget = autoremediation_rollback_budget_report(
        run_results=run_results,
        rollback_budget=int(args.rollback_budget),
        window_size=int(args.rollback_window_size),
        max_failures_per_window=int(args.rollback_max_failures_per_window),
    )

    payload = {
        "ok": True,
        "run_id": run_id,
        "workspace": workspace,
        "requested_mode": "apply" if args.apply else "dry-run",
        "batch_exit_code": int(batch_proc.returncode),
        "batch": batch_payload,
        "stage_governance": stage_governance,
        "rollback_budget": rollback_budget,
    }
    print(json.dumps(payload, ensure_ascii=True))

    stage_decision = str((stage_governance or {}).get("decision", "hold"))
    budget_status = str((rollback_budget or {}).get("status", "allow"))
    if stage_decision == "handoff" or budget_status == "handoff":
        return 5
    if args.apply and int(batch_proc.returncode) != 0:
        return 4
    return 0


def _run_batch(
    *,
    workspace: str,
    trace_file: str,
    runs: int,
    run_interval_sec: int,
    now_epoch: int | None,
    apply: bool,
) -> tuple[subprocess.CompletedProcess, dict]:
    cmd = [
        "python3",
        "scripts/runtime_autoremediation_batch.py",
        "--workspace",
        workspace,
        "--runs",
        str(int(runs)),
        "--run-interval-sec",
        str(int(run_interval_sec)),
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
    parser = argparse.ArgumentParser(description="Run staged autoremediation governance with rollback budget checks.")
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

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if int(args.runs) <= 0:
        parser.error("--runs must be greater than 0")
    if not args.dry_run and not args.apply:
        args.dry_run = True
    return args


if __name__ == "__main__":
    raise SystemExit(main())

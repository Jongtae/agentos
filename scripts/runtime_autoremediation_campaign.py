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

from kernel.runtime.autoremediation_campaign_governance import (  # noqa: E402
    autoremediation_campaign_governance_report,
)
from kernel.runtime.autoremediation_campaign_review import (  # noqa: E402
    build_campaign_review_payload,
)


def main() -> int:
    args = _parse_args()
    workspace = str(Path(args.workspace).resolve())
    run_id = str(uuid.uuid4())

    run_results: list[dict] = []
    run_failures = 0

    for run_index in range(1, int(args.runs) + 1):
        run_epoch = _run_epoch(args.now_epoch, run_index, args.run_interval_sec)
        proc, payload = _run_supervisor(
            workspace=workspace,
            trace_file=args.trace_file,
            apply=args.apply,
            now_epoch=run_epoch,
        )
        run_result = {
            "run_index": run_index,
            "exit_code": int(proc.returncode),
            "decision": str(((payload.get("governance", {}) or {}).get("decision", "hold"))),
            "reason": str(((payload.get("governance", {}) or {}).get("reason", "unknown"))),
            "governance": payload.get("governance", {}),
            "handoff": payload.get("handoff", {}),
            "cycle_exit_code": int(payload.get("cycle_exit_code", proc.returncode) or 0),
        }
        run_results.append(run_result)
        if int(proc.returncode) != 0:
            run_failures += 1

    campaign_governance = autoremediation_campaign_governance_report(
        run_results=run_results,
        max_handoff_rate=float(args.max_handoff_rate),
        max_error_runs=int(args.max_error_runs),
    )
    campaign_review = build_campaign_review_payload(
        workspace=workspace,
        campaign_governance=campaign_governance,
        run_results=run_results,
        run_id=run_id,
    )

    payload = {
        "ok": True,
        "run_id": run_id,
        "workspace": workspace,
        "requested_mode": "apply" if args.apply else "dry-run",
        "runs_requested": int(args.runs),
        "run_results": run_results,
        "campaign_governance": campaign_governance,
        "campaign_review": campaign_review,
    }
    print(json.dumps(payload, ensure_ascii=True))

    decision = str((campaign_governance or {}).get("decision", "hold"))
    if decision == "handoff":
        return 5
    if args.apply and run_failures > 0:
        return 4
    return 0


def _run_supervisor(*, workspace: str, trace_file: str, apply: bool, now_epoch: int | None) -> tuple[subprocess.CompletedProcess, dict]:
    cmd = [
        "python3",
        "scripts/runtime_autoremediation_supervisor.py",
        "--workspace",
        workspace,
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
    payload = _safe_parse_json(proc.stdout)
    return proc, payload


def _safe_parse_json(raw: str) -> dict:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if isinstance(value, dict):
        return value
    return {}


def _run_epoch(base_epoch: int | None, run_index: int, run_interval_sec: int) -> int | None:
    if base_epoch is None:
        return None
    return int(base_epoch) + max(0, run_index - 1) * max(0, int(run_interval_sec))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run multi-run autoremediation campaign with governance/review summary.")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--trace-file", default="")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--run-interval-sec", type=int, default=300)
    parser.add_argument("--now-epoch", type=int, default=None)
    parser.add_argument("--max-handoff-rate", type=float, default=0.30)
    parser.add_argument("--max-error-runs", type=int, default=1)
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

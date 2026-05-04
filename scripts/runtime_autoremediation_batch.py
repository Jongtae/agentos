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

from kernel.runtime.autoremediation_batch_governance import (  # noqa: E402
    autoremediation_batch_governance_report,
)
from kernel.runtime.autoremediation_batch_review import build_batch_review_payload  # noqa: E402


def main() -> int:
    args = _parse_args()
    workspace = str(Path(args.workspace).resolve())
    run_id = str(uuid.uuid4())

    campaign_proc, campaign_payload = _run_campaign(
        workspace=workspace,
        trace_file=args.trace_file,
        runs=args.runs,
        run_interval_sec=args.run_interval_sec,
        now_epoch=args.now_epoch,
        apply=args.apply,
        max_handoff_rate=args.campaign_max_handoff_rate,
        max_error_runs=args.campaign_max_error_runs,
    )

    batch_governance = autoremediation_batch_governance_report(
        campaign_payload=campaign_payload,
        max_handoff_rate=float(args.batch_max_handoff_rate),
        max_error_runs=int(args.batch_max_error_runs),
        max_blocked_runs=int(args.batch_max_blocked_runs),
    )
    batch_review = build_batch_review_payload(
        workspace=workspace,
        batch_governance=batch_governance,
        campaign_payload=campaign_payload,
        run_id=run_id,
    )

    payload = {
        "ok": True,
        "run_id": run_id,
        "workspace": workspace,
        "requested_mode": "apply" if args.apply else "dry-run",
        "campaign_exit_code": int(campaign_proc.returncode),
        "campaign": campaign_payload,
        "batch_governance": batch_governance,
        "batch_review": batch_review,
    }
    print(json.dumps(payload, ensure_ascii=True))

    decision = str((batch_governance or {}).get("decision", "hold"))
    if decision == "handoff":
        return 5
    if args.apply and int(campaign_proc.returncode) != 0:
        return 4
    return 0


def _run_campaign(
    *,
    workspace: str,
    trace_file: str,
    runs: int,
    run_interval_sec: int,
    now_epoch: int | None,
    apply: bool,
    max_handoff_rate: float,
    max_error_runs: int,
) -> tuple[subprocess.CompletedProcess, dict]:
    cmd = [
        "python3",
        "scripts/runtime_autoremediation_campaign.py",
        "--workspace",
        workspace,
        "--runs",
        str(int(runs)),
        "--run-interval-sec",
        str(int(run_interval_sec)),
        "--max-handoff-rate",
        str(float(max_handoff_rate)),
        "--max-error-runs",
        str(int(max_error_runs)),
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
    parser = argparse.ArgumentParser(description="Run batched autoremediation governance/review over campaign outcomes.")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--trace-file", default="")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--run-interval-sec", type=int, default=300)
    parser.add_argument("--now-epoch", type=int, default=None)

    parser.add_argument("--campaign-max-handoff-rate", type=float, default=0.30)
    parser.add_argument("--campaign-max-error-runs", type=int, default=1)
    parser.add_argument("--batch-max-handoff-rate", type=float, default=0.30)
    parser.add_argument("--batch-max-error-runs", type=int, default=1)
    parser.add_argument("--batch-max-blocked-runs", type=int, default=1)

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

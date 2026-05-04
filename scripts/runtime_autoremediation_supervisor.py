#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.runtime.autoremediation_handoff import build_operator_handoff_payload  # noqa: E402
from kernel.runtime.autoremediation_loop_governance import autoremediation_loop_governance_report  # noqa: E402


def main() -> int:
    args = _parse_args()

    cmd = [
        "python3",
        "scripts/runtime_autoremediation_cycle.py",
        "--workspace",
        args.workspace,
    ]
    if args.trace_file:
        cmd.extend(["--trace-file", args.trace_file])
    if args.now_epoch is not None:
        cmd.extend(["--now-epoch", str(args.now_epoch)])
    if args.apply:
        cmd.append("--apply")
    else:
        cmd.append("--dry-run")

    import subprocess

    proc = subprocess.run(cmd, cwd=str(ROOT_DIR), capture_output=True, text=True, check=False)
    cycle_payload = {}
    if proc.stdout.strip():
        cycle_payload = json.loads(proc.stdout.strip())

    governance = autoremediation_loop_governance_report(cycle_payload=cycle_payload)
    run_id = str(uuid.uuid4())
    handoff = build_operator_handoff_payload(
        workspace=str(Path(args.workspace).resolve()),
        governance=governance,
        cycle_payload=cycle_payload,
        run_id=run_id,
    )

    payload = {
        "ok": True,
        "run_id": run_id,
        "requested_mode": "apply" if args.apply else "dry-run",
        "cycle_exit_code": int(proc.returncode),
        "cycle": cycle_payload,
        "governance": governance,
        "handoff": handoff,
    }
    print(json.dumps(payload, ensure_ascii=True))

    decision = str((governance or {}).get("decision", "hold"))
    if decision == "handoff":
        return 5
    if args.apply and int(proc.returncode) != 0:
        return int(proc.returncode)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run autoremediation supervisor cycle with governance and handoff.")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--trace-file", default="")
    parser.add_argument("--now-epoch", type=int, default=None)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        args.dry_run = True
    return args


if __name__ == "__main__":
    raise SystemExit(main())

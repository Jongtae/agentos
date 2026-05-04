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

from kernel.runtime.retention import apply_trace_retention, is_path_within_dir, plan_trace_retention


def main() -> int:
    args = _parse_args()

    workspace = Path(args.workspace).resolve()
    artifacts_root = workspace / "artifacts"
    trace_file = (
        Path(args.trace_file).resolve()
        if args.trace_file
        else (artifacts_root / "runtime_trace.jsonl").resolve()
    )

    if not is_path_within_dir(trace_file, artifacts_root):
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "trace_file_must_be_within_workspace_artifacts",
                    "workspace": str(workspace),
                    "artifacts_root": str(artifacts_root),
                    "trace_file": str(trace_file),
                },
                ensure_ascii=True,
            )
        )
        return 1

    actions = plan_trace_retention(
        trace_file=trace_file,
        retention_days=args.retention_days,
        keep_archives=args.keep_archives,
    )
    summary = apply_trace_retention(actions, apply=args.apply)

    payload = {
        "ok": True,
        "workspace": str(workspace),
        "artifacts_root": str(artifacts_root),
        "trace_file": str(trace_file),
        "retention_days": args.retention_days,
        "keep_archives": args.keep_archives,
        "mode": "apply" if args.apply else "dry-run",
        "summary": summary,
        "actions": [
            {
                "path": item.path,
                "reason": item.reason,
                "age_days": round(item.age_days, 4),
                "size_bytes": item.size_bytes,
            }
            for item in actions
        ],
    }
    print(json.dumps(payload, ensure_ascii=True))
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply retention policy to runtime trace archives.")
    parser.add_argument("--workspace", default="./workspaces/default", help="Workspace directory path")
    parser.add_argument("--trace-file", default="", help="Optional runtime trace file override")
    parser.add_argument("--retention-days", type=int, default=7, help="Delete archives older than this threshold")
    parser.add_argument("--keep-archives", type=int, default=1, help="Always keep newest N archives")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview mode (default)")
    mode.add_argument("--apply", action="store_true", help="Apply deletions")
    args = parser.parse_args()
    if args.retention_days < 0:
        parser.error("--retention-days must be >= 0")
    if args.keep_archives < 0:
        parser.error("--keep-archives must be >= 0")
    if not args.dry_run and not args.apply:
        args.dry_run = True
    return args


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
LEDGER_PATH = ROOT_DIR / "docs" / "issue-branch-ledger.jsonl"
DEFAULT_REPO = "Jongtae/agentos"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "work-item"


def phase_issue_title(stage: int, phase: int, title: str) -> str:
    return f"EPIC: Stage {stage} / Phase {phase} {title}"


def task_issue_title(task_id: str, title: str) -> str:
    return f"[{task_id}] {title}"


def phase_branch_name(stage: int, phase: int, title: str) -> str:
    return f"codex/stage{stage}-phase{phase}-{slugify(title)}"


def task_branch_name(task_id: str, title: str) -> str:
    return f"codex/{task_id.lower()}-{slugify(title)}"


def run(cmd: list[str], *, cwd: Path = ROOT_DIR, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), check=True, text=True, capture_output=capture)


def git_is_dirty(cwd: Path = ROOT_DIR) -> bool:
    result = run(["git", "status", "--porcelain"], cwd=cwd)
    return bool(result.stdout.strip())


def append_ledger(entry: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=True) + "\n")


def parse_issue_number(issue_url: str) -> int:
    match = re.search(r"/issues/(\d+)$", issue_url.strip())
    if not match:
        raise ValueError(f"Could not parse issue number from {issue_url!r}")
    return int(match.group(1))


def do_start(args: argparse.Namespace) -> int:
    if git_is_dirty() and not args.allow_dirty:
        raise SystemExit("Refusing to start work item on a dirty worktree. Commit or stash first, or pass --allow-dirty.")

    if args.kind == "phase":
        if args.stage is None or args.phase is None:
            raise SystemExit("--stage and --phase are required for phase work items")
        issue_title = phase_issue_title(args.stage, args.phase, args.title)
        branch = phase_branch_name(args.stage, args.phase, args.title)
        task_id = None
    else:
        if not args.task_id or args.phase is None:
            raise SystemExit("--task-id and --phase are required for task work items")
        issue_title = task_issue_title(args.task_id, args.title)
        branch = task_branch_name(args.task_id, args.title)
        task_id = args.task_id

    issue_url = "dry-run://issue/0"
    issue_number = 0

    if not args.dry_run:
        body_lines = [
            "Tracked through the AgentOS issue/branch lifecycle policy.",
            "",
            f"- Kind: `{args.kind}`",
            f"- Stage: `{args.stage}`" if args.stage is not None else None,
            f"- Phase: `{args.phase}`" if args.phase is not None else None,
            f"- Task ID: `{task_id}`" if task_id else None,
            f"- Planned branch: `{branch}`",
        ]
        body = "\n".join(line for line in body_lines if line is not None)
        result = run(["gh", "issue", "create", "-R", args.repo, "--title", issue_title, "--body", body], cwd=ROOT_DIR)
        issue_url = result.stdout.strip().splitlines()[-1]
        issue_number = parse_issue_number(issue_url)
        checkout_cmd = ["git", "checkout", "-b", branch]
        if args.base_branch:
            checkout_cmd.append(args.base_branch)
        run(checkout_cmd, cwd=ROOT_DIR, capture=False)

    entry = {
        "timestamp_utc": utc_now(),
        "action": "start",
        "kind": args.kind,
        "stage": args.stage,
        "phase": args.phase,
        "task_id": task_id,
        "title": args.title,
        "issue_title": issue_title,
        "issue_number": issue_number,
        "issue_url": issue_url,
        "branch": branch,
        "base_branch": args.base_branch,
        "repo": args.repo,
        "dry_run": args.dry_run,
    }
    append_ledger(entry)
    print(json.dumps(entry, ensure_ascii=True))
    return 0


def do_close(args: argparse.Namespace) -> int:
    if git_is_dirty() and not args.allow_dirty:
        raise SystemExit("Refusing to close work item on a dirty worktree. Commit or stash first, or pass --allow-dirty.")

    if not args.commit:
        raise SystemExit("--commit is required for close")

    if not args.dry_run:
        current_branch = run(["git", "branch", "--show-current"], cwd=ROOT_DIR).stdout.strip()
        if current_branch != args.branch:
            raise SystemExit(f"Current branch is {current_branch!r}, expected {args.branch!r} before merge.")
        run(["git", "checkout", args.merge_target], cwd=ROOT_DIR, capture=False)
        run(["git", "merge", "--no-ff", args.branch, "-m", f"Merge {args.branch} into {args.merge_target}"], cwd=ROOT_DIR, capture=False)
        body_lines = [
            "Implemented and verified.",
            "",
            f"- Branch: `{args.branch}`",
            f"- Merge target: `{args.merge_target}`",
            f"- Commit: `{args.commit}`",
        ]
        if args.pr:
            body_lines.insert(3, f"- PR: `#{args.pr}`")
        body = "\n".join(body_lines)
        run(["gh", "issue", "close", str(args.issue), "-R", args.repo, "--comment", body], cwd=ROOT_DIR, capture=False)
        if args.delete_branch:
            run(["git", "branch", "-d", args.branch], cwd=ROOT_DIR, capture=False)

    entry = {
        "timestamp_utc": utc_now(),
        "action": "close",
        "issue_number": args.issue,
        "branch": args.branch,
        "merge_target": args.merge_target,
        "commit": args.commit,
        "pr": args.pr,
        "repo": args.repo,
        "delete_branch": args.delete_branch,
        "dry_run": args.dry_run,
    }
    append_ledger(entry)
    print(json.dumps(entry, ensure_ascii=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage AgentOS issue/branch lifecycle records and workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Create an issue, create its branch, and record the start event")
    start.add_argument("--kind", choices=["phase", "task"], required=True)
    start.add_argument("--stage", type=int)
    start.add_argument("--phase", type=int)
    start.add_argument("--task-id")
    start.add_argument("--title", required=True)
    start.add_argument("--repo", default=DEFAULT_REPO)
    start.add_argument("--base-branch")
    start.add_argument("--dry-run", action="store_true")
    start.add_argument("--allow-dirty", action="store_true")
    start.set_defaults(func=do_start)

    close = subparsers.add_parser("close", help="Merge a completed branch, close the issue, and record the closeout")
    close.add_argument("--issue", type=int, required=True)
    close.add_argument("--branch", required=True)
    close.add_argument("--merge-target", required=True)
    close.add_argument("--commit", required=True)
    close.add_argument("--pr", type=int)
    close.add_argument("--repo", default=DEFAULT_REPO)
    close.add_argument("--delete-branch", action="store_true")
    close.add_argument("--dry-run", action="store_true")
    close.add_argument("--allow-dirty", action="store_true")
    close.set_defaults(func=do_close)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

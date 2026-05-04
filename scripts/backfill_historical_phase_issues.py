#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.work_item_lifecycle import (
    DEFAULT_REPO,
    append_ledger,
    parse_issue_number,
    phase_branch_name,
    phase_issue_title,
    utc_now,
)


BACKFILL_TARGETS = [
    {"stage": 9, "phase": 118, "title": "Evaluator Cohort Pack"},
    {"stage": 9, "phase": 119, "title": "Feedback Triage and Promotion Buckets"},
    {"stage": 9, "phase": 120, "title": "Direct-Boot UX Burn-Down"},
    {"stage": 9, "phase": 121, "title": "Limited Preview Readiness Scoreboard"},
    {"stage": 10, "phase": 122, "title": "Broader Preview Candidate Pack"},
    {"stage": 10, "phase": 123, "title": "Stage 10 Closeout / Broader Preview Gate"},
    {"stage": 11, "phase": 124, "title": "Recovery Clarity Fix Loop"},
    {"stage": 11, "phase": 125, "title": "Direct-Boot Messaging Consistency"},
    {"stage": 11, "phase": 126, "title": "Limited Preview Iteration Ledger"},
    {"stage": 12, "phase": 127, "title": "Broader Preview Readiness Scoreboard"},
    {"stage": 12, "phase": 128, "title": "Broader Preview Launch Pack"},
    {"stage": 12, "phase": 129, "title": "Stage 12 Closeout / Broader Preview Decision"},
    {"stage": 13, "phase": 130, "title": "Recovery Rejoin Summary"},
    {"stage": 13, "phase": 131, "title": "Recovery Copy Consistency"},
    {"stage": 13, "phase": 132, "title": "Recovery Watch Re-evaluation"},
    {"stage": 14, "phase": 133, "title": "Preview Posture Re-score"},
    {"stage": 14, "phase": 134, "title": "Updated Broader Preview Launch Pack"},
    {"stage": 14, "phase": 135, "title": "Stage 14 Closeout / Updated Broader Preview Decision"},
    {"stage": 15, "phase": 136, "title": "Broader Preview Cohort Operations"},
    {"stage": 15, "phase": 137, "title": "Broader Preview Issue Ledger"},
    {"stage": 15, "phase": 138, "title": "Broader Preview Health Summary"},
    {"stage": 16, "phase": 139, "title": "Broader Preview Continuation Pack"},
    {"stage": 16, "phase": 140, "title": "Public Preview Position Update"},
    {"stage": 16, "phase": 141, "title": "Stage 16 Closeout / Broader Preview Operating Decision"},
    {"stage": 17, "phase": 142, "title": "Broader Preview Signal Snapshot"},
    {"stage": 17, "phase": 143, "title": "Broader Preview Drift Ledger"},
    {"stage": 17, "phase": 144, "title": "Broader Preview Weekly Summary"},
    {"stage": 18, "phase": 145, "title": "Public Preview Escalation Pack"},
    {"stage": 18, "phase": 146, "title": "Public Preview Announcement Readiness"},
    {"stage": 18, "phase": 147, "title": "Stage 18 Closeout / Public Preview Escalation Decision"},
    {"stage": 19, "phase": 148, "title": "Public Preview Decision Ledger"},
    {"stage": 19, "phase": 149, "title": "Public Preview Messaging Review"},
    {"stage": 19, "phase": 150, "title": "Public Preview Operating Brief"},
    {"stage": 20, "phase": 151, "title": "Public Preview Decision Pack"},
    {"stage": 20, "phase": 152, "title": "Public Preview Launch Readiness Review"},
    {"stage": 20, "phase": 153, "title": "Stage 20 Closeout / Public Preview Go/No-Go"},
    {"stage": 21, "phase": 154, "title": "Base Image and Remaster Contract"},
    {"stage": 21, "phase": 155, "title": "ISO Remaster Pipeline"},
    {"stage": 21, "phase": 156, "title": "Default Path Without Ubuntu Installer"},
    {"stage": 22, "phase": 157, "title": "Welcome Shell App"},
    {"stage": 22, "phase": 158, "title": "Modern Network Step"},
    {"stage": 22, "phase": 159, "title": "Welcome-to-Setup Handoff"},
    {"stage": 23, "phase": 160, "title": "Install-Later Productization"},
    {"stage": 23, "phase": 161, "title": "Writable State Partition Foundation"},
    {"stage": 23, "phase": 162, "title": "Installed Appliance Boot Identity"},
    {"stage": 24, "phase": 163, "title": "Slot Layout Realization"},
    {"stage": 24, "phase": 164, "title": "Image Update Prototype"},
    {"stage": 24, "phase": 165, "title": "Rollback and Recovery Slot Logic"},
    {"stage": 25, "phase": 166, "title": "Boot Flow Proof Artifact"},
    {"stage": 25, "phase": 167, "title": "Boot Target Activation Wiring"},
    {"stage": 25, "phase": 168, "title": "VM First-Screen Evidence Export"},
    {"stage": 26, "phase": 169, "title": "Next-Boot Target Integration"},
    {"stage": 26, "phase": 170, "title": "Installed Slot Switch Evidence"},
    {"stage": 26, "phase": 171, "title": "Stage 26 Closeout / Boot Target Baseline"},
]


def run(cmd: list[str], *, cwd: Path = ROOT_DIR) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), check=True, text=True, capture_output=True)


def load_existing_phase_issues(repo: str) -> dict[int, dict]:
    result = run(["gh", "issue", "list", "-R", repo, "--state", "all", "--limit", "300", "--json", "number,title,state,url"])
    issues = json.loads(result.stdout)
    existing: dict[int, dict] = {}
    for issue in issues:
        match = re.match(r"EPIC: Stage (\d+) / Phase (\d+) (.+)", issue["title"])
        if not match:
            continue
        existing[int(match.group(2))] = {
            "stage": int(match.group(1)),
            "title": match.group(3),
            "number": issue["number"],
            "state": issue["state"],
            "url": issue["url"],
        }
    return existing


def create_issue(repo: str, issue_title: str, body: str) -> tuple[int, str]:
    result = run(["gh", "issue", "create", "-R", repo, "--title", issue_title, "--body", body])
    issue_url = result.stdout.strip().splitlines()[-1]
    return parse_issue_number(issue_url), issue_url


def close_issue(repo: str, issue_number: int, body: str) -> None:
    subprocess.run(
        ["gh", "issue", "close", str(issue_number), "-R", repo, "--comment", body],
        cwd=str(ROOT_DIR),
        check=True,
        text=True,
    )


def start_entry(repo: str, target: dict, issue_number: int, issue_url: str) -> dict:
    return {
        "timestamp_utc": utc_now(),
        "action": "start",
        "kind": "phase",
        "stage": target["stage"],
        "phase": target["phase"],
        "task_id": None,
        "title": target["title"],
        "issue_title": phase_issue_title(target["stage"], target["phase"], target["title"]),
        "issue_number": issue_number,
        "issue_url": issue_url,
        "branch": None,
        "planned_branch": phase_branch_name(target["stage"], target["phase"], target["title"]),
        "base_branch": None,
        "repo": repo,
        "dry_run": False,
        "historical_backfill": True,
    }


def close_entry(repo: str, target: dict, issue_number: int, commit: str) -> dict:
    return {
        "timestamp_utc": utc_now(),
        "action": "close",
        "issue_number": issue_number,
        "branch": None,
        "planned_branch": phase_branch_name(target["stage"], target["phase"], target["title"]),
        "merge_target": None,
        "commit": commit,
        "pr": None,
        "repo": repo,
        "delete_branch": False,
        "dry_run": False,
        "historical_backfill": True,
    }


def build_create_body(target: dict, planned_branch: str) -> str:
    return "\n".join(
        [
            "Historical backfill for a phase that is already complete in the repository.",
            "",
            f"- Stage: `{target['stage']}`",
            f"- Phase: `{target['phase']}`",
            f"- Historical planned branch: `{planned_branch}`",
            "- This issue is being created after implementation to restore issue continuity.",
        ]
    )


def build_close_body(target: dict, commit: str) -> str:
    return "\n".join(
        [
            "Historical backfill closeout.",
            "",
            f"- Phase: `{target['phase']}`",
            f"- Backfill provenance commit: `{commit}`",
            "- This phase was already complete in the repository before the issue-first policy was fully enforced for this execution window.",
        ]
    )


def do_backfill(args: argparse.Namespace) -> int:
    existing = load_existing_phase_issues(args.repo)
    created: list[dict] = []
    skipped: list[dict] = []

    for target in BACKFILL_TARGETS:
        if target["phase"] in existing:
            skipped.append({"phase": target["phase"], "number": existing[target["phase"]]["number"]})
            continue

        issue_title = phase_issue_title(target["stage"], target["phase"], target["title"])
        planned_branch = phase_branch_name(target["stage"], target["phase"], target["title"])
        if args.dry_run:
            created.append({"phase": target["phase"], "issue_title": issue_title, "planned_branch": planned_branch, "dry_run": True})
            continue

        issue_number, issue_url = create_issue(args.repo, issue_title, build_create_body(target, planned_branch))
        append_ledger(start_entry(args.repo, target, issue_number, issue_url))
        close_issue(args.repo, issue_number, build_close_body(target, args.commit))
        append_ledger(close_entry(args.repo, target, issue_number, args.commit))
        created.append({"phase": target["phase"], "issue_number": issue_number, "issue_url": issue_url})

    print(
        json.dumps(
            {
                "created": created,
                "skipped_existing": skipped,
                "target_count": len(BACKFILL_TARGETS),
                "created_count": len(created),
                "skipped_count": len(skipped),
            },
            ensure_ascii=True,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill historical phase EPIC issues and ledger records")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--commit", help="Backfill provenance commit to cite in close comments")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.dry_run and not args.commit:
        parser.error("--commit is required unless --dry-run is used")
    return do_backfill(args)


if __name__ == "__main__":
    sys.exit(main())

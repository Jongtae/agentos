#!/usr/bin/env python3
"""Read-only GitHub PR gate snapshot. Never merges or changes repository policy.

Exit 0 means the observation was produced, NOT that merging is approved.
Required-check discovery and repo metadata failures remain explicit unknowns.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
from typing import Any


def gh_json(args: list[str]) -> tuple[Any, int]:
    """Use the owner's existing CLI auth; do not read/print credential files."""
    try:
        result = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=30, check=False
        )
        return json.loads(result.stdout), result.returncode
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None, -1


def collect(repo: str, number: int) -> dict[str, Any]:
    fields = "number,state,isDraft,headRefOid,mergeable,mergeStateStatus,reviewDecision,mergedAt,url"
    pr, code = gh_json(["pr", "view", str(number), "--repo", repo, "--json", fields])
    if code != 0 or not isinstance(pr, dict):
        raise ValueError("PR metadata unavailable; check repository access and gh authentication locally.")
    checks, check_code = gh_json([
        "pr", "checks", str(number), "--repo", repo, "--required",
        "--json", "name,state,bucket,link"
    ])
    metadata, meta_code = gh_json(["api", f"repos/{repo}"])
    # Re-read the head: do not combine checks collected for a moving commit.
    after, after_code = gh_json(["pr", "view", str(number), "--repo", repo, "--json", "headRefOid"])
    stable = after_code == 0 and isinstance(after, dict) and after.get("headRefOid") == pr.get("headRefOid")
    return {
        "pr": pr,
        "required_checks": checks if isinstance(checks, list) else [],
        "required_checks_known": check_code in (0, 1, 8) and isinstance(checks, list),
        "head_stable": stable,
        "allow_auto_merge": metadata.get("allow_auto_merge")
            if meta_code == 0 and isinstance(metadata, dict) else None,
    }


def classify(snapshot: dict[str, Any], expected_head: str | None = None) -> dict[str, Any]:
    pr = snapshot.get("pr")
    if not isinstance(pr, dict) or not pr.get("headRefOid"):
        raise ValueError("Snapshot requires PR metadata and headRefOid.")
    checks = snapshot.get("required_checks", [])
    if not isinstance(checks, list) or any(not isinstance(c, dict) for c in checks):
        raise ValueError("required_checks must be a list of objects.")
    state = str(pr.get("state", "")).upper()
    merge_state = str(pr.get("mergeStateStatus", "UNKNOWN")).upper()
    review = str(pr.get("reviewDecision") or "UNKNOWN").upper()
    buckets = [str(c.get("bucket", "unknown")).lower() for c in checks]
    result = {
        "schema_version": 1, "pr": pr.get("number"), "url": pr.get("url"),
        "head": pr["headRefOid"], "state": state, "merge_state": merge_state,
        "review_decision": review, "required_checks": checks,
        "allow_auto_merge": snapshot.get("allow_auto_merge"),
        "read_only": True, "automatic_retry": False,
        "scope": "Repository-gate observation only; not code approval, a security sign-off or full goal completion.",
    }
    if state == "MERGED" or pr.get("mergedAt"):
        outcome, action = "merged", "Verify main CI and record the exact delivered scope; do not merge again."
    elif state == "CLOSED":
        outcome, action = "closed_unmerged", "Inspect why the PR was closed; do not claim delivery."
    elif state != "OPEN":
        outcome, action = "metadata_unknown", "Refresh authoritative PR state."
    elif expected_head and expected_head != pr["headRefOid"]:
        outcome, action = "head_changed", "Review and validate the new head before any merge attempt."
    elif snapshot.get("head_stable") is not True:
        outcome, action = "head_changed", "Refresh after the head stabilizes; this mixed snapshot cannot authorize a merge."
    elif pr.get("isDraft") is True:
        outcome, action = "draft", "Finish the scoped change and mark ready only with verified evidence."
    elif pr.get("mergeable") == "CONFLICTING" or merge_state == "DIRTY":
        outcome, action = "conflict", "Resolve the actual conflict on the PR branch and rerun validation."
    elif snapshot.get("required_checks_known") is not True:
        outcome, action = "checks_unknown", "Inspect required checks; failed discovery is not an empty passing check set."
    elif any(b in ("fail", "cancel") for b in buckets):
        outcome, action = "validation_failed", "Fix the failing check or retry a transient failure only after diagnosis."
    elif any(b == "pending" for b in buckets):
        outcome, action = "ci_pending", "Continue safe in-scope work; recheck on a changed check result, not a tight poll loop."
    elif any(b != "pass" for b in buckets):
        outcome, action = "checks_need_inspection", "Inspect skipped/unknown required results; do not invent success."
    elif review == "CHANGES_REQUESTED":
        outcome, action = "changes_requested", "Address substantive requested changes; never fabricate or self-supply independent approval."
    elif review == "REVIEW_REQUIRED":
        outcome, action = "review_pending", "Request the missing review once; preserve the verified implementation and handoff."
    elif merge_state == "BEHIND":
        outcome, action = "base_update_needed", "Update against current base and rerun the affected validation."
    elif merge_state in ("CLEAN", "HAS_HOOKS") and pr.get("mergeable") == "MERGEABLE":
        outcome, action = "normal_merge_candidate", "After scoped review is satisfied, attempt one ordinary SHA-pinned merge. GitHub is final authority."
    else:
        outcome, action = "integration_pending", "Record the exact missing gate/permission and next actor. No admin bypass or repeated unchanged merge calls."
    result.update(outcome=outcome, next_action=action)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="Jongtae/personal-agentos")
    parser.add_argument("--pr", type=int)
    parser.add_argument("--snapshot", type=Path, help="Read a captured/test JSON snapshot without calling GitHub.")
    parser.add_argument("--expected-head")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo):
        parser.error("Expected owner/repository.")
    if args.expected_head and not re.fullmatch(r"[0-9a-fA-F]{40}", args.expected_head):
        parser.error("Expected a full 40-character commit SHA.")
    if not args.snapshot and (args.pr is None or args.pr < 1):
        parser.error("Use --pr with a positive number or --snapshot.")
    try:
        snapshot = json.loads(args.snapshot.read_text()) if args.snapshot else collect(args.repo, args.pr)
        if not isinstance(snapshot, dict):
            raise ValueError("Snapshot must be a JSON object.")
        output = classify(snapshot, args.expected_head)
    except (OSError, ValueError) as exc:
        print(json.dumps({"outcome": "inspection_unavailable", "read_only": True,
                          "error": type(exc).__name__, "next_action": "Check CLI access or snapshot format locally; no merge was attempted."}))
        return 2
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

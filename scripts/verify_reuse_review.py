#!/usr/bin/env python3
"""Fail a pull request whose structured Existing Solutions Review is absent or incomplete."""

from __future__ import annotations

import os
import re
import sys


HEADING = "## Existing solutions review (Adopt / Adapt / Build)"
DECISIONS = {"Adopt", "Adapt", "Build", "N/A"}
REQUIRED_FIELDS = (
    "problem/boundary",
    "internal repository candidates",
    "search evidence (paths/symbols/docs checked)",
    "standard-library/platform candidates",
    "official SDK/reference/standard candidates",
    "mature open-source/framework candidates",
    "maintenance/security/supply-chain fit",
    "licence fit",
    "runtime/deployment/compatibility fit",
    "why rejected candidates are insufficient",
    "AgentOS-owned policy/authority boundary kept outside the dependency",
)
PLACEHOLDERS = {"", "-", "todo", "tbd", "fill me", "placeholder"}


class ReuseReviewError(ValueError):
    pass


def _section(body: str) -> str:
    start = body.lower().find(HEADING.lower())
    if start < 0:
        raise ReuseReviewError("missing Existing solutions review section")
    tail = body[start + len(HEADING):]
    match = re.search(r"(?m)^##\s+", tail)
    return tail[:match.start()] if match else tail


def _field(section: str, label: str) -> str:
    match = re.search(
        rf"(?im)^-\s*{re.escape(label)}\s*:\s*(.*?)\s*$",
        section,
    )
    return match.group(1).strip() if match else ""


def _clean(value: str) -> str:
    return value.strip().strip("`").strip("*").strip()


def _meaningful(value: str) -> bool:
    cleaned = _clean(value)
    return cleaned.lower() not in PLACEHOLDERS and len(cleaned) >= 3


def validate_pr_body(body: str) -> None:
    section = _section(body)
    decision = _clean(_field(section, "decision"))
    if decision not in DECISIONS:
        raise ReuseReviewError("decision must be one of Adopt / Adapt / Build / N/A")

    if decision == "N/A":
        reason = _field(section, "N/A reason")
        if not _meaningful(reason):
            raise ReuseReviewError("N/A requires a concrete reason")
        return

    missing = [label for label in REQUIRED_FIELDS if not _meaningful(_field(section, label))]
    if missing:
        raise ReuseReviewError("incomplete Existing Solutions Review fields: " + ", ".join(missing))

    if decision == "Build":
        rationale = _clean(_field(section, "why rejected candidates are insufficient")).lower()
        weak = {"none", "not needed", "simpler", "easier", "fewer dependencies", "custom is easier"}
        if rationale in weak:
            raise ReuseReviewError("Build requires a concrete unsatisfied-contract rationale")


def main() -> int:
    body = os.environ.get("PR_BODY")
    if body is None:
        print("PR_BODY is not set", file=sys.stderr)
        return 2
    try:
        validate_pr_body(body)
    except ReuseReviewError as exc:
        print(f"Reuse review gate failed: {exc}", file=sys.stderr)
        return 1
    print("Structured Existing Solutions Review verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

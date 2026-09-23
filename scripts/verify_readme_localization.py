#!/usr/bin/env python3
"""Guard public README semantic/structural parity.

English is the canonical factual source, but the public localized READMEs are
one product surface. This verifier intentionally checks stable semantic anchors
and shared safety/status facts instead of requiring literal translations.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

READMES = (
    "README.md",
    "README.ko.md",
    "README.ja.md",
    "README.zh-CN.md",
)

LOCALIZED_READMES = READMES[1:]

SECTION_MARKERS = (
    "<!-- readme-section:hero -->",
    "<!-- readme-section:everyday-scene -->",
    "<!-- readme-section:delegation-flow -->",
    "<!-- readme-section:chatbot-difference -->",
    "<!-- readme-section:try-today -->",
    "<!-- readme-section:status -->",
    "<!-- readme-section:why-agentos -->",
    "<!-- readme-section:owner-control -->",
    "<!-- readme-section:architecture -->",
    "<!-- readme-section:bdi -->",
    "<!-- readme-section:ecosystem -->",
    "<!-- readme-section:portability -->",
    "<!-- readme-section:development -->",
)

CAPABILITY_MARKERS = (
    "<!-- capability:illustrative-product-direction -->",
    "<!-- capability:current-supported-slice -->",
)

NAV_LINKS = (
    "[English](README.md)",
    "[한국어](README.ko.md)",
    "[简体中文](README.zh-CN.md)",
    "[日本語](README.ja.md)",
)

SHARED_FACTS = (
    "<!-- readme-parity:v1 -->",
    "brew install jongtae/agentos/agentos",
    "v1.0.4",
    "https://github.com/Jongtae/personal-agentos/issues/472",
    "Owner · Context · Memory · Artifact · Capability · Runtime · Grant · Work · Event · Evidence",
    "downloaded != installed != enabled != connected != authorized-for-action",
)


def validate_body(name: str, body: str) -> list[str]:
    errors: list[str] = []

    for token in NAV_LINKS + SHARED_FACTS + CAPABILITY_MARKERS:
        count = body.count(token)
        if count != 1:
            errors.append(f"{name}: expected exactly one {token!r}, found {count}")

    last = -1
    for marker in SECTION_MARKERS:
        count = body.count(marker)
        if count != 1:
            errors.append(f"{name}: expected exactly one section marker {marker!r}, found {count}")
            continue
        index = body.index(marker)
        if index <= last:
            errors.append(f"{name}: section marker is out of order: {marker}")
        last = index

    product_direction = body.find(CAPABILITY_MARKERS[0])
    current_slice = body.find(CAPABILITY_MARKERS[1])
    if product_direction >= 0 and current_slice >= 0 and product_direction >= current_slice:
        errors.append(
            f"{name}: illustrative product direction must be identified before the current supported slice"
        )

    install = body.find("brew install jongtae/agentos/agentos")
    status = body.find("<!-- readme-section:status -->")
    if install >= 0 and status >= 0 and install >= status:
        errors.append(f"{name}: install/current supported slice must appear before detailed status")

    return errors


def validate_readmes(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for name in READMES:
        path = root / name
        if not path.is_file():
            errors.append(f"{name}: missing public README")
            continue
        errors.extend(validate_body(name, path.read_text(encoding="utf-8")))
    return errors


def validate_changed_paths(changed_paths: set[str]) -> list[str]:
    """Canonical README changes must update every public locale in the same PR."""
    if "README.md" not in changed_paths:
        return []
    missing = [name for name in LOCALIZED_READMES if name not in changed_paths]
    if not missing:
        return []
    return [
        "README.md changed without all public locales in the same change: "
        + ", ".join(missing)
    ]


def git_changed_paths(base_ref: str, root: Path = ROOT) -> set[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"origin/{base_ref}...HEAD"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"cannot compare README localization against origin/{base_ref}: "
            f"{proc.stderr.strip() or 'git diff failed'}"
        )
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check-git-diff",
        action="store_true",
        help="On a pull request, also require every locale when README.md changed.",
    )
    args = parser.parse_args(argv)

    errors = validate_readmes()

    if args.check_git_diff:
        base_ref = os.environ.get("GITHUB_BASE_REF", "").strip()
        if base_ref:
            try:
                changed = git_changed_paths(base_ref)
            except RuntimeError as exc:
                errors.append(str(exc))
            else:
                errors.extend(validate_changed_paths(changed))

    if errors:
        for error in errors:
            print(f"README parity failure: {error}", file=sys.stderr)
        return 1

    print("README localization parity: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

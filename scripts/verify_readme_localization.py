#!/usr/bin/env python3
"""Guard public README semantic/structural parity.

English is the canonical factual source, but the public localized READMEs are
one product surface. This verifier checks stable semantic anchors and derives
the full public section sequence from the canonical README, rather than
requiring literal translations.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
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

# These are the core sections that may not disappear from every locale at once.
# Extra canonical sections are allowed, but are discovered dynamically from
# README.md and must then appear in every public locale in the same order.
CORE_SECTION_IDS = (
    "hero",
    "everyday-scene",
    "delegation-flow",
    "chatbot-difference",
    "try-today",
    "status",
    "why-agentos",
    "owner-control",
    "architecture",
    "bdi",
    "ecosystem",
    "portability",
    "development",
)

SECTION_MARKER_RE = re.compile(
    r"<!-- readme-section:([a-z0-9][a-z0-9-]*) -->"
)
H2_RE = re.compile(r"^## (?!#)", re.MULTILINE)

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

PRODUCT_DIRECTION_LABELS = {
    "README.md": "> **Product direction — not a current capability claim.**",
    "README.ko.md": "> **Product direction — 현재 지원 기능을 뜻하지 않습니다.**",
    "README.ja.md": "> **Product direction — 現在の対応機能を意味しません。**",
    "README.zh-CN.md": "> **Product direction — 不代表当前已支持。**",
}

PRODUCT_DIRECTION_DISCLAIMERS = {
    "README.md": (
        "**This scene is illustrative product direction, not a claim that "
        "autonomous shopping or checkout is shipped today.**"
    ),
    "README.ko.md": (
        "**이 장면은 product direction을 설명하기 위한 예시이며, 현재 자율 "
        "구매나 결제가 제공된다는 뜻이 아닙니다.**"
    ),
    "README.ja.md": (
        "**この場面は product direction を説明する例であり、現在 autonomous "
        "shopping や checkout が提供されているという意味ではありません。**"
    ),
    "README.zh-CN.md": (
        "**这个场景用于说明 product direction，并不表示今天已经支持 "
        "autonomous shopping 或 checkout。**"
    ),
}

STATUS_EVIDENCE_BOUNDARIES = {
    "README.md": "**live provider operation was not run**",
    "README.ko.md": "**실제 외부 제공자 운영은 실행하지 않았습니다.**",
    "README.ja.md": "**live provider operation は実行していません。**",
    "README.zh-CN.md": "**live provider operation 没有运行。**",
}

STATIC_SHARED_FACTS = (
    "<!-- readme-parity:v1 -->",
    "brew install jongtae/agentos/agentos",
    "https://github.com/Jongtae/personal-agentos/issues/472",
    "Owner · Context · Memory · Artifact · Capability · Runtime · Grant · Work · Event · Evidence",
    "downloaded != installed != enabled != connected != authorized-for-action",
)


def version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def newest_published_version(root: Path = ROOT) -> str:
    manifest = json.loads(
        (root / "docs" / "release-manifest.json").read_text(encoding="utf-8")
    )
    published = [row["version"] for row in manifest["published"]]
    if not published:
        raise ValueError("release manifest records no published release")
    return max(published, key=version_key)


def section_markers(body: str) -> tuple[str, ...]:
    return tuple(match.group(1) for match in SECTION_MARKER_RE.finditer(body))


def validate_heading_marker_discipline(name: str, body: str) -> list[str]:
    """Every public H2 needs a semantic marker immediately above it.

    Blank lines are ignored. This prevents a new user-facing canonical section
    from bypassing parity merely by omitting the marker.
    """
    errors: list[str] = []
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("## "):
            continue
        cursor = index - 1
        while cursor >= 0 and not lines[cursor].strip():
            cursor -= 1
        previous = lines[cursor].strip() if cursor >= 0 else ""
        if not SECTION_MARKER_RE.fullmatch(previous):
            errors.append(
                f"{name}: H2 {line!r} is missing a readme-section marker immediately above it"
            )
    return errors


def section_slice(body: str, section_id: str, next_section_id: str | None) -> str:
    start_marker = f"<!-- readme-section:{section_id} -->"
    start = body.find(start_marker)
    if start < 0:
        return ""
    if next_section_id is None:
        return body[start:]
    end_marker = f"<!-- readme-section:{next_section_id} -->"
    end = body.find(end_marker, start + len(start_marker))
    return body[start:] if end < 0 else body[start:end]


def validate_body(
    name: str,
    body: str,
    canonical_sections: tuple[str, ...],
    release_version: str,
) -> list[str]:
    errors: list[str] = []

    for token in NAV_LINKS + STATIC_SHARED_FACTS + CAPABILITY_MARKERS + (
        f"v{release_version}",
    ):
        count = body.count(token)
        if count != 1:
            errors.append(f"{name}: expected exactly one {token!r}, found {count}")

    errors.extend(validate_heading_marker_discipline(name, body))

    actual_sections = section_markers(body)
    if len(actual_sections) != len(set(actual_sections)):
        errors.append(f"{name}: duplicate readme-section marker in {actual_sections!r}")
    if actual_sections != canonical_sections:
        errors.append(
            f"{name}: section sequence differs from canonical README.md; "
            f"expected {canonical_sections!r}, found {actual_sections!r}"
        )

    product_direction = body.find(CAPABILITY_MARKERS[0])
    current_slice = body.find(CAPABILITY_MARKERS[1])
    if product_direction >= 0 and current_slice >= 0 and product_direction >= current_slice:
        errors.append(
            f"{name}: illustrative product direction must be identified before the current supported slice"
        )

    everyday = section_slice(body, "everyday-scene", "delegation-flow")
    label = PRODUCT_DIRECTION_LABELS[name]
    disclaimer = PRODUCT_DIRECTION_DISCLAIMERS[name]
    if label not in everyday:
        errors.append(f"{name}: everyday scene is missing its visible product-direction label")
    if disclaimer not in everyday:
        errors.append(
            f"{name}: everyday scene is missing the visible not-shipped capability disclaimer"
        )
    if label in everyday:
        first_quote = everyday.find("> **")
        if first_quote >= 0 and everyday.find(label) > first_quote:
            errors.append(
                f"{name}: product-direction label must appear before the illustrative scene"
            )

    status = section_slice(body, "status", "why-agentos")
    if STATUS_EVIDENCE_BOUNDARIES[name] not in status:
        errors.append(
            f"{name}: status section is missing its visible synthetic-vs-live evidence boundary"
        )

    install = body.find("brew install jongtae/agentos/agentos")
    status_marker = body.find("<!-- readme-section:status -->")
    if install >= 0 and status_marker >= 0 and install >= status_marker:
        errors.append(
            f"{name}: install/current supported slice must appear before detailed status"
        )

    return errors


def validate_readmes(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    bodies: dict[str, str] = {}

    for name in READMES:
        path = root / name
        if not path.is_file():
            errors.append(f"{name}: missing public README")
            continue
        bodies[name] = path.read_text(encoding="utf-8")

    canonical = bodies.get("README.md")
    if canonical is None:
        return errors

    canonical_sections = section_markers(canonical)
    if not canonical_sections:
        errors.append("README.md: no readme-section markers found")
    if len(canonical_sections) != len(set(canonical_sections)):
        errors.append(
            f"README.md: duplicate readme-section marker in {canonical_sections!r}"
        )

    missing_core = [
        section_id
        for section_id in CORE_SECTION_IDS
        if section_id not in canonical_sections
    ]
    if missing_core:
        errors.append(
            "README.md: missing required core section marker(s): "
            + ", ".join(missing_core)
        )

    try:
        release_version = newest_published_version(root)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"cannot determine newest published release: {exc}")
        return errors

    for name, body in bodies.items():
        errors.extend(
            validate_body(name, body, canonical_sections, release_version)
        )
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

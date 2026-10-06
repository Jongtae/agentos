#!/usr/bin/env python3
"""Guard public README semantic/structural parity.

English is the canonical factual source, but the public localized READMEs are
one product surface. This verifier checks stable semantic anchors and derives
the full public section sequence from the canonical README, rather than
requiring literal translations.
"""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
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
    "ownership",
    "presence",
    "conversation",
    "try-today",
    "more",
    "license",
)

# The evidence/boundary page behind the README. English is canonical and
# carries the product-direction scene, the status table and the release
# note; the Korean page mirrors it for the owner. Japanese and Chinese
# READMEs link to the English page.
STATUS_DOCS = {
    "docs/product-status.en.md": "README.md",
    "docs/product-status.ko.md": "README.ko.md",
}
STATUS_DOC_LINKS = {
    "README.md": "docs/product-status.en.md",
    "README.ko.md": "docs/product-status.ko.md",
    "README.ja.md": "docs/product-status.en.md",
    "README.zh-CN.md": "docs/product-status.en.md",
}

SECTION_MARKER_RE = re.compile(
    r"<!-- readme-section:([a-z0-9][a-z0-9-]*) -->"
)
ATX_H2_RE = re.compile(r"^ {0,3}##(?!#)(?:[ \t]+|$)")
SETEXT_H2_RE = re.compile(r"^ {0,3}-+[ \t]*$")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")

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

STATUS_ROW_EVIDENCE_TOKEN = "Synthetic **pass-with-friction**"

# This scene explains the intended experience; it cannot silently become
# a shipped integration claim when the README narrative changes.
README_DIRECTION_DISCLAIMERS = {
    "README.md": "Illustrative product direction, not an observed live run or a shipped shopping integration.",
    "README.ko.md": "제품 방향을 설명하는 예시이며, 실제 관찰 실행이나 배포된 구매 기능을 뜻하지 않습니다.",
    "README.ja.md": "製品の方向性を説明する例であり、実際に観測した動作や提供済みの購入機能ではありません。",
    "README.zh-CN.md": "这是产品方向示例，并非实际观测的运行，也不代表已发布的购物功能。",
}

README_RELEASE_BOUNDARIES = {
    "README.md": "Homebrew installs **v{version}** ({date}), an earlier preview. Newer Presence work is on `main`.",
    "README.ko.md": "Homebrew는 이전 프리뷰인 **v{version}**({date})을 설치합니다. 이후의 Presence 구현은 `main`에 있습니다.",
    "README.ja.md": "Homebrew で入るのは以前のプレビュー版 **v{version}**（{date}）です。その後の Presence 実装は `main` にあります。",
    "README.zh-CN.md": "Homebrew 安装的是较早的预览版 **v{version}**（{date}），后续的 Presence 实现在 `main` 中。",
}

IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
HTML_TAG_RE = re.compile(r"<[^>]+>")


def visible_prose(section: str) -> str:
    """Required copy must be readable, not an image alt or HTML attribute."""
    return HTML_TAG_RE.sub("", IMAGE_RE.sub("", COMMENT_RE.sub("", section)))


# Keep the established localized wording, now beside the ownership explanation
# rather than forcing implementation caveats into the opening thesis.
HERO_LOCAL_FIRST_LABELS = {
    "README.md": "Local-first is not local-only",
    "README.ko.md": "로컬 우선(local-first)은 로컬 전용(local-only)이 아닙니다",
    "README.ja.md": "ローカルファースト（local-first）はローカル限定（local-only）ではありません",
    "README.zh-CN.md": "本地优先（local-first）不等于只在本地（local-only）",
}

LOCALE_PRESENCE_VISUALS = {
    "README.md": "docs/assets/readme/presence-overview.en.svg",
    "README.ko.md": "docs/assets/readme/presence-overview.ko.svg",
    "README.ja.md": "docs/assets/readme/presence-overview.ja.svg",
    "README.zh-CN.md": "docs/assets/readme/presence-overview.zh-CN.svg",
}


class PictureParser(HTMLParser):
    """Read actual picture elements, so a path in a comment is insufficient."""

    def __init__(self):
        super().__init__()
        self.pictures: list[list[tuple[str, dict[str, str | None]]]] = []
        self.current: list[tuple[str, dict[str, str | None]]] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "picture":
            self.current = []
            self.pictures.append(self.current)
        elif self.current is not None and tag in ("source", "img"):
            self.current.append((tag, dict(attrs)))

    def handle_endtag(self, tag):
        if tag == "picture":
            self.current = None


def validate_presence_picture(name: str, section: str, root: Path) -> list[str]:
    errors: list[str] = []
    desktop = LOCALE_PRESENCE_VISUALS[name]
    narrow = desktop.removesuffix(".svg") + ".narrow.svg"
    parser = PictureParser()
    parser.feed(without_fenced_code(section))
    if len(parser.pictures) != 1:
        return [f"{name}: presence must contain exactly one localized picture"]
    entries = parser.pictures[0]
    images = [attrs for tag, attrs in entries if tag == "img"]
    sources = [attrs for tag, attrs in entries if tag == "source"]
    if len(images) != 1 or images[0].get("src") != desktop:
        errors.append(f"{name}: presence picture must use localized img src {desktop!r}")
    if len(images) == 1 and not (images[0].get("alt") or "").strip():
        errors.append(f"{name}: presence picture needs meaningful alt text")
    if (len(sources) != 1 or sources[0].get("srcset") != narrow
            or sources[0].get("media") != "(max-width: 600px)"):
        errors.append(f"{name}: presence picture needs narrow source {narrow!r} at 600px")
    for visual in (desktop, narrow):
        if not (root / visual).is_file():
            errors.append(f"{name}: missing presence asset {visual!r}")
    return errors


STATUS_EVIDENCE_BOUNDARIES = {
    "README.md": "**live provider operation was not run**",
    "README.ko.md": "**실제 외부 제공자 운영은 실행하지 않았습니다.**",
    "README.ja.md": "**live provider operation は実行していません。**",
    "README.zh-CN.md": "**live provider operation 没有运行。**",
}

STATIC_SHARED_FACTS = (
    "[QUICKSTART](QUICKSTART.md)",
    "docs/release-manifest.json",
)

# Facts the status page must carry so the README can stay short without
# the boundaries disappearing from the repository's public surface.
STATUS_DOC_FACTS = (
    "brew install jongtae/agentos/agentos",
    "https://github.com/Jongtae/agentos/issues/472",
    "Owner · Context · Memory · Artifact · Capability · Runtime · Grant · Work · Event · Evidence",
    "downloaded != installed != enabled != connected != authorized-for-action",
    "AGPL-3.0-only",
)


def version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def newest_published_release(root: Path = ROOT) -> dict[str, str]:
    manifest = json.loads(
        (root / "docs" / "release-manifest.json").read_text(encoding="utf-8")
    )
    published = manifest["published"]
    if not published:
        raise ValueError("release manifest records no published release")
    newest = max(published, key=lambda row: version_key(row["version"]))
    return {"version": newest["version"], "tag_date": newest["tag_date"]}


def section_markers(body: str) -> tuple[str, ...]:
    return tuple(match.group(1) for match in SECTION_MARKER_RE.finditer(body))


def without_fenced_code(body: str) -> str:
    """Blank fenced code while retaining line numbers for heading diagnostics."""
    lines = body.splitlines()
    fence_char: str | None = None
    fence_len = 0
    visible_lines: list[str] = []

    for line in lines:
        fence = FENCE_RE.match(line)
        if fence:
            token = fence.group(1)
            char = token[0]
            rest = line[fence.end():].strip()
            if fence_char is None:
                fence_char = char
                fence_len = len(token)
            elif char == fence_char and len(token) >= fence_len and not rest:
                fence_char = None
                fence_len = 0
            visible_lines.append("")
            continue
        visible_lines.append(line if fence_char is None else "")
    return "\n".join(visible_lines)


def public_h2_indexes(body: str) -> list[tuple[int, str]]:
    """Return public Markdown H2 headings outside fenced code blocks.

    Detect both ATX H2 headings and setext H2 headings so a new user-facing
    section cannot bypass parity by changing Markdown syntax.
    """
    lines = without_fenced_code(body).splitlines()
    headings: list[tuple[int, str]] = []

    for index, line in enumerate(lines):
        if ATX_H2_RE.match(line):
            headings.append((index, line.strip()))
            continue

        if (
            line.strip()
            and not line.startswith(("    ", "\t"))
            and index + 1 < len(lines)
            and SETEXT_H2_RE.match(lines[index + 1])
        ):
            headings.append((index, line.strip()))

    return headings


def validate_heading_marker_discipline(name: str, body: str) -> list[str]:
    """Every public H2 needs a semantic marker immediately above it."""
    errors: list[str] = []
    lines = body.splitlines()
    for index, heading in public_h2_indexes(body):
        cursor = index - 1
        while cursor >= 0 and not lines[cursor].strip():
            cursor -= 1
        previous = lines[cursor].strip() if cursor >= 0 else ""
        if not SECTION_MARKER_RE.fullmatch(previous):
            errors.append(
                f"{name}: H2 {heading!r} is missing a readme-section marker immediately above it"
            )
    return errors


def next_section_id(sections: tuple[str, ...], section_id: str) -> str | None:
    if section_id not in sections:
        return None
    index = sections.index(section_id)
    return sections[index + 1] if index + 1 < len(sections) else None


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
    release: dict[str, str],
    root: Path,
) -> list[str]:
    errors: list[str] = []
    release_version = release["version"]

    if "<!-- readme-parity:v1 -->" not in body:
        errors.append(f"{name}: missing readme-parity:v1 marker")
    for token in NAV_LINKS + STATIC_SHARED_FACTS + (STATUS_DOC_LINKS[name],):
        if token not in COMMENT_RE.sub("", body):
            errors.append(f"{name}: expected {token!r}, found none")
    if body.count(f"v{release_version}") != 1:
        errors.append(
            f"{name}: expected exactly one 'v{release_version}' next to the brew command, "
            f"found {body.count(f'v{release_version}')}"
        )

    errors.extend(validate_heading_marker_discipline(name, body))
    actual_sections = section_markers(body)
    if len(actual_sections) != len(set(actual_sections)):
        errors.append(f"{name}: duplicate readme-section marker in {actual_sections!r}")
    if actual_sections != canonical_sections:
        errors.append(
            f"{name}: section sequence differs from canonical README.md; "
            f"expected {canonical_sections!r}, found {actual_sections!r}"
        )

    def section(section_id: str) -> str:
        return section_slice(body, section_id, next_section_id(canonical_sections, section_id))

    if HERO_LOCAL_FIRST_LABELS[name] not in visible_prose(section("ownership")):
        errors.append(
            f"{name}: ownership is missing the visible local-first != local-only sentence"
        )
    if README_DIRECTION_DISCLAIMERS[name] not in visible_prose(section("conversation")):
        errors.append(
            f"{name}: conversation is missing its visible illustrative product-direction boundary"
        )
    errors.extend(validate_presence_picture(name, section("presence"), root))

    installation = visible_prose(section("try-today"))
    for token in ("brew install jongtae/agentos/agentos", "http://127.0.0.1:8787/"):
        if token not in installation:
            errors.append(f"{name}: try-today is missing {token!r}")
    boundary = README_RELEASE_BOUNDARIES[name].format(
        version=release_version, date=release["tag_date"]
    )
    if boundary not in installation:
        errors.append(
            f"{name}: try-today is missing its visible published-release/main boundary "
            f"for v{release_version} ({release['tag_date']})"
        )
    license_section = visible_prose(section("license"))
    for token in ("AGPL-3.0-only", "TRADEMARKS.md"):
        if token not in license_section:
            errors.append(f"{name}: license is missing {token!r}")
    return errors


def validate_status_doc(path: str, name: str, body: str, release_version: str) -> list[str]:
    """The status page keeps the boundaries the README no longer spells out."""
    errors: list[str] = []
    for token in STATUS_DOC_FACTS + (CAPABILITY_MARKERS[0], f"v{release_version}"):
        count = body.count(token)
        if count != 1:
            errors.append(f"{path}: expected exactly one {token!r}, found {count}")

    sections = section_markers(body)
    everyday = section_slice(body, "everyday-scene", next_section_id(sections, "everyday-scene"))
    label = PRODUCT_DIRECTION_LABELS[name]
    disclaimer = PRODUCT_DIRECTION_DISCLAIMERS[name]
    if label not in everyday:
        errors.append(f"{path}: everyday scene is missing its visible product-direction label")
    if disclaimer not in everyday:
        errors.append(
            f"{path}: everyday scene is missing the visible not-shipped capability disclaimer"
        )
    if label in everyday:
        first_quote = everyday.find("> **")
        if first_quote >= 0 and everyday.find(label) > first_quote:
            errors.append(
                f"{path}: product-direction label must appear before the illustrative scene"
            )

    status = section_slice(body, "status", next_section_id(sections, "status"))
    if STATUS_EVIDENCE_BOUNDARIES[name] not in status:
        errors.append(
            f"{path}: status section is missing its visible synthetic-vs-live evidence boundary"
        )
    if status.count(STATUS_ROW_EVIDENCE_TOKEN) == 0:
        errors.append(
            f"{path}: status section lost every synthetic pass-with-friction row while #472 "
            "remains the shared audit source; an evidence-class promotion requires deliberate "
            "verifier review"
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

    core_order = tuple(section for section in canonical_sections if section in CORE_SECTION_IDS)
    if not missing_core and core_order != CORE_SECTION_IDS:
        errors.append("README.md: core section order must follow thesis, ownership, presence, conversation, installation, references, license")

    try:
        release = newest_published_release(root)
        release_version = release["version"]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"cannot determine newest published release: {exc}")
        return errors

    for name, body in bodies.items():
        errors.extend(validate_body(name, body, canonical_sections, release, root))

    canonical_rows = None
    for path, name in STATUS_DOCS.items():
        file = root / path
        if not file.is_file():
            errors.append(f"{path}: missing status page")
            continue
        body = file.read_text(encoding="utf-8")
        errors.extend(validate_status_doc(path, name, body, release_version))
        rows = section_slice(body, "status", next_section_id(section_markers(body), "status")).count(
            STATUS_ROW_EVIDENCE_TOKEN
        )
        if canonical_rows is None:
            canonical_rows = rows
        elif rows != canonical_rows:
            errors.append(
                f"{path}: status evidence-class count differs from docs/product-status.en.md; "
                f"expected {canonical_rows} occurrences of {STATUS_ROW_EVIDENCE_TOKEN!r}, found {rows}"
            )
    return errors


def validate_changed_paths(changed_paths: set[str]) -> list[str]:
    """Canonical README changes must update every public locale in the same
    PR; the English status page likewise carries its Korean mirror."""
    errors: list[str] = []
    if "README.md" in changed_paths:
        missing = [name for name in LOCALIZED_READMES if name not in changed_paths]
        if missing:
            errors.append(
                "README.md changed without all public locales in the same change: "
                + ", ".join(missing)
            )
    if "docs/product-status.en.md" in changed_paths and "docs/product-status.ko.md" not in changed_paths:
        errors.append(
            "docs/product-status.en.md changed without docs/product-status.ko.md in the same change"
        )
    return errors


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

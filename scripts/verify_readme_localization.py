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
CONTAINER_PREFIX_RE = re.compile(r"(?:>[ \t]?|[-+*][ \t]+|[0-9]{1,9}[.)][ \t]+)")

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
    "README.md": "A condensed, redacted reconstruction based on owner-pilot conversations. It is not an evidence record of those conversations, and the map and shopping integrations shown are product direction, not shipped features.",
    "README.ko.md": "소유자 파일럿 대화를 바탕으로 압축·비식별화해 재구성한 그림입니다. 그 대화의 증거 기록은 아니며, 그림 속 지도·쇼핑 연동은 배포된 기능이 아니라 제품 방향입니다.",
    "README.ja.md": "オーナーのパイロット会話をもとに、要約と匿名化を加えて再構成した図です。その会話の証拠記録ではなく、図中の地図・ショッピング連携は提供済みの機能ではなく製品の方向性です。",
    "README.zh-CN.md": "这是基于所有者试点对话浓缩并脱敏后的重构图。它不是那些对话的证据记录；图中的地图和购物集成属于产品方向，并非已发布的功能。",
}

README_RELEASE_BOUNDARIES = {
    "README.md": "Homebrew installs **v{version}** ({date}), built from the tagged main commit. The meeting illustration and reconstructed conversations are product direction. The owner-use GIF records separate pilot sessions and is not release-specific end-to-end validation.",
    "README.ko.md": "Homebrew는 태그가 붙은 main 커밋의 **v{version}**({date})을 설치합니다. 미팅 설명 그림과 재구성 대화는 제품 방향 예시입니다. 실제 사용 GIF는 별도 소유자 파일럿 기록이며, 이 배포본의 종단 간 검증은 아닙니다.",
    "README.ja.md": "Homebrew からは、タグを付けた main コミットの **v{version}**（{date}）が入ります。会議の説明図と再構成した会話は製品の方向性です。実際の利用GIFは別のオーナー・パイロット記録であり、この版の一連の動作を検証したものではありません。",
    "README.zh-CN.md": "Homebrew 安装的是从已打标签的 main 提交构建的 **v{version}**（{date}）。会议示意图和重构对话属于产品方向。真实使用GIF记录的是独立的所有者试点会话，并非该发行版本的端到端验证。",
}

IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
HTML_TAG_RE = re.compile(r"<[^>]+>")


def text_without_hidden_markup(section: str) -> str:
    """Exclude comments and image/HTML attributes; retain literal command code."""
    return HTML_TAG_RE.sub("", IMAGE_RE.sub("", COMMENT_RE.sub("", section)))


def fence_state(line: str, char: str | None, length: int) -> tuple[str | None, int, bool]:
    """Share the existing fence rules between Markdown and HTML-code scans."""
    fence = FENCE_RE.match(line)
    if fence is None:
        return char, length, False
    token = fence.group(1)
    if char is None:
        return token[0], len(token), True
    if token[0] == char and len(token) >= length and not line[fence.end():].strip():
        return None, 0, True
    return char, length, True


class HTMLCodeMasker(HTMLParser):
    """Locate HTML code elements without interpreting literal fenced samples."""

    def __init__(self, source: str):
        super().__init__(convert_charrefs=False)
        self.offsets = [0]
        for line in source.splitlines(keepends=True):
            self.offsets.append(self.offsets[-1] + len(line))
        self.tags: list[str] = []
        self.start = 0
        self.ranges: list[tuple[int, int]] = []

    def source_offset(self) -> int:
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if tag in ("pre", "code"):
            if not self.tags:
                self.start = self.source_offset()
            self.tags.append(tag)

    # In HTML these are non-void elements: a trailing slash does not close them.
    handle_startendtag = handle_starttag

    def handle_endtag(self, tag):
        if tag in self.tags:
            index = len(self.tags) - 1 - self.tags[::-1].index(tag)
            del self.tags[index:]
            if not self.tags:
                self.ranges.append((self.start, self.source_offset()))


def without_html_code(section: str) -> str:
    """Mask entire pre/code contents, retaining line positions and separation."""
    parser = HTMLCodeMasker(section)
    parts = re.split(r"(\n[ \t]*\n)", section)
    inline_mask = "".join(inline_code_atoms(part, mask=True) if index % 2 == 0 else part
                          for index, part in enumerate(parts))
    char: str | None = None
    length = 0
    previous_blank = True
    indented = False
    for line, masked_line in zip(section.splitlines(keepends=True), inline_mask.splitlines(keepends=True)):
        hidden = False
        if not parser.tags:
            indented = char is None and (
                ((previous_blank or indented) and line.startswith(("    ", "\t")))
                or (indented and not line.strip())
            )
            if indented:
                hidden = True
            else:
                candidate = line.lstrip(" \t")
                while prefix := CONTAINER_PREFIX_RE.match(candidate):
                    candidate = candidate[prefix.end():].lstrip(" \t")
                char, length, is_fence = fence_state(candidate, char, length)
                hidden = is_fence or char is not None
        previous_blank = not line.strip()
        # Preserve parser offsets, but do not parse HTML written in Markdown
        # code. Within an actual HTML code element, backticks remain literal.
        if hidden:
            parser.feed(re.sub(r"[^\n]", " ", line))
        else:
            for part in re.finditer(r"\0+|[^\0]+", masked_line):
                text = line[part.start():part.end()]
                parser.feed(text if parser.tags or not part[0].startswith("\0")
                            else part[0].replace("\0", " "))
    parser.close()
    if parser.tags:
        parser.ranges.append((parser.start, len(section)))
    chars = list(section)
    for start, end in parser.ranges:
        chars[start:end] = ["\n" if char == "\n" else "\0" for char in section[start:end]]
    return "".join(chars)


def inline_code_atoms(paragraph: str, *, mask: bool = False) -> str:
    """Normalize code spans as opaque atoms, or mask with positions intact."""
    ticks = re.compile(r"`+")
    result: list[str] = []
    cursor = 0
    while opening := ticks.search(paragraph, cursor):
        prefix = paragraph[:opening.start()]
        escaped = (len(prefix) - len(prefix.rstrip("\\"))) % 2
        closing = None if escaped else next(
            (match for match in ticks.finditer(paragraph, opening.end())
             if len(match[0]) == len(opening[0])), None
        )
        if closing is None:
            result.append(paragraph[cursor:opening.end()])
            cursor = opening.end()
            continue
        content = paragraph[opening.end():closing.start()].replace("\n", " ")
        if content.startswith(" ") and content.endswith(" ") and content.strip(" "):
            content = content[1:-1]
        result.append(paragraph[cursor:opening.start()])
        result.append(re.sub(r"[^\n]", "\0", paragraph[opening.start():closing.end()]) if mask
                      else "\0code:" + content.encode("utf-8").hex() + "\0")
        cursor = closing.end()
    result.append(paragraph[cursor:])
    return "".join(result)


def standalone_claim_text(section: str) -> str:
    """Required claims use wholly unindented, non-container paragraphs.

    Normalize quote/list prefixes solely for the conservative fence scan;
    this is not a general Markdown renderer. Decide eligibility on original
    paragraphs before removing lines: deleting an indented inline-code
    delimiter must not expose its contents as prose. Normalizing container
    closing fences keeps later standalone prose outside those examples.
    """
    container = CONTAINER_PREFIX_RE
    lines = text_without_hidden_markup(without_html_code(section)).splitlines()
    normalized: list[str] = []
    standalone: list[bool] = []
    for line in lines:
        plain = line.lstrip(" \t")
        standalone.append(plain == line and not container.match(plain))
        while prefix := container.match(plain):
            plain = plain[prefix.end():].lstrip(" \t")
        normalized.append(plain)
    start = 0
    for index, line in enumerate(lines + [""]):
        if not line.strip():
            if not all(standalone[start:index]):
                standalone[start:index] = [False] * (index - start)
            start = index + 1
    scanned = without_fenced_code("\n".join(normalized)).splitlines()
    return "\n".join(line if eligible else ""
                     for line, eligible in zip(scanned, standalone))


def visible_prose(section: str) -> str:
    """Normalize claim prose while excluding Markdown and HTML code examples.

    An inline identifier such as `main` remains an opaque atom, so comparing
    equally normalized required copy permits that formatting but cannot find
    a whole disclaimer hidden inside one code span. Spans stop at paragraph
    breaks; unmatched or escaped backticks remain literal.
    """
    text = standalone_claim_text(section)
    parts = re.split(r"(\n[ \t]*\n)", text)
    return "".join(inline_code_atoms(part) if index % 2 == 0 else part
                   for index, part in enumerate(parts))


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
LOCALE_SCENE_VISUALS = {
    "README.md": "docs/assets/readme/owner-pilot-conversation.en.png",
    "README.ko.md": "docs/assets/readme/owner-pilot-conversation.ko.png",
    "README.ja.md": "docs/assets/readme/owner-pilot-conversation.ja.png",
    "README.zh-CN.md": "docs/assets/readme/owner-pilot-conversation.zh-CN.png",
}
SECTION_VISUALS = {
    "presence": LOCALE_PRESENCE_VISUALS,
    "conversation": LOCALE_SCENE_VISUALS,
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


def standalone_picture_html(section: str) -> str:
    """Accept the README's standalone HTML format, not Markdown code examples.

    Outer picture tags occupy their own lines with at most three leading
    spaces. A block starts after a blank line (or at the section start).
    Child tags may be indented freely inside that HTML block; a blank line
    ends it, as it does for this CommonMark HTML-block form.
    """
    lines = without_fenced_code(
        without_html_code(COMMENT_RE.sub("", section)), normalize_containers=True
    ).splitlines()
    opening = re.compile(r" {0,3}<picture>[ \t]*", re.I)
    closing = re.compile(r" {0,3}</picture>[ \t]*", re.I)
    blocks: list[str] = []
    start: int | None = None
    for index, line in enumerate(lines):
        if start is None:
            if opening.fullmatch(line) and (index == 0 or not lines[index - 1].strip()):
                start = index
        elif not line.strip():
            start = None
        elif closing.fullmatch(line):
            blocks.append("\n".join(lines[start:index + 1]))
            start = None
    return "\n".join(blocks)


def validate_localized_picture(
    name: str, section_id: str, section: str, root: Path
) -> list[str]:
    errors: list[str] = []
    desktop = SECTION_VISUALS[section_id][name]
    # Each localized conversation image uses one source at every width;
    # the architecture SVG still has a separate narrow composition.
    narrow = desktop if section_id == "conversation" else desktop.removesuffix(".svg") + ".narrow.svg"
    parser = PictureParser()
    parser.feed(standalone_picture_html(section))
    if len(parser.pictures) != 1:
        return [f"{name}: {section_id} must contain exactly one localized picture"]
    entries = parser.pictures[0]
    if [tag for tag, _attrs in entries] != ["source", "img"]:
        errors.append(f"{name}: {section_id} picture needs source before img")
    images = [attrs for tag, attrs in entries if tag == "img"]
    sources = [attrs for tag, attrs in entries if tag == "source"]
    if len(images) != 1 or images[0].get("src") != desktop:
        errors.append(f"{name}: {section_id} picture must use localized img src {desktop!r}")
    if len(images) == 1:
        alt = (images[0].get("alt") or "").strip()
        # Detect empty/path-only placeholders; the description's actual meaning
        # is reviewed with the rendered figure instead of pinned word-for-word.
        if not alt or alt in (desktop, narrow, Path(desktop).name, Path(narrow).name):
            errors.append(f"{name}: {section_id} picture needs meaningful alt text")
    if (len(sources) != 1 or sources[0].get("srcset") != narrow
            or sources[0].get("media") != "(max-width: 600px)"):
        errors.append(f"{name}: {section_id} picture needs narrow source {narrow!r} at 600px")
    for visual in set((desktop, narrow)):
        if not (root / visual).is_file():
            errors.append(f"{name}: missing {section_id} asset {visual!r}")
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


def without_fenced_code(body: str, *, normalize_containers: bool = False) -> str:
    """Blank fenced code while retaining original non-code lines.

    Picture validation scans container fences too, so an example's indented
    closing fence cannot accidentally hide a later standalone picture.
    """
    lines = body.splitlines()
    fence_char: str | None = None
    fence_len = 0
    visible_lines: list[str] = []

    for line in lines:
        candidate = line
        if normalize_containers:
            candidate = candidate.lstrip(" \t")
            while prefix := CONTAINER_PREFIX_RE.match(candidate):
                candidate = candidate[prefix.end():].lstrip(" \t")
        fence_char, fence_len, is_fence = fence_state(candidate, fence_char, fence_len)
        if is_fence:
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
    for section_id in SECTION_VISUALS:
        errors.extend(validate_localized_picture(name, section_id, section(section_id), root))

    installation = section("try-today")
    command_text = text_without_hidden_markup(installation)
    for token in ("brew install jongtae/agentos/agentos", "http://127.0.0.1:8787/"):
        if token not in command_text:
            errors.append(f"{name}: try-today is missing {token!r}")
    boundary = README_RELEASE_BOUNDARIES[name].format(
        version=release_version, date=release["tag_date"]
    )
    if visible_prose(boundary) not in visible_prose(installation):
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

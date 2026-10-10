#!/usr/bin/env python3
"""Stamp the published release into the static site before a Pages deploy.

The README's one-line install command is the source of the pinned installer
commit, and docs/release-manifest.json is the source of the newest published
version. Release work already keeps both current; this copies them into the
site so its install commands and version line never fall behind.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN = re.compile(r"(Jongtae/agentos/(?:blob/)?)([0-9a-f]{40})(/scripts/install\.sh)")
VERSION = re.compile(r'(<span data-release="version">)v[0-9]+\.[0-9]+\.[0-9]+(</span>)')


def release_values(root: Path = ROOT) -> tuple[str, str]:
    readme = (root / "README.md").read_text(encoding="utf-8")
    pins = {m.group(2) for m in PIN.finditer(readme)}
    if len(pins) != 1:
        raise SystemExit(f"README.md must pin exactly one installer commit, found {sorted(pins)}")
    manifest = json.loads((root / "docs/release-manifest.json").read_text(encoding="utf-8"))
    newest = max(manifest["published"], key=lambda row: tuple(int(x) for x in row["version"].split(".")))
    return pins.pop(), newest["version"]


def stamp(site: Path, commit: str, version: str) -> list[Path]:
    changed = []
    for page in sorted(site.glob("*.html")):
        text = page.read_text(encoding="utf-8")
        new = PIN.sub(lambda m: m.group(1) + commit + m.group(3), text)
        new = VERSION.sub(lambda m: f"{m.group(1)}v{version}{m.group(2)}", new)
        if new != text:
            page.write_text(new, encoding="utf-8")
            changed.append(page)
    return changed


def main(argv: list[str]) -> int:
    site = Path(argv[1]) if len(argv) > 1 else ROOT / "site"
    commit, version = release_values()
    for page in stamp(site, commit, version):
        print(f"stamped {page.name}: installer {commit[:12]}, v{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

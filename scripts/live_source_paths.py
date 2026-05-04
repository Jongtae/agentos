#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _parse_install_sources_yaml(path: Path) -> list[str]:
    paths: list[str] = []
    if not path.is_file():
        return paths
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw_line.strip()
        if not stripped.startswith("path:"):
            continue
        candidate = stripped.split(":", 1)[1].strip()
        if not candidate.endswith(".squashfs"):
            continue
        if "enhanced-secureboot" in candidate:
            continue
        relpath = f"casper/{candidate}"
        if relpath not in paths:
            paths.append(relpath)
    return paths


def resolve_live_source_paths(iso_root: Path) -> list[Path]:
    yaml_paths = [
        iso_root / relpath for relpath in _parse_install_sources_yaml(iso_root / "casper" / "install-sources.yaml")
    ]
    existing_yaml_paths = [path for path in yaml_paths if path.is_file()]
    if existing_yaml_paths:
        live_overlay = iso_root / "casper" / "minimal.standard.live.squashfs"
        if live_overlay.is_file() and live_overlay not in existing_yaml_paths:
            existing_yaml_paths.append(live_overlay)
        return existing_yaml_paths

    direct_candidates = [
        iso_root / "casper" / "filesystem.squashfs",
        iso_root / "live" / "filesystem.squashfs",
        iso_root / "LiveOS" / "squashfs.img",
    ]
    for candidate in direct_candidates:
        if candidate.is_file():
            return [candidate]

    glob_matches: list[Path] = []
    for pattern in ("*.live.squashfs", "*.squashfs"):
        for candidate in sorted((iso_root / "casper").glob(pattern)):
            if candidate.is_file() and candidate not in glob_matches:
                glob_matches.append(candidate)
    return glob_matches[:1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve active live source squashfs paths for an AgentOS ISO tree")
    parser.add_argument("--iso-root", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    iso_root = Path(args.iso_root).resolve()
    paths = resolve_live_source_paths(iso_root)
    relpaths = [str(path.relative_to(iso_root)) for path in paths]
    if args.json:
        print(json.dumps({"iso_root": str(iso_root), "live_source_paths": relpaths}, ensure_ascii=True))
    else:
        for relpath in relpaths:
            print(relpath)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

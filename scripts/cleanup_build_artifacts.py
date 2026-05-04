#!/usr/bin/env python3
"""Detect and optionally remove stale build-output artifacts."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

SCHEMA_VERSION = "agentos-build-artifact-cleanup-policy.v1"
VERSION_RE = re.compile(r"agentos-v(?P<version>\d+\.\d+\.\d+)-(?P<arch>amd64|arm64)\.iso$")


@dataclass
class Candidate:
    path: str
    kind: str
    reason: str
    size_bytes: int


def _dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except FileNotFoundError:
            pass
    return total


def _parse_release_version(path: Path) -> tuple[int, int, int] | None:
    match = VERSION_RE.match(path.name)
    if not match:
        return None
    return tuple(int(part) for part in match.group("version").split("."))


def _iter_regular_release_isos(release_dir: Path) -> list[Path]:
    versions: list[tuple[tuple[int, int, int], Path]] = []
    for path in release_dir.glob("agentos-v*-*.iso"):
        version = _parse_release_version(path)
        if version is None:
            continue
        versions.append((version, path))
    return [path for _, path in sorted(versions)]


def _gather_candidates(build_root: Path, keep_release_count: int) -> list[Candidate]:
    candidates: list[Candidate] = []
    if not build_root.exists():
        return candidates

    release_dir = build_root / "release"
    iso_assets_dir = build_root / "iso-assets"

    regular_release_isos = _iter_regular_release_isos(release_dir)
    keep_isos = {path.name for path in regular_release_isos[-keep_release_count:]}
    keep_versions = {
        VERSION_RE.match(path.name).group("version")
        for path in regular_release_isos[-keep_release_count:]
        if VERSION_RE.match(path.name)
    }

    for path in regular_release_isos:
        if path.name not in keep_isos:
            candidates.append(
                Candidate(
                    path=str(path),
                    kind="release_iso",
                    reason=f"not in latest {keep_release_count} regular release ISOs",
                    size_bytes=_dir_size_bytes(path),
                )
            )

    for path in release_dir.iterdir() if release_dir.exists() else []:
        if path.name.endswith("-boot-test.iso") or "-boot-test" in path.name:
            candidates.append(
                Candidate(
                    path=str(path),
                    kind="release_boot_test",
                    reason="ephemeral boot-test image",
                    size_bytes=_dir_size_bytes(path),
                )
            )

    for path in build_root.iterdir():
        if path.name.startswith("manifest-vsmoke-iso-") or path.name.startswith("manifest-debug-iso-"):
            candidates.append(
                Candidate(
                    path=str(path),
                    kind="manifest_ephemeral",
                    reason="ephemeral smoke/debug manifest",
                    size_bytes=_dir_size_bytes(path),
                )
            )
            continue
        if path.name.startswith("manifest-v0.") and path.suffix == ".txt":
            version = path.stem.removeprefix("manifest-v")
            if version not in keep_versions:
                candidates.append(
                    Candidate(
                        path=str(path),
                        kind="manifest_versioned",
                        reason=f"version {version} is outside latest {keep_release_count} retained releases",
                        size_bytes=_dir_size_bytes(path),
                    )
                )

    for path in build_root.iterdir():
        if path.name.startswith("remaster-vsmoke-iso-"):
            candidates.append(
                Candidate(
                    path=str(path),
                    kind="remaster_smoke_dir",
                    reason="ephemeral smoke remaster workdir",
                    size_bytes=_dir_size_bytes(path),
                )
            )
            continue
        if path.name.startswith("remaster-v0.") and path.is_dir():
            version = path.name.removeprefix("remaster-v")
            if version not in keep_versions:
                candidates.append(
                    Candidate(
                        path=str(path),
                        kind="remaster_versioned_dir",
                        reason=f"version {version} is outside latest {keep_release_count} retained releases",
                        size_bytes=_dir_size_bytes(path),
                    )
                )

    for path in iso_assets_dir.iterdir() if iso_assets_dir.exists() else []:
        if path.name == ".DS_Store":
            candidates.append(
                Candidate(
                    path=str(path),
                    kind="iso_assets_noise",
                    reason="Finder metadata",
                    size_bytes=_dir_size_bytes(path),
                )
            )
            continue
        if path.name.startswith("vsmoke-iso-"):
            candidates.append(
                Candidate(
                    path=str(path),
                    kind="iso_assets_smoke_dir",
                    reason="ephemeral smoke iso-assets bundle",
                    size_bytes=_dir_size_bytes(path),
                )
            )
            continue
        if path.name.startswith("v0."):
            version = path.name.removeprefix("v")
            if version not in keep_versions:
                candidates.append(
                    Candidate(
                        path=str(path),
                        kind="iso_assets_versioned_dir",
                        reason=f"version {version} is outside latest {keep_release_count} retained releases",
                        size_bytes=_dir_size_bytes(path),
                    )
                )

    return sorted(candidates, key=lambda c: c.size_bytes, reverse=True)


def _delete_candidate(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=False)
        else:
            path.unlink()
        return not path.exists()
    except Exception:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
        return not path.exists()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-root", default="build-output")
    parser.add_argument("--keep-release-count", type=int, default=2)
    parser.add_argument("--delete", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    build_root = Path(args.build_root).resolve()
    candidates = _gather_candidates(build_root, args.keep_release_count)
    deleted: list[str] = []
    failed_delete: list[str] = []

    if args.delete:
        for candidate in candidates:
            if _delete_candidate(Path(candidate.path)):
                deleted.append(candidate.path)
            else:
                failed_delete.append(candidate.path)
        candidates = _gather_candidates(build_root, args.keep_release_count)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "policy_status": "pass" if not candidates and not failed_delete else "fail",
        "build_root": str(build_root),
        "keep_release_count": args.keep_release_count,
        "stale_candidate_count": len(candidates),
        "stale_reclaimable_bytes": sum(candidate.size_bytes for candidate in candidates),
        "deleted_count": len(deleted),
        "failed_delete_count": len(failed_delete),
        "deleted": deleted,
        "failed_delete": failed_delete,
        "candidates": [asdict(candidate) for candidate in candidates],
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"policy_status={payload['policy_status']}")
        print(f"stale_candidate_count={payload['stale_candidate_count']}")
        print(f"stale_reclaimable_bytes={payload['stale_reclaimable_bytes']}")
        for candidate in candidates:
            print(f"{candidate.kind}\t{candidate.size_bytes}\t{candidate.reason}\t{candidate.path}")

    return 0 if payload["policy_status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())

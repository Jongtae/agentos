#!/usr/bin/env python3
"""Detect and optionally remove stale AgentOS temp artifacts.

This policy tool focuses on artifacts that are large enough to distort macOS
System Data reporting:
- remaster sparseimages and workdirs under /private/tmp
- remaster-shaped tmp.* directories under /private/var/folders/.../T
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = "agentos-temp-artifact-cleanup-policy.v1"
DEFAULT_AGE_HOURS = 24.0
DEFAULT_MIN_TMP_DIR_SIZE_MB = 512
REMASTER_PREFIX = "agentos-remaster-"
REMATER_MARKERS = (
    "casper",
    "boot/grub",
    "boot/memtest86+x64.bin",
    "EFI/boot",
    "agentos/runtime",
    "agentos/postinstall",
)


@dataclass
class Candidate:
    path: str
    kind: str
    size_bytes: int
    age_hours: float
    in_use: bool
    markers: list[str]


def _size_bytes(path: Path) -> int:
    try:
        output = subprocess.check_output(["du", "-sk", str(path)], text=True)
        kib = int(output.split()[0])
        return kib * 1024
    except Exception:
        return 0


def _age_hours(path: Path, now: float) -> float:
    try:
        stat_result = path.stat()
    except FileNotFoundError:
        return 0.0
    return max(0.0, (now - stat_result.st_mtime) / 3600.0)


def _path_in_use(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["lsof", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return len(lines) > 1


def _marker_hits(path: Path) -> list[str]:
    hits: list[str] = []
    for marker in REMATER_MARKERS:
        if (path / marker).exists():
            hits.append(marker)
    return hits


def _iter_private_tmp_candidates(private_tmp_root: Path) -> Iterable[Path]:
    if not private_tmp_root.exists():
        return []
    return sorted(private_tmp_root.glob(f"{REMASTER_PREFIX}*"))


def _iter_var_folder_candidates(var_folders_root: Path) -> Iterable[Path]:
    if not var_folders_root.exists():
        return []
    pattern = "*/*/T/tmp.*"
    return sorted(var_folders_root.glob(pattern))


def _collect_candidates(
    *,
    private_tmp_root: Path,
    var_folders_root: Path,
    older_than_hours: float,
    min_tmp_dir_size_mb: int,
) -> list[Candidate]:
    now = time.time()
    candidates: list[Candidate] = []

    for path in _iter_private_tmp_candidates(private_tmp_root):
        if not path.exists():
            continue
        age = _age_hours(path, now)
        if age < older_than_hours:
            continue
        candidates.append(
            Candidate(
                path=str(path),
                kind="private_tmp_remaster_artifact",
                size_bytes=_size_bytes(path),
                age_hours=round(age, 2),
                in_use=_path_in_use(path),
                markers=[],
            )
        )

    min_tmp_dir_size_bytes = min_tmp_dir_size_mb * 1024 * 1024
    for path in _iter_var_folder_candidates(var_folders_root):
        if not path.exists() or not path.is_dir():
            continue
        markers = _marker_hits(path)
        if not markers:
            continue
        age = _age_hours(path, now)
        if age < older_than_hours:
            continue
        size_bytes = _size_bytes(path)
        if size_bytes < min_tmp_dir_size_bytes:
            continue
        candidates.append(
            Candidate(
                path=str(path),
                kind="var_folders_remaster_tmpdir",
                size_bytes=size_bytes,
                age_hours=round(age, 2),
                in_use=_path_in_use(path),
                markers=markers,
            )
        )

    return sorted(candidates, key=lambda item: item.size_bytes, reverse=True)


def _chmod_recursive(path: Path) -> None:
    try:
        subprocess.run(["chflags", "-R", "nouchg", str(path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass

    for root, dirs, files in os.walk(path, topdown=False):
        root_path = Path(root)
        try:
            root_path.chmod(root_path.stat().st_mode | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRUSR)
        except Exception:
            pass
        for name in files:
            item = root_path / name
            try:
                item.chmod(item.stat().st_mode | stat.S_IWUSR | stat.S_IRUSR)
            except Exception:
                pass
        for name in dirs:
            item = root_path / name
            try:
                item.chmod(item.stat().st_mode | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRUSR)
            except Exception:
                pass


def _delete_path(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        if path.is_dir():
            _chmod_recursive(path)
            shutil.rmtree(path, ignore_errors=False)
        else:
            try:
                path.chmod(path.stat().st_mode | stat.S_IWUSR | stat.S_IRUSR)
            except Exception:
                pass
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
    parser.add_argument("--delete", action="store_true", help="Remove stale candidates instead of only reporting them.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--older-than-hours", type=float, default=DEFAULT_AGE_HOURS)
    parser.add_argument("--min-tmp-dir-size-mb", type=int, default=DEFAULT_MIN_TMP_DIR_SIZE_MB)
    parser.add_argument("--private-tmp-root", default="/private/tmp")
    parser.add_argument("--var-folders-root", default="/private/var/folders")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidates = _collect_candidates(
        private_tmp_root=Path(args.private_tmp_root),
        var_folders_root=Path(args.var_folders_root),
        older_than_hours=args.older_than_hours,
        min_tmp_dir_size_mb=args.min_tmp_dir_size_mb,
    )

    deleted: list[str] = []
    failed_delete: list[str] = []
    stale_candidates = [candidate for candidate in candidates if not candidate.in_use]
    in_use_candidates = [candidate for candidate in candidates if candidate.in_use]

    if args.delete:
        for candidate in stale_candidates:
            path = Path(candidate.path)
            if _delete_path(path):
                deleted.append(candidate.path)
            else:
                failed_delete.append(candidate.path)
        candidates = _collect_candidates(
            private_tmp_root=Path(args.private_tmp_root),
            var_folders_root=Path(args.var_folders_root),
            older_than_hours=args.older_than_hours,
            min_tmp_dir_size_mb=args.min_tmp_dir_size_mb,
        )
        stale_candidates = [candidate for candidate in candidates if not candidate.in_use]
        in_use_candidates = [candidate for candidate in candidates if candidate.in_use]

    payload = {
        "schema_version": SCHEMA_VERSION,
        "policy_status": "pass" if not stale_candidates and not failed_delete else "fail",
        "older_than_hours": args.older_than_hours,
        "min_tmp_dir_size_mb": args.min_tmp_dir_size_mb,
        "stale_candidate_count": len(stale_candidates),
        "in_use_candidate_count": len(in_use_candidates),
        "stale_reclaimable_bytes": sum(candidate.size_bytes for candidate in stale_candidates),
        "in_use_bytes": sum(candidate.size_bytes for candidate in in_use_candidates),
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
        print(f"in_use_candidate_count={payload['in_use_candidate_count']}")
        print(f"stale_reclaimable_bytes={payload['stale_reclaimable_bytes']}")
        for candidate in candidates:
            marker_text = ",".join(candidate.markers) if candidate.markers else "-"
            print(
                f"{candidate.kind}\t{candidate.size_bytes}\t{candidate.age_hours:.2f}h\t"
                f"in_use={str(candidate.in_use).lower()}\tmarkers={marker_text}\t{candidate.path}"
            )

    return 0 if payload["policy_status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())

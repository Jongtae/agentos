#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import warnings
from pathlib import Path

PACKAGE_NAME = "qemu-guest-agent"
SKIP_DEPENDENCY_PACKAGES = {"libc6", "init-system-helpers"}
PACKAGE_SUITES = ("noble-updates", "noble-security", "noble")
PACKAGE_COMPONENTS = ("universe", "main")
UBUNTU_ARCHIVE = "https://archive.ubuntu.com/ubuntu"
UBUNTU_PORTS_ARCHIVE = "https://ports.ubuntu.com/ubuntu-ports"


def _archive_for_arch(arch: str) -> str:
    if arch == "amd64":
        return UBUNTU_ARCHIVE
    if arch == "arm64":
        return UBUNTU_PORTS_ARCHIVE
    raise ValueError(f"unsupported Ubuntu package arch: {arch}")


def _find_package(package_name: str = PACKAGE_NAME, *, arch: str = "amd64") -> dict:
    archive_base = _archive_for_arch(arch)
    for suite in PACKAGE_SUITES:
        for component in PACKAGE_COMPONENTS:
            url = f"{archive_base}/dists/{suite}/{component}/binary-{arch}/Packages.gz"
            try:
                raw = urllib.request.urlopen(url, timeout=30).read()
            except Exception:
                continue
            data = gzip.decompress(raw).decode("utf-8", "replace")
            for block in data.split("\n\n"):
                if f"Package: {package_name}\n" not in block + "\n":
                    continue
                fields: dict[str, str] = {}
                for line in block.splitlines():
                    if ": " in line:
                        key, value = line.split(": ", 1)
                        fields[key] = value
                filename = fields.get("Filename", "").strip()
                version = fields.get("Version", "").strip()
                if filename and version:
                    return {
                        "package": package_name,
                        "suite": suite,
                        "component": component,
                        "version": version,
                        "filename": filename,
                        "url": f"{archive_base}/{filename}",
                        "depends": fields.get("Depends", "").strip(),
                        "arch": arch,
                    }
    raise RuntimeError(f"unable to locate {package_name} in Ubuntu archive metadata")


def _download(url: str, destination: Path) -> None:
    with urllib.request.urlopen(url, timeout=60) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def _deb_is_valid(path: Path) -> bool:
    proc = subprocess.run(["ar", "t", str(path)], check=False, capture_output=True, text=True)
    return proc.returncode == 0 and "data.tar" in proc.stdout


def _extract_deb_data(deb_path: Path, destination: Path) -> list[str]:
    def extract_all(archive: tarfile.TarFile) -> list[str]:
        names = archive.getnames()
        try:
            archive.extractall(destination, filter="fully_trusted")
        except TypeError:
            # Python < 3.12 does not support the filter argument. Keep the
            # fallback narrow and quiet so normal ISO builds do not flood the
            # operator with forward-compatibility warnings.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                archive.extractall(destination)
        return names

    with tempfile.TemporaryDirectory() as td:
        tempdir = Path(td)
        subprocess.run(["ar", "x", str(deb_path)], cwd=tempdir, check=True, capture_output=True, text=True)
        data_members = sorted(tempdir.glob("data.tar.*"))
        if not data_members:
            raise RuntimeError(f"deb archive has no data.tar member: {deb_path}")
        data_member = data_members[0]

        if data_member.suffix == ".zst":
            proc = subprocess.run(["zstd", "-d", "-c", str(data_member)], check=True, capture_output=True)
            tar_stream = io.BytesIO(proc.stdout)
            with tarfile.open(fileobj=tar_stream, mode="r:") as archive:
                return extract_all(archive)
        if data_member.suffix in {".xz", ".gz"}:
            mode = "r:xz" if data_member.suffix == ".xz" else "r:gz"
            with tarfile.open(data_member, mode) as archive:
                return extract_all(archive)
        raise RuntimeError(f"unsupported deb data member: {data_member.name}")


def _parse_dependency_package_names(depends: str) -> list[str]:
    packages: list[str] = []
    for entry in depends.split(","):
        entry = entry.strip()
        if not entry:
            continue
        first_alternative = entry.split("|", 1)[0].strip()
        package = re.split(r"\s*\(", first_alternative, maxsplit=1)[0].strip()
        if not package or package in SKIP_DEPENDENCY_PACKAGES:
            continue
        packages.append(package)
    return packages


def _download_package(package: dict, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    deb_path = cache_dir / Path(package["filename"]).name
    if deb_path.exists() and not _deb_is_valid(deb_path):
        deb_path.unlink()
    if not deb_path.exists():
        _download(package["url"], deb_path)
    if not _deb_is_valid(deb_path):
        deb_path.unlink(missing_ok=True)
        _download(package["url"], deb_path)
    return deb_path


def _payload_missing_from_live_root(deb_path: Path, live_root: Path) -> bool:
    with tempfile.TemporaryDirectory() as td:
        staging_root = Path(td)
        extracted = _extract_deb_data(deb_path, staging_root)
        for relpath in extracted:
            candidate = live_root / relpath
            if not candidate.exists() and not candidate.is_symlink():
                return True
    return False


def stage_guest_agent(*, live_root: Path, cache_dir: Path, arch: str = "amd64") -> dict:
    live_root = live_root.resolve(strict=False)
    cache_dir = cache_dir.resolve(strict=False)
    cache_dir.mkdir(parents=True, exist_ok=True)

    package = _find_package(arch=arch)
    deb_path = _download_package(package, cache_dir)

    dependency_reports: list[dict] = []
    staged_dependencies: list[str] = []
    for dependency_name in _parse_dependency_package_names(package.get("depends", "")):
        dependency = _find_package(dependency_name, arch=arch)
        dependency_deb = _download_package(dependency, cache_dir)
        missing = _payload_missing_from_live_root(dependency_deb, live_root)
        dependency_reports.append(
            {
                "package": dependency_name,
                "version": dependency["version"],
                "deb_path": str(dependency_deb),
                "payload_missing_from_live_root": missing,
            }
        )
        if not missing:
            continue
        _extract_deb_data(dependency_deb, live_root)
        staged_dependencies.append(dependency_name)

    extracted = _extract_deb_data(deb_path, live_root)

    binary_path = live_root / "usr/sbin/qemu-ga"
    service_path = live_root / "lib/systemd/system/qemu-guest-agent.service"
    alt_service_path = live_root / "usr/lib/systemd/system/qemu-guest-agent.service"
    service_present = service_path.exists() or alt_service_path.exists()
    enabled_target = live_root / "etc/systemd/system/multi-user.target.wants/qemu-guest-agent.service"
    if enabled_target.is_symlink() or enabled_target.exists():
        enabled_target.unlink()
    udev_rule = live_root / "usr/lib/udev/rules.d/60-qemu-guest-agent.rules"
    udev_trigger_present = udev_rule.exists()

    return {
        "ok": True,
        "package": PACKAGE_NAME,
        "arch": arch,
        "package_version": package["version"],
        "package_url": package["url"],
        "deb_path": str(deb_path),
        "live_root": str(live_root),
        "dependency_packages": dependency_reports,
        "staged_dependency_packages": staged_dependencies,
        "binary_present": binary_path.exists(),
        "service_present": service_present,
        "service_enabled": udev_trigger_present,
        "service_trigger": "udev",
        "udev_trigger_present": udev_trigger_present,
        "service_enable_path": str(enabled_target),
        "service_enable_target": "",
        "extracted_entries": len(extracted),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage qemu-guest-agent into a live-root")
    parser.add_argument("--live-root", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--arch", choices=("amd64", "arm64"), default="amd64")
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = stage_guest_agent(live_root=Path(args.live_root), cache_dir=Path(args.cache_dir), arch=args.arch)
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(report, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

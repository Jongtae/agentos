#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ISO_PATTERN = re.compile(r"^agentos-([A-Za-z0-9._-]+)-(amd64|arm64)\.iso$")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_sha256sums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        row = line.strip()
        if not row:
            continue
        parts = row.split()
        if len(parts) < 2:
            continue
        digest = parts[0].lower()
        name = parts[-1].lstrip("*")
        result[name] = digest
    return result


def _parse_manifest(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        row = line.strip()
        if not row or "=" not in row:
            continue
        k, v = row.split("=", 1)
        values[k.strip()] = v.strip()
    return values


def verify_metadata(iso_path: str, sha256sums_path: str, manifest_path: str) -> dict:
    iso = Path(iso_path)
    sha = Path(sha256sums_path)
    manifest = Path(manifest_path)

    errors: list[str] = []
    warnings: list[str] = []

    if not iso.exists():
        errors.append(f"iso not found: {iso}")
    if not sha.exists():
        errors.append(f"sha256sums not found: {sha}")
    if not manifest.exists():
        errors.append(f"manifest not found: {manifest}")

    if errors:
        return {"ok": False, "exit_code": 1, "errors": errors, "warnings": warnings}

    iso_name = iso.name
    m = ISO_PATTERN.match(iso_name)
    if not m:
        errors.append(f"invalid iso filename contract: {iso_name}")
        version = ""
        arch = ""
    else:
        version = m.group(1)
        arch = m.group(2)

    expected_digest = _sha256(iso)
    sha_map = _parse_sha256sums(sha)
    digest_in_file = sha_map.get(iso_name, "")
    if not digest_in_file:
        errors.append(f"SHA256SUMS missing entry for {iso_name}")
    elif digest_in_file != expected_digest:
        errors.append("SHA256SUMS digest mismatch for ISO")

    manifest_data = _parse_manifest(manifest)
    manifest_version = manifest_data.get("agentos_version", "")
    manifest_output_iso = manifest_data.get("output_iso", "")
    manifest_arch = manifest_data.get("arch", "")
    manifest_toolchain = manifest_data.get("toolchain", "")

    if version and manifest_version and version != manifest_version:
        errors.append(f"manifest version mismatch: iso={version} manifest={manifest_version}")
    if manifest_arch and arch and manifest_arch != arch:
        errors.append(f"manifest arch mismatch: expected {arch}, got {manifest_arch}")
    if manifest_toolchain and manifest_toolchain != "ubuntu-image+autoinstall":
        warnings.append(f"unexpected toolchain label: {manifest_toolchain}")

    if manifest_output_iso:
        if Path(manifest_output_iso).name != iso_name:
            errors.append("manifest output_iso filename does not match ISO filename")
    else:
        warnings.append("manifest missing output_iso key")

    return {
        "ok": len(errors) == 0,
        "exit_code": 0 if len(errors) == 0 else 1,
        "iso": str(iso),
        "iso_name": iso_name,
        "version": version,
        "arch": arch,
        "sha256_actual": expected_digest,
        "sha256_from_file": digest_in_file,
        "sha256sums_file": str(sha),
        "manifest_file": str(manifest),
        "manifest": manifest_data,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify AgentOS ISO release metadata and hashes")
    parser.add_argument("--iso", required=True)
    parser.add_argument("--sha256sums", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = verify_metadata(args.iso, args.sha256sums, args.manifest)
    if args.json:
        print(json.dumps(report, ensure_ascii=True))
    else:
        print("AgentOS ISO Release Metadata Verification")
        print("=======================================")
        print(f"ISO: {report.get('iso', '')}")
        print(f"SHA256SUMS: {report.get('sha256sums_file', '')}")
        print(f"Manifest: {report.get('manifest_file', '')}")
        print(f"Result: {'PASS' if report['ok'] else 'FAIL'}")
        if report.get("errors"):
            print("Errors:")
            for item in report["errors"]:
                print(f"- {item}")
        if report.get("warnings"):
            print("Warnings:")
            for item in report["warnings"]:
                print(f"- {item}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())

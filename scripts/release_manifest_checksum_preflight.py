#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from release_identity import validate_release_identity_payload

SCHEMA_VERSION = "agentos-release-manifest-checksum-preflight.v1"


def build_preflight(artifact: Path | None, manifest: Path | None, checksum: Path | None) -> dict:
    blockers: list[dict] = []
    proof = {
        "artifact_observed": False,
        "manifest_validated": False,
        "checksum_matched": False,
        "release_uploaded": False,
        "signing_observed": False,
        "vm_iso_proof_completed": False,
    }
    artifact_info: dict = {}
    manifest_info: dict = {}
    checksum_info: dict = {}

    if artifact is None:
        blockers.append(_blocker("release-artifact-required", "No release artifact path was provided."))
    elif not artifact.exists():
        blockers.append(_blocker("release-artifact-missing", f"Release artifact does not exist: {artifact}"))
    else:
        digest = _sha256(artifact)
        artifact_info = {
            "path": str(artifact),
            "name": artifact.name,
            "size_bytes": artifact.stat().st_size,
            "sha256": digest,
        }
        proof["artifact_observed"] = True

    if manifest is None:
        blockers.append(_blocker("release-manifest-required", "No release identity manifest path was provided."))
    elif not manifest.exists():
        blockers.append(_blocker("release-manifest-missing", f"Release identity manifest does not exist: {manifest}"))
    else:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        errors = validate_release_identity_payload(payload)
        manifest_info = {
            "path": str(manifest),
            "schema_version": payload.get("schema_version", ""),
            "artifact_type": payload.get("artifact_type", ""),
            "agentos_version": payload.get("agentos_version", ""),
            "arch": payload.get("arch", ""),
            "source_commit": payload.get("source_commit", ""),
            "errors": errors,
        }
        if errors:
            blockers.append(_blocker("release-manifest-invalid", "Release identity manifest failed validation."))
        else:
            proof["manifest_validated"] = True

    if checksum is None:
        blockers.append(_blocker("checksum-file-required", "No checksum file path was provided."))
    elif not checksum.exists():
        blockers.append(_blocker("checksum-file-missing", f"Checksum file does not exist: {checksum}"))
    else:
        checksum_text = checksum.read_text(encoding="utf-8")
        checksum_info = {"path": str(checksum), "line_count": len(checksum_text.splitlines())}
        if artifact_info:
            expected = artifact_info["sha256"]
            if expected in checksum_text and artifact_info["name"] in checksum_text:
                proof["checksum_matched"] = True
            else:
                blockers.append(_blocker("checksum-mismatch", "Checksum file does not match the release artifact."))

    status = "ready" if not blockers else "blocked"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "artifact": artifact_info,
        "manifest": manifest_info,
        "checksum": checksum_info,
        "blockers": blockers,
        "proof": proof,
        "non_claims": {
            "release_uploaded": True,
            "signing_observed": True,
            "vm_iso_proof_completed": True,
            "installer_readiness": True,
        },
    }


def _blocker(blocker_id: str, reason: str) -> dict:
    return {
        "id": blocker_id,
        "reason": reason,
        "recovery_action": "Provide observed release artifact evidence before claiming release packaging proof.",
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate release manifest and checksum preflight")
    parser.add_argument("--artifact")
    parser.add_argument("--manifest")
    parser.add_argument("--checksum")
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_preflight(
        Path(args.artifact) if args.artifact else None,
        Path(args.manifest) if args.manifest else None,
        Path(args.checksum) if args.checksum else None,
    )
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0 if payload["status"] == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())

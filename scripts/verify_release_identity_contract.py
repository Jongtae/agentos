#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from release_identity import BASE_IMAGE_TYPES, validate_release_identity_payload


ISO_PATTERN = re.compile(r"^agentos-([A-Za-z0-9._-]+)-(amd64|arm64)\.iso$")
DEB_PATTERN = re.compile(r"^agentos_([0-9]+(\.[0-9]+){1,2}([.-][A-Za-z0-9]+)?)_(amd64|arm64)\.deb$")


def _parse_sha256sums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        row = line.strip()
        if not row:
            continue
        parts = row.split()
        if len(parts) < 2:
            continue
        result[parts[-1].lstrip("*")] = parts[0].lower()
    return result


def _parse_manifest(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        row = line.strip()
        if not row or "=" not in row:
            continue
        key, value = row.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def verify_release_identity_contract(metadata_path: str) -> dict:
    metadata = Path(metadata_path)
    errors: list[str] = []
    warnings: list[str] = []

    if not metadata.exists():
        return {
            "ok": False,
            "exit_code": 1,
            "metadata": str(metadata),
            "errors": [f"metadata file not found: {metadata}"],
            "warnings": [],
        }

    payload = json.loads(metadata.read_text(encoding="utf-8"))
    errors.extend(validate_release_identity_payload(payload))

    artifact_type = str(payload.get("artifact_type", "")).strip()
    output_path = Path(str(payload.get("output_path", "")))
    sha_path = Path(str(payload.get("sha256sums_path", "")))

    if output_path.exists() is False:
        errors.append(f"output artifact not found: {output_path}")
    if sha_path.exists() is False:
        errors.append(f"sha256sums file not found: {sha_path}")

    if output_path.exists() and sha_path.exists():
        sha_entries = _parse_sha256sums(sha_path)
        if output_path.name not in sha_entries:
            errors.append(f"SHA256SUMS missing artifact entry: {output_path.name}")

    if artifact_type == "iso":
        if not ISO_PATTERN.match(output_path.name):
            errors.append(f"iso filename does not match contract: {output_path.name}")
        manifest_path = Path(str(payload.get("build_manifest_path", "")))
        base_image_path = Path(str(payload.get("base_image_path", "")))
        asset_bundle_path = Path(str(payload.get("asset_bundle_path", "")))
        asset_manifest_path = Path(str(payload.get("asset_manifest_path", "")))
        for path_name, path in (
            ("build_manifest_path", manifest_path),
            ("base_image_path", base_image_path),
            ("asset_bundle_path", asset_bundle_path),
            ("asset_manifest_path", asset_manifest_path),
        ):
            if not path.exists():
                errors.append(f"{path_name} not found: {path}")
        if manifest_path.exists():
            manifest = _parse_manifest(manifest_path)
            if manifest.get("output_iso") and Path(manifest["output_iso"]).name != output_path.name:
                errors.append("build manifest output_iso does not match artifact name")
            if manifest.get("agentos_version") and manifest.get("agentos_version") != payload.get("agentos_version"):
                errors.append("build manifest agentos_version does not match release identity payload")
        if payload.get("boot_experience_contract") != "agentos_direct_ai_boot":
            errors.append("iso boot_experience_contract does not match direct-ai-boot contract")
        if payload.get("iso_default_boot_path") != "continue_to_agentos_default_path":
            errors.append("iso_default_boot_path does not match Continue to AgentOS default path")
        if payload.get("iso_fallback_boot_path") != "installer_heavy_compatibility":
            errors.append("iso_fallback_boot_path does not match compatibility fallback path")
        if payload.get("grub_theme_contract") != "agentos_minimal_appliance_grub.v1":
            errors.append("grub_theme_contract does not match minimal appliance grub contract")
        if payload.get("splash_theme_contract") != "agentos_minimal_appliance_splash.v1":
            errors.append("splash_theme_contract does not match minimal appliance splash contract")
        if payload.get("base_image_type") not in BASE_IMAGE_TYPES:
            errors.append(
                "base_image_type does not match an allowed AgentOS base contract: "
                f"{sorted(BASE_IMAGE_TYPES)}"
            )
        if payload.get("remaster_mode") != "required_for_product_path":
            errors.append("remaster_mode does not match required remaster contract")
        if payload.get("welcome_shell_contract") != "agentos_welcome_shell.v1":
            errors.append("welcome_shell_contract does not match AgentOS welcome shell contract")
        if payload.get("recovery_shell_contract") != "agentos_recovery_shell.v1":
            errors.append("recovery_shell_contract does not match AgentOS recovery shell contract")
        if payload.get("boot_flow_proof_contract") != "agentos-remastered-boot-flow-proof.v1":
            errors.append("boot_flow_proof_contract does not match remastered boot flow proof contract")
        if not isinstance(payload.get("boot_flow_proof_included"), bool):
            errors.append("boot_flow_proof_included must be a boolean")
        if payload.get("default_boot_target_contract") != "agentos_continue_boot_target.v1":
            errors.append("default_boot_target_contract does not match Continue to AgentOS boot target contract")
        if payload.get("default_boot_target_label") != "Continue to AgentOS":
            errors.append("default_boot_target_label does not match Continue to AgentOS")
        if not isinstance(payload.get("boot_target_activated"), bool):
            errors.append("boot_target_activated must be a boolean")
        if payload.get("vm_first_screen_evidence_contract") != "agentos_vm_first_screen_evidence.v1":
            errors.append("vm_first_screen_evidence_contract does not match VM first-screen evidence contract")
        if not isinstance(payload.get("vm_first_screen_evidence_included"), bool):
            errors.append("vm_first_screen_evidence_included must be a boolean")
        if not isinstance(payload.get("installer_hidden_default_path"), bool):
            errors.append("installer_hidden_default_path must be a boolean")
    elif artifact_type == "deb":
        if not DEB_PATTERN.match(output_path.name):
            errors.append(f"deb filename does not match contract: {output_path.name}")
        if str(payload.get("install_root", "")).strip() != "/usr/lib/agentos":
            errors.append("install_root does not match deb contract")
        if str(payload.get("default_workspace", "")).strip() != "/var/lib/agentos/workspaces/default":
            errors.append("default_workspace does not match deb contract")

    return {
        "ok": not errors,
        "exit_code": 0 if not errors else 1,
        "metadata": str(metadata),
        "artifact_type": artifact_type,
        "artifact_path": str(output_path),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify AgentOS packaging artifacts against the release identity contract")
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = verify_release_identity_contract(args.metadata)
    if args.json:
        print(json.dumps(report, ensure_ascii=True))
    else:
        print("AgentOS Release Identity Contract Verification")
        print("============================================")
        print(f"Metadata: {report['metadata']}")
        print(f"Artifact type: {report.get('artifact_type', '')}")
        print(f"Artifact path: {report.get('artifact_path', '')}")
        print(f"Result: {'PASS' if report['ok'] else 'FAIL'}")
        if report["errors"]:
            print("Errors:")
            for error in report["errors"]:
                print(f"- {error}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())

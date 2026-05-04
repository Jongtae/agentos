#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from export_install_verification_manifest import build_manifest as build_install_manifest
from export_install_verification_manifest import validate_manifest as validate_install_manifest

SCHEMA_VERSION = "agentos-platform-validation-matrix.v1"
MATRIX_CONTRACT = "agentos_x86_64_appliance_validation_baseline"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_platform_validation_matrix(
    *,
    workspace: str,
    report_dir: str,
    install_root: str = "",
    metadata: str = "",
    snapshot_label: str = "agentos-platform-baseline",
) -> dict:
    if metadata or install_root:
        install_manifest = build_install_manifest(
            metadata=metadata,
            install_root=install_root,
            workspace=workspace,
            snapshot_label=snapshot_label,
            root_dir=ROOT_DIR,
        )
        install_errors = validate_install_manifest(install_manifest)
        install_state = "verified" if not install_errors else "invalid"
    else:
        install_manifest = {
            "schema_version": "agentos-install-verification.v1",
            "mode": "guidance_only",
            "required_inputs": ["--install-root", "--metadata"],
            "commands": [
                f"python3 {ROOT_DIR / 'scripts' / 'verify_install_validation_contract.py'} --install-root /tmp/agentos-root --json",
                f"python3 {ROOT_DIR / 'scripts' / 'export_install_verification_manifest.py'} --install-root /tmp/agentos-root --workspace {workspace} --json",
            ],
        }
        install_errors = []
        install_state = "guidance_only"

    matrix = {
        "x86_64_live_appliance_vm": {
            "tier": "active_baseline",
            "environment_class": "virtual_machine",
            "host_profile": "ubuntu_24_04_downstream_eval_vm",
            "session_origin": "live_appliance_boot",
            "path_family": "appliance_first",
            "purpose": "fastest appliance-first evaluation path from ISO boot to tiny setup and ai>",
            "required_checks": [
                "live_appliance_boot_origin",
                "tiny_setup_then_ai",
                "agentos_recovery_path",
                "preview_release_contract",
                "milestone_bundle_export",
            ],
            "helpers": [
                str(ROOT_DIR / "scripts" / "agentos-kernelctl") + f" runtime-entry --json",
                str(ROOT_DIR / "scripts" / "agentos-kernelctl") + f" session-contract --workspace {workspace} --json",
                str(ROOT_DIR / "scripts" / "agentos-kernelctl") + f" milestone-bundle --workspace {workspace} --report-dir {report_dir} --json",
            ],
            "status": "active",
        },
        "x86_64_installed_appliance_vm": {
            "tier": "active_baseline",
            "environment_class": "virtual_machine",
            "host_profile": "ubuntu_24_04_downstream_eval_vm",
            "session_origin": "installed_appliance_boot",
            "path_family": "appliance_first",
            "purpose": "install-later persistence path that preserves AgentOS identity after reboot",
            "required_checks": [
                "install_validation_contract",
                "installed_appliance_boot_origin",
                "managed_session_entry",
                "agentos_recovery_path",
                "preview_release_contract",
            ],
            "helpers": [
                str(ROOT_DIR / "scripts" / "install_kernel_boot_integration.sh"),
                str(ROOT_DIR / "scripts" / "agentos-kernelctl") + f" status --workspace {workspace} --json",
                str(ROOT_DIR / "scripts" / "agentos-kernelctl") + f" session-contract --workspace {workspace} --json",
            ],
            "status": "active",
        },
        "x86_64_workstation_legacy_compat": {
            "tier": "compatibility_baseline",
            "environment_class": "developer_workstation",
            "host_profile": "ubuntu_24_04_downstream_workstation",
            "session_origin": "legacy_local_tty1",
            "path_family": "legacy_compatibility",
            "purpose": "compatibility validation for the pre-appliance tty1 integration path during migration",
            "required_checks": [
                "managed_session_entry",
                "runtime_entry_contract",
                "operator_mode_contract",
                "agentos_recovery_path",
                "legacy_boot_compatibility",
            ],
            "helpers": [
                str(ROOT_DIR / "scripts" / "install_kernel_boot_integration.sh"),
                str(ROOT_DIR / "scripts" / "agentos-kernelctl") + " runtime-entry --json",
                str(ROOT_DIR / "scripts" / "agentos-kernelctl") + " operator-mode --json",
            ],
            "status": "active",
        },
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "report_dir": str(Path(report_dir).resolve()),
        "baseline": {
            "architecture": "x86_64",
            "substrate": "ubuntu_24_04_downstream",
            "packaging_paths": ["iso", "deb"],
            "runtime_model": "agentos_appliance_first_setup_to_ai_shell",
            "preferred_session_origins": ["live_appliance_boot", "installed_appliance_boot"],
            "compatibility_session_origins": ["legacy_local_tty1"],
        },
        "matrix_contract": MATRIX_CONTRACT,
        "validation_matrix": matrix,
        "artifacts": {
            "install_verification_manifest": install_manifest,
            "latest_review_bundle_manifest": str(Path(report_dir).resolve() / "review-bundles" / "latest-bundle-manifest.json"),
            "latest_milestone_bundle_manifest": str(Path(report_dir).resolve() / "milestone-bundles" / "latest-milestone-manifest.json"),
            "references": [
                str(ROOT_DIR / "docs" / "reference" / "platform-validation-matrix-v1.md"),
                str(ROOT_DIR / "docs" / "reference" / "install-validation-contract.md"),
                str(ROOT_DIR / "docs" / "reference" / "agentos-recovery-path-contract-v1.md"),
                str(ROOT_DIR / "docs" / "reference" / "installed-appliance-session-contract-v1.md"),
            ],
        },
        "summary": {
            "ok": not install_errors,
            "active_architecture": "x86_64",
            "environment_count": len(matrix),
            "active_environment_count": sum(1 for item in matrix.values() if item.get("status") == "active"),
            "active_origin_count": len({item.get("session_origin") for item in matrix.values()}),
            "install_verification_state": install_state,
            "supports_live_appliance_path": True,
            "supports_installed_appliance_path": True,
            "supports_legacy_compatibility_path": True,
        },
        "origin_summary": {
            "preferred": ["live_appliance_boot", "installed_appliance_boot"],
            "compatibility": ["legacy_local_tty1"],
            "preferred_path_family": "appliance_first",
        },
        "errors": install_errors,
    }


def validate_platform_validation_matrix(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "workspace",
        "report_dir",
        "baseline",
        "matrix_contract",
        "validation_matrix",
        "artifacts",
        "summary",
        "origin_summary",
        "errors",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("matrix_contract") != MATRIX_CONTRACT:
        errors.append(f"matrix_contract must be {MATRIX_CONTRACT}")

    baseline = payload.get("baseline")
    if not isinstance(baseline, dict):
        errors.append("baseline must be an object")
    else:
        if baseline.get("architecture") != "x86_64":
            errors.append("baseline.architecture must be x86_64")
        if baseline.get("substrate") != "ubuntu_24_04_downstream":
            errors.append("baseline.substrate must be ubuntu_24_04_downstream")
        if not isinstance(baseline.get("packaging_paths"), list) or sorted(baseline.get("packaging_paths", [])) != ["deb", "iso"]:
            errors.append("baseline.packaging_paths must include iso and deb")
        if baseline.get("runtime_model") != "agentos_appliance_first_setup_to_ai_shell":
            errors.append("baseline.runtime_model must be agentos_appliance_first_setup_to_ai_shell")
        if baseline.get("preferred_session_origins") != ["live_appliance_boot", "installed_appliance_boot"]:
            errors.append("baseline.preferred_session_origins must list live_appliance_boot and installed_appliance_boot")

    matrix = payload.get("validation_matrix")
    if not isinstance(matrix, dict):
        errors.append("validation_matrix must be an object")
    else:
        for key in ("x86_64_live_appliance_vm", "x86_64_installed_appliance_vm", "x86_64_workstation_legacy_compat"):
            if key not in matrix:
                errors.append(f"validation_matrix missing required entry: {key}")
        for key, env in matrix.items():
            if not isinstance(env, dict):
                errors.append(f"validation_matrix.{key} must be an object")
                continue
            if env.get("status") != "active":
                errors.append(f"validation_matrix.{key}.status must be active")
            if env.get("session_origin") not in {"live_appliance_boot", "installed_appliance_boot", "legacy_local_tty1"}:
                errors.append(f"validation_matrix.{key}.session_origin must be a known origin")
            if env.get("path_family") not in {"appliance_first", "legacy_compatibility"}:
                errors.append(f"validation_matrix.{key}.path_family must be appliance_first or legacy_compatibility")
            if not isinstance(env.get("required_checks"), list) or not env.get("required_checks"):
                errors.append(f"validation_matrix.{key}.required_checks must be a non-empty list")
            if not isinstance(env.get("helpers"), list) or not env.get("helpers"):
                errors.append(f"validation_matrix.{key}.helpers must be a non-empty list")

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        errors.append("artifacts must be an object")
    else:
        manifest = artifacts.get("install_verification_manifest")
        if not isinstance(manifest, dict):
            errors.append("artifacts.install_verification_manifest must be an object")
        elif manifest.get("mode") == "guidance_only":
            if not isinstance(manifest.get("required_inputs"), list) or not manifest.get("required_inputs"):
                errors.append("guidance_only install_verification_manifest must list required_inputs")
            if not isinstance(manifest.get("commands"), list) or not manifest.get("commands"):
                errors.append("guidance_only install_verification_manifest must list commands")
        else:
            errors.extend(validate_install_manifest(manifest))
        refs = artifacts.get("references")
        if not isinstance(refs, list) or len(refs) < 3:
            errors.append("artifacts.references must list at least three reference documents")

    origin_summary = payload.get("origin_summary")
    if not isinstance(origin_summary, dict):
        errors.append("origin_summary must be an object")
    else:
        if origin_summary.get("preferred") != ["live_appliance_boot", "installed_appliance_boot"]:
            errors.append("origin_summary.preferred must list live_appliance_boot and installed_appliance_boot")
        if origin_summary.get("compatibility") != ["legacy_local_tty1"]:
            errors.append("origin_summary.compatibility must list legacy_local_tty1")
        if origin_summary.get("preferred_path_family") != "appliance_first":
            errors.append("origin_summary.preferred_path_family must be appliance_first")

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary must be an object")
    else:
        if summary.get("ok") is not True:
            errors.append("summary.ok must be true")
        if summary.get("active_architecture") != "x86_64":
            errors.append("summary.active_architecture must be x86_64")
        if summary.get("environment_count") != 3:
            errors.append("summary.environment_count must be 3")
        if summary.get("active_environment_count") != 3:
            errors.append("summary.active_environment_count must be 3")
        if summary.get("active_origin_count") != 3:
            errors.append("summary.active_origin_count must be 3")
        if summary.get("supports_live_appliance_path") is not True:
            errors.append("summary.supports_live_appliance_path must be true")
        if summary.get("supports_installed_appliance_path") is not True:
            errors.append("summary.supports_installed_appliance_path must be true")

    if not isinstance(payload.get("errors"), list):
        errors.append("errors must be a list")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate the AgentOS x86_64 platform validation matrix")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--report-dir", default="./workspaces/default/artifacts")
    parser.add_argument("--install-root", default="")
    parser.add_argument("--metadata", default="")
    parser.add_argument("--snapshot-label", default="agentos-platform-baseline")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_platform_validation_matrix(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_platform_validation_matrix(
        workspace=args.workspace,
        report_dir=args.report_dir,
        install_root=args.install_root,
        metadata=args.metadata,
        snapshot_label=args.snapshot_label,
    )
    errors = validate_platform_validation_matrix(payload)
    payload["errors"] = errors
    payload["summary"]["ok"] = not errors

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    if args.json or not args.output:
        print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

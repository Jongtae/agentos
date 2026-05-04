#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from verify_install_validation_contract import build_report as build_install_validation_report
from vm_appliance_manifest import build_manifest as build_vm_appliance_manifest
from vm_appliance_manifest import validate_manifest as validate_vm_appliance_manifest


SCHEMA_VERSION = "agentos-install-verification.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_manifest(
    *,
    metadata: str = "",
    install_root: str = "",
    workspace: str = "./workspaces/default",
    snapshot_label: str = "agentos-demo-clean",
    root_dir: Path,
) -> dict:
    install_report = build_install_validation_report(metadata=metadata, install_root=install_root)
    appliance_manifest = build_vm_appliance_manifest(workspace, snapshot_label, root_dir)
    appliance_errors = validate_vm_appliance_manifest(appliance_manifest)

    metadata_payload = install_report.get("metadata", {}) if isinstance(install_report.get("metadata"), dict) else {}
    install_root_payload = install_report.get("install_root", {}) if isinstance(install_report.get("install_root"), dict) else {}

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "distribution_contract": "agentos_managed_session",
        "primary_entry_contract": "agentos_setup_to_ai_shell",
        "preferred_session_origins": ["live_appliance_boot", "installed_appliance_boot"],
        "compatibility_session_origins": ["legacy_local_tty1"],
        "install_validation": install_report,
        "appliance_manifest": appliance_manifest,
        "summary": {
            "ok": bool(install_report.get("ok")) and not appliance_errors,
            "artifact_type": metadata_payload.get("artifact_type", ""),
            "metadata_checked": bool(metadata),
            "install_root_checked": bool(install_root),
            "install_assets_ok": bool(install_root_payload.get("ok")),
            "recovery_controls": install_report.get("recovery_controls", {}),
            "health_commands": appliance_manifest.get("health_commands", []),
            "recovery_commands": appliance_manifest.get("recovery_commands", []),
        },
        "errors": list(install_report.get("errors", [])) + appliance_errors,
    }


def validate_manifest(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "distribution_contract",
        "primary_entry_contract",
        "preferred_session_origins",
        "compatibility_session_origins",
        "install_validation",
        "appliance_manifest",
        "summary",
        "errors",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("distribution_contract") != "agentos_managed_session":
        errors.append("distribution_contract must be agentos_managed_session")
    if payload.get("primary_entry_contract") != "agentos_setup_to_ai_shell":
        errors.append("primary_entry_contract must be agentos_setup_to_ai_shell")
    if payload.get("preferred_session_origins") != ["live_appliance_boot", "installed_appliance_boot"]:
        errors.append("preferred_session_origins must list live_appliance_boot and installed_appliance_boot")
    if payload.get("compatibility_session_origins") != ["legacy_local_tty1"]:
        errors.append("compatibility_session_origins must list legacy_local_tty1")

    install_validation = payload.get("install_validation")
    if not isinstance(install_validation, dict):
        errors.append("install_validation must be an object")
    else:
        if install_validation.get("ok") is not True:
            errors.append("install_validation.ok must be true")
        if not isinstance(install_validation.get("recovery_controls"), dict):
            errors.append("install_validation.recovery_controls must be an object")

    appliance_manifest = payload.get("appliance_manifest")
    if not isinstance(appliance_manifest, dict):
        errors.append("appliance_manifest must be an object")
    else:
        errors.extend(validate_vm_appliance_manifest(appliance_manifest))

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary must be an object")
    else:
        for key in ("ok", "health_commands", "recovery_commands", "recovery_controls"):
            if key not in summary:
                errors.append(f"summary missing required field: {key}")
        if summary.get("ok") is not True:
            errors.append("summary.ok must be true")
        if not isinstance(summary.get("health_commands"), list) or not summary.get("health_commands"):
            errors.append("summary.health_commands must be a non-empty list")
        if not isinstance(summary.get("recovery_commands"), list) or not summary.get("recovery_commands"):
            errors.append("summary.recovery_commands must be a non-empty list")
        if not isinstance(summary.get("recovery_controls"), dict) or not summary.get("recovery_controls"):
            errors.append("summary.recovery_controls must be a non-empty object")

    if not isinstance(payload.get("errors"), list):
        errors.append("errors must be a list")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate the AgentOS install verification manifest")
    parser.add_argument("--metadata", default="")
    parser.add_argument("--install-root", default="")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--snapshot-label", default="agentos-demo-clean")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parent.parent

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_manifest(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("install verification manifest: PASS" if result["ok"] else "install verification manifest: FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_manifest(
        metadata=args.metadata,
        install_root=args.install_root,
        workspace=args.workspace,
        snapshot_label=args.snapshot_label,
        root_dir=root_dir,
    )
    errors = validate_manifest(payload)
    if errors:
        if args.json:
            print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=True))
        else:
            for error in errors:
                print(error)
        return 1

    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

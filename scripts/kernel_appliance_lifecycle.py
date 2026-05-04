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
from kernel_operator_review_bundle import resolve_bundle_root

SCHEMA_VERSION = "agentos-appliance-lifecycle.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_appliance_lifecycle(
    *,
    workspace: str,
    report_dir: str,
    install_root: str = "",
    metadata: str = "",
    snapshot_label: str = "agentos-demo-clean",
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
        install_verification_state = "verified" if not install_errors else "invalid"
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
        install_verification_state = "guidance_only"

    bundle_root = resolve_bundle_root(report_dir)
    latest_bundle_manifest = bundle_root / "latest-bundle-manifest.json"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "report_dir": str(Path(report_dir).resolve()),
        "distribution_contract": "agentos_managed_session",
        "primary_entry_contract": "agentos_setup_to_ai_shell",
        "lifecycle_contract": "agentos_appliance_managed_lifecycle",
        "profiles": {
            "evaluation_vm": {
                "status": "active",
                "purpose": "repeatable validation and demo rehearsal",
                "entry_helpers": [
                    str(ROOT_DIR / "scripts" / "vm_demo_flow.sh"),
                    str(ROOT_DIR / "scripts" / "vm_demo_reset.sh"),
                ],
            },
            "demo_image": {
                "status": "documented_candidate",
                "purpose": "presentation-oriented image path",
                "current_contract": "use evaluation_vm lifecycle until a distinct image contract exists",
            },
            "operator_image": {
                "status": "active_via_export",
                "purpose": "portable verification and review handoff",
                "entry_helpers": [
                    str(ROOT_DIR / "scripts" / "export_install_verification_manifest.py"),
                    str(ROOT_DIR / "scripts" / "agentos-kernelctl") + f" review-bundle --workspace {workspace} --report-dir {report_dir} --json",
                ],
            },
        },
        "actions": {
            "install": {
                "status": "active",
                "verification": [
                    f"python3 {ROOT_DIR / 'scripts' / 'verify_install_validation_contract.py'} --install-root {install_root or '/tmp/agentos-root'} --json",
                    f"python3 {ROOT_DIR / 'scripts' / 'export_install_verification_manifest.py'} --install-root {install_root or '/tmp/agentos-root'} --workspace {workspace} --json",
                ],
            },
            "upgrade": {
                "status": "active_managed_refresh",
                "verification": [
                    str(ROOT_DIR / "scripts" / "install_kernel_boot_integration.sh"),
                    str(ROOT_DIR / "scripts" / "agentos-kernelctl") + f" status --workspace {workspace} --json",
                    str(ROOT_DIR / "scripts" / "agentos-kernelctl") + f" health --workspace {workspace} --json",
                ],
            },
            "rollback": {
                "status": "active",
                "recovery_controls": [
                    "AGENTOS_BOOT_AUTOSTART=0",
                    "AGENTOS_BROKER_BYPASS=1",
                    "AGENTOS_KERNEL_POLICY_DISABLE=1",
                    str(ROOT_DIR / "scripts" / "uninstall_kernel_boot_integration.sh"),
                ],
            },
            "reset": {
                "status": "active",
                "helper": str(ROOT_DIR / "scripts" / "vm_demo_reset.sh"),
                "snapshot_label": snapshot_label,
            },
            "export": {
                "status": "active",
                "artifacts": [
                    "install_verification_manifest",
                    "review_bundle",
                ],
                "helpers": [
                    str(ROOT_DIR / "scripts" / "export_install_verification_manifest.py"),
                    str(ROOT_DIR / "scripts" / "agentos-kernelctl") + f" review-bundle --workspace {workspace} --report-dir {report_dir} --json",
                ],
                "latest_bundle_manifest": str(latest_bundle_manifest),
            },
        },
        "install_verification_manifest": install_manifest,
        "summary": {
            "ok": not install_errors,
            "install_ok": bool(install_manifest.get("summary", {}).get("ok")),
            "install_verification_state": install_verification_state,
            "recovery_controls_explicit": True,
            "reset_helper_defined": True,
            "export_helper_defined": True,
            "profile_count": 3,
            "action_count": 5,
        },
        "errors": install_errors,
    }
    return payload


def validate_appliance_lifecycle(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "workspace",
        "report_dir",
        "distribution_contract",
        "primary_entry_contract",
        "lifecycle_contract",
        "profiles",
        "actions",
        "install_verification_manifest",
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
    if payload.get("lifecycle_contract") != "agentos_appliance_managed_lifecycle":
        errors.append("lifecycle_contract must be agentos_appliance_managed_lifecycle")

    profiles = payload.get("profiles")
    if not isinstance(profiles, dict):
        errors.append("profiles must be an object")
    else:
        for key in ("evaluation_vm", "demo_image", "operator_image"):
            if key not in profiles:
                errors.append(f"profiles missing required entry: {key}")

    actions = payload.get("actions")
    if not isinstance(actions, dict):
        errors.append("actions must be an object")
    else:
        for key in ("install", "upgrade", "rollback", "reset", "export"):
            if key not in actions:
                errors.append(f"actions missing required entry: {key}")
        rollback = actions.get("rollback", {}) if isinstance(actions.get("rollback"), dict) else {}
        if not isinstance(rollback.get("recovery_controls"), list) or len(rollback.get("recovery_controls", [])) < 4:
            errors.append("rollback.recovery_controls must be a list with at least four entries")

    manifest = payload.get("install_verification_manifest")
    if not isinstance(manifest, dict):
        errors.append("install_verification_manifest must be an object")
    else:
        if manifest.get("mode") == "guidance_only":
            if not isinstance(manifest.get("required_inputs"), list) or not manifest.get("required_inputs"):
                errors.append("guidance_only install_verification_manifest must list required_inputs")
            if not isinstance(manifest.get("commands"), list) or not manifest.get("commands"):
                errors.append("guidance_only install_verification_manifest must list commands")
        else:
            errors.extend(validate_install_manifest(manifest))

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary must be an object")
    else:
        for key in ("ok", "install_ok", "install_verification_state", "recovery_controls_explicit", "reset_helper_defined", "export_helper_defined"):
            if key not in summary:
                errors.append(f"summary missing required field: {key}")
        if summary.get("ok") is not True:
            errors.append("summary.ok must be true")

    if not isinstance(payload.get("errors"), list):
        errors.append("errors must be a list")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate the AgentOS appliance lifecycle contract")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--report-dir", default="./workspaces/default/artifacts")
    parser.add_argument("--install-root", default="")
    parser.add_argument("--metadata", default="")
    parser.add_argument("--snapshot-label", default="agentos-demo-clean")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_appliance_lifecycle(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("appliance lifecycle contract: PASS" if result["ok"] else "appliance lifecycle contract: FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_appliance_lifecycle(
        workspace=args.workspace,
        report_dir=args.report_dir,
        install_root=args.install_root,
        metadata=args.metadata,
        snapshot_label=args.snapshot_label,
    )
    errors = validate_appliance_lifecycle(payload)
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

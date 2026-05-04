#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA_VERSION = "agentos-boot-target-activation.v1"
BOOT_TARGET_CONTRACT = "agentos_continue_boot_target.v1"
DEFAULT_BOOT_TARGET_LABEL = "Continue to AgentOS"


def build_report(*, iso_root: Path, boot_patch_report: Path) -> dict:
    patch_payload = json.loads(boot_patch_report.read_text(encoding="utf-8")) if boot_patch_report.exists() else {}
    report_path = iso_root / "agentos" / "boot-target-activation.json"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "boot_target_contract": BOOT_TARGET_CONTRACT,
        "iso_root": str(iso_root),
        "boot_patch_report": str(boot_patch_report),
        "default_boot_target_label": patch_payload.get("default_boot_target_label", ""),
        "default_boot_target_entry_index": patch_payload.get("default_boot_target_entry_index"),
        "grub_default_target_configured": bool(patch_payload.get("grub_default_target_configured")),
        "default_boot_target_configured": bool(patch_payload.get("default_boot_target_configured")),
        "install_path_available": bool(patch_payload.get("install_path_available")),
        "installer_hidden_default_path": bool(patch_payload.get("installer_hidden_default_path")),
        "boot_target_activated": False,
        "activation_status": "inactive",
        "report_path": str(report_path),
    }
    payload["boot_target_activated"] = bool(
        payload["default_boot_target_label"] == DEFAULT_BOOT_TARGET_LABEL
        and payload["default_boot_target_entry_index"] == 0
        and payload["grub_default_target_configured"]
        and payload["default_boot_target_configured"]
        and payload["installer_hidden_default_path"]
    )
    payload["activation_status"] = "ready" if payload["boot_target_activated"] else "inactive"
    return payload


def validate_report(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("boot_target_contract") != BOOT_TARGET_CONTRACT:
        errors.append(f"boot_target_contract must be {BOOT_TARGET_CONTRACT}")
    if payload.get("default_boot_target_label") != DEFAULT_BOOT_TARGET_LABEL:
        errors.append(f"default_boot_target_label must be {DEFAULT_BOOT_TARGET_LABEL}")
    if payload.get("default_boot_target_entry_index") != 0:
        errors.append("default_boot_target_entry_index must be 0")
    if payload.get("grub_default_target_configured") is not True:
        errors.append("grub_default_target_configured must be true")
    if payload.get("default_boot_target_configured") is not True:
        errors.append("default_boot_target_configured must be true")
    if payload.get("install_path_available") is not True:
        errors.append("install_path_available must be true")
    if payload.get("installer_hidden_default_path") is not True:
        errors.append("installer_hidden_default_path must be true")
    if payload.get("boot_target_activated") is not True:
        errors.append("boot_target_activated must be true")
    if payload.get("activation_status") != "ready":
        errors.append("activation_status must be ready")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or validate AgentOS boot target activation report")
    parser.add_argument("--iso-root", default="")
    parser.add_argument("--boot-patch-report", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_report(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        print(json.dumps(result, ensure_ascii=True) if args.json else ("PASS" if result["ok"] else "FAIL"))
        if not args.json and errors:
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_report(
        iso_root=Path(args.iso_root).resolve(),
        boot_patch_report=Path(args.boot_patch_report).resolve(),
    )
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

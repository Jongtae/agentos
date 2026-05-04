#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


SCHEMA_VERSION = "agentos-vm-appliance.v1"


def build_manifest(workspace: str, snapshot_label: str, root_dir: Path) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "appliance_contract": "agentos_vm_demo",
        "platform": "ubuntu-24.04",
        "workspace": workspace,
        "snapshot_label": snapshot_label,
        "recommended_hypervisors": ["qemu", "utm"],
        "primary_entry_contract": "agentos_setup_to_ai_shell",
        "launch_helper": str(root_dir / "scripts" / "vm_demo_flow.sh"),
        "reset_helper": str(root_dir / "scripts" / "vm_demo_reset.sh"),
        "health_commands": [
            f"{root_dir / 'scripts' / 'agentos-kernelctl'} health --workspace {workspace}",
            f"{root_dir / 'scripts' / 'agentos-kernelctl'} status --workspace {workspace} --json",
            f"{root_dir / 'scripts' / 'agentos-kernelctl'} broker-status --workspace {workspace} --json",
        ],
        "recovery_commands": [
            "export AGENTOS_BOOT_AUTOSTART=0",
            "export AGENTOS_BROKER_BYPASS=1",
            f"{root_dir / 'scripts' / 'vm_demo_reset.sh'} --workspace {workspace} --snapshot-label {snapshot_label}",
        ],
    }


def validate_manifest(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "appliance_contract",
        "platform",
        "workspace",
        "snapshot_label",
        "recommended_hypervisors",
        "primary_entry_contract",
        "launch_helper",
        "reset_helper",
        "health_commands",
        "recovery_commands",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("appliance_contract") != "agentos_vm_demo":
        errors.append("appliance_contract must be agentos_vm_demo")
    if payload.get("platform") != "ubuntu-24.04":
        errors.append("platform must be ubuntu-24.04")
    if payload.get("primary_entry_contract") != "agentos_setup_to_ai_shell":
        errors.append("primary_entry_contract must be agentos_setup_to_ai_shell")
    if not payload.get("workspace"):
        errors.append("workspace must be non-empty")
    if not isinstance(payload.get("recommended_hypervisors"), list) or not payload.get("recommended_hypervisors"):
        errors.append("recommended_hypervisors must be a non-empty list")
    for key in ("health_commands", "recovery_commands"):
        if not isinstance(payload.get(key), list) or not payload.get(key):
            errors.append(f"{key} must be a non-empty list")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Write or validate the AgentOS VM appliance manifest")
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
            print("vm appliance manifest: PASS" if result["ok"] else "vm appliance manifest: FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_manifest(args.workspace, args.snapshot_label, root_dir)
    errors = validate_manifest(payload)
    if errors:
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

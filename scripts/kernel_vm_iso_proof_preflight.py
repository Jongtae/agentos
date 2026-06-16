#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "agentos-vm-iso-proof-preflight.v1"
ROOT_DIR = Path(__file__).resolve().parents[1]

REQUIRED_SCRIPTS = [
    "scripts/build_latest_agentos_iso.sh",
    "scripts/smoke_build_agentos_iso.sh",
    "scripts/vm_utmctl_observation.py",
    "scripts/kernel_vm_e2e_scenario.py",
    "scripts/kernel_vm_e2e_proof.py",
    "scripts/kernel_remastered_vm_boot_checklist.py",
]


def build_preflight_report(*, workspace: str | Path, vm_name: str = "", iso_path: str = "") -> dict:
    workspace_path = Path(workspace).expanduser().resolve()
    vm_name = str(vm_name or "<utm-vm-name>")
    iso_path = str(iso_path or "<agentos-iso-path>")
    script_checks = [_script_check(path) for path in REQUIRED_SCRIPTS]
    command_checks = [
        {"command": "python3", "available": bool(shutil.which("python3"))},
        {"command": "git", "available": bool(shutil.which("git"))},
        {"command": "utmctl", "available": bool(shutil.which("utmctl")), "required_for_preflight": False},
    ]
    planned_commands = [
        "scripts/smoke_build_agentos_iso.sh",
        "scripts/build_latest_agentos_iso.sh",
        f"scripts/agentos-kernelctl vm-utm-observe --vm {vm_name} --workspace {workspace_path} --json",
        f"python3 scripts/kernel_vm_e2e_scenario.py --workspace {workspace_path} --session-id agentos:tty1 --json",
        f"python3 scripts/kernel_vm_e2e_proof.py --workspace {workspace_path} --session-id agentos:tty1 --use-existing-manifests --json",
        "python3 scripts/kernel_remastered_vm_boot_checklist.py --report-dir <proof-dir> --boot-flow-proof <json> --boot-target-activation <json> --vm-first-screen-evidence <json> --json",
    ]
    observation_checklist = [
        "Build or select a fresh AgentOS ISO.",
        "Boot the ISO in a VM such as UTM on Apple Silicon.",
        "Observe first screen, setup path, managed runtime entry, reboot/recovery path, and session rejoin.",
        "Attach logs or exported JSON evidence to the lifecycle issue before claiming VM/ISO proof.",
    ]
    missing_required = [check["path"] for check in script_checks if not check["exists"]]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace_path),
        "vm_name": vm_name,
        "iso_path": iso_path,
        "script_checks": script_checks,
        "command_checks": command_checks,
        "planned_commands": planned_commands,
        "observation_checklist": observation_checklist,
        "blockers": [
            {
                "id": "vm-iso-proof-not-observed",
                "reason": "This preflight only verifies the proof path; no VM boot was observed.",
                "recovery_action": "Run the planned commands with a real VM and attach observed evidence before signoff.",
            }
        ],
        "proof": {
            "ok": not missing_required,
            "preflight_completed": not missing_required,
            "vm_iso_proof_completed": False,
            "observed_vm_boot": False,
            "observed_reboot_recovery": False,
            "observed_managed_runtime_rejoin": False,
            "destructive_action_executed": False,
        },
    }
    return payload


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    proof = payload.get("proof") or {}
    if proof.get("preflight_completed") is not True:
        errors.append("proof.preflight_completed must be true")
    for key in ("vm_iso_proof_completed", "observed_vm_boot", "observed_reboot_recovery", "observed_managed_runtime_rejoin"):
        if proof.get(key) is not False:
            errors.append(f"proof.{key} must stay false until observed")
    if not payload.get("blockers"):
        errors.append("blockers must include the unobserved VM/ISO proof blocker")
    if not payload.get("planned_commands"):
        errors.append("planned_commands must be present")
    return errors


def _script_check(path: str) -> dict:
    target = ROOT_DIR / path
    return {
        "path": path,
        "exists": target.exists(),
        "executable": bool(target.exists() and target.stat().st_mode & 0o111),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or validate the AgentOS VM/ISO proof preflight report")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--vm-name", default="")
    parser.add_argument("--iso-path", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_payload(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("vm iso proof preflight: PASS" if result["ok"] else "vm iso proof preflight: FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_preflight_report(workspace=args.workspace, vm_name=args.vm_name, iso_path=args.iso_path)
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0 if payload.get("proof", {}).get("preflight_completed") else 1


if __name__ == "__main__":
    raise SystemExit(main())

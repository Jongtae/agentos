#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.appliance_platform import build_next_boot_target_summary

SCHEMA_VERSION = "agentos-installed-slot-switch-evidence.v1"


def _read_env_file(path: Path) -> dict[str, str]:
    payload: dict[str, str] = {}
    if not path.exists():
        return payload
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        payload[key.strip()] = value.strip()
    return payload


def build_switch_evidence() -> dict:
    next_boot_target = build_next_boot_target_summary()
    evidence_file = Path(os.environ.get("AGENTOS_SLOT_SWITCH_EVIDENCE_FILE", "/tmp/agentos-slot-switch-evidence.env"))
    installed_boot_file = Path(os.environ.get("AGENTOS_INSTALLED_BOOT_FILE", "/tmp/agentos-installed-boot.env"))
    evidence_env = _read_env_file(evidence_file)
    installed_boot_env = _read_env_file(installed_boot_file)
    planned_slot = evidence_env.get("planned_slot", next_boot_target.get("target_slot", ""))
    observed_slot = evidence_env.get("observed_slot", next_boot_target.get("active_slot", ""))
    switch_confirmed = evidence_env.get("switch_confirmed", "false").lower() == "true"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "planned_target": next_boot_target,
        "evidence_file": str(evidence_file),
        "evidence_exists": evidence_file.exists(),
        "installed_boot_file": str(installed_boot_file),
        "installed_boot_exists": installed_boot_file.exists(),
        "planned_slot": planned_slot,
        "observed_slot": observed_slot,
        "switch_confirmed": switch_confirmed,
        "evidence_status": evidence_env.get("evidence_status", "missing"),
        "transition_kind": evidence_env.get("transition_kind", ""),
        "observed_identity_path": installed_boot_env.get("identity_path", ""),
        "payload_version": evidence_env.get("payload_version", next_boot_target.get("payload_version", "")),
        "payload_channel": evidence_env.get("payload_channel", next_boot_target.get("payload_channel", "")),
    }
    return payload


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not payload.get("evidence_exists"):
        errors.append("evidence_exists must be true")
    if not payload.get("installed_boot_exists"):
        errors.append("installed_boot_exists must be true")
    if not payload.get("planned_slot"):
        errors.append("planned_slot must be non-empty")
    if not payload.get("observed_slot"):
        errors.append("observed_slot must be non-empty")
    if payload.get("switch_confirmed") is not True:
        errors.append("switch_confirmed must be true")
    if payload.get("evidence_status") != "ready":
        errors.append("evidence_status must be ready")
    if payload.get("transition_kind") != "booted_planned_slot":
        errors.append("transition_kind must be booted_planned_slot")
    if "AgentOS Managed Session" not in str(payload.get("observed_identity_path", "")):
        errors.append("observed_identity_path must contain AgentOS Managed Session")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export installed slot switch evidence")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_payload(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        print(json.dumps(result, ensure_ascii=True) if args.json else ("PASS" if result["ok"] else "FAIL"))
        if not args.json and errors:
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_switch_evidence()
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

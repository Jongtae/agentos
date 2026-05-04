#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.appliance_platform import build_next_boot_target_summary

SCHEMA_VERSION = "agentos-next-boot-target-integration.v1"


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not payload.get("target_slot"):
        errors.append("target_slot must be non-empty")
    if payload.get("target_origin") not in {"", "installed_appliance_boot"}:
        errors.append("target_origin must be installed_appliance_boot when staged")
    if payload.get("staged") and payload.get("target_role") != f"installed_slot_{str(payload.get('target_slot')).lower()}":
        errors.append("target_role must match target_slot")
    if payload.get("staged") and payload.get("transition_kind") not in {"switch_to_inactive_slot", "reaffirm_active_slot"}:
        errors.append("transition_kind must describe the staged next-boot transition")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS next-boot target integration summary")
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

    payload = {"schema_version": SCHEMA_VERSION, **build_next_boot_target_summary()}
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

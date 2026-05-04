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

from kernel.service_governance import SERVICE_GOVERNANCE_SCHEMA_VERSION, build_service_governance_report


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {"schema_version", "workspace", "inventory", "governance_rules", "evidence", "summary"}
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SERVICE_GOVERNANCE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {SERVICE_GOVERNANCE_SCHEMA_VERSION}")
    inventory = payload.get("inventory") or []
    if not isinstance(inventory, list) or not inventory:
        errors.append("inventory must be a non-empty list")
    else:
        units = {item.get("unit") for item in inventory if isinstance(item, dict)}
        if "agentos-kernel.service" not in units:
            errors.append("inventory must include agentos-kernel.service")
    rules = payload.get("governance_rules") or []
    if not isinstance(rules, list) or not rules:
        errors.append("governance_rules must be a non-empty list")
    evidence = payload.get("evidence") or {}
    if not isinstance((evidence.get("unit_state_events") or {}).get("observed_units", []), list):
        errors.append("evidence.unit_state_events.observed_units must be a list")
    summary = payload.get("summary") or {}
    if "mandatory_broker_units" not in summary:
        errors.append("summary must include mandatory_broker_units")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate the AgentOS service governance model")
    parser.add_argument("--workspace", default="./workspaces/default")
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
            print("service governance contract: PASS" if result["ok"] else "service governance contract: FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_service_governance_report(args.workspace)
    errors = validate_payload(payload)
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

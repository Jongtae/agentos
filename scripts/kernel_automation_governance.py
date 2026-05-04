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

from kernel.automation_governance import AUTOMATION_GOVERNANCE_SCHEMA_VERSION, build_automation_governance_report


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {"schema_version", "workspace", "scheduled_tasks", "background_agents", "override_and_rollback_rules", "evidence", "summary"}
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != AUTOMATION_GOVERNANCE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {AUTOMATION_GOVERNANCE_SCHEMA_VERSION}")
    if not isinstance(payload.get("scheduled_tasks"), list) or not payload.get("scheduled_tasks"):
        errors.append("scheduled_tasks must be a non-empty list")
    if not isinstance(payload.get("background_agents"), list) or not payload.get("background_agents"):
        errors.append("background_agents must be a non-empty list")
    if not isinstance(payload.get("override_and_rollback_rules"), list) or not payload.get("override_and_rollback_rules"):
        errors.append("override_and_rollback_rules must be a non-empty list")
    summary = payload.get("summary") or {}
    if "approval_gated_items" not in summary:
        errors.append("summary must include approval_gated_items")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate the AgentOS automation governance model")
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
            print("automation governance contract: PASS" if result["ok"] else "automation governance contract: FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_automation_governance_report(args.workspace)
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

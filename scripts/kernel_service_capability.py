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

from kernel.service_permission_capability import SERVICE_CAPABILITY_SCHEMA_VERSION, build_service_capability_report


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SERVICE_CAPABILITY_SCHEMA_VERSION:
        errors.append(f"schema_version must be {SERVICE_CAPABILITY_SCHEMA_VERSION}")
    if payload.get("capability") != "service_control":
        errors.append("capability must be service_control")
    if not isinstance(payload.get("control_units"), list) or not payload.get("control_units"):
        errors.append("control_units must be a non-empty list")
    if "broker_mediated_control_units" not in (payload.get("summary") or {}):
        errors.append("summary.broker_mediated_control_units must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS service capability report")
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
            print("service capability: PASS" if result["ok"] else "service capability: FAIL")
        return 0 if result["ok"] else 1

    payload = build_service_capability_report(args.workspace)
    errors = validate_payload(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=True))
        return 1
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

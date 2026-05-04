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

from kernel.service_permission_capability import (
    PERMISSION_CAPABILITY_SCHEMA_VERSION,
    SERVICE_CAPABILITY_SCHEMA_VERSION,
    SERVICE_PERMISSION_CAPABILITY_SURFACE_SCHEMA_VERSION,
    build_service_permission_capability_surface,
)


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {"schema_version", "workspace", "service_capability", "permission_capability", "summary"}
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SERVICE_PERMISSION_CAPABILITY_SURFACE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {SERVICE_PERMISSION_CAPABILITY_SURFACE_SCHEMA_VERSION}")

    service = payload.get("service_capability") or {}
    if service.get("schema_version") != SERVICE_CAPABILITY_SCHEMA_VERSION:
        errors.append(f"service_capability.schema_version must be {SERVICE_CAPABILITY_SCHEMA_VERSION}")
    if not isinstance(service.get("control_units"), list) or not service.get("control_units"):
        errors.append("service_capability.control_units must be a non-empty list")

    permission = payload.get("permission_capability") or {}
    if permission.get("schema_version") != PERMISSION_CAPABILITY_SCHEMA_VERSION:
        errors.append(f"permission_capability.schema_version must be {PERMISSION_CAPABILITY_SCHEMA_VERSION}")
    if not isinstance(((permission.get("evidence") or {}).get("recent_permission_events")), list):
        errors.append("permission_capability.evidence.recent_permission_events must be a list")

    summary = payload.get("summary") or {}
    if "service_broker_mediated_control_units" not in summary:
        errors.append("summary must include service_broker_mediated_control_units")
    if "permission_escalated_events" not in summary:
        errors.append("summary must include permission_escalated_events")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate the AgentOS service and permission capability surface")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--limit", type=int, default=50)
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
            print("service permission capability surface: PASS" if result["ok"] else "service permission capability surface: FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_service_permission_capability_surface(
        args.workspace,
        session_id=args.session_id,
        limit=args.limit,
    )
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

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

from kernel.operator_mode import OPERATOR_MODE_SCHEMA_VERSION, operator_mode_contract


def build_payload(*, session_origin: str, setup_status: str) -> dict:
    return operator_mode_contract(
        session_origin={"category": session_origin},
        setup_state={"status": setup_status},
    )


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "current_mode",
        "reason",
        "setup_status",
        "session_origin",
        "controls",
        "surfaces",
        "recommended_surface",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != OPERATOR_MODE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {OPERATOR_MODE_SCHEMA_VERSION}")
    if payload.get("current_mode") not in {"user_mode", "operator_mode", "recovery_mode"}:
        errors.append("current_mode must be one of user_mode/operator_mode/recovery_mode")
    if not isinstance(payload.get("surfaces"), dict):
        errors.append("surfaces must be an object")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate the AgentOS operator mode contract")
    parser.add_argument("--session-origin", default="noninteractive")
    parser.add_argument("--setup-status", default="pending")
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
            print("operator mode contract: PASS" if result["ok"] else "operator mode contract: FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_payload(session_origin=args.session_origin, setup_status=args.setup_status)
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

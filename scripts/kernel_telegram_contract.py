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

from kernel.capability_substrate import (
    TELEGRAM_INGRESS_SCHEMA,
    build_telegram_ingress_contract,
)


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != TELEGRAM_INGRESS_SCHEMA:
        errors.append(f"schema_version must be {TELEGRAM_INGRESS_SCHEMA}")
    if payload.get("capability") != "telegram_ingress_contract":
        errors.append("capability must be telegram_ingress_contract")
    if not isinstance(payload.get("paths"), list) or not payload.get("paths"):
        errors.append("paths must be a non-empty list")
    if not payload.get("proof_fields"):
        errors.append("proof_fields must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS Telegram ingress contract")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--session-id", default="")
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
            print("telegram ingress contract: PASS" if result["ok"] else "telegram ingress contract: FAIL")
        return 0 if result["ok"] else 1

    payload = build_telegram_ingress_contract(args.workspace, session_id=args.session_id)
    errors = validate_payload(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors, "schema_version": payload.get("schema_version", TELEGRAM_INGRESS_SCHEMA)}))
        return 1

    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

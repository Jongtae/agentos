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
    TELEGRAM_WEB_EXECUTION_SCHEMA,
    build_telegram_web_execution_report,
)


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != TELEGRAM_WEB_EXECUTION_SCHEMA:
        errors.append(f"schema_version must be {TELEGRAM_WEB_EXECUTION_SCHEMA}")
    if payload.get("capability") != "telegram_web_execution":
        errors.append("capability must be telegram_web_execution")
    if not payload.get("telegram_request_id"):
        errors.append("telegram_request_id must be present")
    if not isinstance(payload.get("telegram_request_routed"), bool):
        errors.append("telegram_request_routed must be a boolean")
    if "selected_path" not in payload:
        errors.append("selected_path must be present")
    if "selected_intent" not in payload:
        errors.append("selected_intent must be present")
    if not payload.get("execution_url") and payload.get("selected_path") == "internal_web_access":
        errors.append("execution_url must be present for internal_web_access")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS Telegram web execution report")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--message-text", default="")
    parser.add_argument("--chat-id", default="")
    parser.add_argument("--request-id", default="")
    parser.add_argument("--message-id", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--allow-domain", action="append", default=[])
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
            print("telegram web execution: PASS" if result["ok"] else "telegram web execution: FAIL")
        return 0 if result["ok"] else 1

    payload = build_telegram_web_execution_report(
        args.workspace,
        message_text=args.message_text,
        chat_id=args.chat_id,
        request_id=args.request_id,
        message_id=args.message_id,
        session_id=args.session_id,
        domain_allowlist=args.allow_domain,
    )
    errors = validate_payload(payload)
    if errors:
        print(
            json.dumps(
                {"ok": False, "errors": errors, "schema_version": payload.get("schema_version", TELEGRAM_WEB_EXECUTION_SCHEMA)},
                ensure_ascii=True,
            )
        )
        return 1

    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)

    return 0 if payload.get("proof", {}).get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())

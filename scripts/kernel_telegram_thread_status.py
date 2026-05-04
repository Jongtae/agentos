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

from kernel.capability_substrate import TELEGRAM_THREAD_STATUS_SCHEMA, build_telegram_thread_status_report


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != TELEGRAM_THREAD_STATUS_SCHEMA:
        errors.append(f"schema_version must be {TELEGRAM_THREAD_STATUS_SCHEMA}")
    if payload.get("capability") != "telegram_thread_status":
        errors.append("capability must be telegram_thread_status")
    if not isinstance(payload.get("current_context"), dict):
        errors.append("current_context must be a dict")
    if "telegram_thread_continuity_ready" not in payload:
        errors.append("telegram_thread_continuity_ready must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS Telegram thread continuity status")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--message-text", default="")
    parser.add_argument("--chat-id", default="")
    parser.add_argument("--request-id", default="")
    parser.add_argument("--message-id", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--follow-up", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_payload(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        print(json.dumps(result, ensure_ascii=True) if args.json else ("telegram thread status: PASS" if result["ok"] else "telegram thread status: FAIL"))
        return 0 if result["ok"] else 1

    payload = build_telegram_thread_status_report(
        args.workspace,
        message_text=args.message_text,
        chat_id=args.chat_id,
        request_id=args.request_id,
        message_id=args.message_id,
        session_id=args.session_id,
        follow_up=args.follow_up,
    )
    errors = validate_payload(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors, "schema_version": payload.get("schema_version", TELEGRAM_THREAD_STATUS_SCHEMA)}, ensure_ascii=True))
        return 1
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

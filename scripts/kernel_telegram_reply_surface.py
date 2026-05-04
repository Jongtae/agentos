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

from kernel.capability_substrate import TELEGRAM_REPLY_SCHEMA, build_telegram_reply_surface_report


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != TELEGRAM_REPLY_SCHEMA:
        errors.append(f"schema_version must be {TELEGRAM_REPLY_SCHEMA}")
    if payload.get("capability") != "telegram_reply_surface":
        errors.append("capability must be telegram_reply_surface")
    if not isinstance(payload.get("reply_ready"), bool):
        errors.append("reply_ready must be a boolean")
    if "reply_text" not in payload:
        errors.append("reply_text must be present")
    if not isinstance(payload.get("reply_sent"), bool):
        errors.append("reply_sent must be a boolean")
    if not isinstance(payload.get("proof"), dict):
        errors.append("proof must be a dict")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS Telegram reply surface report")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--message-text", default="")
    parser.add_argument("--chat-id", default="")
    parser.add_argument("--request-id", default="")
    parser.add_argument("--message-id", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--allow-domain", action="append", default=[])
    parser.add_argument("--send", action="store_true")
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
            print("telegram reply surface: PASS" if result["ok"] else "telegram reply surface: FAIL")
        return 0 if result["ok"] else 1

    payload = build_telegram_reply_surface_report(
        args.workspace,
        message_text=args.message_text,
        chat_id=args.chat_id,
        request_id=args.request_id,
        message_id=args.message_id,
        session_id=args.session_id,
        send_reply=args.send,
        domain_allowlist=args.allow_domain,
    )
    errors = validate_payload(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors, "schema_version": payload.get("schema_version", TELEGRAM_REPLY_SCHEMA)}, ensure_ascii=True))
        return 1

    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if payload.get("proof", {}).get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())

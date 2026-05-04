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

from kernel.capability_substrate import TELEGRAM_LIVE_LOOP_SCHEMA, build_telegram_live_loop_report


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != TELEGRAM_LIVE_LOOP_SCHEMA:
        errors.append(f"schema_version must be {TELEGRAM_LIVE_LOOP_SCHEMA}")
    if payload.get("capability") != "telegram_live_loop":
        errors.append("capability must be telegram_live_loop")
    for key in (
        "telegram_polling_attempted",
        "telegram_live_update_received",
        "telegram_live_message_routed",
        "telegram_live_search_success",
        "telegram_reply_sent",
        "telegram_update_offset_persisted",
    ):
        if not isinstance(payload.get(key), bool):
            errors.append(f"{key} must be a boolean")
    rendered = json.dumps(payload, ensure_ascii=True)
    if "bot_token_value" in rendered:
        errors.append("payload must not include raw bot_token_value")
    if not isinstance(payload.get("proof"), dict):
        errors.append("proof must be a dict")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one AgentOS Telegram polling/search/reply loop")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--once", action="store_true", help="Poll at most one Telegram update.")
    parser.add_argument("--send", action="store_true", help="Send the generated reply through Telegram sendMessage.")
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
        print(json.dumps(result, ensure_ascii=True) if args.json else ("telegram live loop: PASS" if result["ok"] else "telegram live loop: FAIL"))
        return 0 if result["ok"] else 1

    payload = build_telegram_live_loop_report(
        args.workspace,
        once=True if args.once else True,
        send_reply=args.send,
        session_id=args.session_id,
        domain_allowlist=args.allow_domain or None,
    )
    errors = validate_payload(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors, "schema_version": payload.get("schema_version", TELEGRAM_LIVE_LOOP_SCHEMA)}, ensure_ascii=True))
        return 1
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if payload.get("proof", {}).get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())

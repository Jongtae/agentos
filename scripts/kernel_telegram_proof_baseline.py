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

from kernel.capability_substrate import TELEGRAM_PROOF_SCHEMA, build_telegram_proof_baseline_report


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != TELEGRAM_PROOF_SCHEMA:
        errors.append(f"schema_version must be {TELEGRAM_PROOF_SCHEMA}")
    if payload.get("capability") != "telegram_proof_baseline":
        errors.append("capability must be telegram_proof_baseline")
    if not isinstance(payload.get("summary"), dict):
        errors.append("summary must be a dict")
    if not isinstance(payload.get("artifacts"), dict):
        errors.append("artifacts must be a dict")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS Telegram proof baseline")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--message-text", default="")
    parser.add_argument("--chat-id", default="")
    parser.add_argument("--request-id", default="")
    parser.add_argument("--message-id", default="")
    parser.add_argument("--reply-sent", action="store_true")
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
            print("telegram proof baseline: PASS" if result["ok"] else "telegram proof baseline: FAIL")
        return 0 if result["ok"] else 1

    payload = build_telegram_proof_baseline_report(
        args.workspace,
        message_text=args.message_text,
        chat_id=args.chat_id,
        request_id=args.request_id,
        message_id=args.message_id,
        reply_sent=args.reply_sent,
        session_id=args.session_id,
    )
    errors = validate_payload(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors, "schema_version": payload.get("schema_version", TELEGRAM_PROOF_SCHEMA)}))
        return 1

    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

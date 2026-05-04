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

from io_utils import scrub_payload, write_json_file
from kernel.intent_dispatch import INTENT_DISPATCH_SCHEMA_VERSION, build_intent_dispatch_report


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != INTENT_DISPATCH_SCHEMA_VERSION:
        errors.append(f"schema_version must be {INTENT_DISPATCH_SCHEMA_VERSION}")
    if payload.get("capability") != "intent_dispatch":
        errors.append("capability must be intent_dispatch")
    for key in ("intent", "capability_executed", "response"):
        if not isinstance(payload.get(key), str):
            errors.append(f"{key} must be a string")
    if not isinstance(payload.get("web_search_used"), bool):
        errors.append("web_search_used must be a boolean")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify and dispatch one AgentOS operator/Telegram request")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--source", choices=("operator", "telegram"), default="operator")
    parser.add_argument("--message", default="")
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
        print(json.dumps(result, ensure_ascii=True) if args.json else ("intent dispatch: PASS" if result["ok"] else "intent dispatch: FAIL"))
        return 0 if result["ok"] else 1

    payload = build_intent_dispatch_report(
        args.workspace,
        source=args.source,
        message_text=args.message,
        chat_id=args.chat_id,
        request_id=args.request_id,
        message_id=args.message_id,
        session_id=args.session_id,
        send_reply=args.send,
        domain_allowlist=args.allow_domain,
        write_manifest=True,
    )
    scrubbed = scrub_payload(payload)
    errors = validate_payload(scrubbed)
    if errors:
        print(json.dumps({"ok": False, "errors": errors, "schema_version": scrubbed.get("schema_version", "")}, ensure_ascii=True))
        return 1
    if args.output:
        write_json_file(args.output, scrubbed)
    if args.json or not args.output:
        print(json.dumps(scrubbed, ensure_ascii=True))
    return 0 if scrubbed.get("proof", {}).get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())

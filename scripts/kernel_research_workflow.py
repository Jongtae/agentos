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
    RESEARCH_WORKFLOW_SCHEMA,
    build_research_request_response_workflow_report,
)


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != RESEARCH_WORKFLOW_SCHEMA:
        errors.append(f"schema_version must be {RESEARCH_WORKFLOW_SCHEMA}")
    if payload.get("capability") != "research_request_response_workflow":
        errors.append("capability must be research_request_response_workflow")
    if payload.get("workflow_id") != "research_request_response":
        errors.append("workflow_id must be research_request_response")
    steps = payload.get("steps")
    if not isinstance(steps, list) or [step.get("id") for step in steps] != [
        "telegram_request_routing",
        "internal_web_execution",
        "telegram_reply",
    ]:
        errors.append("steps must contain routing, internal web execution, and telegram reply in order")
    links = payload.get("links")
    if not isinstance(links, dict) or not links.get("proof") or not links.get("runtime") or not links.get("reply"):
        errors.append("links must include proof, runtime, and reply entries")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the AgentOS research request response workflow report")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--message-text", default="search agentos roadmap")
    parser.add_argument("--chat-id", default="1001")
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
            print("research workflow: PASS" if result["ok"] else "research workflow: FAIL")
        return 0 if result["ok"] else 1

    payload = build_research_request_response_workflow_report(
        args.workspace,
        message_text=args.message_text,
        chat_id=args.chat_id,
        request_id=args.request_id,
        message_id=args.message_id,
        session_id=args.session_id,
        send_reply=args.send,
        domain_allowlist=args.allow_domain or None,
    )
    errors = validate_payload(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors, "schema_version": payload.get("schema_version", RESEARCH_WORKFLOW_SCHEMA)}))
        return 1

    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

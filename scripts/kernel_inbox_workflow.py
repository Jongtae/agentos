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
    INBOX_WORKFLOW_SCHEMA,
    build_inbox_triage_summary_response_workflow_report,
)


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != INBOX_WORKFLOW_SCHEMA:
        errors.append(f"schema_version must be {INBOX_WORKFLOW_SCHEMA}")
    if payload.get("capability") != "inbox_triage_summary_response_workflow":
        errors.append("capability must be inbox_triage_summary_response_workflow")
    if payload.get("workflow_id") != "inbox_triage_summary_response":
        errors.append("workflow_id must be inbox_triage_summary_response")
    steps = payload.get("steps")
    if not isinstance(steps, list) or [step.get("id") for step in steps] != [
        "inbox_intake",
        "inbox_proof",
        "first_run_summary",
    ]:
        errors.append("steps must contain inbox intake, inbox proof, and first run summary in order")
    links = payload.get("links")
    if not isinstance(links, dict) or not links.get("proof") or not links.get("runtime") or not links.get("reply"):
        errors.append("links must include proof, runtime, and reply entries")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the AgentOS inbox triage summary response workflow report")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--maildir", default="")
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
            print("inbox workflow: PASS" if result["ok"] else "inbox workflow: FAIL")
        return 0 if result["ok"] else 1

    payload = build_inbox_triage_summary_response_workflow_report(
        args.workspace,
        maildir_path=args.maildir,
        session_id=args.session_id,
    )
    errors = validate_payload(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors, "schema_version": payload.get("schema_version", INBOX_WORKFLOW_SCHEMA)}))
        return 1

    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

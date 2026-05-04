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

from kernel.first_run_summary import FIRST_RUN_SUMMARY_SCHEMA, build_first_run_summary_report


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != FIRST_RUN_SUMMARY_SCHEMA:
        errors.append(f"schema_version must be {FIRST_RUN_SUMMARY_SCHEMA}")
    summary = payload.get("summary") or {}
    for key in ("document_native_handled", "web_handled", "capability_proof_ready", "summary_text"):
        if key not in summary:
            errors.append(f"summary.{key} must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS repo-free first-run summary")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--path", default="")
    parser.add_argument("--url", default="https://example.com")
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
            print("first run summary: PASS" if result["ok"] else "first run summary: FAIL")
        return 0 if result["ok"] else 1

    payload = build_first_run_summary_report(
        args.workspace,
        document_path=args.path or "documents/agentos-first-run.md",
        web_url=args.url,
        domain_allowlist=args.allow_domain or ["example.com"],
    )
    errors = validate_payload(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=True))
        return 1

    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    else:
        print("AgentOS Repo-Free First-Run Summary")
        print("===================================")
        print(f"Workspace: {payload['workspace']}")
        print(f"Document path: {payload['summary']['document_path']}")
        print(f"Web URL: {payload['summary']['web_url']}")
        print(f"Document native handled: {payload['summary']['document_native_handled']}")
        print(f"Web handled: {payload['summary']['web_handled']}")
        print(f"Capability proof ready: {payload['summary']['capability_proof_ready']}")
        print(payload["summary"]["summary_text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

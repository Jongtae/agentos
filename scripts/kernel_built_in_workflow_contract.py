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
    BUILT_IN_WORKFLOW_CONTRACT_SCHEMA,
    build_built_in_workflow_contract,
)


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != BUILT_IN_WORKFLOW_CONTRACT_SCHEMA:
        errors.append(f"schema_version must be {BUILT_IN_WORKFLOW_CONTRACT_SCHEMA}")
    if payload.get("capability") != "built_in_workflow_contract":
        errors.append("capability must be built_in_workflow_contract")
    workflows = payload.get("workflows")
    if not isinstance(workflows, list) or len(workflows) != 2:
        errors.append("workflows must contain the two built-in workflow entries")
    else:
        ids = [str(item.get("id", "")) for item in workflows]
        if ids != ["research_request_response", "inbox_triage_summary_response"]:
            errors.append("workflow ids must match the built-in workflow vocabulary")
    policy = payload.get("workflow_policy")
    if not isinstance(policy, dict):
        errors.append("workflow_policy must be present")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts.get("latest_built_in_workflow_contract_manifest_json"):
        errors.append("workflow contract artifact path must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the AgentOS built-in workflow contract")
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
            print("built-in workflow contract: PASS" if result["ok"] else "built-in workflow contract: FAIL")
        return 0 if result["ok"] else 1

    payload = build_built_in_workflow_contract(args.workspace, session_id=args.session_id)
    errors = validate_payload(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors, "schema_version": payload.get("schema_version", BUILT_IN_WORKFLOW_CONTRACT_SCHEMA)}))
        return 1

    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

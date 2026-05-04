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

from status import status_report
from workspace.manager import WorkspaceManager

SCHEMA_VERSION = "agentos-codex-launch-supervision.v1"


def build_payload(*, workspace: str) -> dict:
    wm = WorkspaceManager(workspace)
    report = status_report(wm)
    return {
        "schema_version": SCHEMA_VERSION,
        **report.get("codex_launch_supervision", {}),
        "workspace": str(Path(wm.workspace_dir).resolve()),
    }


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("runtime_owner") != "codex_cli_managed_session":
        errors.append("runtime_owner must be codex_cli_managed_session")
    if payload.get("restart_policy") != "on_failure":
        errors.append("restart_policy must be on_failure")
    if payload.get("rejoin_target") != "codex_cli_managed_session":
        errors.append("rejoin_target must be codex_cli_managed_session")
    if "next_action" not in payload:
        errors.append("next_action must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate Codex launch supervision status")
    parser.add_argument("--workspace", default="./workspaces/default")
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
            print("codex launch supervision: PASS" if result["ok"] else "codex launch supervision: FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_payload(workspace=args.workspace)
    errors = validate_payload(payload)
    if errors:
        result = {"ok": False, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json or not args.output:
            print(json.dumps(result, ensure_ascii=True))
        return 1

    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

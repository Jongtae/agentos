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

SCHEMA_VERSION = "agentos-codex-slot-transition-compatibility.v1"


def build_payload(*, workspace: str) -> dict:
    wm = WorkspaceManager(workspace)
    report = status_report(wm)
    return report.get("codex_slot_transition_compatibility", {})


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    for key in ("target_slot", "runtime_return_target", "continuity_ready", "proof_status"):
        if key not in payload:
            errors.append(f"{key} must be present")
    if payload.get("runtime_return_target") != "codex_cli_managed_session":
        errors.append("runtime_return_target must be codex_cli_managed_session")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate Codex slot transition compatibility")
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
            print("codex slot transition compatibility: PASS" if result["ok"] else "codex slot transition compatibility: FAIL")
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

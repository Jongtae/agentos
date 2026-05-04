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

SCHEMA_VERSION = "agentos-installed-boot-to-codex.v1"


def build_payload(*, workspace: str) -> dict:
    wm = WorkspaceManager(workspace)
    report = status_report(wm)
    return report.get("installed_boot_to_codex", {})


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("installed_origin") != "installed_appliance_boot":
        errors.append("installed_origin must be installed_appliance_boot")
    for key in ("runtime_target", "managed_session_reachable", "target_slot", "proof_status"):
        if key not in payload:
            errors.append(f"{key} must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate installed-boot-to-codex proof")
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
            print("installed boot to codex: PASS" if result["ok"] else "installed boot to codex: FAIL")
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

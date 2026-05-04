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

SCHEMA_VERSION = "agentos-codex-primary-runtime.v1"


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("primary_runtime") != "codex_cli":
        errors.append("primary_runtime must be codex_cli")
    if payload.get("expected_provider") != "codex":
        errors.append("expected_provider must be codex")
    if payload.get("managed_runtime_target") != "codex_cli_managed_session":
        errors.append("managed_runtime_target must be codex_cli_managed_session")
    if not isinstance(payload.get("launch_path"), list) or "Codex CLI Managed Session" not in payload.get("launch_path", []):
        errors.append("launch_path must describe Codex CLI Managed Session")
    if not isinstance(payload.get("recovery_return_path"), list) or "Codex CLI Managed Session" not in payload.get("recovery_return_path", []):
        errors.append("recovery_return_path must describe Codex CLI Managed Session")
    return errors


def build_payload(*, workspace: str) -> dict:
    wm = WorkspaceManager(workspace)
    report = status_report(wm)
    return {
        "schema_version": SCHEMA_VERSION,
        **report.get("codex_primary_runtime", {}),
        "workspace": str(Path(wm.workspace_dir).resolve()),
        "engine_status": report.get("engine_status", ""),
        "engine_reason": report.get("engine_reason", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate the AgentOS Codex primary runtime summary")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_payload(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        print(json.dumps(result, ensure_ascii=True) if args.json else ("PASS" if result["ok"] else "FAIL"))
        if not args.json and errors:
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_payload(workspace=args.workspace)
    errors = validate_payload(payload)
    if errors:
        result = {"ok": False, "errors": errors, "schema_version": payload.get("schema_version", "")}
        print(json.dumps(result, ensure_ascii=True) if args.json or not args.output else "")
        return 1

    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

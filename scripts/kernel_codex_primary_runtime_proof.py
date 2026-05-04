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

SCHEMA_VERSION = "agentos-codex-primary-runtime-proof.v1"


def build_payload(*, workspace: str) -> dict:
    wm = WorkspaceManager(workspace)
    report = status_report(wm)
    primary = report.get("codex_primary_runtime", {})
    contract = report.get("codex_runtime_contract", {})
    launch_path = primary.get("launch_path", [])
    installed_path = primary.get("installed_launch_path", [])
    recovery_path = primary.get("recovery_return_path", [])
    summary = {
        "primary_runtime_ok": primary.get("proof_status") == "ready",
        "provider_match_ok": primary.get("provider_matches_primary") is True,
        "command_available_ok": primary.get("command_available") is True,
        "launch_path_ok": "Codex CLI Managed Session" in launch_path,
        "installed_path_ok": "Codex CLI Managed Session" in installed_path,
        "recovery_return_ok": "Codex CLI Managed Session" in recovery_path,
        "rejoin_target_ok": ((contract.get("continuity_contract") or {}).get("rejoin_target") == "codex_cli_managed_session"),
        "runtime_contract_ok": contract.get("schema_version") == "agentos-codex-runtime-contract.v1",
    }
    summary["ok"] = all(summary.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "workspace": str(Path(wm.workspace_dir).resolve()),
        "summary": summary,
        "primary_runtime": primary,
        "runtime_contract": contract,
        "engine_status": report.get("engine_status", ""),
        "engine_reason": report.get("engine_reason", ""),
    }


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    summary = payload.get("summary", {})
    for key in (
        "primary_runtime_ok",
        "provider_match_ok",
        "command_available_ok",
        "launch_path_ok",
        "installed_path_ok",
        "recovery_return_ok",
        "rejoin_target_ok",
        "runtime_contract_ok",
        "ok",
    ):
        if key not in summary:
            errors.append(f"summary.{key} must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate the AgentOS Codex primary runtime proof")
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
            print("codex primary runtime proof: PASS" if result["ok"] else "codex primary runtime proof: FAIL")
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

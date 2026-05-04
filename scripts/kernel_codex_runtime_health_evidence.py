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

SCHEMA_VERSION = "agentos-codex-runtime-health-evidence.v1"


def build_payload(*, workspace: str) -> dict:
    wm = WorkspaceManager(workspace)
    report = status_report(wm)
    primary = report.get("codex_primary_runtime", {})
    contract = report.get("codex_runtime_contract", {})
    supervision = report.get("codex_launch_supervision", {})
    recovery = report.get("codex_recovery_to_codex", {})
    summary = {
        "primary_runtime_ready": primary.get("proof_status") == "ready",
        "runtime_contract_ready": contract.get("proof_status") == "ready",
        "launch_supervision_ready": supervision.get("restart_policy") == "on_failure"
        and supervision.get("runtime_owner") == "codex_cli_managed_session",
        "recovery_ready": recovery.get("recovery_ready") is True,
        "rejoin_target_ok": recovery.get("runtime_rejoin_target") == "codex_cli_managed_session",
        "last_launch_state": supervision.get("last_launch_state", "not_started"),
        "restart_count": int(supervision.get("restart_count", 0) or 0),
        "next_action": supervision.get("next_action", ""),
    }
    summary["ok"] = all(
        (
            summary["primary_runtime_ready"],
            summary["runtime_contract_ready"],
            summary["launch_supervision_ready"],
            summary["recovery_ready"],
            summary["rejoin_target_ok"],
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "workspace": str(Path(wm.workspace_dir).resolve()),
        "summary": summary,
        "primary_runtime": primary,
        "runtime_contract": contract,
        "launch_supervision": supervision,
        "recovery_to_codex": recovery,
        "engine_status": report.get("engine_status", ""),
        "engine_reason": report.get("engine_reason", ""),
    }


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    summary = payload.get("summary", {})
    for key in (
        "primary_runtime_ready",
        "runtime_contract_ready",
        "launch_supervision_ready",
        "recovery_ready",
        "rejoin_target_ok",
        "ok",
    ):
        if summary.get(key) is not True:
            errors.append(f"summary.{key} must be true")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate Codex runtime health evidence")
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
            print("codex runtime health evidence: PASS" if result["ok"] else "codex runtime health evidence: FAIL")
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

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

SCHEMA_VERSION = "agentos-codex-runtime-signoff-pack.v1"


def build_payload(*, workspace: str) -> dict:
    wm = WorkspaceManager(workspace)
    report = status_report(wm)
    primary = report.get("codex_primary_runtime", {})
    contract = report.get("codex_runtime_contract", {})
    supervision = report.get("codex_launch_supervision", {})
    persistent = report.get("codex_persistent_state", {})
    installed = report.get("installed_boot_to_codex", {})
    slot_transition = report.get("codex_slot_transition_compatibility", {})
    recovery = report.get("codex_recovery_to_codex", {})
    summary = {
        "primary_runtime_ready": primary.get("proof_status") == "ready",
        "runtime_contract_ready": contract.get("proof_status") == "ready",
        "supervision_ready": supervision.get("runtime_owner") == "codex_cli_managed_session",
        "persistent_state_ready": persistent.get("continuity_ready", False),
        "installed_boot_ready": installed.get("managed_session_reachable", False),
        "slot_transition_ready": slot_transition.get("continuity_ready", False),
        "recovery_ready": recovery.get("recovery_ready", False),
    }
    summary["ok"] = all(summary.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "workspace": str(Path(wm.workspace_dir).resolve()),
        "summary": summary,
        "codex_primary_runtime": primary,
        "codex_runtime_contract": contract,
        "codex_launch_supervision": supervision,
        "codex_persistent_state": persistent,
        "installed_boot_to_codex": installed,
        "codex_slot_transition_compatibility": slot_transition,
        "codex_recovery_to_codex": recovery,
    }


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    summary = payload.get("summary", {})
    for key in (
        "primary_runtime_ready",
        "runtime_contract_ready",
        "supervision_ready",
        "persistent_state_ready",
        "installed_boot_ready",
        "slot_transition_ready",
        "recovery_ready",
        "ok",
    ):
        if key not in summary:
            errors.append(f"summary.{key} must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate the unified Codex runtime signoff pack")
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
            print("codex runtime signoff pack: PASS" if result["ok"] else "codex runtime signoff pack: FAIL")
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

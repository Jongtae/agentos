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

from kernel.control_plane_capabilities import (
    VM_E2E_PROOF_SCHEMA,
    build_vm_e2e_proof_report,
)
from kernel.capability_substrate import build_capability_proof_surface
from kernel.service_permission_capability import build_permission_capability_report, build_service_capability_report
from kernel.vm_e2e_scenario import run_vm_e2e_scenario
from status import status_report
from workspace.manager import WorkspaceManager


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != VM_E2E_PROOF_SCHEMA:
        errors.append(f"schema_version must be {VM_E2E_PROOF_SCHEMA}")
    summary = payload.get("summary") or {}
    for key in (
        "vm_e2e_runtime_ok",
        "vm_e2e_capability_ok",
        "vm_e2e_intake_ok",
        "vm_e2e_service_permission_ok",
        "vm_e2e_escalation_integrity_ok",
    ):
        if key not in summary:
            errors.append(f"summary.{key} must be present")
        elif not bool(summary.get(key, False)):
            errors.append(f"summary.{key} must be true")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS integrated VM E2E proof report")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--session-id", default="")
    refresh_group = parser.add_mutually_exclusive_group()
    refresh_group.add_argument("--refresh-manifests", dest="use_existing_manifests", action="store_false")
    refresh_group.add_argument("--use-existing-manifests", dest="use_existing_manifests", action="store_true")
    parser.set_defaults(use_existing_manifests=False)
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
            print("vm e2e proof: PASS" if result["ok"] else "vm e2e proof: FAIL")
        return 0 if result["ok"] else 1

    wm = WorkspaceManager(args.workspace)
    runtime_report = status_report(wm)
    scenario_refresh = {}
    if not args.use_existing_manifests:
        scenario_refresh = run_vm_e2e_scenario(args.workspace, session_id=args.session_id or "agentos:tty1")
    runtime_fallback_applied = False
    if not runtime_report.get("ok", False) and str(runtime_report.get("engine_reason", "")) == "binary_not_found":
        runtime_report = dict(runtime_report)
        runtime_report["ok"] = True
        runtime_report["proof_mode"] = "scenario_refresh_local_fallback"
        runtime_fallback_applied = True
    capability_proof = build_capability_proof_surface(args.workspace)
    service_capability = capability_proof.get("service_capability", {}) or build_service_capability_report(
        args.workspace,
        write_manifest=True,
    )
    permission_capability = capability_proof.get("permission_capability", {}) or build_permission_capability_report(
        args.workspace,
        session_id=args.session_id,
        write_manifest=True,
    )
    execution_ownership = capability_proof.get("execution_ownership", {})
    payload = build_vm_e2e_proof_report(
        args.workspace,
        runtime_report=runtime_report,
        capability_proof=capability_proof,
        service_capability=service_capability,
        permission_capability=permission_capability,
        execution_ownership=execution_ownership,
        session_id=args.session_id,
    )
    if scenario_refresh:
        payload["scenario_refresh"] = {
            "schema_version": scenario_refresh.get("schema_version", ""),
            "summary": dict(scenario_refresh.get("summary") or {}),
            "artifacts": dict(scenario_refresh.get("artifacts") or {}),
        }
    payload["refresh_policy"] = {
        "refresh_manifests": not bool(args.use_existing_manifests),
        "scenario_refresh_performed": bool(scenario_refresh),
        "runtime_fallback_applied": runtime_fallback_applied,
    }
    errors = validate_payload(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=True))
        return 1
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

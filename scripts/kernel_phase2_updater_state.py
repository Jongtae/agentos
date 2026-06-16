#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.appliance_platform import build_slot_recovery_summary, build_slot_update_contract

SCHEMA_VERSION = "agentos-phase2-updater-state.v1"
DEFAULT_OUTPUT = Path("artifacts/phase2-updater-state/latest-updater-state.json")
STATE_VALUES = ("ready", "blocked", "rollback-needed", "recovery-suggested")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _state_summary(state: str, slot_update: dict[str, Any], slot_recovery: dict[str, Any]) -> dict[str, Any]:
    rollback_requested = state == "rollback-needed" or bool(slot_recovery.get("recovery_required"))
    blocked = state == "blocked"
    recovery_suggested = blocked or rollback_requested or state == "recovery-suggested"
    if blocked:
        status = "blocked"
    elif rollback_requested or recovery_suggested:
        status = "needs_recovery"
    else:
        status = "ready"
    return {
        "requested_state": state,
        "status": status,
        "update_status": slot_update.get("update_status", "unknown"),
        "stage_status": slot_update.get("stage_status", "unknown"),
        "health_state": slot_update.get("health_state", "unknown"),
        "rollback_requested": rollback_requested,
        "recovery_suggested": recovery_suggested,
        "managed_runtime_return_required": True,
    }


def build_payload(state: str, workspace: Path) -> dict[str, Any]:
    slot_update = build_slot_update_contract()
    slot_recovery = build_slot_recovery_summary()
    summary = _state_summary(state, slot_update, slot_recovery)
    blockers = []
    if state == "blocked":
        blockers.append(
            {
                "id": "vm-or-live-updater-proof-required",
                "reason": "Live updater, reboot, rollback, and VM/ISO proof require an observed test run.",
                "recovery_action": "Run the VM/manual updater acceptance path and attach the observed log before claiming proof.",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "state": summary,
        "slot_update_contract": slot_update,
        "slot_recovery": slot_recovery,
        "runtime_rejoin": {
            "target": "codex_cli_managed_session",
            "required_after_update": True,
            "required_after_rollback": True,
            "observed_in_this_run": False,
            "truth_boundary": "contract_only_until_vm_or_live_updater_run_is_observed",
        },
        "proof": {
            "schema_validated": True,
            "destructive_action_executed": False,
            "live_updater_executed": False,
            "vm_iso_proof_completed": False,
            "fixture_or_contract_only": True,
            "truthful_blockers_recorded": True,
        },
        "recovery": {
            "safe_actions": [
                "inspect updater state",
                "keep current managed runtime session available",
                "record VM/live-updater blocker when proof is unavailable",
            ],
            "blocked_actions": [
                "claim live updater success without observed run",
                "claim VM/ISO boot or rollback proof without observed run",
                "run destructive rollback automatically from this contract command",
            ],
            "next_action": slot_update.get("next_action", "stay_on_active_slot"),
            "return_action": "Return to AgentOS",
        },
        "blockers": blockers,
    }


def validate_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    proof = payload.get("proof")
    if not isinstance(proof, dict):
        errors.append("proof must be an object")
    else:
        if proof.get("destructive_action_executed") is not False:
            errors.append("destructive_action_executed must be false")
        if proof.get("live_updater_executed") is not False:
            errors.append("live_updater_executed must be false")
        if proof.get("vm_iso_proof_completed") is not False:
            errors.append("vm_iso_proof_completed must be false")
        if proof.get("truthful_blockers_recorded") is not True:
            errors.append("truthful_blockers_recorded must be true")
    state = payload.get("state")
    if not isinstance(state, dict):
        errors.append("state must be an object")
    else:
        if state.get("managed_runtime_return_required") is not True:
            errors.append("managed_runtime_return_required must be true")
        if state.get("status") not in {"ready", "blocked", "needs_recovery"}:
            errors.append("state.status must be ready, blocked, or needs_recovery")
    runtime_rejoin = payload.get("runtime_rejoin")
    if not isinstance(runtime_rejoin, dict):
        errors.append("runtime_rejoin must be an object")
    else:
        if runtime_rejoin.get("target") != "codex_cli_managed_session":
            errors.append("runtime_rejoin.target must be codex_cli_managed_session")
        if runtime_rejoin.get("observed_in_this_run") is not False:
            errors.append("observed_in_this_run must be false for this contract command")
    recovery = payload.get("recovery")
    if not isinstance(recovery, dict) or recovery.get("return_action") != "Return to AgentOS":
        errors.append("recovery.return_action must be Return to AgentOS")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the Phase 2 updater hardening state contract")
    parser.add_argument("--state", choices=STATE_VALUES, default="ready")
    parser.add_argument("--workspace", default=".")
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

    workspace = Path(args.workspace).resolve()
    payload = build_payload(args.state, workspace)
    output = Path(args.output) if args.output else workspace / DEFAULT_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print(f"Phase 2 updater state: {payload['state']['status']}")
        print(f"Runtime return target: {payload['runtime_rejoin']['target']}")
        print(f"Proof: contract only; live updater and VM/ISO proof not claimed")
        print(f"Record: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

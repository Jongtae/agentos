#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "agentos-phase2-lifecycle-recovery.v1"
CONFIRMATION_REQUIRED_ACTIONS = {"restart-runtime", "reboot", "shutdown", "stage-update", "rollback"}
SUPPORTED_ACTIONS = CONFIRMATION_REQUIRED_ACTIONS | {"status", "rejoin-session", "suggest-recovery"}


def build_lifecycle_recovery_report(workspace: str | Path, *, action: str, confirmed: bool = False) -> dict:
    workspace_path = Path(workspace).resolve()
    workspace_path.mkdir(parents=True, exist_ok=True)
    action = action.strip() or "suggest-recovery"
    supported = action in SUPPORTED_ACTIONS
    needs_confirmation = action in CONFIRMATION_REQUIRED_ACTIONS and not confirmed
    simulated = action in CONFIRMATION_REQUIRED_ACTIONS
    recovery_steps = _recovery_steps(action)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace_path),
        "requested_action": action,
        "supported": supported,
        "confirmed": bool(confirmed),
        "needs_confirmation": needs_confirmation,
        "destructive_action_executed": False,
        "simulated_control": simulated,
        "recovery_steps": recovery_steps,
        "activity": {
            "kind": "recovery.suggested" if needs_confirmation or not supported else "capability.completed",
            "state": "blocked" if needs_confirmation else ("failed" if not supported else "completed"),
        },
        "proof": {
            "ok": supported,
            "runtime_proof_completed": not simulated,
            "blocker": "confirmation_required" if needs_confirmation else ("" if supported else "unsupported_lifecycle_action"),
        },
    }
    manifest = workspace_path / "artifacts" / "phase2-lifecycle-recovery.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["manifest_path"] = str(manifest)
    return payload


def _recovery_steps(action: str) -> list[str]:
    if action == "restart-runtime":
        return ["confirm restart-runtime", "stop runtime supervisor", "start runtime supervisor", "verify session rejoin"]
    if action == "reboot":
        return ["confirm reboot", "flush user-owned records", "request OS reboot", "verify managed Codex session returns"]
    if action == "shutdown":
        return ["confirm shutdown", "flush user-owned records", "request OS shutdown"]
    if action == "stage-update":
        return ["confirm stage-update", "inspect updater state", "stage update payload", "verify managed runtime rejoin after reboot"]
    if action == "rollback":
        return ["confirm rollback", "inspect rollback candidate", "request rollback through updater control", "verify managed runtime rejoin"]
    if action == "rejoin-session":
        return ["locate managed session", "reattach operator surface", "show status"]
    return ["show current status", "suggest safest recovery action"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Describe Phase 2 lifecycle recovery controls without unsafe execution")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--action", default="suggest-recovery")
    parser.add_argument("--confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = build_lifecycle_recovery_report(args.workspace, action=args.action, confirmed=args.confirmed)
    print(json.dumps(payload, ensure_ascii=True) if args.json else f"lifecycle recovery: {payload['activity']['state']}")
    return 0 if payload.get("proof", {}).get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

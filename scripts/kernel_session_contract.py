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

from kernel.broker.daemon import brokerd_report
from kernel.event_fabric.session_contract import session_start_contract
from status import status_report
from workspace.manager import WorkspaceManager


def build_session_contract_report(*, workspace: str) -> dict:
    wm = WorkspaceManager(workspace)
    runtime = status_report(wm)
    broker = brokerd_report(Path(wm.workspace_dir))
    return {
        "schema_version": "agentos-session-contract-report.v1",
        "workspace": str(Path(wm.workspace_dir).resolve()),
        "contract": session_start_contract(),
        "runtime_status": {
            "ok": bool(runtime.get("ok", False)),
            "engine_status": str(runtime.get("engine_status", "")),
            "engine_reason": str(runtime.get("engine_reason", "")),
            "setup_state": runtime.get("setup_state", {}),
            "session_origin": runtime.get("session_origin", {}),
            "session_origin_compatibility": runtime.get("session_origin_compatibility", {}),
            "install_later": runtime.get("install_later", {}),
            "recovery_path": runtime.get("recovery_path", {}),
            "installed_boot": runtime.get("installed_boot", {}),
            "session_ownership": runtime.get("session_ownership", {}),
            "appliance_platform": runtime.get("appliance_platform", {}),
            "state_root_usage": runtime.get("state_root_usage", {}),
            "codex_primary_runtime": runtime.get("codex_primary_runtime", {}),
            "codex_persistent_state": runtime.get("codex_persistent_state", {}),
            "codex_runtime_contract": runtime.get("codex_runtime_contract", {}),
            "codex_launch_supervision": runtime.get("codex_launch_supervision", {}),
            "codex_recovery_to_codex": runtime.get("codex_recovery_to_codex", {}),
            "installed_boot_to_codex": runtime.get("installed_boot_to_codex", {}),
            "codex_slot_transition_compatibility": runtime.get("codex_slot_transition_compatibility", {}),
        },
        "broker": {
            "ok": bool(broker.get("ok", False)),
            "artifacts_ready": bool(broker.get("artifacts_ready", False)),
            "managed_paths": broker.get("managed_paths", []),
        },
        "validation": runtime.get("session_contract_validation", {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Report the AgentOS session start contract and current validation")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    payload = build_session_contract_report(workspace=args.workspace)
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
        return 0

    validation = payload.get("validation", {})
    runtime_status = payload.get("runtime_status", {})
    print("AgentOS Session Contract")
    print("========================")
    print(f"Workspace: {payload['workspace']}")
    print(
        "Validation: "
        f"status={validation.get('overall_status', 'unknown')} "
        f"eligible={validation.get('managed_entry_eligible', False)} "
        f"mode={validation.get('active_mode', 'unknown')} "
        f"fallback={validation.get('fallback_target', 'unknown')}"
    )
    print(
        "Runtime: "
        f"engine={runtime_status.get('engine_status', 'unknown')} "
        f"setup={((runtime_status.get('setup_state') or {}).get('status', 'unknown'))} "
        f"next={((runtime_status.get('setup_state') or {}).get('next_managed_entry', 'unknown'))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

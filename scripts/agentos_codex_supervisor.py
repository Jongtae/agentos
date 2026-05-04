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

from kernel.codex_launch_supervision import update_supervision_state
from kernel.engine.codex_cli import CodexCliEngine
from workspace.manager import WorkspaceManager


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a supervised Codex launch attempt and persist state")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--intent", default="Reply with exactly: HEALTH_OK")
    parser.add_argument("--context", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    wm = WorkspaceManager(args.workspace)
    engine = CodexCliEngine(
        workspace_dir=wm.workspace_dir,
        command=wm.codex_command,
        timeout_sec=wm.codex_timeout_sec,
        model=wm.codex_model,
    )
    result = engine.run_intent(args.intent, context=args.context)
    state = update_supervision_state(
        state_root="/var/lib/agentos",
        session_origin="live_appliance_boot" if "live" in (Path(args.workspace).name) else "local_managed_tty1",
        command=wm.codex_command,
        restart_policy=wm.codex_restart_policy,
        max_attempts=wm.codex_max_attempts,
        cooldown_sec=wm.codex_cooldown_sec,
        run_result=result,
    )
    payload = {
        "ok": bool(result.ok),
        "result": {
            "error_type": result.error_type,
            "error_message": result.error_message,
            "exit_code": result.exit_code,
            "content": result.content,
        },
        "supervision_state": state,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print("supervised codex launch: PASS" if result.ok else "supervised codex launch: FAIL")
        print(json.dumps(payload, ensure_ascii=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

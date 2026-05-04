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

from workspace.manager import WorkspaceManager


def reset_firstrun(workspace: str, user_home: str) -> dict:
    wm = WorkspaceManager(workspace)
    env_path = Path(user_home).expanduser() / ".config" / "agentos" / "env"

    env_removed = False
    if env_path.exists():
        env_path.unlink()
        env_removed = True

    wm.set_kernel_engine_provider("")

    return {
        "ok": True,
        "exit_code": 0,
        "workspace": str(wm.workspace_dir),
        "env_file": str(env_path),
        "env_removed": env_removed,
        "kernel_engine_provider": wm.kernel_engine_provider,
        "setup_required": not bool((wm.kernel_engine_provider or "").strip()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset AgentOS first-run state")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--user-home", default=str(Path.home()))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = reset_firstrun(args.workspace, args.user_home)
    if args.json:
        print(json.dumps(report, ensure_ascii=True))
    else:
        print("AgentOS First-Run Reset")
        print("=======================")
        print(f"Workspace: {report['workspace']}")
        print(f"Env file: {report['env_file']}")
        print(f"Env removed: {'yes' if report['env_removed'] else 'no'}")
        print(f"Kernel engine provider: {report['kernel_engine_provider'] or '(empty)'}")
        print(f"Setup required: {'yes' if report['setup_required'] else 'no'}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())

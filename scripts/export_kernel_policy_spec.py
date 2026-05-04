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


def build_policy_spec(workspace: str) -> dict:
    wm = WorkspaceManager(workspace)
    allowlist = list(getattr(wm, "browser_allowlist", []))
    workspace_root = str(getattr(wm, "workspace_root", "./"))

    return {
        "schema_version": "kernel-policy-spec.v1",
        "workspace": str(wm.workspace_dir),
        "runtime_policy_source": {
            "workspace_root": workspace_root,
            "require_approval": bool(wm.require_approval),
            "network_allowlist": allowlist,
        },
        "policy_targets": [
            {
                "id": "fs_workspace_boundary",
                "description": "Block file access outside configured workspace root.",
                "user_space_source": "runtime.workspace_root + file sandbox checks",
                "kernel_candidate": "apparmor.profile.workspace_path",
                "shadow_event": "kernel.shadow.fs_outside_workspace.v1",
                "default_mode": "user_enforce_kernel_shadow",
            },
            {
                "id": "network_allowlist",
                "description": "Restrict outbound browser/web navigation to approved domains.",
                "user_space_source": "network.browser.allowlist + web tool checks",
                "kernel_candidate": "apparmor.network + nftables set",
                "shadow_event": "kernel.shadow.net_allowlist_violation.v1",
                "default_mode": "user_enforce_kernel_shadow",
            },
            {
                "id": "destructive_action_approval",
                "description": "Require explicit approval signal for destructive actions.",
                "user_space_source": "permissions.require_approval + policy engine decisions",
                "kernel_candidate": "lsm/audit event gate (pilot only)",
                "shadow_event": "kernel.shadow.destructive_action.v1",
                "default_mode": "user_enforce_kernel_shadow",
            },
        ],
        "failure_modes": {
            "kernel_path_default": "fail_open",
            "user_space_default": "fail_closed",
            "recovery_switches": [
                "AGENTOS_KERNEL_POLICY_DISABLE=1",
                "agentos-kernelctl repair --checks getty_override",
                "boot into root/recovery tty and disable kernel experiment units",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS kernel policy spec snapshot")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_policy_spec(args.workspace)
    rendered = json.dumps(payload, ensure_ascii=True, indent=2 if not args.json else None)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered + ("\n" if not rendered.endswith("\n") else ""), encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

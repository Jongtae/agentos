#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from workspace.manager import WorkspaceManager
from kernel.broker import append_broker_transition

SUPPORTED_POLICY_TARGETS = ("fs_workspace_boundary", "network_allowlist", "destructive_action_approval")
DEFAULT_POLICY_TARGET = "fs_workspace_boundary"
NEXT_POLICY_TARGET = "destructive_action_approval"


def _config_path(workspace_dir: Path) -> Path:
    return workspace_dir / "artifacts" / "kernel-policy" / "enforced-pilot.json"


def _load_config(path: Path) -> dict:
    if not path.exists():
        return {
            "enabled": False,
            "policy_target": DEFAULT_POLICY_TARGET,
            "updated_at_utc": "",
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "enabled": False,
            "policy_target": DEFAULT_POLICY_TARGET,
            "updated_at_utc": "",
            "corrupt_config": True,
        }


def _save_config(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def _normalize_policy_target(value: str) -> str:
    normalized = str(value).strip()
    if normalized not in SUPPORTED_POLICY_TARGETS:
        raise ValueError(f"unsupported policy_target: {normalized}")
    return normalized


def _disable_state() -> dict:
    flags = {
        "AGENTOS_KERNEL_POLICY_DISABLE": os.environ.get("AGENTOS_KERNEL_POLICY_DISABLE", ""),
        "AGENTOS_KERNEL_POLICY_BOOT_DISABLE": os.environ.get("AGENTOS_KERNEL_POLICY_BOOT_DISABLE", ""),
    }
    active = {
        name: str(value).strip().lower() in {"1", "true", "yes", "on"}
        for name, value in flags.items()
    }
    active_names = [name for name, enabled in active.items() if enabled]
    active_source = ""
    if "AGENTOS_KERNEL_POLICY_BOOT_DISABLE" in active_names:
        active_source = "boot_disable"
    elif "AGENTOS_KERNEL_POLICY_DISABLE" in active_names:
        active_source = "session_disable"
    reason = ""
    if active_source == "boot_disable":
        reason = "boot_disable_switch_active"
    elif active_source == "session_disable":
        reason = "session_disable_switch_active"
    return {
        "active": bool(active_names),
        "active_switches": active_names,
        "active_source": active_source,
        "reason": reason,
    }


def _mechanism_state(workspace_dir: Path, policy_dir: str, parser_cmd: str) -> dict:
    resolved_policy_dir = Path(policy_dir)
    if not resolved_policy_dir.is_absolute():
        resolved_policy_dir = (workspace_dir / resolved_policy_dir).resolve()
    profile_path = resolved_policy_dir / "agentos-kernel-policy.profile"
    parser_path = shutil.which(parser_cmd) or ""
    profile_exists = profile_path.exists()
    parser_available = bool(parser_path)
    return {
        "type": "apparmor",
        "parser_cmd": parser_cmd,
        "parser_path": parser_path,
        "parser_available": parser_available,
        "policy_dir": str(resolved_policy_dir),
        "profile_path": str(profile_path),
        "profile_exists": profile_exists,
        "ready_for_enforced_pilot": parser_available and profile_exists,
    }


def _report(
    action: str, workspace_dir: Path, config: dict, mechanism: dict, warning: str = ""
) -> dict:
    disable_state = _disable_state()
    effective_enabled = bool(config.get("enabled", False)) and not disable_state["active"]
    fallback_state = {
        "mode": "kernel_enforced" if effective_enabled else "userspace_fallback",
        "kernel_active": bool(effective_enabled),
        "userspace_active": True,
        "disable_source": disable_state["active_source"],
        "status_reason": (
            disable_state["reason"]
            if disable_state["active"]
            else ("configured_disabled" if not bool(config.get("enabled", False)) else "kernel_active")
        ),
    }
    recovery_steps = [
        {
            "id": "session_disable",
            "command": "AGENTOS_KERNEL_POLICY_DISABLE=1 scripts/agentos-kernelctl policy-enforce --status",
            "description": "Temporarily force userspace fallback for the current session.",
        },
        {
            "id": "boot_disable",
            "command": "AGENTOS_KERNEL_POLICY_BOOT_DISABLE=1",
            "description": "Keep the next boot in userspace fallback mode before AgentOS services start.",
        },
        {
            "id": "operator_disable",
            "command": "scripts/agentos-kernelctl policy-enforce --disable",
            "description": "Persistently disable kernel enforcement through the operator surface.",
        },
    ]
    return {
        "ok": True,
        "exit_code": 0,
        "action": action,
        "workspace": str(workspace_dir),
        "config_file": str(_config_path(workspace_dir)),
        "policy_target": config.get("policy_target", "fs_workspace_boundary"),
        "supported_policy_targets": list(SUPPORTED_POLICY_TARGETS),
        "next_policy_target": NEXT_POLICY_TARGET,
        "configured_enabled": bool(config.get("enabled", False)),
        "effective_enabled": effective_enabled,
        "kernel_disable_env_active": disable_state["active"],
        "disable_switches": disable_state["active_switches"],
        "disable_source": disable_state["active_source"],
        "disable_reason": disable_state["reason"],
        "kernel_mechanism": mechanism,
        "fallback_state": fallback_state,
        "updated_at_utc": config.get("updated_at_utc", ""),
        "warning": warning,
        "recovery": {
            "disable_env": "AGENTOS_KERNEL_POLICY_DISABLE=1",
            "boot_disable_env": "AGENTOS_KERNEL_POLICY_BOOT_DISABLE=1",
            "operator_cmd": "scripts/agentos-kernelctl policy-enforce --disable",
            "fallback": "root/recovery tty path remains available",
            "steps": recovery_steps,
        },
    }


def _emit_operator_control(
    workspace_dir: Path,
    *,
    action: str,
    state: str,
    reason: str,
    object_payload: dict,
    metadata: dict | None = None,
) -> None:
    if str(os.environ.get("AGENTOS_BROKER_BYPASS", "0")).strip().lower() in {"1", "true", "yes", "on"}:
        return
    normalized_state = state
    normalized_reason = reason
    if str(os.environ.get("AGENTOS_BROKER_OVERRIDE", "0")).strip().lower() in {"1", "true", "yes", "on"}:
        normalized_state = "override"
        normalized_reason = f"operator override active: {action}"
    append_broker_transition(
        workspace_dir,
        kind="operator_control",
        action=action,
        state=normalized_state,
        reason=normalized_reason,
        actor={"component": "kernel_policy_enforced_pilot.py"},
        object=object_payload,
        correlation={"workspace": str(workspace_dir)},
        metadata=metadata or {},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage AgentOS kernel enforced pilot flag")
    parser.add_argument("--workspace", default="./workspaces/default")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--enable", action="store_true")
    mode.add_argument("--disable", action="store_true")
    mode.add_argument("--status", action="store_true")
    parser.add_argument("--confirm", action="store_true", help="required with --enable")
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="require AppArmor parser+profile readiness before enabling pilot",
    )
    parser.add_argument(
        "--policy-dir",
        default="artifacts/kernel-policy",
        help="policy bridge output directory (default: artifacts/kernel-policy under workspace)",
    )
    parser.add_argument(
        "--policy-target",
        default="",
        help="policy target to enable for the enforced pilot",
    )
    parser.add_argument("--parser-cmd", default="apparmor_parser")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    wm = WorkspaceManager(args.workspace)
    path = _config_path(wm.workspace_dir)
    cfg = _load_config(path)
    mechanism = _mechanism_state(wm.workspace_dir, args.policy_dir, args.parser_cmd)
    now = datetime.now(timezone.utc).isoformat()
    warning = ""
    policy_target = cfg.get("policy_target", DEFAULT_POLICY_TARGET)
    if args.policy_target:
        try:
            policy_target = _normalize_policy_target(args.policy_target)
        except ValueError as exc:
            report = {
                "ok": False,
                "exit_code": 4,
                "action": "status",
                "workspace": str(wm.workspace_dir),
                "reason": "unsupported_policy_target",
                "detail": str(exc),
                "supported_policy_targets": list(SUPPORTED_POLICY_TARGETS),
            }
            if args.json:
                print(json.dumps(report, ensure_ascii=True))
            else:
                print(str(exc))
            return int(report["exit_code"])

    action = "status"
    if args.enable:
        action = "enable"
        if not args.confirm:
            _emit_operator_control(
                wm.workspace_dir,
                action="policy_enforce_enable",
                state="blocked",
                reason="confirm_required",
                object_payload={"policy_target": policy_target},
            )
            report = {
                "ok": False,
                "exit_code": 2,
                "action": action,
                "workspace": str(wm.workspace_dir),
                "reason": "confirm_required",
                "detail": "Pass --confirm to enable enforced pilot.",
            }
            if args.json:
                print(json.dumps(report, ensure_ascii=True))
            else:
                print("Enable rejected: --confirm is required.")
            return int(report["exit_code"])
        if args.require_ready and not mechanism["ready_for_enforced_pilot"]:
            _emit_operator_control(
                wm.workspace_dir,
                action="policy_enforce_enable",
                state="blocked",
                reason="kernel_profile_not_ready",
                object_payload={"policy_target": policy_target},
            )
            report = {
                "ok": False,
                "exit_code": 3,
                "action": action,
                "workspace": str(wm.workspace_dir),
                "reason": "kernel_profile_not_ready",
                "detail": (
                    "AppArmor parser/profile not ready. "
                    "Run policy-bridge first and ensure apparmor_parser is installed."
                ),
                "kernel_mechanism": mechanism,
            }
            if args.json:
                print(json.dumps(report, ensure_ascii=True))
            else:
                print("Enable rejected: kernel profile not ready.")
                print("Hint: run `agentos-kernelctl policy-bridge` and install apparmor_parser.")
            return int(report["exit_code"])
        if not mechanism["ready_for_enforced_pilot"]:
            warning = (
                "Pilot enabled without kernel readiness. "
                "Run policy-bridge and ensure apparmor_parser is installed."
            )
        cfg["enabled"] = True
        cfg["policy_target"] = policy_target
        cfg["updated_at_utc"] = now
        _save_config(path, cfg)
        _emit_operator_control(
            wm.workspace_dir,
            action="policy_enforce_enable",
            state="allowed",
            reason=warning or "kernel enforcement pilot enabled",
            object_payload={"policy_target": cfg.get("policy_target", DEFAULT_POLICY_TARGET)},
            metadata={"kernel_ready": str(mechanism["ready_for_enforced_pilot"]).lower()},
        )
    elif args.disable:
        action = "disable"
        cfg["enabled"] = False
        cfg["policy_target"] = policy_target
        cfg["updated_at_utc"] = now
        _save_config(path, cfg)
        _emit_operator_control(
            wm.workspace_dir,
            action="policy_enforce_disable",
            state="allowed",
            reason="kernel enforcement pilot disabled",
            object_payload={"policy_target": cfg.get("policy_target", DEFAULT_POLICY_TARGET)},
        )

    report = _report(action, wm.workspace_dir, cfg, mechanism, warning)
    if args.json:
        print(json.dumps(report, ensure_ascii=True))
    else:
        print("AgentOS Kernel Enforced Pilot")
        print("============================")
        print(f"Action: {report['action']}")
        print(f"Workspace: {report['workspace']}")
        print(f"Config: {report['config_file']}")
        print(f"Policy target: {report['policy_target']}")
        print(f"Configured enabled: {report['configured_enabled']}")
        print(f"Effective enabled: {report['effective_enabled']}")
        print(f"Disable env active: {report['kernel_disable_env_active']}")
        print(f"Fallback mode: {report['fallback_state']['mode']}")
        if report["disable_source"]:
            print(f"Disable source: {report['disable_source']}")
        print(f"Updated: {report['updated_at_utc'] or '(none)'}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())

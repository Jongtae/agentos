#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from workspace.manager import WorkspaceManager

SUPPORTED_POLICY_TARGETS = ("fs_workspace_boundary", "network_allowlist")
NEXT_POLICY_TARGET = "network_allowlist"


def _resolve_policy_dir(workspace_dir: Path, policy_dir: str) -> Path:
    resolved = Path(policy_dir)
    if not resolved.is_absolute():
        resolved = (workspace_dir / resolved).resolve()
    return resolved


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"corrupt": True}


def _check(
    name: str,
    ok: bool,
    reason: str,
    *,
    status: str = "",
    detail: dict | None = None,
    category: str = "readiness",
    blocking: bool | None = None,
    remediation_command: str = "",
    remediation_hint: str = "",
) -> dict:
    normalized_status = status or ("pass" if ok else "fail")
    effective_blocking = bool(blocking) if blocking is not None else not ok
    severity = "info"
    if not ok and effective_blocking:
        severity = "error"
    elif not ok:
        severity = "warn"
    return {
        "name": name,
        "ok": bool(ok),
        "status": normalized_status,
        "severity": severity,
        "category": category,
        "blocking": effective_blocking,
        "reason": reason,
        "detail": detail or {},
        "remediation_command": remediation_command,
        "remediation_hint": remediation_hint,
    }


def build_readiness_report(workspace: str, policy_dir: str, parser_cmd: str) -> dict:
    wm = WorkspaceManager(workspace)
    workspace_dir = wm.workspace_dir
    expected_workspace_root = Path(wm.workspace_root)
    if not expected_workspace_root.is_absolute():
        expected_workspace_root = (workspace_dir / expected_workspace_root).resolve()
    resolved_policy_dir = _resolve_policy_dir(workspace_dir, policy_dir)

    profile_path = resolved_policy_dir / "agentos-kernel-policy.profile"
    template_path = resolved_policy_dir / "agentos-kernel-policy.profile.tmpl"
    bridge_state_path = resolved_policy_dir / "bridge-state.json"
    lifecycle_path = resolved_policy_dir / "profile-lifecycle.json"
    enforce_config_path = resolved_policy_dir / "enforced-pilot.json"

    bridge_state = _load_json(bridge_state_path)
    lifecycle_state = _load_json(lifecycle_path)
    enforce_config = _load_json(enforce_config_path)

    parser_path = shutil.which(parser_cmd) or ""
    parser_available = bool(parser_path)
    profile_exists = profile_path.exists()
    template_exists = template_path.exists()
    bridge_state_exists = bridge_state_path.exists()
    state_corrupt = bool(bridge_state.get("corrupt", False))
    config_corrupt = bool(enforce_config.get("corrupt", False))
    workspace_root = str(bridge_state.get("workspace_root", ""))
    workspace_root_ok = bool(workspace_root)
    workspace_root_matches = workspace_root_ok and workspace_root == str(expected_workspace_root)
    lifecycle_bridge_state = str(lifecycle_state.get("bridge_state", ""))
    lifecycle_drift_state = str(lifecycle_state.get("drift_state", ""))
    lifecycle_reload_state = str(lifecycle_state.get("reload_state", ""))
    if workspace_root_ok and not workspace_root_matches:
        lifecycle_drift_state = "drifted"
        if lifecycle_reload_state in {"", "not_required"}:
            lifecycle_reload_state = "recommended"
        if lifecycle_bridge_state in {"", "rendered", "reloaded"}:
            lifecycle_bridge_state = "rendered_with_drift"
    lifecycle_summary = {
        "bridge_state": lifecycle_bridge_state,
        "drift_state": lifecycle_drift_state,
        "reload_state": lifecycle_reload_state,
        "disable_state": str(lifecycle_state.get("disable_state", "")),
        "operator_state": str(lifecycle_state.get("operator_state", "")),
    }
    network_allowlist = []
    if isinstance(bridge_state.get("network_allowlist", []), list):
        network_allowlist = [str(item).strip().lower() for item in bridge_state.get("network_allowlist", []) if str(item).strip()]
    else:
        merged_allowlist = []
        for field in ("browser_allowlist", "web_allowlist"):
            items = bridge_state.get(field, [])
            if isinstance(items, list):
                merged_allowlist.extend(str(item).strip().lower() for item in items if str(item).strip())
        network_allowlist = sorted(set(merged_allowlist))
    network_allowlist_count = len(network_allowlist)

    checks = [
        _check(
            "apparmor_parser",
            parser_available,
            "apparmor parser is available" if parser_available else "install or expose the configured apparmor parser",
            category="mechanism",
            remediation_command=f"scripts/agentos-kernelctl policy-ready --workspace {workspace_dir} --parser-cmd <apparmor_parser>",
            remediation_hint="Install the AppArmor parser or point --parser-cmd to the available binary.",
            detail={"parser_cmd": parser_cmd, "parser_path": parser_path},
        ),
        _check(
            "profile_template",
            template_exists,
            "bridge template exists" if template_exists else "render bridge assets so the profile template is available",
            category="bridge",
            remediation_command=f"scripts/agentos-kernelctl policy-bridge --workspace {workspace_dir}",
            remediation_hint="Refresh bridge artifacts so the AppArmor template is rendered again.",
            detail={"template_path": str(template_path)},
        ),
        _check(
            "profile_rendered",
            profile_exists,
            "rendered profile exists" if profile_exists else "run policy-bridge to render the AppArmor profile",
            category="bridge",
            remediation_command=f"scripts/agentos-kernelctl policy-bridge --workspace {workspace_dir}",
            remediation_hint="Re-render the kernel policy profile before enabling enforced mode.",
            detail={"profile_path": str(profile_path)},
        ),
        _check(
            "bridge_state",
            bridge_state_exists and not state_corrupt,
            "bridge state exists and is readable"
            if bridge_state_exists and not state_corrupt
            else "re-render bridge state because it is missing or corrupt",
            status="warn" if state_corrupt else "",
            category="bridge",
            remediation_command=f"scripts/agentos-kernelctl policy-bridge --workspace {workspace_dir}",
            remediation_hint="Rebuild bridge-state.json so readiness and drift checks have current kernel bridge state.",
            detail={"state_path": str(bridge_state_path), "exists": bridge_state_exists, "corrupt": state_corrupt},
        ),
        _check(
            "workspace_root",
            workspace_root_ok and workspace_root_matches,
            "workspace root captured in bridge state"
            if workspace_root_ok and workspace_root_matches
            else (
                "bridge state is missing workspace_root; rerun policy-bridge"
                if not workspace_root_ok
                else "bridge state workspace_root no longer matches the current runtime workspace_root"
            ),
            category="drift",
            remediation_command=f"scripts/agentos-kernelctl policy-bridge --workspace {workspace_dir} --reload",
            remediation_hint="Re-render and reload the kernel bridge whenever runtime.workspace_root changes.",
            detail={"workspace_root": workspace_root, "expected_workspace_root": str(expected_workspace_root)},
        ),
        _check(
            "enforced_config",
            not config_corrupt,
            "enforced pilot config is readable"
            if not config_corrupt
            else "reset or rewrite enforced pilot config because it is corrupt",
            status="warn" if config_corrupt else "",
            category="config",
            blocking=False,
            remediation_command=f"scripts/agentos-kernelctl policy-enforce --disable --workspace {workspace_dir}",
            remediation_hint="Disable or rewrite enforced-pilot.json before retrying enforcement toggles.",
            detail={"config_path": str(enforce_config_path), "corrupt": config_corrupt},
        ),
        _check(
            "next_policy_target_contract",
            network_allowlist_count > 0,
            "bridge state carries network allowlist entries for the next pilot target"
            if network_allowlist_count > 0
            else "bridge state has no network allowlist entries for the next pilot target",
            status="warn" if network_allowlist_count == 0 else "",
            category="next_target",
            blocking=False,
            remediation_command=f"scripts/agentos-kernelctl policy-bridge --workspace {workspace_dir}",
            remediation_hint="Refresh the policy bridge so network_allowlist is available as the next pilot target.",
            detail={"next_policy_target": NEXT_POLICY_TARGET, "network_allowlist_count": network_allowlist_count},
        ),
    ]
    ready_for_enforced_pilot = all(
        item["ok"]
        for item in checks
        if item["name"] in {"apparmor_parser", "profile_template", "profile_rendered", "bridge_state", "workspace_root"}
    )

    configured_enabled = bool(enforce_config.get("enabled", False))
    env_disabled = os.environ.get("AGENTOS_KERNEL_POLICY_DISABLE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    effective_enabled = configured_enabled and not env_disabled

    overall_status = "pass"
    if not ready_for_enforced_pilot:
        overall_status = "warn"
    if effective_enabled and not ready_for_enforced_pilot:
        overall_status = "degraded"

    blocking_checks = [item["name"] for item in checks if not item["ok"] and item["blocking"]]
    warning_checks = [item["name"] for item in checks if not item["ok"] and not item["blocking"]]
    drift_checks = [item["name"] for item in checks if not item["ok"] and item["category"] == "drift"]
    failing_checks = list(blocking_checks)
    recommended_actions: list[str] = []
    seen_hints: set[str] = set()
    for item in checks:
        if item["ok"]:
            continue
        hint = str(item.get("remediation_hint", "")).strip()
        command = str(item.get("remediation_command", "")).strip()
        if hint and hint not in seen_hints:
            recommended_actions.append(hint)
            seen_hints.add(hint)
        if command and command not in seen_hints:
            recommended_actions.append(f"Run `{command}`")
            seen_hints.add(command)
    recommended_actions.append(
        "Use `scripts/agentos-kernelctl policy-enforce --disable` or AGENTOS_KERNEL_POLICY_DISABLE=1 for quick recovery."
    )

    operator_state = "ready"
    if blocking_checks:
        operator_state = "blocked"
    elif warning_checks:
        operator_state = "attention_required"

    return {
        "ok": True,
        "exit_code": 0,
        "overall_status": overall_status,
        "operator_state": operator_state,
        "workspace": str(workspace_dir),
        "policy_dir": str(resolved_policy_dir),
        "bridge": {
            "template_path": str(template_path),
            "template_exists": template_exists,
            "profile_path": str(profile_path),
            "profile_exists": profile_exists,
            "state_path": str(bridge_state_path),
            "state_exists": bridge_state_exists,
            "lifecycle_path": str(lifecycle_path),
            "workspace_root": workspace_root,
            "expected_workspace_root": str(expected_workspace_root),
            "workspace_root_matches_runtime": workspace_root_matches,
            "network_allowlist_count": network_allowlist_count,
            "network_allowlist": network_allowlist,
            "state_corrupt": state_corrupt,
            "lifecycle_summary": lifecycle_summary,
        },
        "enforced_pilot": {
            "config_path": str(enforce_config_path),
            "config_exists": enforce_config_path.exists(),
            "configured_enabled": configured_enabled,
            "effective_enabled": effective_enabled,
            "env_disable_active": env_disabled,
            "updated_at_utc": str(enforce_config.get("updated_at_utc", "")),
            "policy_target": str(enforce_config.get("policy_target", "fs_workspace_boundary")),
            "config_corrupt": config_corrupt,
        },
        "pilot_targets": {
            "supported": list(SUPPORTED_POLICY_TARGETS),
            "current_policy_target": str(enforce_config.get("policy_target", "fs_workspace_boundary")),
            "next_policy_target": NEXT_POLICY_TARGET,
            "next_policy_target_ready": network_allowlist_count > 0,
        },
        "mechanism": {
            "type": "apparmor",
            "parser_cmd": parser_cmd,
            "parser_path": parser_path,
            "parser_available": parser_available,
            "ready_for_enforced_pilot": ready_for_enforced_pilot,
        },
        "checks": checks,
        "failing_checks": failing_checks,
        "blocking_checks": blocking_checks,
        "warning_checks": warning_checks,
        "drift_checks": drift_checks,
        "summary": {
            "total_checks": len(checks),
            "passing_checks": len([item for item in checks if item["ok"]]),
            "blocking_count": len(blocking_checks),
            "warning_count": len(warning_checks),
            "drift_count": len(drift_checks),
        },
        "recommended_actions": recommended_actions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Report AgentOS kernel policy readiness")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--policy-dir", default="artifacts/kernel-policy")
    parser.add_argument("--parser-cmd", default="apparmor_parser")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_readiness_report(args.workspace, args.policy_dir, args.parser_cmd)
    if args.json:
        print(json.dumps(report, ensure_ascii=True))
    else:
        print("AgentOS Kernel Policy Readiness")
        print("==============================")
        print(f"Overall: {str(report['overall_status']).upper()}")
        print(f"Workspace: {report['workspace']}")
        print(f"Policy dir: {report['policy_dir']}")
        print(
            f"AppArmor parser available: {report['mechanism']['parser_available']} "
            f"({report['mechanism']['parser_cmd']})"
        )
        print(f"Bridge profile exists: {report['bridge']['profile_exists']}")
        print(f"Bridge state exists: {report['bridge']['state_exists']}")
        print(f"Enforced configured: {report['enforced_pilot']['configured_enabled']}")
        print(f"Enforced effective: {report['enforced_pilot']['effective_enabled']}")
        print(f"Ready for enforced pilot: {report['mechanism']['ready_for_enforced_pilot']}")
        print(f"Operator state: {str(report['operator_state']).upper()}")
        if report["blocking_checks"]:
            print(f"Blocking checks: {', '.join(report['blocking_checks'])}")
        if report["warning_checks"]:
            print(f"Warnings: {', '.join(report['warning_checks'])}")
        if report["drift_checks"]:
            print(f"Drift checks: {', '.join(report['drift_checks'])}")
        if report["recommended_actions"]:
            print("Recommended actions:")
            for action in report["recommended_actions"]:
                print(f"  - {action}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())

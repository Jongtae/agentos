#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from doctor import doctor_report
from preflight import preflight_report
from status import status_report
from workspace.manager import WorkspaceManager


def _kernel_policy_readiness(workspace: str, parser_cmd: str, policy_dir: str) -> dict:
    cmd = [
        "python3",
        str(ROOT_DIR / "scripts" / "kernel_policy_readiness.py"),
        "--workspace",
        workspace,
        "--parser-cmd",
        parser_cmd,
        "--policy-dir",
        policy_dir,
        "--json",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=8)
    except Exception as exc:
        return {
            "ok": False,
            "available": False,
            "reason": "policy_ready_exec_error",
            "detail": str(exc),
        }

    if proc.returncode != 0:
        return {
            "ok": False,
            "available": False,
            "reason": "policy_ready_nonzero",
            "detail": (proc.stderr or proc.stdout or "").strip(),
        }

    try:
        payload = json.loads((proc.stdout or "").strip())
    except Exception:
        return {
            "ok": False,
            "available": False,
            "reason": "policy_ready_parse_error",
            "detail": (proc.stdout or "").strip(),
        }
    payload["available"] = True
    return payload


def _systemd_service_state(service_name: str, systemctl_cmd: str) -> dict:
    from shutil import which

    cmd_bin = which(systemctl_cmd)
    if not cmd_bin:
        return {
            "available": False,
            "active": "unavailable",
            "enabled": "unavailable",
            "healthy": True,
            "reason": "systemctl_not_found",
        }

    def run_one(*args: str) -> str:
        try:
            proc = subprocess.run(
                [systemctl_cmd, *args],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except Exception:
            return "unknown"
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        return out or err or "unknown"

    active = run_one("is-active", service_name)
    enabled = run_one("is-enabled", service_name)
    active_ok = active in {"active", "activating"}

    return {
        "available": True,
        "active": active,
        "enabled": enabled,
        "healthy": active_ok,
        "reason": "ok" if active_ok else "service_not_active",
    }


def health_report(
    workspace: str,
    service_name: str,
    systemctl_cmd: str,
    policy_parser_cmd: str,
    policy_dir: str,
) -> dict:
    wm = WorkspaceManager(workspace)
    doctor = doctor_report(wm)
    status = status_report(wm)
    preflight = preflight_report(wm)
    service = _systemd_service_state(service_name, systemctl_cmd)
    policy_ready = _kernel_policy_readiness(
        workspace=str(wm.workspace_dir),
        parser_cmd=policy_parser_cmd,
        policy_dir=policy_dir,
    )

    effective_enabled = bool(
        (policy_ready.get("enforced_pilot", {}) or {}).get("effective_enabled", False)
    )
    ready_for_enforced = bool(
        (policy_ready.get("mechanism", {}) or {}).get("ready_for_enforced_pilot", False)
    )
    policy_ready_ok = bool(policy_ready.get("available", False))
    if effective_enabled and not ready_for_enforced:
        policy_ready_ok = False

    ok = (
        bool(doctor.get("ok", False))
        and bool(status.get("ok", False))
        and bool(preflight.get("ready", False))
        and bool(service.get("healthy", False))
        and policy_ready_ok
    )

    return {
        "ok": ok,
        "exit_code": 0 if ok else 1,
        "workspace": str(wm.workspace_dir),
        "service": {
            "name": service_name,
            "role": "managed_shell_session",
            **service,
        },
        "checks": {
            "doctor_ok": bool(doctor.get("ok", False)),
            "status_ok": bool(status.get("ok", False)),
            "preflight_ready": bool(preflight.get("ready", False)),
            "service_healthy": bool(service.get("healthy", False)),
            "policy_ready_ok": bool(policy_ready_ok),
        },
        "doctor": doctor,
        "status": status,
        "preflight": preflight,
        "policy_ready": policy_ready,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentOS kernel boot healthcheck")
    parser.add_argument("--workspace", default=os.environ.get("DEFAULT_WORKSPACE", str(ROOT_DIR / "workspaces" / "default")))
    parser.add_argument("--service-name", default=os.environ.get("AGENTOS_KERNEL_SERVICE_NAME", "agentos-kernel.service"))
    parser.add_argument("--systemctl-cmd", default=os.environ.get("AGENTOS_SYSTEMCTL_CMD", "systemctl"))
    parser.add_argument("--policy-parser-cmd", default=os.environ.get("AGENTOS_POLICY_PARSER_CMD", "apparmor_parser"))
    parser.add_argument("--policy-dir", default=os.environ.get("AGENTOS_POLICY_DIR", "artifacts/kernel-policy"))
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()

    report = health_report(
        args.workspace,
        args.service_name,
        args.systemctl_cmd,
        args.policy_parser_cmd,
        args.policy_dir,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=True))
        return int(report["exit_code"])

    print("AgentOS Kernel Health")
    print("====================")
    print(f"Workspace: {report['workspace']}")
    svc = report["service"]
    print(f"Managed session service: {svc['name']}")
    print(f"Service active: {svc['active']}")
    print(f"Service enabled: {svc['enabled']}")
    print(f"Doctor: {'PASS' if report['checks']['doctor_ok'] else 'FAIL'}")
    print(f"Status: {'PASS' if report['checks']['status_ok'] else 'FAIL'}")
    print(f"Preflight: {'PASS' if report['checks']['preflight_ready'] else 'FAIL'}")
    print(f"Service health: {'PASS' if report['checks']['service_healthy'] else 'FAIL'}")
    print(f"Policy readiness: {'PASS' if report['checks']['policy_ready_ok'] else 'FAIL'}")
    print(f"Overall: {'PASS' if report['ok'] else 'FAIL'}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())

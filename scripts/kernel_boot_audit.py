#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.event_fabric.policy_evidence import policy_evidence_report
from kernel.event_fabric.report import event_coverage_summary, query_events, query_session_timeline


def _check_file(path: Path, required_texts: list[str]) -> dict:
    if not path.exists():
        return {"exists": False, "ok": False, "missing_patterns": required_texts}

    try:
        body = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {"exists": True, "ok": False, "missing_patterns": required_texts}

    missing = [p for p in required_texts if p not in body]
    return {
        "exists": True,
        "ok": len(missing) == 0,
        "missing_patterns": missing,
    }


def _shadow_summary(workspace: str, shadow_cmd: str) -> dict:
    cmd = [shadow_cmd, "--workspace", workspace, "--json"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except Exception as exc:
        return {
            "available": False,
            "ok": False,
            "command": " ".join(cmd),
            "exit_code": 1,
            "error": str(exc),
            "aligned": False,
            "delta": 0,
        }

    payload = {}
    parse_ok = False
    if proc.stdout.strip():
        try:
            parsed = json.loads(proc.stdout.strip())
            if isinstance(parsed, dict):
                payload = parsed
                parse_ok = True
        except Exception:
            parse_ok = False

    comparison = payload.get("comparison", {}) if isinstance(payload, dict) else {}
    aligned = bool(comparison.get("aligned", False)) if isinstance(comparison, dict) else False
    delta = int(comparison.get("delta", 0)) if isinstance(comparison, dict) else 0
    coverage_summary = payload.get("coverage_summary", {}) if isinstance(payload, dict) else {}
    policy_targets = payload.get("policy_targets", []) if isinstance(payload, dict) else []
    return {
        "available": bool(parse_ok),
        "ok": bool(parse_ok) and int(proc.returncode) == 0 and bool(aligned),
        "command": " ".join(cmd),
        "exit_code": int(proc.returncode),
        "aligned": bool(aligned),
        "delta": int(delta),
        "user_space_blocked_count": int(payload.get("user_space_blocked_count", 0))
        if isinstance(payload, dict)
        else 0,
        "shadow_detected_count": int(payload.get("shadow_detected_count", 0))
        if isinstance(payload, dict)
        else 0,
        "coverage_summary": coverage_summary if isinstance(coverage_summary, dict) else {},
        "policy_targets": policy_targets if isinstance(policy_targets, list) else [],
    }


def audit_report(
    install_root: str,
    workspace: str = "./workspaces/default",
    shadow_cmd: str = "",
) -> dict:
    root = Path(install_root)
    if not shadow_cmd:
        shadow_cmd = str(Path(__file__).resolve().parent / "kernel_policy_shadow_report.py")

    files = {
        "service": root / "etc/systemd/system/agentos-kernel.service",
        "getty_override": root / "etc/systemd/system/getty@tty1.service.d/override.conf",
        "profile_autostart": root / "etc/profile.d/agentos-kernel-autostart.sh",
        "agentos_shell": root / "usr/local/bin/agentos-shell",
        "agentos_kernelctl": root / "usr/local/bin/agentos-kernelctl",
    }

    checks = {
        "service": _check_file(files["service"], ["agentos-shell", "--doctor", "--preflight"]),
        "getty_override": _check_file(files["getty_override"], ["--autologin"]),
        "profile_autostart": _check_file(files["profile_autostart"], ["agentos-shell", "--kernel-mode"]),
        "agentos_shell": {"exists": files["agentos_shell"].exists(), "ok": files["agentos_shell"].exists()},
        "agentos_kernelctl": {"exists": files["agentos_kernelctl"].exists(), "ok": files["agentos_kernelctl"].exists()},
    }

    ok = all(item.get("ok", False) for item in checks.values())
    shadow_mode = _shadow_summary(workspace=workspace, shadow_cmd=shadow_cmd)
    event_fabric = _event_fabric_summary(workspace=workspace)
    return {
        "ok": ok,
        "exit_code": 0 if ok else 1,
        "install_root": str(root),
        "workspace": str(Path(workspace).resolve()),
        "checks": checks,
        "shadow_mode": shadow_mode,
        "event_fabric": event_fabric,
    }


def _event_fabric_summary(workspace: str) -> dict:
    try:
        events_report = query_events(workspace, limit=5)
        sessions_report = query_session_timeline(workspace, limit=5)
        policy_report = policy_evidence_report(workspace)
    except Exception as exc:
        return {
            "available": False,
            "ok": False,
            "error": str(exc),
            "event_file_exists": False,
            "total_events": 0,
            "recent_kinds": [],
            "policy_targets": [],
        }

    targets = []
    for item in policy_report.get("policy_targets", []) or []:
        comparison = item.get("comparison", {}) or {}
        targets.append(
            {
                "policy_target": str(item.get("policy_target", "")),
                "status": str(comparison.get("status", "")),
                "aligned": bool(comparison.get("aligned", False)),
                "delta": int(comparison.get("delta", 0) or 0),
                "user_space_count": int(item.get("user_space_count", 0) or 0),
                "os_evidence_count": int(item.get("os_evidence_count", 0) or 0),
            }
        )

    return {
        "available": True,
        "ok": bool(events_report.get("event_file_exists", False)),
        "event_file_exists": bool(events_report.get("event_file_exists", False)),
        "archive_file_exists": bool(events_report.get("archive_file_exists", False)),
        "event_file": str(events_report.get("event_file", "")),
        "total_events": int(events_report.get("total_events", 0) or 0),
        "recent_kinds": [str(item.get("kind", "")) for item in (events_report.get("events", []) or []) if item.get("kind")],
        "enforced_pilot": policy_report.get("enforced_pilot", {}),
        "supported_policy_targets": [
            "fs_workspace_boundary",
            "network_allowlist",
            "destructive_action_approval",
        ],
        "policy_targets": targets,
        "overall_aligned": bool(policy_report.get("overall_aligned", False)),
        "next_policy_target": "destructive_action_approval",
        "session_ownership": sessions_report.get("ownership_summary", {}),
        "session_correlation": sessions_report.get("correlation_evidence", {}),
        "collector_coverage": event_coverage_summary(workspace, sample_limit=100),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentOS kernel boot config audit")
    parser.add_argument("--install-root", default=os.environ.get("AGENTOS_INSTALL_ROOT", "/"))
    parser.add_argument("--workspace", default=os.environ.get("DEFAULT_WORKSPACE", "./workspaces/default"))
    parser.add_argument(
        "--shadow-cmd",
        default=str(Path(__file__).resolve().parent / "kernel_policy_shadow_report.py"),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    shadow_cmd = args.shadow_cmd
    if "/" not in shadow_cmd:
        resolved = shutil.which(shadow_cmd)
        if resolved:
            shadow_cmd = resolved
    report = audit_report(args.install_root, workspace=args.workspace, shadow_cmd=shadow_cmd)
    if args.json:
        print(json.dumps(report, ensure_ascii=True))
        return int(report["exit_code"])

    print("AgentOS Kernel Boot Audit")
    print("=========================")
    print(f"Install root: {report['install_root']}")
    print(f"Workspace: {report['workspace']}")
    for name, item in report["checks"].items():
        state = "PASS" if item.get("ok", False) else "FAIL"
        print(f"- {name}: {state}")
        if item.get("missing_patterns"):
            print(f"  missing: {', '.join(item['missing_patterns'])}")
    shadow = report.get("shadow_mode", {}) or {}
    shadow_state = "PASS" if shadow.get("ok", False) else "WARN"
    print(f"- shadow_mode: {shadow_state}")
    print(
        f"  aligned={bool(shadow.get('aligned', False))} "
        f"delta={int(shadow.get('delta', 0))} "
        f"user={int(shadow.get('user_space_blocked_count', 0))} "
        f"shadow={int(shadow.get('shadow_detected_count', 0))}"
    )
    if shadow.get("coverage_summary"):
        coverage = shadow.get("coverage_summary", {}) or {}
        print(
            "  coverage: "
            f"targets={int(coverage.get('policy_target_count', 0) or 0)} "
            f"aligned={int(coverage.get('aligned_count', 0) or 0)} "
            f"divergent={int(coverage.get('divergent_count', 0) or 0)}"
        )
    for item in shadow.get("policy_targets", []) or []:
        comparison = item.get("comparison", {}) or {}
        print(
            f"  - {item.get('policy_target')}: "
            f"status={comparison.get('status')} "
            f"delta={comparison.get('delta')}"
        )
    fabric = report.get("event_fabric", {}) or {}
    fabric_state = "PASS" if fabric.get("ok", False) else "WARN"
    print(f"- event_fabric: {fabric_state}")
    print(
        f"  events={int(fabric.get('total_events', 0))} "
        f"recent={','.join(fabric.get('recent_kinds', [])) or '(none)'} "
        f"aligned={bool(fabric.get('overall_aligned', False))}"
    )
    print(f"Overall: {'PASS' if report['ok'] else 'FAIL'}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())

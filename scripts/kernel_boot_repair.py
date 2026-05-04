#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path

from kernel_boot_audit import audit_report

CHECK_NAMES = (
    "service",
    "getty_override",
    "profile_autostart",
    "agentos_shell",
    "agentos_kernelctl",
)


def _write_report_file(path: str, payload: dict) -> tuple[bool, str]:
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _build_report_file_path(report_file: str | None, report_dir: str | None) -> str | None:
    if report_file:
        return report_file
    if not report_dir:
        return None
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return str(Path(report_dir) / f"kernel-repair-{ts}.json")


def _apply_report_retention(report_dir: str, keep: int) -> dict:
    result = {"applied": True, "keep": keep, "deleted_files": [], "remaining_files": []}
    directory = Path(report_dir)
    if keep <= 0:
        result["applied"] = False
        result["reason"] = "keep must be > 0"
        return result

    files = sorted(directory.glob("kernel-repair-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    keep_files = files[:keep]
    delete_files = files[keep:]
    deleted: list[str] = []
    for path in delete_files:
        try:
            path.unlink()
            deleted.append(str(path))
        except Exception:
            # non-fatal retention failure should not hide successful repair
            continue
    result["deleted_files"] = deleted
    result["remaining_files"] = [str(p) for p in keep_files if p.exists()]
    return result


def _run_install(root_dir: Path, workspace: str, install_root: str) -> tuple[int, str]:
    installer = root_dir / "scripts" / "install_kernel_boot_integration.sh"
    env = os.environ.copy()
    env["DEFAULT_WORKSPACE"] = workspace
    env["AGENTOS_INSTALL_ROOT"] = install_root
    if install_root != "/":
        env["AGENTOS_ENABLE_SYSTEMD"] = "0"

    proc = subprocess.run(
        [str(installer)],
        cwd=str(root_dir),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout or "").strip()
    if proc.stderr:
        if output:
            output = f"{output}\n{proc.stderr.strip()}"
        else:
            output = proc.stderr.strip()
    return proc.returncode, output


def _parse_checks(checks: str | None) -> tuple[list[str], list[str]]:
    if not checks:
        return [], []
    requested = [item.strip() for item in checks.split(",") if item.strip()]
    invalid = [item for item in requested if item not in CHECK_NAMES]
    valid = [item for item in requested if item in CHECK_NAMES]
    return valid, invalid


def repair_report(
    workspace: str,
    install_root: str,
    dry_run: bool = False,
    checks: str | None = None,
) -> dict:
    root_dir = Path(__file__).resolve().parent.parent

    selected_checks, invalid_checks = _parse_checks(checks)
    if invalid_checks:
        return {
            "ok": False,
            "exit_code": 2,
            "mode": "dry_run" if dry_run else "apply",
            "workspace": workspace,
            "install_root": install_root,
            "checks_requested": selected_checks + invalid_checks,
            "invalid_checks": invalid_checks,
            "needs_repair": False,
            "repaired": False,
            "before": {},
            "after": {},
            "install": {"exit_code": 2, "output": f"invalid checks: {', '.join(invalid_checks)}"},
        }

    before = audit_report(install_root)
    drift_checks = [name for name, item in before.get("checks", {}).items() if not item.get("ok", False)]
    effective_scope = selected_checks if selected_checks else list(CHECK_NAMES)
    scoped_drift = [name for name in drift_checks if name in effective_scope]
    repaired = False
    needs_repair = len(scoped_drift) > 0
    install = {"exit_code": 0, "output": "already healthy, no changes applied"}

    if dry_run and needs_repair:
        install = {"exit_code": 0, "output": "dry-run: scoped drift detected, managed assets would be reinstalled"}
    elif needs_repair:
        repaired = True
        install_code, install_output = _run_install(root_dir, workspace, install_root)
        install = {"exit_code": install_code, "output": install_output}

    after = before if dry_run else audit_report(install_root)
    if not needs_repair:
        ok = install["exit_code"] == 0
    else:
        ok = install["exit_code"] == 0 and (dry_run or after.get("ok", False))
    return {
        "ok": ok,
        "exit_code": 0 if ok else 1,
        "mode": "dry_run" if dry_run else "apply",
        "workspace": workspace,
        "install_root": install_root,
        "checks_requested": selected_checks,
        "drift_checks": drift_checks,
        "scoped_drift_checks": scoped_drift,
        "needs_repair": needs_repair,
        "repaired": repaired,
        "before": before,
        "after": after,
        "install": install,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentOS kernel boot config repair")
    parser.add_argument("--workspace", default=os.environ.get("DEFAULT_WORKSPACE", "./workspaces/default"))
    parser.add_argument("--install-root", default=os.environ.get("AGENTOS_INSTALL_ROOT", "/"))
    parser.add_argument("--checks", help="comma-separated check names to scope repair/audit drift")
    parser.add_argument("--list-checks", action="store_true", help="list supported check names and exit")
    parser.add_argument("--report-file", help="write repair report JSON to this file")
    parser.add_argument("--report-dir", help="write repair report JSON under this directory with timestamp filename")
    parser.add_argument("--report-retain", type=int, default=0, help="when using --report-dir, retain only latest N reports")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.list_checks:
        payload = {"checks": list(CHECK_NAMES)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=True))
        else:
            print("Supported checks:")
            for name in CHECK_NAMES:
                print(f"- {name}")
        return 0

    report_path = _build_report_file_path(args.report_file, args.report_dir)

    report = repair_report(args.workspace, args.install_root, dry_run=args.dry_run, checks=args.checks)
    if report_path:
        report["report_file"] = report_path
        ok, error = _write_report_file(report_path, report)
        if not ok:
            report["ok"] = False
            report["exit_code"] = 1
            report["report_file_write_error"] = error
        elif args.report_dir and args.report_retain > 0:
            report["report_retention"] = _apply_report_retention(args.report_dir, args.report_retain)

    if args.json:
        print(json.dumps(report, ensure_ascii=True))
        return int(report["exit_code"])

    print("AgentOS Kernel Boot Repair")
    print("==========================")
    print(f"Workspace: {report['workspace']}")
    print(f"Install root: {report['install_root']}")
    print(f"Mode: {report['mode']}")
    print(f"Checks requested: {', '.join(report['checks_requested']) if report['checks_requested'] else '(all)'}")
    print(f"Drift checks: {', '.join(report['drift_checks']) if report['drift_checks'] else '(none)'}")
    print(
        f"Scoped drift checks: {', '.join(report['scoped_drift_checks']) if report['scoped_drift_checks'] else '(none)'}"
    )
    print(f"Needs repair: {'yes' if report['needs_repair'] else 'no'}")
    print(f"Repair attempted: {'yes' if report['repaired'] else 'no'}")
    if report_path:
        print(f"Report file: {report_path}")
        if report.get("report_file_write_error"):
            print(f"Report file write: FAIL ({report['report_file_write_error']})")
        else:
            print("Report file write: PASS")
    if report.get("report_retention"):
        r = report["report_retention"]
        print(f"Report retention: keep={r.get('keep')} deleted={len(r.get('deleted_files', []))}")
    print(f"Install step: {'PASS' if report['install']['exit_code'] == 0 else 'FAIL'}")
    print(f"Before audit: {'PASS' if report['before']['ok'] else 'FAIL'}")
    print(f"After audit: {'PASS' if report['after']['ok'] else 'FAIL'}")
    print(f"Overall: {'PASS' if report['ok'] else 'FAIL'}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())

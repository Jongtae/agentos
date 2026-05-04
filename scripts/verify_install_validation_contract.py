#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


EXPECTED_DISTRIBUTION_CONTRACT = "agentos_managed_session"
EXPECTED_ENTRY_CONTRACT = "agentos_setup_to_ai_shell"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _contains(path: Path, needle: str) -> bool:
    if not path.exists():
        return False
    return needle in path.read_text(encoding="utf-8", errors="replace")


def build_report(metadata: str = "", install_root: str = "") -> dict:
    report: dict = {
        "ok": True,
        "exit_code": 0,
        "metadata": {},
        "install_root": {},
        "recovery_controls": {
            "boot_autostart_bypass": "AGENTOS_BOOT_AUTOSTART=0",
            "broker_bypass": "AGENTOS_BROKER_BYPASS=1",
            "kernel_disable": "AGENTOS_KERNEL_POLICY_DISABLE=1",
            "operator_uninstall": "scripts/uninstall_kernel_boot_integration.sh",
        },
        "errors": [],
    }

    if not metadata and not install_root:
        report["ok"] = False
        report["exit_code"] = 2
        report["errors"].append("at least one of --metadata or --install-root is required")
        return report

    if metadata:
        path = Path(metadata).resolve()
        payload = _read_json(path)
        meta_errors = []
        if payload.get("distribution_contract") != EXPECTED_DISTRIBUTION_CONTRACT:
            meta_errors.append("distribution_contract mismatch")
        if payload.get("primary_entry_contract") != EXPECTED_ENTRY_CONTRACT:
            meta_errors.append("primary_entry_contract mismatch")
        report["metadata"] = {
            "path": str(path),
            "artifact_type": str(payload.get("artifact_type", "")),
            "distribution_contract": str(payload.get("distribution_contract", "")),
            "primary_entry_contract": str(payload.get("primary_entry_contract", "")),
            "ok": len(meta_errors) == 0,
            "errors": meta_errors,
        }
        report["errors"].extend(meta_errors)

    if install_root:
        root = Path(install_root).resolve()
        paths = {
            "agentos_shell": root / "usr/local/bin/agentos-shell",
            "agentos_kernelctl": root / "usr/local/bin/agentos-kernelctl",
            "agentos_firstrun": root / "usr/local/bin/agentos-firstrun",
            "agentos_live_firstrun_service": root / "usr/local/bin/agentos-live-firstrun-service",
            "managed_shell_service": root / "etc/systemd/system/agentos-kernel.service",
            "setup_session_service": root / "etc/systemd/system/agentos-firstrun.service",
            "tty1_override": root / "etc/systemd/system/getty@tty1.service.d/override.conf",
            "tty1_profile": root / "etc/profile.d/agentos-kernel-autostart.sh",
        }
        assets = {name: path.exists() for name, path in paths.items()}
        content_checks = {
            "managed_shell_service_contract": _contains(paths["managed_shell_service"], "agentos-shell"),
            "setup_session_service_contract": _contains(paths["setup_session_service"], "AgentOS Setup Session Service"),
            "tty1_override_contract": _contains(paths["tty1_override"], "--autologin"),
            "tty1_profile_shell_contract": _contains(paths["tty1_profile"], "agentos-shell"),
            "tty1_profile_setup_contract": _contains(paths["tty1_profile"], "agentos-firstrun"),
        }
        install_errors = [f"missing install asset: {name}" for name, ok in assets.items() if not ok]
        install_errors.extend([f"install contract mismatch: {name}" for name, ok in content_checks.items() if not ok])
        report["install_root"] = {
            "path": str(root),
            "assets": assets,
            "content_checks": content_checks,
            "ok": len(install_errors) == 0,
            "errors": install_errors,
        }
        report["errors"].extend(install_errors)

    report["ok"] = len(report["errors"]) == 0
    report["exit_code"] = 0 if report["ok"] else 1
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify AgentOS install validation contract")
    parser.add_argument("--metadata", default="")
    parser.add_argument("--install-root", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_report(metadata=args.metadata, install_root=args.install_root)
    if args.json:
        print(json.dumps(report, ensure_ascii=True))
        return int(report["exit_code"])

    print("AgentOS Install Validation Contract")
    print("===================================")
    if report["metadata"]:
        metadata = report["metadata"]
        print(f"Metadata: {'PASS' if metadata.get('ok') else 'FAIL'}")
        print(f"  Path: {metadata.get('path')}")
        print(f"  Distribution contract: {metadata.get('distribution_contract')}")
        print(f"  Primary entry contract: {metadata.get('primary_entry_contract')}")
    if report["install_root"]:
        install = report["install_root"]
        print(f"Install root: {'PASS' if install.get('ok') else 'FAIL'}")
        print(f"  Path: {install.get('path')}")
    if report["errors"]:
        print("Errors:")
        for item in report["errors"]:
            print(f"  - {item}")
    print(f"Overall: {'PASS' if report['ok'] else 'FAIL'}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())

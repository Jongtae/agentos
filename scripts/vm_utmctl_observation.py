#!/usr/bin/env python3
"""
vm_utmctl_observation.py — observe a UTM-backed VM and refresh E2E proof.

utmctl fails with OSStatus -1743 outside GUI sessions (Codex, SSH, launchd
Background agents).  This script uses utm_client.py which tries three
backends in order:
  1. UTM built-in REST API  (UTM → Preferences → Server → Enable)
  2. AgentOS utm-proxy      (utm_proxy_server.py launchd user agent)
  3. utmctl direct          (works in GUI session only — last resort)

Quick setup to unblock Codex today:
  Option A — enable UTM REST API:
    UTM → Preferences → Server → Enable Server  (port 34722)
  Option B — install launchd proxy (run once, from your Mac terminal):
    python3 scripts/utm_proxy_server.py --install
    launchctl load ~/Library/LaunchAgents/com.agentos.utm-proxy.plist
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# utm_client is in the same scripts/ directory
_SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

SCHEMA_VERSION = "agentos-utmctl-vm-observation.v1"


def _quote(command: list[str]) -> str:
    return shlex.join(command)


def _planned_commands(vm_name: str, workspace: str, session_id: str) -> list[str]:
    scenario_cmd = [
        sys.executable,
        str(ROOT_DIR / "scripts" / "kernel_vm_e2e_scenario.py"),
        "--workspace",
        workspace,
        "--session-id",
        session_id or "agentos:tty1",
        "--json",
    ]
    proof_cmd = [
        sys.executable,
        str(ROOT_DIR / "scripts" / "kernel_vm_e2e_proof.py"),
        "--workspace",
        workspace,
        "--session-id",
        session_id or "agentos:tty1",
        "--use-existing-manifests",
        "--json",
    ]
    utm_cli = [sys.executable, str(ROOT_DIR / "scripts" / "utm_client.py")]
    return [
        _quote(utm_cli + ["status", vm_name]),
        _quote(utm_cli + ["start",  vm_name]),
        _quote(utm_cli + ["ip",     vm_name]),
        _quote(scenario_cmd),
        _quote(proof_cmd),
    ]


def _utmctl_executable() -> str:
    return shutil.which("utmctl") or "utmctl"


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _nonempty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _vm_is_running_or_suspended(text: str) -> bool:
    lowered = text.lower()
    if any(token in lowered for token in ("not running", "stopped", "shutdown", "powered off")):
        return False
    if re.search(r"(?:state|status)\s*:\s*(running|suspended)\b", text, re.IGNORECASE):
        return True
    if re.search(r"^\s*(running|suspended)\s*$", text, re.IGNORECASE | re.MULTILINE):
        return True
    return False


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not payload.get("vm_name"):
        errors.append("vm_name must be non-empty")
    if not payload.get("workspace"):
        errors.append("workspace must be non-empty")
    summary = payload.get("summary") or {}
    if "observation_mode" not in summary:
        errors.append("summary.observation_mode must be present")
    if summary.get("observation_mode") == "dry_run":
        if not isinstance(payload.get("planned_commands"), list) or not payload.get("planned_commands"):
            errors.append("planned_commands must be a non-empty list in dry-run mode")
    else:
        if not isinstance(payload.get("utmctl"), dict):
            errors.append("utmctl must be present in live mode")
        if not isinstance(payload.get("scenario_refresh"), dict):
            errors.append("scenario_refresh must be present in live mode")
        if not isinstance(payload.get("vm_e2e_proof"), dict):
            errors.append("vm_e2e_proof must be present in live mode")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Observe a UTM-backed VM and refresh the VM E2E proof path")
    parser.add_argument("--vm-name", required=True)
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--validate", default="")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_payload(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("utmctl vm observation: PASS" if result["ok"] else "utmctl vm observation: FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    workspace = str(Path(args.workspace).resolve())
    session_id = args.session_id or "agentos:tty1"
    proof_cmd = [
        sys.executable,
        str(ROOT_DIR / "scripts" / "kernel_vm_e2e_proof.py"),
        "--workspace",
        workspace,
        "--session-id",
        session_id,
        "--use-existing-manifests",
        "--json",
    ]
    scenario_cmd = [
        sys.executable,
        str(ROOT_DIR / "scripts" / "kernel_vm_e2e_scenario.py"),
        "--workspace",
        workspace,
        "--session-id",
        session_id,
        "--json",
    ]

    payload: dict = {
        "schema_version": SCHEMA_VERSION,
        "vm_name": args.vm_name,
        "workspace": workspace,
        "session_id": session_id,
        "refresh_policy": {
            "scenario_refresh": True,
            "proof_uses_existing_manifests": True,
        },
        "planned_commands": _planned_commands(args.vm_name, workspace, session_id),
        "summary": {
            "observation_mode": "dry_run" if args.dry_run else "live",
            "scenario_refreshed": False,
            "proof_exported": False,
            "utmctl_started": False,
            "utmctl_status_seen": False,
        },
    }

    if args.dry_run:
        if args.json:
            print(json.dumps(payload, ensure_ascii=True))
        else:
            print("UTM-backed VM observation")
            print(f"VM name: {args.vm_name}")
            print(f"Workspace: {workspace}")
            print("Planned commands:")
            for command in payload["planned_commands"]:
                print(f"  {command}")
            print("utmctl vm observation dry-run: PASS")
        return 0

    # ── live mode: use utm_client (auto-discovers utm_api / proxy / utmctl) ──
    try:
        from utm_client import UTMClient, UTMError
    except ImportError:
        print("utm_client not found; ensure scripts/ is on sys.path", file=sys.stderr)
        return 1

    try:
        client = UTMClient()
    except Exception as e:  # UTMError or any import-time failure
        print(str(e), file=sys.stderr)
        return 1

    backend_name = client.backend_name
    utm_cli = [sys.executable, str(ROOT_DIR / "scripts" / "utm_client.py")]

    # status
    try:
        is_running = client.status(args.vm_name)
        status_output = "running" if is_running else "stopped"
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1

    # start if needed
    should_start = not is_running
    start_output = ""
    if should_start:
        try:
            client.start(args.vm_name)
            start_output = "started"
            payload["summary"]["utmctl_started"] = True
        except Exception as e:
            # retry status — maybe it was already running
            try:
                is_running = client.status(args.vm_name)
                status_output = "running" if is_running else "stopped"
                if not is_running:
                    print(str(e), file=sys.stderr)
                    return 1
                start_output = "already running"
            except Exception as e2:
                print(str(e2), file=sys.stderr)
                return 1

    # ip
    try:
        ip_list = client.ip(args.vm_name)
        ip_output = "\n".join(ip_list)
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1

    scenario_proc = subprocess.run(scenario_cmd, capture_output=True, text=True, check=False)
    if scenario_proc.returncode != 0:
        print(scenario_proc.stderr.strip() or scenario_proc.stdout.strip() or "vm e2e scenario refresh failed", file=sys.stderr)
        return scenario_proc.returncode or 1
    scenario_payload = json.loads(scenario_proc.stdout)

    proof_proc = subprocess.run(proof_cmd, capture_output=True, text=True, check=False)
    if proof_proc.returncode != 0:
        print(proof_proc.stderr.strip() or proof_proc.stdout.strip() or "vm e2e proof failed", file=sys.stderr)
        return proof_proc.returncode or 1
    proof_payload = json.loads(proof_proc.stdout)

    payload.update(
        {
            "utmctl": {
                "backend": backend_name,
                "status_command": _quote(utm_cli + ["status", args.vm_name]),
                "status_output": status_output,
                "start_command": _quote(utm_cli + ["start", args.vm_name]) if should_start else "",
                "start_output": start_output,
                "ip_address_command": _quote(utm_cli + ["ip", args.vm_name]),
                "ip_address_output": ip_output,
                "ip_addresses": _nonempty_lines(ip_output),
            },
            "scenario_refresh": {
                "schema_version": scenario_payload.get("schema_version", ""),
                "summary": dict(scenario_payload.get("summary") or {}),
                "artifacts": dict(scenario_payload.get("artifacts") or {}),
            },
            "vm_e2e_proof": proof_payload,
            "summary": {
                "observation_mode": "live",
                "scenario_refreshed": True,
                "proof_exported": True,
                "utmctl_started": should_start,
                "utmctl_status_seen": True,
                "proof_used_existing_manifests": True,
                "vm_e2e_refresh_manifests": True,
                "vm_e2e_runtime_ok": bool((proof_payload.get("summary") or {}).get("vm_e2e_runtime_ok", False)),
                "vm_e2e_service_permission_ok": bool((proof_payload.get("summary") or {}).get("vm_e2e_service_permission_ok", False)),
            },
        }
    )

    errors = validate_payload(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=True))
        return 1

    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print("UTM-backed VM observation")
        print(f"VM name: {args.vm_name}")
        print(f"Workspace: {workspace}")
        print(f"UTM status: {status_output or '(no status output)'}")
        if start_output:
            print(f"UTM start: {start_output}")
        print(f"UTM IP addresses: {', '.join(_nonempty_lines(ip_output)) or '(none)'}")
        print("VM E2E scenario refresh: PASS")
        print("VM E2E proof export: PASS")
        print("utmctl vm observation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import plistlib
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from utm_client import UTMClient, UTMError

SCHEMA_VERSION = "agentos-utm-disposable-vm.v1"
UTM_DOCUMENTS_DIR = Path.home() / "Library" / "Containers" / "com.utmapp.UTM" / "Data" / "Documents"
UTM_APPLESCRIPT_REF = 'application id "com.utmapp.UTM"'


class VMOrchestratorError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def default_vm_name(version: str) -> str:
    return f"AgentOS Acceptance {version} {_slug_timestamp()}"


def _escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _run_osascript(lines: list[str]) -> str:
    command = ["osascript"]
    for line in lines:
        command.extend(["-e", line])
    proc = subprocess.CompletedProcess(command, 1, "", "")
    error_text = ""
    for attempt in range(5):
        proc = subprocess.run(command, capture_output=True, text=True, check=False)
        error_text = proc.stderr.strip() or proc.stdout.strip()
        if proc.returncode == 0:
            break
        if "Application isn’t running. (-600)" not in error_text:
            break
        subprocess.run(["open", "-a", "UTM"], capture_output=True, text=True, check=False)
        subprocess.run(
            ["osascript", "-e", f"tell {UTM_APPLESCRIPT_REF} to activate"],
            capture_output=True,
            text=True,
            check=False,
        )
        time.sleep(2 + attempt)
    if proc.returncode != 0:
        raise VMOrchestratorError(error_text or "osascript failed")
    return proc.stdout.strip()


def _list_vm_names() -> list[str]:
    output = _run_osascript(
        [
            f"tell {UTM_APPLESCRIPT_REF}",
            "set vmNames to name of every virtual machine",
            "set outputText to \"\"",
            "repeat with vmName in vmNames",
            "set outputText to outputText & (contents of vmName) & linefeed",
            "end repeat",
            "return outputText",
            "end tell",
        ]
    )
    if not output:
        return []
    return [item.strip() for item in output.splitlines() if item.strip()]


def _bundle_path(vm_name: str) -> Path:
    return UTM_DOCUMENTS_DIR / f"{vm_name}.utm"


def _config_path(vm_name: str) -> Path:
    return _bundle_path(vm_name) / "config.plist"


def _wait_for_path(path: Path, *, timeout_sec: int = 30) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.2)
    raise VMOrchestratorError(f"timed out waiting for {path}")


def _normalize_guest_arch(arch: str) -> str:
    value = (arch or "amd64").strip()
    aliases = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "aarch64", "aarch64": "aarch64"}
    if value not in aliases:
        raise VMOrchestratorError(f"unsupported UTM guest architecture: {arch}")
    return aliases[value]


def _target_for_arch(utm_arch: str) -> str:
    return "virt" if utm_arch == "aarch64" else "q35"


def _hypervisor_for_arch(utm_arch: str) -> bool:
    return utm_arch == "aarch64"


def _patch_config(
    vm_name: str,
    *,
    memory_mib: int,
    cpu_cores: int,
    uefi_boot: bool = False,
    arch: str = "amd64",
) -> dict:
    config_path = _config_path(vm_name)
    _wait_for_path(config_path)
    with config_path.open("rb") as handle:
        payload = plistlib.load(handle)

    payload.setdefault("Information", {})
    payload["Information"].setdefault("Icon", "linux")
    payload.setdefault("System", {})
    utm_arch = _normalize_guest_arch(arch)
    payload["System"]["MemorySize"] = memory_mib
    payload["System"]["CPUCount"] = cpu_cores
    payload["System"]["Architecture"] = utm_arch
    payload["System"]["Target"] = _target_for_arch(utm_arch)
    payload.setdefault("QEMU", {})
    payload["QEMU"]["Hypervisor"] = _hypervisor_for_arch(utm_arch)
    # Acceptance is serial/TTY-first. Desktop-live remasters prefer the simpler
    # hybrid ISO BIOS path, while the lightweight live-server proof path keeps
    # Ubuntu's UEFI-oriented boot flow intact.
    payload["QEMU"]["UEFIBoot"] = bool(uefi_boot)
    payload["QEMU"]["RNGDevice"] = True
    payload["QEMU"]["DebugLog"] = True
    payload["QEMU"]["AdditionalArguments"] = list(payload["QEMU"].get("AdditionalArguments") or [])
    payload.setdefault("Display", [])
    if not payload["Display"]:
        payload["Display"] = [
            {
                "Hardware": "virtio-gpu-pci",
                "DynamicResolution": True,
                "NativeResolution": False,
                "UpscalingFilter": "Nearest",
                "DownscalingFilter": "Linear",
            }
        ]
    payload.setdefault("Serial", [])
    if not payload["Serial"]:
        payload["Serial"] = [{"Mode": "Ptty", "Target": "Auto"}]

    with config_path.open("wb") as handle:
        plistlib.dump(payload, handle)
    return payload


def build_vm_info(vm_name: str) -> dict:
    config_path = _config_path(vm_name)
    if not config_path.exists():
        raise VMOrchestratorError(f"UTM config not found for VM: {vm_name}")
    with config_path.open("rb") as handle:
        payload = plistlib.load(handle)
    info = dict(payload.get("Information") or {})
    drives = list(payload.get("Drive") or [])
    disk_image_name = ""
    for drive in drives:
        if drive.get("ImageType") == "Disk" and drive.get("ImageName"):
            disk_image_name = str(drive["ImageName"])
            break
    serial_enabled = bool(payload.get("Serial"))
    return {
        "schema_version": SCHEMA_VERSION,
        "vm_name": vm_name,
        "bundle_path": str(_bundle_path(vm_name)),
        "config_path": str(config_path),
        "uuid": str(info.get("UUID") or ""),
        "backend": str(payload.get("Backend") or "QEMU"),
        "memory_mib": int((payload.get("System") or {}).get("MemorySize") or 0),
        "cpu_cores": int((payload.get("System") or {}).get("CPUCount") or 0),
        "disk_image_path": str((_bundle_path(vm_name) / "Data" / disk_image_name).resolve()) if disk_image_name else "",
        "serial_enabled": serial_enabled,
        "screenshot_path": str((_bundle_path(vm_name) / "screenshot.png").resolve()),
        "generated_at_utc": _utc_now(),
    }


def create_vm(
    *,
    vm_name: str,
    iso_path: str,
    disk_size_mib: int,
    memory_mib: int,
    cpu_cores: int,
    uefi_boot: bool = False,
    arch: str = "amd64",
) -> dict:
    iso_file = Path(iso_path).resolve()
    if not iso_file.is_file():
        raise VMOrchestratorError(f"ISO not found: {iso_file}")
    if vm_name in _list_vm_names():
        raise VMOrchestratorError(f"UTM VM already exists: {vm_name}")

    escaped_iso = _escape_applescript(str(iso_file))
    utm_arch = _normalize_guest_arch(arch)
    hypervisor = _hypervisor_for_arch(utm_arch)
    script_lines = [
        f"tell {UTM_APPLESCRIPT_REF}",
        f'set iso to POSIX file "{escaped_iso}"',
        (
            'set vm to make new virtual machine with properties '
            f'{{backend:qemu, configuration:{{name:"{_escape_applescript(vm_name)}", architecture:"{utm_arch}", '
            f'memory:{memory_mib}, cpu cores:{cpu_cores}, hypervisor:{str(hypervisor).lower()}, '
            f'uefi:{str(bool(uefi_boot)).lower()}, '
            f'drives:{{{{removable:true, source:iso}}, {{guest size:{disk_size_mib}}}}}}}}}'
        ),
        "return name of vm",
        "end tell",
    ]
    result_name = _run_osascript(script_lines)
    if result_name.strip() != vm_name:
        raise VMOrchestratorError(f"unexpected UTM VM name: {result_name!r}")
    _patch_config(vm_name, memory_mib=memory_mib, cpu_cores=cpu_cores, uefi_boot=uefi_boot, arch=arch)

    payload = build_vm_info(vm_name)
    payload["iso_path"] = str(iso_file)
    payload["disk_size_mib"] = disk_size_mib
    payload["provisioner"] = "applescript_direct_iso"
    payload["uefi_boot"] = bool(uefi_boot)
    payload["guest_arch"] = arch
    payload["utm_architecture"] = utm_arch
    payload["utm_target"] = _target_for_arch(utm_arch)
    payload["hypervisor"] = hypervisor
    return payload


def force_delete_vm(vm_name: str, *, if_exists: bool = False, wait_timeout_sec: int = 30) -> dict:
    names = _list_vm_names()
    if vm_name not in names:
      if if_exists:
          return {
              "schema_version": SCHEMA_VERSION,
              "vm_name": vm_name,
              "deleted": False,
              "missing": True,
              "generated_at_utc": _utc_now(),
          }
      raise VMOrchestratorError(f"UTM VM not found: {vm_name}")

    client: UTMClient | None = None
    client_error = ""
    try:
        client = UTMClient()
    except Exception as exc:
        client_error = str(exc)
    stop_error = ""
    try:
        _run_osascript(
            [
                f"tell {UTM_APPLESCRIPT_REF}",
                f'try\nstop virtual machine named "{_escape_applescript(vm_name)}" by force\nend try',
                f'try\nstop virtual machine named "{_escape_applescript(vm_name)}" by kill\nend try',
                "end tell",
            ]
        )
    except Exception as exc:
        stop_error = str(exc)

    if client is not None:
        deadline = time.time() + wait_timeout_sec
        while time.time() < deadline:
            try:
                if not client.status(vm_name):
                    break
            except Exception:
                break
            time.sleep(1)

    last_error = ""
    for _ in range(5):
        try:
            _run_osascript(
                [
                    f"tell {UTM_APPLESCRIPT_REF}",
                    f'delete virtual machine named "{_escape_applescript(vm_name)}"',
                    "end tell",
                ]
            )
            break
        except VMOrchestratorError as exc:
            last_error = str(exc)
            if "-2700" not in last_error and "stopped before" not in last_error.lower():
                raise
            time.sleep(1)
    else:
        raise VMOrchestratorError(last_error or stop_error or client_error or f"failed to delete {vm_name}")

    return {
        "schema_version": SCHEMA_VERSION,
        "vm_name": vm_name,
        "deleted": True,
        "missing": False,
        "generated_at_utc": _utc_now(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create and clean up disposable UTM validation VMs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a fresh UTM VM for AgentOS acceptance")
    create_parser.add_argument("--iso-path", required=True)
    create_parser.add_argument("--vm-name", default="")
    create_parser.add_argument("--version", default="")
    create_parser.add_argument("--disk-size-mib", type=int, default=32768)
    create_parser.add_argument("--memory-mib", type=int, default=8192)
    create_parser.add_argument("--cpu-cores", type=int, default=4)
    create_parser.add_argument("--arch", choices=("amd64", "arm64"), default="amd64")
    create_parser.add_argument("--json", action="store_true")

    delete_parser = subparsers.add_parser("delete", help="Delete a UTM VM")
    delete_parser.add_argument("--vm-name", required=True)
    delete_parser.add_argument("--if-exists", action="store_true")
    delete_parser.add_argument("--json", action="store_true")

    info_parser = subparsers.add_parser("info", help="Read disposable VM bundle details")
    info_parser.add_argument("--vm-name", required=True)
    info_parser.add_argument("--json", action="store_true")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "create":
            version = args.version or Path(args.iso_path).stem.replace("agentos-", "")
            vm_name = args.vm_name or default_vm_name(version)
            payload = create_vm(
                vm_name=vm_name,
                iso_path=args.iso_path,
                disk_size_mib=args.disk_size_mib,
                memory_mib=args.memory_mib,
                cpu_cores=args.cpu_cores,
                arch=args.arch,
            )
        elif args.command == "delete":
            payload = force_delete_vm(args.vm_name, if_exists=args.if_exists)
        else:
            payload = build_vm_info(args.vm_name)
    except (VMOrchestratorError, UTMError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=True))
    elif args.command == "create":
        print(f"Created UTM VM: {payload['vm_name']}")
        print(f"Bundle: {payload['bundle_path']}")
    elif args.command == "delete":
        print(f"Deleted UTM VM: {payload['vm_name']}")
    else:
        print(f"UTM VM: {payload['vm_name']}")
        print(f"Bundle: {payload['bundle_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Verify that the live-root is staged to bring up qemu-guest-agent on first boot.

The remaster host is macOS, so pre-installing ``qemu-guest-agent`` into
the live squashfs from this host is not trivial (no cross-arch
chroot+dpkg path). What *is* truthful and verifiable on the host is
whether the live session has everything it needs to bring the guest
agent up on first boot:

* the live session bootstrap helper is installed at
  ``/usr/local/bin/agentos-live-session-bootstrap`` inside the live-root;
* the Welcome autostart entry delegates to that helper (not to the
  welcome shell directly), so the guest-agent bootstrap runs under the
  logged-in live user with passwordless sudo available;
* the apt policy flag ``qemu-guest-agent`` is required, so the
  bootstrap's apt-get install path targets a known package.

This helper emits a structured JSON report recording those signals plus
an honest ``live_guest_agent_prestaged`` field, which stays false until a
real binary is staged into the live-root (a future slice on a Linux
remaster host). Its purpose is truth-telling, not gating.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

QEMU_GUEST_AGENT_PACKAGE = "qemu-guest-agent"
BOOTSTRAP_BIN_RELPATH = "usr/local/bin/agentos-live-session-bootstrap"
WELCOME_AUTOSTART_RELPATH = "etc/xdg/autostart/agentos-welcome.desktop"
QEMU_GUEST_AGENT_REQUIRED_SHARED_LIBS = (
    "liburing.so.2",
    "libglib-2.0.so.0",
    "libgmodule-2.0.so.0",
    "libnuma.so.1",
    "libudev.so.1",
)


def _policy_requires_guest_agent(policy_path: Path) -> bool:
    if not policy_path.exists():
        return False
    for raw_line in policy_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) < 4:
            continue
        name = parts[0].strip()
        tier = parts[3].strip()
        if name == QEMU_GUEST_AGENT_PACKAGE and tier == "core":
            return True
    return False


def _autostart_delegates_to_bootstrap(desktop_path: Path) -> bool:
    if not desktop_path.exists():
        return False
    body = desktop_path.read_text(encoding="utf-8", errors="replace")
    exec_line = next(
        (line for line in body.splitlines() if line.strip().lower().startswith("exec=")),
        "",
    )
    return "agentos-live-session-bootstrap" in exec_line


def _guest_agent_binary_prestaged(live_root: Path) -> bool:
    for relpath in ("usr/sbin/qemu-ga", "usr/bin/qemu-ga"):
        if (live_root / relpath).exists():
            return True
    return False


def _guest_agent_service_prestaged(live_root: Path) -> bool:
    for relpath in (
        "usr/lib/systemd/system/qemu-guest-agent.service",
        "lib/systemd/system/qemu-guest-agent.service",
    ):
        if (live_root / relpath).exists():
            return True
    return False


def _guest_agent_udev_trigger_present(live_root: Path) -> bool:
    rules_path = live_root / "usr/lib/udev/rules.d/60-qemu-guest-agent.rules"
    if not rules_path.exists():
        return False
    body = rules_path.read_text(encoding="utf-8", errors="replace")
    return "org.qemu.guest_agent.0" in body and "qemu-guest-agent.service" in body


def _library_paths_present(live_root: Path, soname: str) -> bool:
    search_roots = (
        live_root / "usr/lib",
        live_root / "lib",
        live_root / "usr/lib/x86_64-linux-gnu",
        live_root / "lib/x86_64-linux-gnu",
    )
    for search_root in search_roots:
        if not search_root.exists():
            continue
        if list(search_root.rglob(soname)):
            return True
        if list(search_root.rglob(f"{soname}*")):
            return True
    return False


def _required_shared_libs_present(live_root: Path) -> dict[str, bool]:
    return {
        soname: _library_paths_present(live_root, soname)
        for soname in QEMU_GUEST_AGENT_REQUIRED_SHARED_LIBS
    }


def build_report(*, live_root: Path, apt_policy: Path) -> dict:
    live_root = live_root.resolve(strict=False)
    bootstrap_bin = live_root / BOOTSTRAP_BIN_RELPATH
    autostart = live_root / WELCOME_AUTOSTART_RELPATH

    bootstrap_installed = bootstrap_bin.exists()
    autostart_wires_bootstrap = _autostart_delegates_to_bootstrap(autostart)
    policy_requires = _policy_requires_guest_agent(apt_policy)
    binary_prestaged = _guest_agent_binary_prestaged(live_root)
    service_prestaged = _guest_agent_service_prestaged(live_root)
    udev_trigger_present = _guest_agent_udev_trigger_present(live_root)
    shared_libs_present = _required_shared_libs_present(live_root)
    runtime_dependencies_present = all(shared_libs_present.values())

    bootstrap_staged = bool(
        bootstrap_installed and autostart_wires_bootstrap and policy_requires
    )
    prestaged = bool(
        binary_prestaged and service_prestaged and udev_trigger_present and runtime_dependencies_present
    )

    reachability_path = (
        "prestaged"
        if prestaged
        else ("runtime_apt_install" if bootstrap_staged else "unstaged")
    )

    return {
        "ok": True,
        "live_root": str(live_root),
        "apt_policy": str(apt_policy),
        "qemu_guest_agent_package": QEMU_GUEST_AGENT_PACKAGE,
        "bootstrap_bin": str(bootstrap_bin),
        "bootstrap_installed": bootstrap_installed,
        "welcome_autostart_delegates_to_bootstrap": autostart_wires_bootstrap,
        "apt_policy_requires_guest_agent": policy_requires,
        "live_guest_agent_bootstrap_staged": bootstrap_staged,
        "live_guest_agent_binary_prestaged": binary_prestaged,
        "live_guest_agent_service_prestaged": service_prestaged,
        "live_guest_agent_service_enabled": udev_trigger_present,
        "live_guest_agent_service_trigger": "udev",
        "live_guest_agent_udev_trigger_present": udev_trigger_present,
        "live_guest_agent_required_shared_libs_present": shared_libs_present,
        "live_guest_agent_runtime_dependencies_present": runtime_dependencies_present,
        "live_guest_agent_prestaged": prestaged,
        "live_guest_agent_reachability_path": reachability_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify live-root staging for qemu-guest-agent first-boot reachability"
    )
    parser.add_argument("--live-root", required=True)
    parser.add_argument("--apt-policy", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_report(
        live_root=Path(args.live_root),
        apt_policy=Path(args.apt_policy),
    )
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(report, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

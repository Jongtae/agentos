#!/usr/bin/env python3
"""Replace Ubuntu desktop installer autostart with AgentOS bootstrap.

Ubuntu 24.04 desktop live images normally launch
``ubuntu-desktop-installer.service`` in the user graphical session. Simply
masking that service can leave the session without a first-screen owner and
cause the black-screen regression observed in fresh UTM boots.

This helper keeps the same user-service entrypoint but rewires it to an
AgentOS-owned bootstrap unit:
  * remove vendor ``graphical-session.target.wants`` symlinks that point at
    the Ubuntu installer service;
  * replace the user-scope ``ubuntu-desktop-installer.service`` unit with an
    AgentOS bootstrap unit that runs ``/usr/local/bin/agentos-live-session-bootstrap``;
  * recreate the ``graphical-session.target.wants`` symlink so the graphical
    session still launches a first-screen owner through the same systemd path;
  * remove the vendor unit file from ``usr/lib/systemd/user`` so the vendor
    installer cannot reassert itself.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

INSTALLER_UNIT_NAME = "ubuntu-desktop-installer.service"
BOOTSTRAP_EXEC = "/usr/local/bin/agentos-live-session-bootstrap"
BOOTSTRAP_UNIT_CONTENT = f"""[Unit]
Description=AgentOS Live Session Bootstrap
After=graphical-session-pre.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart={BOOTSTRAP_EXEC}
Restart=no

[Install]
WantedBy=graphical-session.target
"""

WANT_LINK_RELPATHS = (
    f"etc/systemd/user/graphical-session.target.wants/{INSTALLER_UNIT_NAME}",
    f"usr/lib/systemd/user/graphical-session.target.wants/{INSTALLER_UNIT_NAME}",
)
ETC_UNIT_RELPATH = f"etc/systemd/user/{INSTALLER_UNIT_NAME}"
VENDOR_UNIT_RELPATH = f"usr/lib/systemd/user/{INSTALLER_UNIT_NAME}"
PRIMARY_WANT_RELPATH = f"etc/systemd/user/graphical-session.target.wants/{INSTALLER_UNIT_NAME}"


def _ensure_inside(live_root: Path, candidate: Path) -> Path:
    resolved_root = live_root.resolve()
    resolved_parent = candidate.parent.resolve(strict=False)
    try:
        resolved_parent.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"refusing to touch path outside live_root: {candidate}") from exc
    return candidate


def disable_ubuntu_installer_autostart(live_root: Path) -> dict:
    live_root = live_root.resolve(strict=False)
    removed_want_links: list[str] = []
    removed_vendor_units: list[str] = []
    skipped: list[str] = []

    for relpath in WANT_LINK_RELPATHS:
        target = _ensure_inside(live_root, live_root / relpath)
        if target.is_symlink() or target.exists():
            target.unlink()
            removed_want_links.append(str(target))
        else:
            skipped.append(str(target))

    etc_unit = _ensure_inside(live_root, live_root / ETC_UNIT_RELPATH)
    etc_unit.parent.mkdir(parents=True, exist_ok=True)
    if etc_unit.is_symlink() or etc_unit.exists():
        etc_unit.unlink()
    etc_unit.write_text(BOOTSTRAP_UNIT_CONTENT, encoding="utf-8")

    vendor_unit = _ensure_inside(live_root, live_root / VENDOR_UNIT_RELPATH)
    if vendor_unit.is_symlink() or vendor_unit.exists():
        vendor_unit.unlink()
        removed_vendor_units.append(str(vendor_unit))
    else:
        skipped.append(str(vendor_unit))

    primary_want = _ensure_inside(live_root, live_root / PRIMARY_WANT_RELPATH)
    primary_want.parent.mkdir(parents=True, exist_ok=True)
    if primary_want.is_symlink() or primary_want.exists():
        primary_want.unlink()
    os.symlink(f"../{INSTALLER_UNIT_NAME}", primary_want)

    installer_masked = (
        etc_unit.exists()
        and BOOTSTRAP_EXEC in etc_unit.read_text(encoding="utf-8")
        and not vendor_unit.exists()
    )
    graphical_session_wants_cleared = all(
        not (live_root / rel).exists() and not (live_root / rel).is_symlink()
        for rel in WANT_LINK_RELPATHS[1:]
    )
    bootstrap_wired = primary_want.is_symlink() and os.readlink(primary_want) == f"../{INSTALLER_UNIT_NAME}"

    return {
        "ok": True,
        "live_root": str(live_root),
        "installer_unit": INSTALLER_UNIT_NAME,
        "removed_want_links": removed_want_links,
        "removed_vendor_units": removed_vendor_units,
        "skipped": skipped,
        "installer_masked": installer_masked,
        "graphical_session_wants_cleared": graphical_session_wants_cleared,
        "bootstrap_unit_path": str(etc_unit),
        "bootstrap_exec": BOOTSTRAP_EXEC,
        "bootstrap_wired": bootstrap_wired,
        "agentos_welcome_owns_first_screen": bool(
            installer_masked and graphical_session_wants_cleared and bootstrap_wired
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replace Ubuntu desktop installer autostart with AgentOS bootstrap inside a live-root"
    )
    parser.add_argument("--live-root", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = disable_ubuntu_installer_autostart(Path(args.live_root))
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(report, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

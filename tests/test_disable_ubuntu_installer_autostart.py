from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from scripts.disable_ubuntu_installer_autostart import (
    BOOTSTRAP_EXEC,
    INSTALLER_UNIT_NAME,
    disable_ubuntu_installer_autostart,
)


class DisableUbuntuInstallerAutostartTests(unittest.TestCase):
    def _build_live_root(self, td: Path) -> Path:
        live_root = td / "live-root"
        (live_root / "etc/systemd/user/graphical-session.target.wants").mkdir(parents=True)
        (live_root / "usr/lib/systemd/user").mkdir(parents=True)
        # simulate Ubuntu 24.04 layout: a real unit file in both etc/ and /usr,
        # with a symlink in graphical-session.target.wants pointing at the unit
        unit_vendor = live_root / "usr/lib/systemd/user" / INSTALLER_UNIT_NAME
        unit_vendor.write_text("[Unit]\nDescription=Ubuntu Desktop Installer\n", encoding="utf-8")
        unit_etc = live_root / "etc/systemd/user" / INSTALLER_UNIT_NAME
        unit_etc.write_text("[Unit]\nDescription=Ubuntu Desktop Installer\n", encoding="utf-8")
        want_link = (
            live_root
            / "etc/systemd/user/graphical-session.target.wants"
            / INSTALLER_UNIT_NAME
        )
        os.symlink(unit_vendor, want_link)
        return live_root

    def test_replaces_installer_with_agentos_bootstrap_and_rewires_autostart(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            live_root = self._build_live_root(Path(td))
            report = disable_ubuntu_installer_autostart(live_root)

            self.assertTrue(report["ok"])
            self.assertTrue(report["installer_masked"])
            self.assertTrue(report["graphical_session_wants_cleared"])
            self.assertTrue(report["bootstrap_wired"])
            self.assertTrue(report["agentos_welcome_owns_first_screen"])

            etc_unit = live_root / "etc/systemd/user" / INSTALLER_UNIT_NAME
            self.assertTrue(etc_unit.exists())
            self.assertFalse(etc_unit.is_symlink())
            self.assertIn(BOOTSTRAP_EXEC, etc_unit.read_text(encoding="utf-8"))

            want_link = (
                live_root
                / "etc/systemd/user/graphical-session.target.wants"
                / INSTALLER_UNIT_NAME
            )
            self.assertTrue(want_link.is_symlink())
            self.assertEqual(os.readlink(want_link), f"../{INSTALLER_UNIT_NAME}")

            vendor_unit = live_root / "usr/lib/systemd/user" / INSTALLER_UNIT_NAME
            self.assertFalse(vendor_unit.exists())

    def test_is_idempotent_when_installer_already_absent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            live_root = Path(td) / "live-root"
            live_root.mkdir()

            report = disable_ubuntu_installer_autostart(live_root)

            self.assertTrue(report["ok"])
            # the etc unit is always replaced with the AgentOS bootstrap so
            # the graphical session still has an explicit first-screen owner
            self.assertTrue(report["installer_masked"])
            self.assertTrue(report["graphical_session_wants_cleared"])
            self.assertTrue(report["bootstrap_wired"])
            etc_unit = live_root / "etc/systemd/user" / INSTALLER_UNIT_NAME
            self.assertIn(BOOTSTRAP_EXEC, etc_unit.read_text(encoding="utf-8"))

            # second run must not error and must keep the replacement unit
            report2 = disable_ubuntu_installer_autostart(live_root)
            self.assertTrue(report2["installer_masked"])
            self.assertTrue(report2["bootstrap_wired"])

    def test_refuses_paths_outside_live_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            live_root = Path(td) / "live-root"
            live_root.mkdir()
            # craft an escape attempt via a traversal symlink
            outside = Path(td) / "outside"
            outside.mkdir()
            (live_root / "etc").mkdir()
            (live_root / "etc" / "systemd").symlink_to(outside)

            with self.assertRaises(ValueError):
                disable_ubuntu_installer_autostart(live_root)

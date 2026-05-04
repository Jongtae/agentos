from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.patch_agentos_boot_entries import patch_boot_entries


class PatchAgentosBootEntriesTests(unittest.TestCase):
    def test_patch_boot_entries_rewrites_ubuntu_labels(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            iso_root = Path(td)
            cfg = iso_root / "boot/grub/grub.cfg"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_text(
                'menuentry "Try or Install Ubuntu" {}\n'
                'menuentry "Install Ubuntu" {}\n'
                'menuentry "Ubuntu (safe graphics)" {}\n',
                encoding="utf-8",
            )

            report = patch_boot_entries(iso_root)
            patched = cfg.read_text(encoding="utf-8")

            self.assertIn('set default="0"', patched)
            self.assertIn("set timeout_style=hidden", patched)
            self.assertIn("set timeout=1", patched)
            self.assertIn("Continue to AgentOS", patched)
            self.assertIn("AgentOS Recovery", patched)
            self.assertTrue(report["installer_hidden_default_path"])
            self.assertEqual(report["default_boot_target_label"], "Continue to AgentOS")
            self.assertEqual(report["default_boot_target_entry_index"], 0)
            self.assertTrue(report["grub_default_target_configured"])
            self.assertTrue(report["default_boot_target_configured"])
            self.assertTrue(report["install_path_available"])
            self.assertEqual(report["forbidden_labels_remaining"], [])

    def test_default_boot_target_can_activate_without_recovery_entry(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            iso_root = Path(td)
            cfg = iso_root / "boot/grub/grub.cfg"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_text(
                'set default="0"\n'
                'menuentry "Try or Install Ubuntu" {\n'
                '\tlinux /casper/vmlinuz --- quiet splash\n'
                '\tinitrd /casper/initrd\n'
                '}\n'
                "menuentry 'Boot from next volume' { exit 1 }\n",
                encoding="utf-8",
            )

            report = patch_boot_entries(iso_root)

            self.assertTrue(report["continue_present"])
            self.assertFalse(report["recovery_present"])
            self.assertTrue(report["grub_default_target_configured"])
            self.assertTrue(report["default_boot_target_configured"])
            self.assertTrue(report["installer_hidden_default_path"])

    def test_patch_boot_entries_keeps_combined_ubuntu_24_04_runtime_first_without_install_peer(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            iso_root = Path(td)
            cfg = iso_root / "boot/grub/grub.cfg"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_text(
                (
                    'set timeout=30\n'
                    'menuentry "Try or Install Ubuntu" {\n'
                    '\tset gfxpayload=keep\n'
                    '\tlinux\t/casper/vmlinuz  --- quiet splash\n'
                    '\tinitrd\t/casper/initrd\n'
                    '}\n'
                    'menuentry "Ubuntu (safe graphics)" {\n'
                    '\tset gfxpayload=keep\n'
                    '\tlinux\t/casper/vmlinuz nomodeset  --- quiet splash\n'
                    '\tinitrd\t/casper/initrd\n'
                    '}\n'
                    'grub_platform\n'
                    'if [ "$grub_platform" = "efi" ]; then\n'
                    'menuentry "UEFI Firmware Settings" { fwsetup }\n'
                    'fi\n'
                ),
                encoding="utf-8",
            )

            report = patch_boot_entries(iso_root)
            patched = cfg.read_text(encoding="utf-8")

            self.assertIn('menuentry "Continue to AgentOS"', patched)
            self.assertIn('menuentry "AgentOS Recovery"', patched)
            self.assertNotIn('menuentry "Install AgentOS"', patched)

            self.assertTrue(report["continue_present"])
            self.assertFalse(report["install_present"])
            self.assertTrue(report["install_path_available"])
            self.assertTrue(report["recovery_present"])
            self.assertTrue(report["installer_hidden_default_path"])
            self.assertEqual(report["default_boot_target_label"], "Continue to AgentOS")
            self.assertEqual(report["default_boot_target_entry_index"], 0)
            self.assertTrue(report["grub_default_target_configured"])
            self.assertTrue(report["default_boot_target_configured"])
            self.assertEqual(report["forbidden_labels_remaining"], [])
            self.assertIn("console=tty0", patched)
            self.assertIn("console=ttyAMA0,115200n8", patched)
            self.assertIn("maxcpus=1", patched)
            self.assertNotIn("--- console=tty0", patched)
            self.assertNotIn("console=tty1", patched)
            self.assertNotIn("systemd.journald.forward_to_console=1", patched)
            self.assertIn("systemd.unit=multi-user.target", patched)
            self.assertIn("plymouth.enable=0", patched)
            self.assertIn("systemd.mask=snapd.apparmor.service", patched)
            self.assertIn("systemd.mask=casper-md5check.service", patched)
            self.assertIn("systemd.mask=serial-getty@ttyS0.service", patched)
            self.assertNotIn("systemd.mask=serial-getty@ttyAMA0.service", patched)
            self.assertNotIn("systemd.mask=serial-getty@ttyS0.service ---", patched)
            self.assertNotIn("quiet", patched)
            self.assertNotIn("splash", patched)
            self.assertIn("terminal_input console", patched)
            self.assertIn("terminal_output console", patched)
            self.assertNotIn("terminal_input console serial", patched)
            self.assertNotIn("terminal_output console serial", patched)
            self.assertNotIn("serial --unit=0", patched)
            self.assertIn("set timeout_style=hidden", patched)
            self.assertIn("set timeout=1", patched)
            self.assertNotIn("\ngrub_platform\n", patched)
            self.assertIn('if [ "$grub_platform" = "efi" ]; then', patched)

    def test_patch_boot_entries_rewrites_live_server_labels_to_exact_runtime_target(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            iso_root = Path(td)
            cfg = iso_root / "boot/grub/grub.cfg"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_text(
                (
                    'menuentry "Ubuntu Server" {\n'
                    '\tlinux /casper/vmlinuz ---\n'
                    '\tinitrd /casper/initrd\n'
                    '}\n'
                    'menuentry "Ubuntu Server with the HWE kernel" {\n'
                    '\tlinux /casper/hwe-vmlinuz ---\n'
                    '\tinitrd /casper/hwe-initrd\n'
                    '}\n'
                ),
                encoding="utf-8",
            )

            report = patch_boot_entries(iso_root)
            patched = cfg.read_text(encoding="utf-8")

            self.assertIn('menuentry "Continue to AgentOS"', patched)
            self.assertIn('menuentry "AgentOS Recovery"', patched)
            self.assertNotIn("Continue to AgentOS Server", patched)
            self.assertNotIn("Ubuntu Server", patched)
            self.assertTrue(report["continue_present"])
            self.assertTrue(report["recovery_present"])
            self.assertTrue(report["installer_hidden_default_path"])
            self.assertTrue(report["default_boot_target_configured"])
            self.assertEqual(report["forbidden_labels_remaining"], [])

    def test_patch_boot_entries_rewrites_try_or_install_server_label_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            iso_root = Path(td)
            cfg = iso_root / "boot/grub/grub.cfg"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_text(
                (
                    'menuentry "Try or Install Ubuntu Server" {\n'
                    '\tlinux /casper/vmlinuz ---\n'
                    '\tinitrd /casper/initrd\n'
                    '}\n'
                    'menuentry "Ubuntu Server with the HWE kernel" {\n'
                    '\tlinux /casper/hwe-vmlinuz ---\n'
                    '\tinitrd /casper/hwe-initrd\n'
                    '}\n'
                ),
                encoding="utf-8",
            )

            report = patch_boot_entries(iso_root)
            patched = cfg.read_text(encoding="utf-8")

            self.assertIn('menuentry "Continue to AgentOS"', patched)
            self.assertIn('menuentry "AgentOS Recovery"', patched)
            self.assertNotIn("Try or Install Continue", patched)
            self.assertNotIn("Ubuntu Server", patched)
            self.assertEqual(report["forbidden_labels_remaining"], [])

    def test_patch_boot_entries_keeps_existing_install_source_entry_out_of_runtime_first_contract(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            iso_root = Path(td)
            cfg = iso_root / "boot/grub/grub.cfg"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_text(
                (
                    'menuentry "Try or Install Ubuntu" {\n'
                    '\tlinux /casper/vmlinuz --- quiet splash\n'
                    '\tinitrd /casper/initrd\n'
                    '}\n'
                    'menuentry "Install Ubuntu" {\n'
                    '\tlinux /casper/vmlinuz only-ubiquity\n'
                    '\tinitrd /casper/initrd\n'
                    '}\n'
                    'menuentry "Ubuntu (safe graphics)" {\n'
                    '\tlinux /casper/vmlinuz nomodeset\n'
                    '\tinitrd /casper/initrd\n'
                    '}\n'
                ),
                encoding="utf-8",
            )
            report = patch_boot_entries(iso_root)
            patched = cfg.read_text(encoding="utf-8")

            self.assertIn('menuentry "Continue to AgentOS"', patched)
            self.assertIn('menuentry "AgentOS Recovery"', patched)
            self.assertNotIn('menuentry "Install AgentOS"', patched)
            self.assertIn('menuentry "Install Ubuntu"', patched)
            self.assertEqual(patched.count('menuentry "Install Ubuntu"'), 1)
            self.assertTrue(report["continue_present"])
            self.assertFalse(report["install_present"])
            self.assertTrue(report["installer_hidden_default_path"])
            self.assertTrue(report["install_path_available"])
            self.assertTrue(report["default_boot_target_configured"])
            self.assertIn("console=tty0", patched)
            self.assertIn("console=ttyAMA0,115200n8", patched)
            self.assertIn("maxcpus=1", patched)
            self.assertNotIn("--- console=tty0", patched)
            self.assertNotIn("console=tty1", patched)
            self.assertNotIn("systemd.journald.forward_to_console=1", patched)
            self.assertIn("systemd.unit=multi-user.target", patched)
            self.assertIn("plymouth.enable=0", patched)
            self.assertIn("systemd.mask=snapd.apparmor.service", patched)
            self.assertIn("systemd.mask=casper-md5check.service", patched)
            self.assertIn("systemd.mask=serial-getty@ttyS0.service", patched)
            self.assertNotIn("systemd.mask=serial-getty@ttyAMA0.service", patched)
            self.assertNotIn("systemd.mask=serial-getty@ttyS0.service ---", patched)
            self.assertNotIn("quiet", patched)
            self.assertNotIn("splash", patched)

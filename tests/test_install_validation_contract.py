from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.verify_install_validation_contract import build_report


class InstallValidationContractTests(unittest.TestCase):
    def test_metadata_and_install_root_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            metadata = root / "agentos-release-metadata.json"
            metadata.write_text(
                json.dumps(
                    {
                        "distribution_contract": "agentos_managed_session",
                        "primary_entry_contract": "agentos_setup_to_ai_shell",
                        "artifact_type": "deb",
                    }
                ),
                encoding="utf-8",
            )

            install_root = root / "install"
            (install_root / "usr/local/bin").mkdir(parents=True, exist_ok=True)
            (install_root / "etc/systemd/system/getty@tty1.service.d").mkdir(parents=True, exist_ok=True)
            (install_root / "etc/profile.d").mkdir(parents=True, exist_ok=True)
            (install_root / "etc/systemd/system").mkdir(parents=True, exist_ok=True)

            for name in ("agentos-shell", "agentos-kernelctl", "agentos-firstrun", "agentos-live-firstrun-service"):
                (install_root / "usr/local/bin" / name).write_text("ok\n", encoding="utf-8")

            (install_root / "etc/systemd/system/agentos-kernel.service").write_text(
                "ExecStart=/usr/local/bin/agentos-shell --kernel-mode\n", encoding="utf-8"
            )
            (install_root / "etc/systemd/system/agentos-firstrun.service").write_text(
                "Description=AgentOS Setup Session Service\n", encoding="utf-8"
            )
            (install_root / "etc/systemd/system/getty@tty1.service.d/override.conf").write_text(
                "--autologin agentos\n", encoding="utf-8"
            )
            (install_root / "etc/profile.d/agentos-kernel-autostart.sh").write_text(
                "agentos-firstrun\nagentos-shell\n", encoding="utf-8"
            )

            report = build_report(metadata=str(metadata), install_root=str(install_root))
            self.assertTrue(report["ok"])
            self.assertTrue(report["metadata"]["ok"])
            self.assertTrue(report["install_root"]["ok"])

    def test_missing_contract_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            metadata = root / "agentos-release-metadata.json"
            metadata.write_text(
                json.dumps(
                    {
                        "distribution_contract": "wrong",
                        "primary_entry_contract": "wrong",
                    }
                ),
                encoding="utf-8",
            )
            report = build_report(metadata=str(metadata))
            self.assertFalse(report["ok"])
            self.assertGreaterEqual(len(report["errors"]), 1)


if __name__ == "__main__":
    unittest.main()

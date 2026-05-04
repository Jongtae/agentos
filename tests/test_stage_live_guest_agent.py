from __future__ import annotations

import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import stage_live_guest_agent


class StageLiveGuestAgentTests(unittest.TestCase):
    def test_archive_for_arch_uses_ubuntu_ports_for_arm64(self) -> None:
        self.assertEqual(stage_live_guest_agent._archive_for_arch("amd64"), stage_live_guest_agent.UBUNTU_ARCHIVE)
        self.assertEqual(stage_live_guest_agent._archive_for_arch("arm64"), stage_live_guest_agent.UBUNTU_PORTS_ARCHIVE)

    def test_stage_guest_agent_reports_binary_and_service_presence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            live_root = root / "live-root"
            cache_dir = root / "cache"
            live_root.mkdir()

            def fake_find_package(package_name: str = stage_live_guest_agent.PACKAGE_NAME, *, arch: str = "amd64") -> dict:
                if package_name == "qemu-guest-agent":
                    return {
                        "package": package_name,
                        "arch": arch,
                        "version": "1:8.2.2+ds-test",
                        "url": "https://example.invalid/qemu-guest-agent.deb",
                        "filename": f"pool/universe/q/qemu/qemu-guest-agent_test_{arch}.deb",
                        "depends": "libc6 (>= 2.38), liburing2 (>= 2.3)",
                    }
                if package_name == "liburing2":
                    return {
                        "package": package_name,
                        "arch": arch,
                        "version": "2.5-test",
                        "url": "https://example.invalid/liburing2.deb",
                        "filename": f"pool/main/libu/liburing/liburing2_test_{arch}.deb",
                        "depends": "",
                    }
                raise AssertionError(package_name)

            def fake_download(url: str, destination: Path) -> None:
                destination.write_bytes(b"deb")

            def fake_extract(deb_path: Path, destination: Path) -> list[str]:
                if "liburing2" in deb_path.name:
                    (destination / "usr" / "lib" / "x86_64-linux-gnu").mkdir(parents=True, exist_ok=True)
                    (destination / "usr" / "lib" / "x86_64-linux-gnu" / "liburing.so.2").write_text(
                        "binary\n", encoding="utf-8"
                    )
                    return ["usr/lib/x86_64-linux-gnu/liburing.so.2"]
                (destination / "usr" / "sbin").mkdir(parents=True, exist_ok=True)
                (destination / "lib" / "systemd" / "system").mkdir(parents=True, exist_ok=True)
                (destination / "usr" / "lib" / "udev" / "rules.d").mkdir(parents=True, exist_ok=True)
                (destination / "usr" / "sbin" / "qemu-ga").write_text("#!/bin/sh\n", encoding="utf-8")
                (destination / "lib" / "systemd" / "system" / "qemu-guest-agent.service").write_text(
                    "[Unit]\nDescription=QEMU Guest Agent\n",
                    encoding="utf-8",
                )
                (destination / "usr" / "lib" / "udev" / "rules.d" / "60-qemu-guest-agent.rules").write_text(
                    'SUBSYSTEM=="virtio-ports", ATTR{name}=="org.qemu.guest_agent.0", '
                    'TAG+="systemd", ENV{SYSTEMD_WANTS}="qemu-guest-agent.service"\n',
                    encoding="utf-8",
                )
                return ["usr/sbin/qemu-ga", "lib/systemd/system/qemu-guest-agent.service"]

            with mock.patch.object(stage_live_guest_agent, "_find_package", fake_find_package), mock.patch.object(
                stage_live_guest_agent, "_download", fake_download
            ), mock.patch.object(stage_live_guest_agent, "_extract_deb_data", fake_extract):
                report = stage_live_guest_agent.stage_guest_agent(live_root=live_root, cache_dir=cache_dir, arch="arm64")

            self.assertTrue(report["ok"])
            self.assertEqual(report["arch"], "arm64")
            self.assertTrue(report["binary_present"])
            self.assertTrue(report["service_present"])
            self.assertTrue(report["service_enabled"])
            self.assertEqual(report["service_trigger"], "udev")
            self.assertTrue(report["udev_trigger_present"])
            self.assertEqual(report["service_enable_target"], "")
            self.assertEqual(report["package_version"], "1:8.2.2+ds-test")
            self.assertEqual(report["staged_dependency_packages"], ["liburing2"])

    def test_skips_dependency_when_payload_already_present(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            live_root = root / "live-root"
            cache_dir = root / "cache"
            (live_root / "usr" / "lib" / "x86_64-linux-gnu").mkdir(parents=True)
            (live_root / "usr" / "lib" / "x86_64-linux-gnu" / "liburing.so.2").write_text(
                "existing\n", encoding="utf-8"
            )

            def fake_find_package(package_name: str = stage_live_guest_agent.PACKAGE_NAME, *, arch: str = "amd64") -> dict:
                if package_name == "qemu-guest-agent":
                    return {
                        "package": package_name,
                        "arch": arch,
                        "version": "1:8.2.2+ds-test",
                        "url": "https://example.invalid/qemu-guest-agent.deb",
                        "filename": "pool/universe/q/qemu/qemu-guest-agent_test_amd64.deb",
                        "depends": "liburing2 (>= 2.3)",
                    }
                return {
                    "package": package_name,
                    "arch": arch,
                    "version": "2.5-test",
                    "url": "https://example.invalid/liburing2.deb",
                    "filename": "pool/main/libu/liburing/liburing2_test_amd64.deb",
                    "depends": "",
                }

            def fake_download(url: str, destination: Path) -> None:
                destination.write_bytes(b"deb")

            def fake_extract(deb_path: Path, destination: Path) -> list[str]:
                if "liburing2" in deb_path.name:
                    (destination / "usr" / "lib" / "x86_64-linux-gnu").mkdir(parents=True, exist_ok=True)
                    (destination / "usr" / "lib" / "x86_64-linux-gnu" / "liburing.so.2").write_text(
                        "binary\n", encoding="utf-8"
                    )
                    return ["usr/lib/x86_64-linux-gnu/liburing.so.2"]
                (destination / "usr" / "sbin").mkdir(parents=True, exist_ok=True)
                (destination / "lib" / "systemd" / "system").mkdir(parents=True, exist_ok=True)
                (destination / "usr" / "lib" / "udev" / "rules.d").mkdir(parents=True, exist_ok=True)
                (destination / "usr" / "sbin" / "qemu-ga").write_text("#!/bin/sh\n", encoding="utf-8")
                (destination / "lib" / "systemd" / "system" / "qemu-guest-agent.service").write_text(
                    "[Unit]\nDescription=QEMU Guest Agent\n",
                    encoding="utf-8",
                )
                (destination / "usr" / "lib" / "udev" / "rules.d" / "60-qemu-guest-agent.rules").write_text(
                    'SUBSYSTEM=="virtio-ports", ATTR{name}=="org.qemu.guest_agent.0", '
                    'TAG+="systemd", ENV{SYSTEMD_WANTS}="qemu-guest-agent.service"\n',
                    encoding="utf-8",
                )
                return ["usr/sbin/qemu-ga", "lib/systemd/system/qemu-guest-agent.service"]

            with mock.patch.object(stage_live_guest_agent, "_find_package", fake_find_package), mock.patch.object(
                stage_live_guest_agent, "_download", fake_download
            ), mock.patch.object(stage_live_guest_agent, "_extract_deb_data", fake_extract):
                report = stage_live_guest_agent.stage_guest_agent(live_root=live_root, cache_dir=cache_dir)

            self.assertEqual(report["staged_dependency_packages"], [])

    def test_extract_deb_data_supports_gzip_tar_members(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            deb_path = root / "pkg.deb"
            dest = root / "dest"
            dest.mkdir()

            data_tar = root / "data.tar.gz"
            with tarfile.open(data_tar, "w:gz") as archive:
                payload = b"hello\n"
                info = tarfile.TarInfo("usr/sbin/qemu-ga")
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))

            def fake_run(cmd, cwd=None, check=None, capture_output=None, text=None):
                if cmd[:2] == ["ar", "x"]:
                    (Path(cwd) / "data.tar.gz").write_bytes(data_tar.read_bytes())
                    class Result:
                        returncode = 0
                        stdout = ""
                        stderr = ""
                    return Result()
                raise AssertionError(cmd)

            with mock.patch.object(stage_live_guest_agent.subprocess, "run", fake_run):
                names = stage_live_guest_agent._extract_deb_data(deb_path, dest)

            self.assertIn("usr/sbin/qemu-ga", names)
            self.assertTrue((dest / "usr" / "sbin" / "qemu-ga").exists())


if __name__ == "__main__":
    unittest.main()

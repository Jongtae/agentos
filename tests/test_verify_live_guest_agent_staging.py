from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.verify_live_guest_agent_staging import build_report


POLICY_WITH_GUEST_AGENT = (
    "# package|min_version|major|tier\n"
    "curl|7.80||core\n"
    "qemu-guest-agent|1:8.0||core\n"
    "ollama|0.1|0|optional\n"
)
POLICY_WITHOUT_GUEST_AGENT = "# package|min_version|major|tier\ncurl|7.80||core\n"

WELCOME_AUTOSTART = (
    "[Desktop Entry]\n"
    "Type=Application\n"
    "Name=AgentOS Welcome\n"
    "Exec=/usr/local/bin/agentos-live-session-bootstrap\n"
    "Terminal=true\n"
)

WELCOME_AUTOSTART_DIRECT_SHELL = (
    "[Desktop Entry]\n"
    "Type=Application\n"
    "Name=AgentOS Welcome\n"
    "Exec=/usr/local/bin/agentos-welcome-shell\n"
    "Terminal=true\n"
)


def _scaffold(tmp: Path, *, bootstrap: bool, autostart: str | None) -> tuple[Path, Path]:
    live_root = tmp / "live-root"
    (live_root / "usr" / "local" / "bin").mkdir(parents=True, exist_ok=True)
    (live_root / "etc" / "xdg" / "autostart").mkdir(parents=True, exist_ok=True)
    if bootstrap:
        (live_root / "usr" / "local" / "bin" / "agentos-live-session-bootstrap").write_text(
            "#!/bin/sh\n", encoding="utf-8"
        )
    if autostart is not None:
        (live_root / "etc" / "xdg" / "autostart" / "agentos-welcome.desktop").write_text(
            autostart, encoding="utf-8"
        )
    policy_path = tmp / "apt-policy"
    policy_path.write_text(POLICY_WITH_GUEST_AGENT, encoding="utf-8")
    return live_root, policy_path


class VerifyLiveGuestAgentStagingTests(unittest.TestCase):
    def test_reports_bootstrap_staged_when_all_signals_present(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            live_root, policy = _scaffold(Path(td), bootstrap=True, autostart=WELCOME_AUTOSTART)
            report = build_report(live_root=live_root, apt_policy=policy)

            self.assertTrue(report["bootstrap_installed"])
            self.assertTrue(report["welcome_autostart_delegates_to_bootstrap"])
            self.assertTrue(report["apt_policy_requires_guest_agent"])
            self.assertTrue(report["live_guest_agent_bootstrap_staged"])
            # binaries/services are not installed in this scaffold, so the
            # report stays honest about prestaging
            self.assertFalse(report["live_guest_agent_prestaged"])
            self.assertFalse(report["live_guest_agent_runtime_dependencies_present"])
            self.assertEqual(report["live_guest_agent_reachability_path"], "runtime_apt_install")

    def test_reports_unstaged_when_autostart_bypasses_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            live_root, policy = _scaffold(
                Path(td), bootstrap=True, autostart=WELCOME_AUTOSTART_DIRECT_SHELL
            )
            report = build_report(live_root=live_root, apt_policy=policy)

            self.assertTrue(report["bootstrap_installed"])
            self.assertFalse(report["welcome_autostart_delegates_to_bootstrap"])
            self.assertFalse(report["live_guest_agent_bootstrap_staged"])
            self.assertEqual(report["live_guest_agent_reachability_path"], "unstaged")

    def test_reports_unstaged_when_policy_does_not_require_package(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            live_root, policy = _scaffold(Path(td), bootstrap=True, autostart=WELCOME_AUTOSTART)
            policy.write_text(POLICY_WITHOUT_GUEST_AGENT, encoding="utf-8")
            report = build_report(live_root=live_root, apt_policy=policy)

            self.assertFalse(report["apt_policy_requires_guest_agent"])
            self.assertFalse(report["live_guest_agent_bootstrap_staged"])

    def test_reports_prestaged_when_binary_and_service_present(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            live_root, policy = _scaffold(Path(td), bootstrap=True, autostart=WELCOME_AUTOSTART)
            (live_root / "usr" / "sbin").mkdir(parents=True)
            (live_root / "usr" / "sbin" / "qemu-ga").write_text("#!/bin/sh\n", encoding="utf-8")
            (live_root / "usr" / "lib" / "systemd" / "system").mkdir(parents=True)
            (live_root / "usr" / "lib" / "systemd" / "system" / "qemu-guest-agent.service").write_text(
                "[Unit]\n", encoding="utf-8"
            )
            (live_root / "usr" / "lib" / "udev" / "rules.d").mkdir(parents=True)
            (live_root / "usr" / "lib" / "udev" / "rules.d" / "60-qemu-guest-agent.rules").write_text(
                'SUBSYSTEM=="virtio-ports", ATTR{name}=="org.qemu.guest_agent.0", '
                'TAG+="systemd", ENV{SYSTEMD_WANTS}="qemu-guest-agent.service"\n',
                encoding="utf-8",
            )
            (live_root / "usr" / "lib" / "x86_64-linux-gnu").mkdir(parents=True)
            for soname in (
                "liburing.so.2",
                "libglib-2.0.so.0",
                "libgmodule-2.0.so.0",
                "libnuma.so.1",
                "libudev.so.1",
            ):
                (live_root / "usr" / "lib" / "x86_64-linux-gnu" / soname).write_text(
                    "binary\n", encoding="utf-8"
                )
            report = build_report(live_root=live_root, apt_policy=policy)

            self.assertTrue(report["live_guest_agent_binary_prestaged"])
            self.assertTrue(report["live_guest_agent_service_prestaged"])
            self.assertTrue(report["live_guest_agent_service_enabled"])
            self.assertEqual(report["live_guest_agent_service_trigger"], "udev")
            self.assertTrue(report["live_guest_agent_udev_trigger_present"])
            self.assertTrue(report["live_guest_agent_runtime_dependencies_present"])
            self.assertTrue(report["live_guest_agent_prestaged"])
            self.assertEqual(report["live_guest_agent_reachability_path"], "prestaged")

    def test_reports_not_prestaged_when_runtime_dependency_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            live_root, policy = _scaffold(Path(td), bootstrap=True, autostart=WELCOME_AUTOSTART)
            (live_root / "usr" / "sbin").mkdir(parents=True)
            (live_root / "usr" / "sbin" / "qemu-ga").write_text("#!/bin/sh\n", encoding="utf-8")
            (live_root / "usr" / "lib" / "systemd" / "system").mkdir(parents=True)
            (live_root / "usr" / "lib" / "systemd" / "system" / "qemu-guest-agent.service").write_text(
                "[Unit]\n", encoding="utf-8"
            )
            (live_root / "usr" / "lib" / "udev" / "rules.d").mkdir(parents=True)
            (live_root / "usr" / "lib" / "udev" / "rules.d" / "60-qemu-guest-agent.rules").write_text(
                'SUBSYSTEM=="virtio-ports", ATTR{name}=="org.qemu.guest_agent.0", '
                'TAG+="systemd", ENV{SYSTEMD_WANTS}="qemu-guest-agent.service"\n',
                encoding="utf-8",
            )
            report = build_report(live_root=live_root, apt_policy=policy)

            self.assertFalse(report["live_guest_agent_runtime_dependencies_present"])
            self.assertFalse(report["live_guest_agent_prestaged"])

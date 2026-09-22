"""PA1-INT-01 WU7: the background-service lifecycle must be reachable from the CLI.

J1 promises the owner can enable supported background operation and receive a
normal Telegram result without keeping an interactive terminal open. The
launchd lifecycle for that is owned by PA1-INSTALL-01 in ``service_control``;
these tests cover only the central-CLI wiring that makes it reachable, and the
requirement that a refused launchd operation is never printed as a success.

Evidence class: injected-runner tests. ``FakeLaunchctl`` replaces launchctl, so
no host launchd state is read or changed and nothing here observes a real
Homebrew install, a real login service, or a machine restart. Those remain
owner operating validation.
"""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from personal_agent import quickstart, service_control
from personal_agent.service_control import CommandResult, LABEL


ACTIONS = ("install", "upgrade", "start", "stop", "restart", "status", "uninstall")


class FakeLaunchctl:
    """Injected launchctl, in the style of tests/test_service_control.py."""

    def __init__(self):
        self.commands = []
        self.loaded = False
        self.running = False
        self.pid = 4321
        self.fail = {}

    def __call__(self, command):
        command = list(command)
        self.commands.append(command)
        key = command[1] if command[0] == "launchctl" and len(command) > 1 else tuple(command)
        if key in self.fail:
            return CommandResult(1, stderr=self.fail[key])
        if command[:2] == ["launchctl", "print"]:
            if not self.loaded:
                return CommandResult(113, stderr="Could not find service")
            state = "running" if self.running else "exited"
            return CommandResult(0, stdout=f"{LABEL} = {{\n state = {state}\n pid = {self.pid}\n}}\n")
        if command[:2] == ["launchctl", "bootstrap"]:
            self.loaded = self.running = True
        elif command[:2] == ["launchctl", "bootout"]:
            self.loaded = self.running = False
        elif command[:2] == ["launchctl", "kickstart"]:
            self.loaded = self.running = True
        return CommandResult(0)


class StartPathReached(Exception):
    """Raised from a patched QuickStore to prove the foreground path was taken."""


class ServiceCliTests(unittest.TestCase):
    def setUp(self):
        umask = os.umask(0o077)
        os.umask(umask)
        self.addCleanup(os.umask, umask)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.plist = self.home / "Library/LaunchAgents" / f"{LABEL}.plist"
        self.cli = self.root / "Cellar/personal-agentos/1.0.4/bin/agentos"
        self.cli.parent.mkdir(parents=True)
        self.cli.write_text("#!/bin/sh\n")
        self.cli.chmod(0o755)
        self.runner = FakeLaunchctl()
        self.seam_calls = []

    def invoke(self, *argv, seam=None):
        """Run `agentos <argv>` and return (exit code, parsed receipt, raw stdout)."""
        real = service_control.service_action

        def injected(action, **options):
            self.seam_calls.append((action, dict(options)))
            if seam is not None:
                return seam(action, **options)
            injected_defaults = {"home": self.home, "cli_path": self.cli, "runner": self.runner,
                                 "uid": 501, "environ": {}}
            return real(action, **{**injected_defaults, **options})

        stdout = io.StringIO()
        with patch.object(quickstart, "service_action", injected), \
             patch.object(sys, "argv", ["agentos", *argv]), \
             patch("sys.stdout", stdout):
            code = quickstart.main()
        raw = stdout.getvalue()
        return code, (json.loads(raw) if raw.strip() else None), raw

    # --- the seam is reachable, and it is the real one -------------------

    def test_cli_calls_the_service_control_seam_itself(self):
        self.assertIs(quickstart.service_action, service_control.service_action)

    def test_every_lifecycle_action_reaches_the_seam(self):
        for action in ACTIONS:
            with self.subTest(action=action):
                self.seam_calls.clear()
                code, receipt, _ = self.invoke(
                    "service", action, seam=lambda name, **options: {"ok": True, "action": name}
                )
                self.assertEqual([call[0] for call in self.seam_calls], [action])
                self.assertEqual(receipt, {"ok": True, "action": action})
                self.assertEqual(code, 0)

    def test_install_and_status_report_background_operation_through_the_cli(self):
        code, receipt, _ = self.invoke("service", "install")
        self.assertEqual(code, 0)
        self.assertTrue(receipt["ok"])
        self.assertTrue(receipt["background_available"])
        self.assertEqual(receipt["operation"], "install")
        self.assertTrue(self.plist.is_file())
        code, receipt, _ = self.invoke("service", "status")
        self.assertEqual(code, 0)
        self.assertEqual(receipt["status"], "running")
        self.assertTrue(receipt["background_available"])

    # --- failures stay failures ------------------------------------------

    def test_refused_install_is_not_reported_as_a_success(self):
        self.runner.fail["bootstrap"] = "Load failed: 5: Input/output error"
        code, receipt, raw = self.invoke("service", "install")
        self.assertEqual(code, 1)
        self.assertFalse(receipt["ok"])
        self.assertFalse(receipt["background_available"])
        self.assertNotEqual(receipt.get("status"), "running")
        self.assertTrue(receipt["data_preserved"])
        self.assertIn("next_action", receipt)
        self.assertNotIn("installed successfully", raw.lower())
        self.assertFalse(self.plist.exists(), "a refused install must not leave a definition behind")

    def test_start_without_an_installed_service_fails_truthfully(self):
        code, receipt, _ = self.invoke("service", "start")
        self.assertEqual(code, 1)
        self.assertFalse(receipt["ok"])
        self.assertFalse(receipt["background_available"])
        self.assertEqual(receipt["observed_status"], "not_installed")
        self.assertIn("foreground", receipt["next_action"])

    def test_unreadable_launchd_state_is_never_rendered_as_available(self):
        self.runner.fail["print"] = "Not authorized"
        code, receipt, _ = self.invoke("service", "status")
        self.assertEqual(code, 1)
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["status"], "unknown")
        self.assertFalse(receipt["background_available"])

    def test_the_printed_receipt_is_exactly_what_the_seam_reported(self):
        canned = {"ok": False, "status": "unknown", "background_available": "unknown",
                  "error": "launchd refused", "next_action": "Inspect service status."}
        code, receipt, raw = self.invoke("service", "status", seam=lambda action, **options: dict(canned))
        self.assertEqual(receipt, canned)
        self.assertEqual(len(raw.strip().splitlines()), 1, "no prose may be added around the receipt")
        self.assertEqual(code, 1)

    # --- the CLI must not invent a data directory -------------------------

    def test_cli_passes_no_data_directory_unless_the_owner_gave_one(self):
        self.invoke("service", "status")
        self.assertEqual(self.seam_calls[-1][1], {})

    def test_explicit_overrides_are_forwarded_to_the_seam(self):
        chosen = self.root / "chosen-data"
        self.invoke("service", "status", "--data", str(chosen), "--cli-path", str(self.cli))
        self.assertEqual(self.seam_calls[-1][1], {"data_dir": str(chosen), "cli_path": str(self.cli)})

    def test_status_reports_the_data_directory_the_service_was_installed_with(self):
        # Note: this pins --data forwarding at install time. The CLI's refusal to
        # invent a default is pinned separately above, because _reported_data_dir
        # would mask a bad default here by re-reading the installed definition.
        installed = self.root / "installed-owner-state"
        code, _, _ = self.invoke("service", "install", "--data", str(installed))
        self.assertEqual(code, 0)
        _, receipt, _ = self.invoke("service", "status")
        self.assertEqual(receipt["data_dir"], str(installed.resolve()))

    # --- dispatch boundaries ----------------------------------------------

    def test_an_unsupported_action_is_rejected_before_the_seam(self):
        with patch.object(sys, "argv", ["agentos", "service", "frobnicate"]), \
             patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                quickstart.main()
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(self.seam_calls, [])

    def test_service_without_an_action_is_rejected_before_the_seam(self):
        with patch.object(sys, "argv", ["agentos", "service"]), \
             patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                quickstart.main()
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(self.seam_calls, [])

    def test_the_foreground_start_action_is_unchanged(self):
        data = self.root / "foreground-data"
        for argv in (["agentos"], ["agentos", "start"], ["agentos", "start", "--no-browser"],
                     ["agentos", "start", "--data", str(data)]):
            with self.subTest(argv=argv):
                with patch.object(quickstart, "service_main",
                                  side_effect=AssertionError("start must not route to service_main")) as routed, \
                     patch.object(quickstart, "QuickStore", side_effect=StartPathReached) as store, \
                     patch.object(sys, "argv", argv):
                    with self.assertRaises(StartPathReached):
                        quickstart.main()
                routed.assert_not_called()
                store.assert_called_once()
                if "--data" in argv:
                    self.assertEqual(store.call_args.args[0], str(data))

    def test_service_dispatch_does_not_disturb_the_sibling_subcommands(self):
        with patch.object(quickstart, "plugins_main", return_value=None) as plugins, \
             patch.object(sys, "argv", ["agentos", "plugins", "list"]):
            quickstart.main()
        plugins.assert_called_once_with(["list"])
        self.assertEqual(self.seam_calls, [])


class ServiceCliProcessExitTests(unittest.TestCase):
    """The documented source-install invocation must also exit non-zero on failure."""

    def test_module_entry_point_propagates_the_failure_exit_code(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            environment = {**os.environ, "HOME": temp, "PYTHONPATH": str(root / "src")}
            environment.pop("AGENTOS_DATA", None)
            completed = subprocess.run(
                [sys.executable, "-m", "personal_agent.quickstart", "service", "start"],
                cwd=root, env=environment, capture_output=True, text=True, timeout=120,
            )
        # No service definition exists under the temporary HOME, so this is a
        # bounded failure receipt rather than an observation of the host.
        receipt = json.loads(completed.stdout)
        self.assertFalse(receipt["ok"])
        self.assertEqual(completed.returncode, 1)


if __name__ == "__main__":
    unittest.main()

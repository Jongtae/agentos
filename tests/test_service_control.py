import importlib.util
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch

from personal_agent.service_control import (
    CommandResult,
    LABEL,
    ServiceController,
    ServiceControlError,
    render_plist,
    resolve_cli_path,
    service_action,
)


SCRIPT_SPEC = importlib.util.spec_from_file_location(
    "quickstart_install_check", Path(__file__).resolve().parents[1] / "scripts/quickstart_install_check.py"
)
install_check = importlib.util.module_from_spec(SCRIPT_SPEC)
SCRIPT_SPEC.loader.exec_module(install_check)


class FakeLaunchctl:
    def __init__(self):
        self.commands = []
        self.loaded = False
        self.running = False
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
            return CommandResult(0, stdout=f"{LABEL} = {{\n state = {state}\n}}\n")
        if command[:2] == ["launchctl", "bootstrap"]:
            self.loaded = self.running = True
        elif command[:2] == ["launchctl", "bootout"]:
            self.loaded = self.running = False
        elif command[:2] == ["launchctl", "kickstart"]:
            self.loaded = self.running = True
        return CommandResult(0)


class ExitAfterFirstBootstrap(FakeLaunchctl):
    def __init__(self):
        super().__init__()
        self.bootstrap_count = 0

    def __call__(self, command):
        result = super().__call__(command)
        if list(command)[:2] == ["launchctl", "bootstrap"]:
            self.bootstrap_count += 1
            if self.bootstrap_count == 1:
                self.running = False
        return result


class FailBothBootstraps(FakeLaunchctl):
    def __call__(self, command):
        if list(command)[:2] == ["launchctl", "bootstrap"]:
            self.commands.append(list(command))
            return CommandResult(1, stderr="bootstrap rejected")
        return super().__call__(command)


class ServiceControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.cli = self.root / "Cellar/personal-agentos/1.0.4/bin/agentos"
        self.cli.parent.mkdir(parents=True)
        self.cli.write_text("#!/bin/sh\n")
        self.cli.chmod(0o755)
        self.runner = FakeLaunchctl()
        self.controller = ServiceController(home=self.home, cli_path=self.cli, runner=self.runner, uid=501)

    def tearDown(self):
        self.temp.cleanup()

    def test_plist_uses_resolved_cli_durable_data_and_loopback(self):
        payload = plistlib.loads(render_plist(self.cli.absolute(), self.controller.data_dir))
        arguments = payload["ProgramArguments"]
        self.assertEqual(arguments[0], str(self.cli.absolute()))
        self.assertEqual(arguments[arguments.index("--host") + 1], "127.0.0.1")
        self.assertEqual(arguments[arguments.index("--data") + 1], str((self.home / ".local/share/agentos").resolve()))
        self.assertEqual(arguments[1:3], ["start", "--no-browser"])
        self.assertTrue(payload["KeepAlive"])

    def test_resolve_cli_uses_path_then_actual_brew_prefix(self):
        self.assertEqual(resolve_cli_path(which=lambda name: str(self.cli) if name == "agentos" else None), self.cli.absolute())
        bin_cli = self.root / "brew-prefix/bin/agentos"
        bin_cli.parent.mkdir(parents=True)
        bin_cli.write_text("#!/bin/sh\n")
        bin_cli.chmod(0o755)

        def brew_runner(command):
            self.assertEqual(command, ["/custom/bin/brew", "--prefix"])
            return CommandResult(0, stdout=str(self.root / "brew-prefix") + "\n")

        resolved = resolve_cli_path(which=lambda name: "/custom/bin/brew" if name == "brew" else None, runner=brew_runner)
        self.assertEqual(resolved, bin_cli.absolute())

    def test_install_start_stop_status_restart_are_deterministic(self):
        installed = self.controller.install()
        self.assertEqual(installed["status"], "running")
        self.assertTrue(installed["background_available"])
        self.assertEqual(self.controller.plist_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.controller.start()["changed"], False)
        stopped = self.controller.stop()
        self.assertEqual(stopped["status"], "stopped")
        self.assertTrue(self.controller.plist_path.exists())
        self.assertTrue(self.controller.data_dir.exists())
        self.assertEqual(self.controller.start()["status"], "running")
        self.assertEqual(self.controller.restart()["status"], "running")
        verbs = [command[1] for command in self.runner.commands]
        self.assertIn("bootstrap", verbs)
        self.assertIn("bootout", verbs)

    def test_custom_data_dir_is_preserved_across_upgrade_and_uninstall(self):
        data = self.root / "owner-state"
        controller = ServiceController(home=self.home, data_dir=data, cli_path=self.cli, runner=self.runner, uid=501)
        controller.install()
        marker = data / "owner.txt"
        marker.write_text("keep")
        replacement = self.root / "brew-prefix/bin/agentos"
        replacement.parent.mkdir(parents=True)
        replacement.write_text("#!/bin/sh\n")
        replacement.chmod(0o755)
        upgraded = ServiceController(home=self.home, data_dir=data, cli_path=replacement, runner=self.runner, uid=501)
        with self.assertRaises(ServiceControlError) as caught:
            upgraded.install()
        self.assertIn("explicit service upgrade", caught.exception.next_action)
        self.assertEqual(upgraded.upgrade()["operation"], "upgrade")
        plist = plistlib.loads(upgraded.plist_path.read_bytes())
        self.assertEqual(plist["ProgramArguments"][0], str(replacement.absolute()))
        removed = upgraded.uninstall()
        self.assertTrue(removed["data_preserved"])
        self.assertEqual(marker.read_text(), "keep")
        self.assertFalse(upgraded.plist_path.exists())

    def test_later_lifecycle_recovers_installed_custom_data_path_by_default(self):
        data = self.root / "owner-state"
        installed = ServiceController(home=self.home, data_dir=data, cli_path=self.cli, runner=self.runner, uid=501)
        installed.install()
        marker = data / "owner.txt"
        marker.write_text("keep")

        restarted_context = ServiceController(home=self.home, cli_path=self.cli, runner=self.runner, uid=501)
        self.assertEqual(restarted_context.data_dir, data.resolve())
        self.assertEqual(restarted_context.status()["data_dir"], str(data.resolve()))
        upgraded = restarted_context.upgrade()
        self.assertEqual(upgraded["data_dir"], str(data.resolve()))
        plist = plistlib.loads(restarted_context.plist_path.read_bytes())
        self.assertEqual(
            plist["ProgramArguments"][plist["ProgramArguments"].index("--data") + 1],
            str(data.resolve()),
        )
        removed = restarted_context.uninstall()
        self.assertEqual(removed["data_dir"], str(data.resolve()))
        self.assertEqual(marker.read_text(), "keep")

    def test_explicit_unchanged_upgrade_restarts_running_process(self):
        self.controller.install()
        before = len(self.runner.commands)
        upgraded = self.controller.upgrade()
        self.assertEqual(upgraded["operation"], "upgrade")
        verbs = [command[1] for command in self.runner.commands[before:]]
        self.assertEqual(verbs, ["print", "print", "bootout", "bootstrap", "print"])

    def test_upgrade_preserves_explicitly_stopped_state_for_same_or_changed_plist(self):
        self.controller.install()
        self.controller.stop()
        before = len(self.runner.commands)
        unchanged = self.controller.upgrade()
        self.assertEqual(unchanged["status"], "stopped")
        self.assertFalse(unchanged["changed"])
        self.assertNotIn("bootstrap", [command[1] for command in self.runner.commands[before:]])

        replacement = self.root / "brew-prefix/bin/agentos"
        replacement.parent.mkdir(parents=True)
        replacement.write_text("#!/bin/sh\n")
        replacement.chmod(0o755)
        changed = ServiceController(home=self.home, cli_path=replacement, runner=self.runner, uid=501)
        before = len(self.runner.commands)
        upgraded = changed.upgrade()
        self.assertEqual(upgraded["status"], "stopped")
        self.assertTrue(upgraded["changed"])
        self.assertNotIn("bootstrap", [command[1] for command in self.runner.commands[before:]])
        self.assertEqual(plistlib.loads(changed.plist_path.read_bytes())["ProgramArguments"][0], str(replacement.absolute()))

    def test_upgrade_confirmation_failure_restores_previous_plist_and_service(self):
        original_runner = self.runner
        self.controller.install()
        previous = self.controller.plist_path.read_bytes()
        replacement = self.root / "brew-prefix/bin/agentos"
        replacement.parent.mkdir(parents=True)
        replacement.write_text("#!/bin/sh\n")
        replacement.chmod(0o755)
        failing_runner = ExitAfterFirstBootstrap()
        failing_runner.loaded = original_runner.loaded
        failing_runner.running = original_runner.running
        failing_runner.fail["kickstart"] = "new executable exited"
        upgraded = ServiceController(home=self.home, cli_path=replacement, runner=failing_runner, uid=501)
        with self.assertRaisesRegex(ServiceControlError, "rolled back"):
            upgraded.upgrade()
        self.assertEqual(upgraded.plist_path.read_bytes(), previous)
        self.assertTrue(failing_runner.loaded)
        self.assertTrue(failing_runner.running)
        self.assertGreaterEqual(failing_runner.bootstrap_count, 2)

    def test_upgrade_staging_failure_does_not_stop_previous_loaded_service(self):
        self.controller.install()
        previous = self.controller.plist_path.read_bytes()
        replacement = self.root / "brew-prefix/bin/agentos"
        replacement.parent.mkdir(parents=True)
        replacement.write_text("#!/bin/sh\n")
        replacement.chmod(0o755)
        upgraded = ServiceController(home=self.home, cli_path=replacement, runner=self.runner, uid=501)
        before = len(self.runner.commands)
        with patch.object(upgraded, "_stage_plist", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                upgraded.upgrade()
        self.assertEqual(upgraded.plist_path.read_bytes(), previous)
        self.assertTrue(self.runner.loaded)
        self.assertTrue(self.runner.running)
        self.assertNotIn("bootout", [command[1] for command in self.runner.commands[before:]])

    def test_failed_rollback_is_reported_as_unverified(self):
        self.controller.install()
        previous = self.controller.plist_path.read_bytes()
        replacement = self.root / "brew-prefix/bin/agentos"
        replacement.parent.mkdir(parents=True)
        replacement.write_text("#!/bin/sh\n")
        replacement.chmod(0o755)
        failing_runner = FailBothBootstraps()
        failing_runner.loaded = True
        failing_runner.running = True
        upgraded = ServiceController(home=self.home, cli_path=replacement, runner=failing_runner, uid=501)
        with self.assertRaisesRegex(ServiceControlError, "rollback could not be verified"):
            upgraded.upgrade()
        self.assertEqual(upgraded.plist_path.read_bytes(), previous)
        self.assertFalse(failing_runner.running)

    def test_failed_install_rolls_back_and_never_claims_background(self):
        self.runner.fail["bootstrap"] = "Bootstrap failed: permission denied"
        with self.assertRaises(ServiceControlError) as caught:
            self.controller.install()
        self.assertIn("foreground `agentos start`", caught.exception.next_action)
        self.assertFalse(self.controller.plist_path.exists())
        self.assertTrue(self.controller.data_dir.exists())
        self.assertFalse(caught.exception.as_dict()["background_available"])

    def test_status_does_not_claim_loaded_service_is_running(self):
        self.controller.plist_path.parent.mkdir(parents=True)
        self.controller.plist_path.write_bytes(render_plist(self.cli, self.controller.data_dir))
        self.runner.loaded = True
        self.runner.running = False
        status = self.controller.status()
        self.assertEqual(status["status"], "loaded_not_running")
        self.assertFalse(status["background_available"])
        self.assertIn("next_action", status)
        started = self.controller.start()
        self.assertEqual(started["status"], "running")
        self.assertEqual(self.runner.commands[-2][1], "kickstart")

    def test_status_reports_unreadable_launchd_state_as_unknown(self):
        self.controller.plist_path.parent.mkdir(parents=True)
        self.controller.plist_path.write_bytes(render_plist(self.cli, self.controller.data_dir))
        self.runner.fail["print"] = "Not authorized"
        status = self.controller.status()
        self.assertFalse(status["ok"])
        self.assertEqual(status["status"], "unknown")
        self.assertFalse(status["background_available"])

    def test_service_action_returns_bounded_failure_for_missing_install(self):
        result = service_action("start", home=self.home, cli_path=self.cli, runner=self.runner, uid=501)
        self.assertFalse(result["ok"])
        self.assertFalse(result["background_available"])
        self.assertTrue(result["data_preserved"])
        self.assertIn("foreground", result["next_action"])

    def test_service_action_bounds_filesystem_failures(self):
        with patch.object(ServiceController, "install", side_effect=OSError("disk full")):
            result = service_action("install", home=self.home, cli_path=self.cli, runner=self.runner, uid=501)
        self.assertFalse(result["ok"])
        self.assertFalse(result["background_available"])
        self.assertTrue(result["data_preserved"])
        self.assertIn("permissions", result["next_action"])

    def test_status_and_uninstall_work_after_cli_has_been_removed(self):
        self.controller.install()
        self.cli.unlink()
        controller = ServiceController(home=self.home, cli_path=self.cli, runner=self.runner, uid=501)
        self.assertEqual(controller.status()["status"], "running")
        self.assertTrue(controller.uninstall()["data_preserved"])

    def test_static_template_has_no_fixed_homebrew_prefix(self):
        template = (Path(__file__).resolve().parents[1] / "deploy/com.personal-agentos.plist").read_text()
        self.assertNotIn("/opt/homebrew", template)
        self.assertNotIn("/usr/local", template)
        self.assertIn("__AGENTOS_CLI__", template)
        self.assertIn("127.0.0.1", template)

    def test_install_check_declares_foreground_only_evidence(self):
        source = Path(install_check.__file__).read_text()
        self.assertIn('"background_service": "owner_validation_pending"', source)
        self.assertIn('"service_mutated": False', source)
        self.assertNotIn("launchctl", source)


if __name__ == "__main__":
    unittest.main()

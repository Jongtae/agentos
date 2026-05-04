from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
WELCOME_SHELL = ROOT_DIR / "image-assets" / "live" / "bin" / "agentos-welcome-shell"
RECOVERY_SHELL = ROOT_DIR / "image-assets" / "live" / "bin" / "agentos-recovery-shell"
HANDOFF_BIN = ROOT_DIR / "image-assets" / "live" / "bin" / "agentos-handoff"


class AgentOSWelcomeShellTests(unittest.TestCase):
    def _continue_env(self, td: str) -> dict[str, str]:
        root = Path(td)
        firstrun = root / "firstrun-shim.sh"
        shell = root / "shell-shim.sh"
        kernelctl = root / "kernelctl-shim.sh"
        workspace = root / "workspace"
        firstrun.write_text("#!/usr/bin/env bash\nprintf 'firstrun shim\\n'\n", encoding="utf-8")
        shell.write_text("#!/usr/bin/env bash\nprintf 'shell shim\\n'\n", encoding="utf-8")
        kernelctl.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "cmd=\"$1\"\n"
            "shift\n"
            "workspace=\"\"\n"
            "while [ \"$#\" -gt 0 ]; do\n"
            "  case \"$1\" in\n"
            "    --workspace) shift; workspace=\"$1\" ;;\n"
            "  esac\n"
            "  shift || true\n"
            "done\n"
            "if [ \"$cmd\" = \"first-run-summary\" ]; then\n"
            "  mkdir -p \"$workspace/artifacts/repo-free-first-run\"\n"
            "  printf '{\"summary\":{\"capability_proof_ready\":true},\"document_access\":{\"native_handled\":true},\"web_access\":{\"native_handled\":true}}\\n' > \"$workspace/artifacts/repo-free-first-run/latest-first-run-summary.json\"\n"
            "elif [ \"$cmd\" = \"vm-e2e-proof\" ]; then\n"
            "  mkdir -p \"$workspace/artifacts/control-plane-capabilities\"\n"
            "  printf '{\"summary\":{\"vm_e2e_runtime_ok\":true,\"vm_e2e_capability_ok\":true,\"vm_e2e_intake_ok\":true,\"vm_e2e_service_permission_ok\":true,\"vm_e2e_escalation_integrity_ok\":true}}\\n' > \"$workspace/artifacts/control-plane-capabilities/latest-vm-e2e-proof.json\"\n"
            "fi\n",
            encoding="utf-8",
        )
        firstrun.chmod(firstrun.stat().st_mode | stat.S_IXUSR)
        shell.chmod(shell.stat().st_mode | stat.S_IXUSR)
        kernelctl.chmod(kernelctl.stat().st_mode | stat.S_IXUSR)
        env = dict(os.environ)
        env["AGENTOS_FIRSTRUN_BIN"] = str(firstrun)
        env["AGENTOS_SHELL_BIN"] = str(shell)
        env["AGENTOS_KERNELCTL_BIN"] = str(kernelctl)
        env["AGENTOS_WELCOME_WORKSPACE"] = str(workspace)
        return env

    def test_continue_action_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env = self._continue_env(td)
            proc = subprocess.run(
                ["bash", str(WELCOME_SHELL), "continue"],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Launching managed Codex CLI session through AgentOS Setup", proc.stdout)

    def test_continue_records_setup_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            handoff = Path(td) / "handoff.env"
            status_dir = Path(td) / "live-bootstrap"
            env = self._continue_env(td)
            env["AGENTOS_HANDOFF_BIN"] = str(HANDOFF_BIN)
            env["AGENTOS_HANDOFF_FILE"] = str(handoff)
            env["AGENTOS_LIVE_BOOTSTRAP_STATE_DIR"] = str(status_dir)
            proc = subprocess.run(
                ["bash", str(WELCOME_SHELL), "continue"],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertTrue(handoff.exists())
            content = handoff.read_text(encoding="utf-8")
            status = json.loads((status_dir / "welcome-status.json").read_text(encoding="utf-8"))
        self.assertIn("route=continue_to_agentos", content)
        self.assertIn("next_step=agentos_setup", content)
        self.assertIn("summary=Continue to AgentOS -> AgentOS Setup -> Codex CLI Managed Session -> ai>", content)
        self.assertIn("runtime_target=codex_cli_managed_session", content)
        self.assertIn("supervision_target=codex_launch_supervision", content)
        self.assertIn("origin=agentos_welcome_shell", content)
        self.assertEqual(status["state"], "managed_shell_invoked")
        self.assertEqual(status["selected_action"], "continue")

    def test_continue_exports_boot_generated_proof_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env = self._continue_env(td)
            proc = subprocess.run(
                ["bash", str(WELCOME_SHELL), "continue"],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            workspace = Path(env["AGENTOS_WELCOME_WORKSPACE"])
            first_run_exists = (workspace / "artifacts/repo-free-first-run/latest-first-run-summary.json").exists()
            vm_proof_exists = (workspace / "artifacts/control-plane-capabilities/latest-vm-e2e-proof.json").exists()
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(first_run_exists)
        self.assertTrue(vm_proof_exists)

    def test_install_action_exits_with_install_code(self) -> None:
        proc = subprocess.run(
            ["bash", str(WELCOME_SHELL), "install"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 10)
        self.assertIn("Install AgentOS selected", proc.stdout)

    def test_install_records_persistence_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            handoff = Path(td) / "handoff.env"
            env = dict(os.environ)
            env["AGENTOS_HANDOFF_BIN"] = str(HANDOFF_BIN)
            env["AGENTOS_HANDOFF_FILE"] = str(handoff)
            proc = subprocess.run(
                ["bash", str(WELCOME_SHELL), "install"],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(proc.returncode, 10)
            content = handoff.read_text(encoding="utf-8")
        self.assertIn("route=install_agentos", content)
        self.assertIn("next_step=persistent_install", content)

    def test_recovery_action_execs_recovery_shell(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            shim = Path(td) / "recovery-shim.sh"
            shim.write_text("#!/usr/bin/env bash\nprintf 'shim recovery\\n'\n", encoding="utf-8")
            shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
            env = dict(os.environ)
            env["AGENTOS_RECOVERY_SHELL_BIN"] = str(shim)
            proc = subprocess.run(
                ["bash", str(WELCOME_SHELL), "recovery"],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Recovery selected", proc.stdout)
        self.assertIn("shim recovery", proc.stdout)

    def test_recovery_records_handoff_before_exec(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            handoff = Path(td) / "handoff.env"
            shim = Path(td) / "recovery-shim.sh"
            shim.write_text("#!/usr/bin/env bash\nprintf 'shim recovery\\n'\n", encoding="utf-8")
            shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
            env = dict(os.environ)
            env["AGENTOS_HANDOFF_BIN"] = str(HANDOFF_BIN)
            env["AGENTOS_HANDOFF_FILE"] = str(handoff)
            env["AGENTOS_RECOVERY_SHELL_BIN"] = str(shim)
            proc = subprocess.run(
                ["bash", str(WELCOME_SHELL), "recovery"],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(proc.returncode, 0)
            content = handoff.read_text(encoding="utf-8")
        self.assertIn("route=recovery", content)
        self.assertIn("next_step=agentos_recovery", content)

    def test_continue_required_network_can_skip_to_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env = self._continue_env(td)
            env["AGENTOS_WELCOME_NETWORK_POLICY"] = "required"
            env["AGENTOS_WELCOME_NETWORK_STATUS"] = "offline"
            env["AGENTOS_WELCOME_NETWORK_ACTION"] = "skip"
            proc = subprocess.run(
                ["bash", str(WELCOME_SHELL), "continue"],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("AgentOS network panel", proc.stdout)
        self.assertIn("Skipping network and continuing with the local AgentOS path", proc.stdout)
        self.assertIn("Launching managed Codex CLI session through AgentOS Setup", proc.stdout)

    def test_continue_required_network_connect_failure_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env = self._continue_env(td)
            env["AGENTOS_WELCOME_NETWORK_POLICY"] = "required"
            env["AGENTOS_WELCOME_NETWORK_STATUS"] = "offline"
            env["AGENTOS_WELCOME_NETWORK_ACTION"] = "connect"
            proc = subprocess.run(
                ["bash", str(WELCOME_SHELL), "continue"],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
        self.assertEqual(proc.returncode, 31)
        self.assertIn("Retrying network check", proc.stdout)
        self.assertIn("Network is still offline", proc.stdout)

    def test_continue_auto_network_offline_proceeds_local(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env = self._continue_env(td)
            env["AGENTOS_WELCOME_NETWORK_POLICY"] = "auto"
            env["AGENTOS_WELCOME_NETWORK_STATUS"] = "offline"
            proc = subprocess.run(
                ["bash", str(WELCOME_SHELL), "continue"],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("continuing with local AgentOS path", proc.stdout)


class AgentOSRecoveryShellTests(unittest.TestCase):
    def test_return_action_exits_zero(self) -> None:
        proc = subprocess.run(
            ["bash", str(RECOVERY_SHELL), "return"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Returning to AgentOS", proc.stdout)

    def test_return_records_setup_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            handoff = Path(td) / "handoff.env"
            env = dict(os.environ)
            env["AGENTOS_HANDOFF_BIN"] = str(HANDOFF_BIN)
            env["AGENTOS_HANDOFF_FILE"] = str(handoff)
            proc = subprocess.run(
                ["bash", str(RECOVERY_SHELL), "return"],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(proc.returncode, 0)
            content = handoff.read_text(encoding="utf-8")
        self.assertIn("route=return_to_agentos", content)
        self.assertIn("next_step=agentos_setup", content)
        self.assertIn("origin=agentos_recovery_shell", content)

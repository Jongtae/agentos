from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parents[1]
SHELL = ROOT_DIR / "scripts" / "agentos-shell"


class AgentosShellTests(unittest.TestCase):
    def _workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        (workspace / "documents").mkdir(parents=True, exist_ok=True)
        (workspace / "data").mkdir(parents=True, exist_ok=True)
        (workspace / "documents" / "agentos-first-run.md").write_text("# First run\n", encoding="utf-8")
        (workspace / "spec.yaml").write_text(
            yaml.dump(
                {
                    "name": "shell-entry-test",
                    "tools": {"bash": True, "file": True, "web": True},
                    "kernel_engine": {
                        "provider": "ollama",
                        "mode": "single",
                        "ollama": {
                            "command": "missing-ollama-binary",
                            "timeout_sec": 10,
                            "model": "smollm2:135m-instruct-q5_K_M",
                        },
                    },
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return workspace

    def _runtime_root(self, root: Path) -> Path:
        runtime_root = root / "runtime-root"
        src = runtime_root / "src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "main.py").write_text(
            "import sys\n"
            "import os\n"
            "print('FAKE_RUNTIME_ENTRY')\n"
            "print('INGRESS=' + os.environ.get('AGENTOS_CONVERSATIONAL_INGRESS_MODE', ''))\n"
            "print('ARGV=' + ' '.join(sys.argv[1:]))\n",
            encoding="utf-8",
        )
        return runtime_root

    def test_managed_tty_entry_prints_guided_operator_before_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = self._workspace(root)
            runtime_root = self._runtime_root(root)
            env = os.environ.copy()
            env["AGENTOS_RUNTIME_ROOT"] = str(runtime_root)
            env["AGENTOS_SESSION_MANAGED"] = "1"
            env["AGENTOS_SESSION_ENTRY"] = "local_tty1"
            result = subprocess.run(
                [str(SHELL), "--workspace", str(workspace), "--kernel-mode"],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
                check=True,
                env=env,
            )
            self.assertIn("AgentOS Guided Operator", result.stdout)
            self.assertIn("Top tasks:", result.stdout)
            self.assertIn("FAKE_RUNTIME_ENTRY", result.stdout)

    def test_managed_runtime_bypass_skips_guided_operator(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = self._workspace(root)
            runtime_root = self._runtime_root(root)
            env = os.environ.copy()
            env["AGENTOS_RUNTIME_ROOT"] = str(runtime_root)
            env["AGENTOS_SESSION_MANAGED"] = "1"
            env["AGENTOS_SESSION_ENTRY"] = "local_tty1"
            result = subprocess.run(
                [str(SHELL), "--workspace", str(workspace), "--kernel-mode", "--managed-runtime"],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
                check=True,
                env=env,
            )
            self.assertNotIn("AgentOS Guided Operator", result.stdout)
            self.assertIn("FAKE_RUNTIME_ENTRY", result.stdout)

    def test_agentos_default_workspace_env_takes_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = self._workspace(root)
            legacy_workspace = self._workspace(root / "legacy")
            runtime_root = self._runtime_root(root)
            env = os.environ.copy()
            env["AGENTOS_RUNTIME_ROOT"] = str(runtime_root)
            env["AGENTOS_DEFAULT_WORKSPACE"] = str(workspace)
            env["DEFAULT_WORKSPACE"] = str(legacy_workspace)
            result = subprocess.run(
                [str(SHELL), "--managed-runtime"],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
                check=True,
                env=env,
            )
            self.assertIn(f"ARGV=--workspace {workspace}", result.stdout)

    def test_telegram_managed_runtime_flags_become_ingress_mode(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = self._workspace(root)
            runtime_root = self._runtime_root(root)
            env = os.environ.copy()
            env["AGENTOS_RUNTIME_ROOT"] = str(runtime_root)
            result = subprocess.run(
                [str(SHELL), "--workspace", str(workspace), "--managed-runtime", "--telegram-ask"],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
                check=True,
                env=env,
            )
            self.assertIn("FAKE_RUNTIME_ENTRY", result.stdout)
            self.assertIn("INGRESS=telegram_ask", result.stdout)
            self.assertIn(f"ARGV=--workspace {workspace}", result.stdout)

            result = subprocess.run(
                [str(SHELL), "--workspace", str(workspace), "--managed-runtime", "--telegram-search-reply"],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
                check=True,
                env=env,
            )
            self.assertIn("INGRESS=telegram_search_reply", result.stdout)

    def test_telegram_ingress_status_short_circuits_to_kernelctl(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = self._workspace(root)
            runtime_root = self._runtime_root(root)
            kernelctl = root / "fake-kernelctl.sh"
            kernelctl.write_text(
                "#!/bin/sh\n"
                "set -eu\n"
                "printf 'FAKE_TELEGRAM_STATUS %s\\n' \"$*\"\n",
                encoding="utf-8",
            )
            kernelctl.chmod(0o755)
            env = os.environ.copy()
            env["AGENTOS_RUNTIME_ROOT"] = str(runtime_root)
            env["AGENTOS_KERNELCTL_BIN"] = str(kernelctl)
            result = subprocess.run(
                [str(SHELL), "--workspace", str(workspace), "--telegram-ingress-status"],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
                check=True,
                env=env,
            )
            self.assertIn("FAKE_TELEGRAM_STATUS telegram-status --workspace", result.stdout)
            self.assertIn(str(workspace), result.stdout)


if __name__ == "__main__":
    unittest.main()

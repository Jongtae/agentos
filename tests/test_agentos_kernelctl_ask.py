from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
KERNELCTL = ROOT_DIR / "scripts" / "agentos-kernelctl"


class AgentosKernelctlAskTests(unittest.TestCase):
    def test_ask_command_passes_workspace_message_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "kernel_ask.py"
            fake.write_text(
                "#!/bin/sh\n"
                "set -eu\n"
                "printf 'ASK_ARGS=%s\\n' \"$*\"\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            workspace = root / "workspace"
            workspace.mkdir()
            env = os.environ.copy()
            env["AGENTOS_KERNEL_ASK_CMD"] = str(fake)
            result = subprocess.run(
                [
                    str(KERNELCTL),
                    "ask",
                    "--workspace",
                    str(workspace),
                    "--message",
                    "hello operator",
                    "--json",
                ],
                cwd=ROOT_DIR,
                env=env,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn(f"--workspace {workspace}", result.stdout)
            self.assertIn("--message hello operator", result.stdout)
            self.assertIn("--json", result.stdout)


if __name__ == "__main__":
    unittest.main()

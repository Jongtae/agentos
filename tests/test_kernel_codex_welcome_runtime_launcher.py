from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_codex_welcome_runtime_launcher.py"


class KernelCodexWelcomeRuntimeLauncherTests(unittest.TestCase):
    def test_cli_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "welcome-runtime-launcher.json"
            subprocess.run(
                ["python3", str(SCRIPT), "--workspace", "./workspaces/default", "--output", str(out)],
                cwd=ROOT_DIR,
                check=True,
            )
            result = subprocess.run(
                ["python3", str(SCRIPT), "--validate", str(out), "--json"],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()

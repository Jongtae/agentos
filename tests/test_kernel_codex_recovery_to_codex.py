from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_codex_recovery_to_codex.py"


class KernelCodexRecoveryToCodexTests(unittest.TestCase):
    def test_cli_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "fake-codex.sh"
            fake.write_text(
                "#!/usr/bin/env bash\nif [ \"${1:-}\" = \"--output-last-message\" ]; then\n  shift\n  printf 'HEALTH_OK'\n  exit 0\nfi\nprintf 'HEALTH_OK'\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            spec = {
                "name": "codex-recovery-to-codex",
                "tools": {"bash": True},
                "kernel_engine": {
                    "provider": "codex",
                    "mode": "single",
                    "codex": {"command": str(fake), "timeout_sec": 5, "model": "gpt-test"},
                },
            }
            (root / "spec.yaml").write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")
            out = root / "codex-recovery-to-codex.json"
            env = dict(os.environ)
            env["OPENAI_API_KEY"] = "dummy"
            env["AGENTOS_SESSION_MANAGED"] = "1"
            env["AGENTOS_SESSION_ENTRY"] = "live_appliance"
            result = subprocess.run(
                ["python3", str(SCRIPT), "--workspace", str(root), "--output", str(out)],
                cwd=ROOT_DIR,
                env=env,
                check=True,
            )
            self.assertEqual(result.returncode, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["runtime_rejoin_target"], "codex_cli_managed_session")
            self.assertIn("Codex CLI Managed Session", payload["detailed_rejoin_path"])


if __name__ == "__main__":
    unittest.main()

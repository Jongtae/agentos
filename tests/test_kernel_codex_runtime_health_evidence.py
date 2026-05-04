from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
PROOF_SCRIPT = ROOT_DIR / "scripts" / "kernel_codex_runtime_health_evidence.py"
SUPERVISOR_SCRIPT = ROOT_DIR / "scripts" / "agentos_codex_supervisor.py"


class KernelCodexRuntimeHealthEvidenceTests(unittest.TestCase):
    def test_cli_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "fake-codex.sh"
            fake.write_text(
                "#!/usr/bin/env bash\nif [ \"${1:-}\" = \"exec\" ]; then\n  printf 'HEALTH_OK'\n  exit 0\nfi\nif [ \"${1:-}\" = \"--output-last-message\" ]; then\n  shift\n  printf 'HEALTH_OK'\n  exit 0\nfi\nprintf 'HEALTH_OK'\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            spec = {
                "name": "codex-runtime-health-evidence",
                "tools": {"bash": True},
                "kernel_engine": {
                    "provider": "codex",
                    "mode": "single",
                    "codex": {
                        "command": str(fake),
                        "timeout_sec": 5,
                        "model": "gpt-test",
                        "supervision": {"enabled": True, "restart_policy": "on_failure", "max_attempts": 3, "cooldown_sec": 1},
                    },
                },
            }
            (root / "spec.yaml").write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")
            env = dict(os.environ)
            env["OPENAI_API_KEY"] = "dummy"
            env["AGENTOS_SESSION_MANAGED"] = "1"
            env["AGENTOS_SESSION_ENTRY"] = "live_appliance"
            env["AGENTOS_CODEX_SUPERVISION_STATE_FILE"] = str(root / "runtime" / "codex-launch-supervision.json")
            subprocess.run(["python3", str(SUPERVISOR_SCRIPT), "--workspace", str(root), "--json"], cwd=ROOT_DIR, env=env, check=True)
            out = root / "codex-runtime-health-evidence.json"
            subprocess.run(["python3", str(PROOF_SCRIPT), "--workspace", str(root), "--output", str(out)], cwd=ROOT_DIR, env=env, check=True)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "agentos-codex-runtime-health-evidence.v1")
            self.assertTrue(payload["summary"]["ok"])


if __name__ == "__main__":
    unittest.main()

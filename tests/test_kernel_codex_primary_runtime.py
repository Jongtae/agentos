from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from kernel.codex_primary_runtime import build_codex_primary_runtime_summary
from scripts.kernel_codex_primary_runtime import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_codex_primary_runtime.py"


class KernelCodexPrimaryRuntimeTests(unittest.TestCase):
    def test_summary_reports_ready_when_codex_provider_and_command_exist(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "fake-codex.sh"
            fake.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            fake.chmod(0o755)
            payload = build_codex_primary_runtime_summary(
                provider="codex",
                command=str(fake),
                model="gpt-test",
                engine_status="PASS",
                session_origin={"category": "live_appliance_boot"},
                setup_state={"next_managed_entry": "ai_shell"},
                install_later={"install_action_label": "Install AgentOS", "target_origin": "installed_appliance_boot"},
                recovery_path={"label": "AgentOS Recovery"},
                installed_boot={"available": False},
            )
            self.assertTrue(payload["provider_matches_primary"])
            self.assertTrue(payload["command_available"])
            self.assertEqual(payload["proof_status"], "ready")
            self.assertEqual(validate_payload({"schema_version": "agentos-codex-primary-runtime.v1", **payload}), [])

    def test_cli_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "fake-codex.sh"
            fake.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            fake.chmod(0o755)
            spec = {
                "name": "codex-primary-runtime",
                "tools": {"bash": True},
                "kernel_engine": {
                    "provider": "codex",
                    "mode": "single",
                    "codex": {"command": str(fake), "timeout_sec": 5, "model": "gpt-test"},
                },
            }
            (root / "spec.yaml").write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")
            out = root / "codex-primary-runtime.json"
            env = dict(os.environ)
            env["AGENTOS_SESSION_MANAGED"] = "1"
            env["AGENTOS_SESSION_ENTRY"] = "live_appliance"
            subprocess.run(["python3", str(SCRIPT), "--workspace", str(root), "--output", str(out)], cwd=ROOT_DIR, env=env, check=True)
            result = subprocess.run(
                ["python3", str(SCRIPT), "--validate", str(out), "--json"],
                cwd=ROOT_DIR,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()

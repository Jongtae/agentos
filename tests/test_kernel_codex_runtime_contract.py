from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from kernel.codex_runtime_contract import build_codex_runtime_contract
from scripts.kernel_codex_runtime_contract import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_codex_runtime_contract.py"


class KernelCodexRuntimeContractTests(unittest.TestCase):
    def test_contract_freezes_launch_env_workspace_state_and_continuity(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "fake-codex.sh"
            fake.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            fake.chmod(0o755)
            payload = build_codex_runtime_contract(
                workspace_dir=str(root),
                workspace_root="./",
                provider="codex",
                command=str(fake),
                timeout_sec=30,
                model="gpt-test",
                engine_status="PASS",
                session_origin={"category": "live_appliance_boot"},
                setup_state={"next_managed_entry": "ai_shell"},
                install_later={"install_action_label": "Install AgentOS", "target_origin": "installed_appliance_boot"},
                recovery_path={"label": "AgentOS Recovery"},
                installed_boot={"available": True},
            )
            self.assertEqual(payload["provider_contract"]["expected_provider"], "codex")
            self.assertTrue(payload["launch_contract"]["command_available"])
            self.assertEqual(payload["continuity_contract"]["rejoin_target"], "codex_cli_managed_session")
            self.assertEqual(validate_payload({"schema_version": payload["schema_version"], **payload}), [])

    def test_cli_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "fake-codex.sh"
            fake.write_text("#!/usr/bin/env bash\necho HEALTH_OK > /dev/null\nexit 0\n", encoding="utf-8")
            fake.chmod(0o755)
            spec = {
                "name": "codex-runtime-contract",
                "tools": {"bash": True},
                "runtime": {"workspace_root": "./sandbox"},
                "kernel_engine": {
                    "provider": "codex",
                    "mode": "single",
                    "codex": {"command": str(fake), "timeout_sec": 5, "model": "gpt-test"},
                },
            }
            (root / "sandbox").mkdir()
            (root / "spec.yaml").write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")
            out = root / "codex-runtime-contract.json"
            env = dict(os.environ)
            env["OPENAI_API_KEY"] = "dummy"
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

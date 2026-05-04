from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.codex_persistent_state import build_codex_persistent_state_summary
from kernel.codex_runtime_contract import build_codex_runtime_contract
from scripts.kernel_codex_persistent_state import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
STATE_INIT = ROOT_DIR / "image-assets" / "live" / "bin" / "agentos-state-root-init"
INSTALLER = ROOT_DIR / "image-assets" / "live" / "bin" / "agentos-install-appliance"
INSTALLED_BOOT = ROOT_DIR / "image-assets" / "live" / "bin" / "agentos-installed-boot"
SCRIPT = ROOT_DIR / "scripts" / "kernel_codex_persistent_state.py"


class KernelCodexPersistentStateTests(unittest.TestCase):
    def test_summary_reports_runtime_continuity_ready(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td) / "state-root"
            install_file = Path(td) / "install.env"
            boot_file = Path(td) / "boot.env"
            env = dict(os.environ)
            env["AGENTOS_STATE_ROOT"] = str(state_root)
            env["AGENTOS_INSTALL_REQUEST_FILE"] = str(install_file)
            env["AGENTOS_INSTALLED_BOOT_FILE"] = str(boot_file)
            subprocess.run(["bash", str(STATE_INIT)], env=env, check=True, capture_output=True, text=True)
            subprocess.run(["bash", str(INSTALLER)], env=env, check=False, capture_output=True, text=True)
            subprocess.run(["bash", str(INSTALLED_BOOT)], env=env, check=True, capture_output=True, text=True)
            state_root_usage = {
                "state_root": str(state_root),
                "manifest_path": str(state_root / "state-layout.env"),
                "initialized": True,
                "present_paths": [
                    "workspaces",
                    "logs",
                    "evidence",
                    "models",
                    "update_metadata",
                    "rollback_markers",
                    "runtime",
                    "codex_runtime",
                    "codex_session",
                    "codex_logs",
                    "codex_evidence",
                ],
                "missing_paths": [],
                "paths": {
                    key: {"path": str(path), "exists": True}
                    for key, path in {
                        "codex_runtime": state_root / "runtime" / "codex",
                        "codex_session": state_root / "runtime" / "codex" / "session",
                        "codex_logs": state_root / "runtime" / "codex" / "logs",
                        "codex_evidence": state_root / "runtime" / "codex" / "evidence",
                    }.items()
                },
            }
            runtime_contract = build_codex_runtime_contract(
                workspace_dir=str(ROOT_DIR / "workspaces" / "default"),
                workspace_root="./",
                provider="codex",
                command="python3",
                timeout_sec=5,
                model="",
                engine_status="PASS",
                session_origin={"category": "installed_appliance_boot"},
                setup_state={"next_managed_entry": "ai_shell"},
                install_later={"available": True},
                recovery_path={"label": "AgentOS Recovery", "runtime_rejoin_target": "codex_cli_managed_session"},
                installed_boot={"available": True, "manifest_path": str(boot_file)},
            )
            summary = build_codex_persistent_state_summary(
                state_root_usage=state_root_usage,
                runtime_contract=runtime_contract,
                install_later={"available": True},
                installed_boot={"available": True, "manifest_path": str(boot_file)},
            )
        self.assertTrue(summary["continuity_ready"])
        self.assertEqual(summary["runtime_owner"], "codex_cli_managed_session")
        self.assertEqual(validate_payload(summary), [])

    def test_cli_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td) / "state-root"
            out = Path(td) / "persistent.json"
            env = dict(os.environ)
            env["AGENTOS_STATE_ROOT"] = str(state_root)
            env["AGENTOS_INSTALL_REQUEST_FILE"] = str(Path(td) / "install.env")
            env["AGENTOS_INSTALLED_BOOT_FILE"] = str(Path(td) / "boot.env")
            subprocess.run(["bash", str(STATE_INIT)], env=env, check=True, capture_output=True, text=True)
            subprocess.run(["bash", str(INSTALLER)], env=env, check=False, capture_output=True, text=True)
            subprocess.run(["bash", str(INSTALLED_BOOT)], env=env, check=True, capture_output=True, text=True)
            subprocess.run(
                ["python3", str(SCRIPT), "--workspace", "./workspaces/default", "--output", str(out)],
                cwd=ROOT_DIR,
                env=env,
                check=True,
            )
            result = subprocess.run(
                ["python3", str(SCRIPT), "--validate", str(out), "--json"],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()

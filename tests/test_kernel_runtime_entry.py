from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.runtime_entry import build_runtime_entry_contract
from scripts.kernel_runtime_entry import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_runtime_entry.py"


class KernelRuntimeEntryTests(unittest.TestCase):
    def test_local_managed_tty1_maps_to_next_managed_entry(self) -> None:
        payload = build_runtime_entry_contract(
            session_origin={"category": "local_managed_tty1"},
            setup_state={"status": "configured", "next_managed_entry": "ai_shell"},
        )
        self.assertEqual(payload["effective_target"], "ai_shell")
        self.assertEqual(payload["fallback_target"], "normal_tty_shell")
        self.assertTrue(payload["agentos_first"])
        self.assertEqual(payload["primary_runtime"], "codex_cli")
        self.assertEqual(payload["managed_runtime_target"], "codex_cli_managed_session")
        self.assertEqual(validate_payload(payload), [])

    def test_ssh_is_passthrough(self) -> None:
        payload = build_runtime_entry_contract(
            session_origin={"category": "ssh"},
            setup_state={"status": "configured", "next_managed_entry": "ai_shell"},
        )
        self.assertEqual(payload["behavior"], "passthrough")
        self.assertEqual(payload["effective_target"], "login_shell")
        self.assertFalse(payload["agentos_first"])

    def test_live_appliance_boot_maps_to_next_managed_entry(self) -> None:
        payload = build_runtime_entry_contract(
            session_origin={"category": "live_appliance_boot"},
            setup_state={"status": "pending", "next_managed_entry": "setup_session"},
        )
        self.assertEqual(payload["effective_target"], "setup_session")
        self.assertEqual(payload["fallback_target"], "agentos_recovery_shell")
        self.assertTrue(payload["agentos_first"])
        self.assertTrue(payload["appliance_boot"])
        self.assertEqual(payload["preferred_origin"], "live_appliance_boot")
        self.assertEqual(payload["platform_model"], "agentos_managed_appliance_os")
        self.assertEqual(payload["update_model"], "image_based_ab_updates")
        self.assertTrue(payload["transitional_origin_vocabulary"])
        self.assertTrue(payload["slot_aware_runtime"])
        self.assertIn("installed_slot_a", payload["target_platform_states"])
        self.assertIn("Codex CLI Managed Session", payload["launch_path_summary"])

    def test_installed_appliance_boot_maps_to_next_managed_entry(self) -> None:
        payload = build_runtime_entry_contract(
            session_origin={"category": "installed_appliance_boot"},
            setup_state={"status": "configured", "next_managed_entry": "ai_shell"},
        )
        self.assertEqual(payload["effective_target"], "ai_shell")
        self.assertEqual(payload["fallback_target"], "agentos_recovery_shell")
        self.assertTrue(payload["agentos_first"])
        self.assertTrue(payload["appliance_boot"])
        self.assertTrue(payload["installed_appliance_boot"])
        self.assertEqual(payload["preferred_installed_origin"], "installed_appliance_boot")
        self.assertEqual(payload["recovery_label"], "AgentOS Recovery")
        self.assertIn("Codex CLI Managed Session", payload["installed_launch_path_summary"])

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "runtime-entry.json"
            subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--session-origin",
                    "local_managed_tty1",
                    "--setup-status",
                    "configured",
                    "--next-managed-entry",
                    "ai_shell",
                    "--output",
                    str(out),
                ],
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

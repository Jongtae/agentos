from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


class KernelPolicyEnforcedPilotTests(unittest.TestCase):
    def _workspace(self) -> Path:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        ws = Path(td.name) / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "spec.yaml").write_text(
            yaml.dump(
                {
                    "name": "enforce-test",
                    "kernel_engine": {"provider": "none", "mode": "single"},
                    "runtime": {"workspace_root": "./"},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return ws

    def test_enable_requires_confirm(self):
        ws = self._workspace()
        proc = subprocess.run(
            ["python3", "scripts/kernel_policy_enforced_pilot.py", "--workspace", str(ws), "--enable", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 2)
        payload = json.loads(proc.stdout.strip())
        self.assertEqual(payload["reason"], "confirm_required")

    def test_enable_and_disable_flow(self):
        ws = self._workspace()
        bridge = subprocess.run(
            ["python3", "scripts/kernel_policy_bridge.py", "--workspace", str(ws), "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(bridge.returncode, 0)

        enable = subprocess.run(
            [
                "python3",
                "scripts/kernel_policy_enforced_pilot.py",
                "--workspace",
                str(ws),
                "--enable",
                "--confirm",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(enable.returncode, 0)
        enabled = json.loads(enable.stdout.strip())
        self.assertTrue(enabled["configured_enabled"])
        self.assertTrue(enabled["effective_enabled"])
        self.assertEqual(enabled["fallback_state"]["mode"], "kernel_enforced")
        self.assertEqual(enabled["policy_target"], "fs_workspace_boundary")
        self.assertIn("destructive_action_approval", enabled["supported_policy_targets"])
        self.assertEqual(enabled["next_policy_target"], "destructive_action_approval")
        self.assertIn("kernel_mechanism", enabled)
        self.assertTrue(enabled["kernel_mechanism"]["profile_exists"])

        disable = subprocess.run(
            ["python3", "scripts/kernel_policy_enforced_pilot.py", "--workspace", str(ws), "--disable", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(disable.returncode, 0)
        disabled = json.loads(disable.stdout.strip())
        self.assertFalse(disabled["configured_enabled"])

    def test_enable_with_network_allowlist_policy_target(self):
        ws = self._workspace()
        bridge = subprocess.run(
            ["python3", "scripts/kernel_policy_bridge.py", "--workspace", str(ws), "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(bridge.returncode, 0)

        enable = subprocess.run(
            [
                "python3",
                "scripts/kernel_policy_enforced_pilot.py",
                "--workspace",
                str(ws),
                "--enable",
                "--confirm",
                "--policy-target",
                "network_allowlist",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(enable.returncode, 0)
        payload = json.loads(enable.stdout.strip())
        self.assertEqual(payload["policy_target"], "network_allowlist")
        self.assertTrue(payload["configured_enabled"])

        status = subprocess.run(
            ["python3", "scripts/kernel_policy_enforced_pilot.py", "--workspace", str(ws), "--status", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(status.returncode, 0)
        status_payload = json.loads(status.stdout.strip())
        self.assertEqual(status_payload["policy_target"], "network_allowlist")

    def test_supports_destructive_action_approval_policy_target(self):
        ws = self._workspace()
        bridge = subprocess.run(
            ["python3", "scripts/kernel_policy_bridge.py", "--workspace", str(ws), "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(bridge.returncode, 0)
        proc = subprocess.run(
            [
                "python3",
                "scripts/kernel_policy_enforced_pilot.py",
                "--workspace",
                str(ws),
                "--enable",
                "--confirm",
                "--policy-target",
                "destructive_action_approval",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout.strip())
        self.assertEqual(payload["policy_target"], "destructive_action_approval")
        self.assertIn("destructive_action_approval", payload["supported_policy_targets"])

    def test_boot_disable_switch_disables_effective_state(self):
        ws = self._workspace()
        bridge = subprocess.run(
            ["python3", "scripts/kernel_policy_bridge.py", "--workspace", str(ws), "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(bridge.returncode, 0)
        enable = subprocess.run(
            [
                "python3",
                "scripts/kernel_policy_enforced_pilot.py",
                "--workspace",
                str(ws),
                "--enable",
                "--confirm",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(enable.returncode, 0)
        proc = subprocess.run(
            ["python3", "scripts/kernel_policy_enforced_pilot.py", "--workspace", str(ws), "--status", "--json"],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "AGENTOS_KERNEL_POLICY_BOOT_DISABLE": "1"},
        )
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout.strip())
        self.assertTrue(payload["configured_enabled"])
        self.assertFalse(payload["effective_enabled"])
        self.assertIn("AGENTOS_KERNEL_POLICY_BOOT_DISABLE", payload["disable_switches"])
        self.assertEqual(payload["disable_source"], "boot_disable")
        self.assertEqual(payload["fallback_state"]["mode"], "userspace_fallback")

    def test_session_disable_switch_reports_userspace_fallback(self):
        ws = self._workspace()
        bridge = subprocess.run(
            ["python3", "scripts/kernel_policy_bridge.py", "--workspace", str(ws), "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(bridge.returncode, 0)
        enable = subprocess.run(
            [
                "python3",
                "scripts/kernel_policy_enforced_pilot.py",
                "--workspace",
                str(ws),
                "--enable",
                "--confirm",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(enable.returncode, 0)
        proc = subprocess.run(
            ["python3", "scripts/kernel_policy_enforced_pilot.py", "--workspace", str(ws), "--status", "--json"],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "AGENTOS_KERNEL_POLICY_DISABLE": "1"},
        )
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout.strip())
        self.assertEqual(payload["disable_source"], "session_disable")
        self.assertEqual(payload["fallback_state"]["status_reason"], "session_disable_switch_active")
        self.assertEqual(payload["fallback_state"]["mode"], "userspace_fallback")
        self.assertGreaterEqual(len(payload["recovery"]["steps"]), 3)

    def test_require_ready_fails_without_bridge_profile(self):
        ws = self._workspace()
        proc = subprocess.run(
            [
                "python3",
                "scripts/kernel_policy_enforced_pilot.py",
                "--workspace",
                str(ws),
                "--enable",
                "--confirm",
                "--require-ready",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 3)
        payload = json.loads(proc.stdout.strip())
        self.assertEqual(payload["reason"], "kernel_profile_not_ready")


if __name__ == "__main__":
    unittest.main()

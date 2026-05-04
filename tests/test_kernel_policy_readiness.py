from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


class KernelPolicyReadinessTests(unittest.TestCase):
    def _workspace(self) -> Path:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        ws = Path(td.name) / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "spec.yaml").write_text(
            yaml.dump(
                {
                    "name": "readiness-test",
                    "kernel_engine": {"provider": "none", "mode": "single"},
                    "runtime": {"workspace_root": "./"},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return ws

    def test_warn_before_bridge_artifacts(self):
        ws = self._workspace()
        proc = subprocess.run(
            [
                "python3",
                "scripts/kernel_policy_readiness.py",
                "--workspace",
                str(ws),
                "--parser-cmd",
                "sh",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout.strip())
        self.assertIn(payload["overall_status"], {"warn", "degraded"})
        self.assertEqual(payload["operator_state"], "blocked")
        self.assertIn("next_policy_target_contract", payload["warning_checks"])
        self.assertEqual(payload["pilot_targets"]["next_policy_target"], "network_allowlist")
        self.assertFalse(payload["pilot_targets"]["next_policy_target_ready"])
        self.assertFalse(payload["mechanism"]["ready_for_enforced_pilot"])
        self.assertIn("profile_rendered", payload["failing_checks"])
        self.assertIn("profile_rendered", payload["blocking_checks"])
        self.assertGreaterEqual(payload["summary"]["blocking_count"], 1)
        self.assertGreaterEqual(len(payload["checks"]), 1)

    def test_pass_after_bridge_artifacts(self):
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
                "scripts/kernel_policy_readiness.py",
                "--workspace",
                str(ws),
                "--parser-cmd",
                "sh",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout.strip())
        self.assertEqual(payload["overall_status"], "pass")
        self.assertTrue(payload["bridge"]["profile_exists"])
        self.assertTrue(payload["bridge"]["state_exists"])
        self.assertTrue(payload["mechanism"]["ready_for_enforced_pilot"])
        self.assertEqual(payload["operator_state"], "ready")
        self.assertEqual(payload["bridge"]["lifecycle_summary"]["bridge_state"], "rendered")
        self.assertEqual(payload["bridge"]["lifecycle_summary"]["drift_state"], "in_sync")
        self.assertGreaterEqual(payload["bridge"]["network_allowlist_count"], 1)
        self.assertEqual(payload["pilot_targets"]["next_policy_target"], "network_allowlist")
        self.assertTrue(payload["pilot_targets"]["next_policy_target_ready"])
        self.assertEqual(payload["failing_checks"], [])
        self.assertEqual(payload["blocking_checks"], [])
        self.assertEqual(payload["warning_checks"], [])

    def test_corrupt_bridge_state_surfaces_specific_failure(self):
        ws = self._workspace()
        policy_dir = ws / "artifacts" / "kernel-policy"
        policy_dir.mkdir(parents=True, exist_ok=True)
        (policy_dir / "agentos-kernel-policy.profile.tmpl").write_text("tmpl", encoding="utf-8")
        (policy_dir / "agentos-kernel-policy.profile").write_text("profile", encoding="utf-8")
        (policy_dir / "bridge-state.json").write_text("{not-json", encoding="utf-8")
        proc = subprocess.run(
            [
                "python3",
                "scripts/kernel_policy_readiness.py",
                "--workspace",
                str(ws),
                "--parser-cmd",
                "sh",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout.strip())
        self.assertEqual(payload["overall_status"], "warn")
        self.assertIn("bridge_state", payload["failing_checks"])
        self.assertIn("bridge_state", payload["blocking_checks"])
        self.assertTrue(payload["bridge"]["state_corrupt"])

    def test_workspace_root_mismatch_requires_bridge_refresh(self):
        ws = self._workspace()
        bridge = subprocess.run(
            ["python3", "scripts/kernel_policy_bridge.py", "--workspace", str(ws), "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(bridge.returncode, 0)
        spec = yaml.safe_load((ws / "spec.yaml").read_text(encoding="utf-8"))
        spec["runtime"]["workspace_root"] = "./changed-root"
        (ws / "spec.yaml").write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")
        (ws / "changed-root").mkdir(parents=True, exist_ok=True)

        proc = subprocess.run(
            [
                "python3",
                "scripts/kernel_policy_readiness.py",
                "--workspace",
                str(ws),
                "--parser-cmd",
                "sh",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout.strip())
        self.assertIn("workspace_root", payload["failing_checks"])
        self.assertIn("workspace_root", payload["drift_checks"])
        self.assertEqual(payload["bridge"]["lifecycle_summary"]["drift_state"], "drifted")
        self.assertFalse(payload["bridge"]["workspace_root_matches_runtime"])

    def test_corrupt_enforced_config_surfaces_warning_not_blocker(self):
        ws = self._workspace()
        bridge = subprocess.run(
            ["python3", "scripts/kernel_policy_bridge.py", "--workspace", str(ws), "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(bridge.returncode, 0)
        policy_dir = ws / "artifacts" / "kernel-policy"
        (policy_dir / "enforced-pilot.json").write_text("{not-json", encoding="utf-8")
        proc = subprocess.run(
            [
                "python3",
                "scripts/kernel_policy_readiness.py",
                "--workspace",
                str(ws),
                "--parser-cmd",
                "sh",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout.strip())
        self.assertEqual(payload["overall_status"], "pass")
        self.assertEqual(payload["operator_state"], "attention_required")
        self.assertEqual(payload["blocking_checks"], [])
        self.assertIn("enforced_config", payload["warning_checks"])
        self.assertTrue(payload["enforced_pilot"]["config_corrupt"])


if __name__ == "__main__":
    unittest.main()

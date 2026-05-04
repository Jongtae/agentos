from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.kernel_policy_bridge import build_bridge


class KernelPolicyBridgeTests(unittest.TestCase):
    def _workspace(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        (root / "spec.yaml").write_text(
            yaml.dump(
                {
                    "name": "bridge-test",
                    "kernel_engine": {"provider": "none", "mode": "single"},
                    "runtime": {"workspace_root": "./sandbox"},
                    "network": {
                        "browser_allowlist": ["openai.com"],
                        "web_allowlist": ["github.com"],
                    },
                    "permissions": {"require_approval": True},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (root / "sandbox").mkdir(parents=True, exist_ok=True)
        self.addCleanup(td.cleanup)
        return td, root

    def test_bridge_renders_artifacts(self):
        _, ws = self._workspace()
        out_dir = ws / "artifacts" / "kernel-policy"
        report = build_bridge(str(ws), str(out_dir))
        self.assertTrue(report["ok"])
        self.assertFalse(report["workspace_root_changed"])
        self.assertFalse(report["reload_recommended"])
        self.assertTrue(report["destructive_action_approval_required"])
        profile = Path(report["profile_path"]).read_text(encoding="utf-8")
        self.assertIn(str((ws / "sandbox").resolve()), profile)
        self.assertIn("browser-allowlist-domain: openai.com", profile)
        self.assertIn("web-allowlist-domain: github.com", profile)
        self.assertIn("destructive-action-approval-required: true", profile)
        self.assertEqual(report["network_allowlist"], ["github.com", "openai.com"])
        self.assertEqual(report["lifecycle"]["last_action"], "render")
        self.assertEqual(report["lifecycle"]["bridge_state"], "rendered")
        self.assertEqual(report["lifecycle"]["drift_state"], "in_sync")
        self.assertEqual(report["lifecycle"]["reload_state"], "not_required")
        self.assertEqual(report["lifecycle_summary"]["bridge_state"], "rendered")
        self.assertTrue(Path(report["lifecycle_path"]).exists())

    def test_bridge_detects_workspace_root_change(self):
        _, ws = self._workspace()
        out_dir = ws / "artifacts" / "kernel-policy"
        _ = build_bridge(str(ws), str(out_dir))

        spec = yaml.safe_load((ws / "spec.yaml").read_text(encoding="utf-8"))
        spec["runtime"]["workspace_root"] = "./sandbox2"
        (ws / "spec.yaml").write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")
        (ws / "sandbox2").mkdir(parents=True, exist_ok=True)

        report = build_bridge(str(ws), str(out_dir))
        self.assertTrue(report["workspace_root_changed"])
        self.assertTrue(report["reload_recommended"])
        self.assertEqual(report["lifecycle"]["bridge_state"], "rendered_with_drift")
        self.assertEqual(report["lifecycle"]["drift_state"], "drifted")
        self.assertEqual(report["lifecycle"]["reload_state"], "recommended")

    def test_bridge_disable_records_lifecycle_state(self):
        _, ws = self._workspace()
        out_dir = ws / "artifacts" / "kernel-policy"
        report = build_bridge(str(ws), str(out_dir), disable_profile=True, parser_cmd="missing-parser")
        self.assertTrue(report["disable_attempted"])
        self.assertFalse(report["disable_ok"])
        self.assertEqual(report["lifecycle"]["last_action"], "disable")
        self.assertEqual(report["lifecycle"]["bridge_state"], "disable_failed")
        self.assertEqual(report["lifecycle"]["disable_state"], "failed")


if __name__ == "__main__":
    unittest.main()

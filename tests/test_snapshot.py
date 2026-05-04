from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from diagnostics import snapshot_report
from workspace.manager import WorkspaceManager


class SnapshotTests(unittest.TestCase):
    def _workspace_with_spec(self, spec: dict) -> str:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        (root / "spec.yaml").write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")
        self.addCleanup(td.cleanup)
        return td.name

    def test_snapshot_report_contains_required_keys(self):
        ws = self._workspace_with_spec(
            {
                "name": "snapshot-test",
                "tools": {"bash": True, "file": True, "web": True},
                "kernel_engine": {
                    "provider": "codex",
                    "mode": "single",
                    "codex": {"command": "missing-codex-binary", "timeout_sec": 5, "model": ""},
                },
            }
        )
        wm = WorkspaceManager(ws)
        payload = snapshot_report(wm)
        self.assertIn("timestamp_utc", payload)
        self.assertIn("app_version", payload)
        self.assertIn("doctor", payload)
        self.assertIn("status", payload)
        self.assertIn("browser_runtime", payload)
        self.assertIn("approval_counters", payload)
        self.assertIn("kernel_policy_ready", payload)
        self.assertIn("git", payload)
        self.assertIn("ok", payload)
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["git"]["is_repo"])

    def test_cli_snapshot_outputs_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            spec = {
                "name": "snapshot-test",
                "tools": {"bash": True, "file": True, "web": True},
                "kernel_engine": {
                    "provider": "codex",
                    "mode": "single",
                    "codex": {"command": "missing-codex-binary", "timeout_sec": 5, "model": ""},
                },
            }
            (root / "spec.yaml").write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")

            repo_root = Path(__file__).resolve().parents[1]
            result = subprocess.run(
                ["python3", "src/main.py", "--snapshot", "--workspace", str(root)],
                cwd=str(repo_root),
                env={**os.environ, **{"PYTHONPATH": "src"}},
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout.strip())
            self.assertIn("doctor", payload)
            self.assertIn("status", payload)
            self.assertIn("browser_runtime", payload)
            self.assertIn("approval_counters", payload)
            self.assertIn("kernel_policy_ready", payload)
            self.assertIn("git", payload)

    def test_cli_snapshot_writes_output_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            spec = {
                "name": "snapshot-test",
                "tools": {"bash": True, "file": True, "web": True},
                "kernel_engine": {
                    "provider": "codex",
                    "mode": "single",
                    "codex": {"command": "missing-codex-binary", "timeout_sec": 5, "model": ""},
                },
            }
            out = root / "artifacts" / "snapshot.json"
            (root / "spec.yaml").write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")

            repo_root = Path(__file__).resolve().parents[1]
            result = subprocess.run(
                [
                    "python3",
                    "src/main.py",
                    "--snapshot",
                    "--snapshot-file",
                    str(out),
                    "--workspace",
                    str(root),
                ],
                cwd=str(repo_root),
                env={**os.environ, **{"PYTHONPATH": "src"}},
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 1)
            self.assertTrue(out.exists())
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("doctor", payload)
            self.assertIn("status", payload)
            self.assertIn("browser_runtime", payload)
            self.assertIn("approval_counters", payload)
            self.assertIn("kernel_policy_ready", payload)
            self.assertIn("git", payload)

    def test_snapshot_report_includes_git_metadata_for_repo(self):
        repo_root = Path(__file__).resolve().parents[1]
        wm = WorkspaceManager(str(repo_root))
        payload = snapshot_report(wm)
        self.assertIn("git", payload)
        self.assertIn("browser_runtime", payload)
        self.assertIn("approval_counters", payload)
        self.assertIn("kernel_policy_ready", payload)
        self.assertTrue(payload["git"]["is_repo"])
        self.assertTrue(payload["git"]["commit"])

    def test_snapshot_file_requires_snapshot(self):
        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["python3", "src/main.py", "--snapshot-file", "/tmp/snapshot.json"],
            cwd=str(repo_root),
            env={**os.environ, **{"PYTHONPATH": "src"}},
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--snapshot-file is only valid with --snapshot.", result.stdout)


if __name__ == "__main__":
    unittest.main()

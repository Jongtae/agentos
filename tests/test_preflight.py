from __future__ import annotations

import json
import io
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import yaml

from preflight import preflight_report, run_preflight
from workspace.manager import WorkspaceManager


class PreflightTests(unittest.TestCase):
    def _workspace_with_spec(self, spec: dict) -> str:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        (root / "spec.yaml").write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")
        self.addCleanup(td.cleanup)
        return td.name

    def test_preflight_report_fails_when_codex_binary_missing(self):
        ws = self._workspace_with_spec(
            {
                "name": "preflight-test",
                "kernel_engine": {
                    "provider": "codex",
                    "mode": "single",
                    "codex": {"command": "missing-codex-binary", "timeout_sec": 5, "model": ""},
                },
            }
        )
        wm = WorkspaceManager(ws)
        report = preflight_report(wm)
        self.assertFalse(report["ready"])
        self.assertEqual(report["exit_code"], 1)

    def test_preflight_report_marks_setup_required(self):
        ws = self._workspace_with_spec(
            {
                "name": "preflight-test",
                "kernel_engine": {
                    "provider": "",
                    "mode": "single",
                    "codex": {"command": "missing-codex-binary", "timeout_sec": 5, "model": ""},
                },
            }
        )
        wm = WorkspaceManager(ws)
        report = preflight_report(wm)
        self.assertTrue(report["setup_required"])

    def test_preflight_json_output(self):
        ws = self._workspace_with_spec(
            {
                "name": "preflight-test",
                "kernel_engine": {
                    "provider": "codex",
                    "mode": "single",
                    "codex": {"command": "missing-codex-binary", "timeout_sec": 5, "model": ""},
                },
            }
        )
        wm = WorkspaceManager(ws)
        out = io.StringIO()
        with redirect_stdout(out):
            code = run_preflight(wm, as_json=True)

        payload = json.loads(out.getvalue().strip())
        self.assertEqual(code, 1)
        self.assertFalse(payload["ready"])
        self.assertIn("actions", payload)
        self.assertIn("doctor", payload)
        self.assertIn("status", payload)

    def test_preflight_actions_include_setup_command(self):
        ws = self._workspace_with_spec(
            {
                "name": "preflight-test",
                "kernel_engine": {
                    "provider": "",
                    "mode": "single",
                    "codex": {"command": "missing-codex-binary", "timeout_sec": 5, "model": ""},
                },
            }
        )
        wm = WorkspaceManager(ws)
        report = preflight_report(wm)
        self.assertIn("python src/main.py --setup-engine", report["actions"])

    def test_preflight_actions_include_api_key_hint(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "fake-codex.sh"
            fake.write_text("#!/bin/sh\necho HEALTH_OK\n", encoding="utf-8")
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            ws = self._workspace_with_spec(
                {
                    "name": "preflight-test",
                    "kernel_engine": {
                        "provider": "codex",
                        "mode": "single",
                        "codex": {"command": str(fake), "timeout_sec": 5, "model": ""},
                    },
                }
            )
            wm = WorkspaceManager(ws)
            old_key = os.environ.pop("OPENAI_API_KEY", None)
            try:
                report = preflight_report(wm)
            finally:
                if old_key is not None:
                    os.environ["OPENAI_API_KEY"] = old_key
            self.assertIn("export OPENAI_API_KEY=<your_api_key>", report["actions"])


if __name__ == "__main__":
    unittest.main()

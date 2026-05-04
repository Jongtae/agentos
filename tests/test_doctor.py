from __future__ import annotations

import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import yaml

from doctor import run_doctor
from workspace.manager import WorkspaceManager


class DoctorTests(unittest.TestCase):
    def _workspace_with_spec(self, spec: dict) -> str:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        (root / "spec.yaml").write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")
        self.addCleanup(td.cleanup)
        return td.name

    def test_doctor_fails_when_codex_binary_missing(self):
        ws = self._workspace_with_spec(
            {
                "name": "doctor-test",
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
            code = run_doctor(wm)

        self.assertEqual(code, 1)
        self.assertIn("[FAIL] Engine health check", out.getvalue())
        self.assertIn("binary_not_found", out.getvalue())

    def test_doctor_defaults_to_codex_when_provider_not_selected(self):
        ws = self._workspace_with_spec(
            {
                "name": "doctor-test",
                "kernel_engine": {
                    "provider": "",
                    "mode": "single",
                    "codex": {"command": "missing-codex-binary", "timeout_sec": 5, "model": ""},
                },
            }
        )

        wm = WorkspaceManager(ws)
        out = io.StringIO()
        with redirect_stdout(out):
            code = run_doctor(wm)

        self.assertEqual(code, 1)
        self.assertIn("Checking provider: ollama", out.getvalue())

    def test_doctor_json_output(self):
        ws = self._workspace_with_spec(
            {
                "name": "doctor-test",
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
            code = run_doctor(wm, as_json=True)

        payload = json.loads(out.getvalue().strip())
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["reason"], "binary_not_found")


if __name__ == "__main__":
    unittest.main()

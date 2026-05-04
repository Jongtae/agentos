from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from kernel.engine.codex_cli import CodexCliEngine


class CodexCliEngineTests(unittest.TestCase):
    def test_health_check_missing_binary(self):
        with tempfile.TemporaryDirectory() as td:
            engine = CodexCliEngine(workspace_dir=Path(td), command="definitely-missing-binary", timeout_sec=1)
            result = engine.health_check()
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, "binary_not_found")

    def test_run_intent_missing_api_key(self):
        with tempfile.TemporaryDirectory() as td:
            engine = CodexCliEngine(workspace_dir=Path(td), command="codex", timeout_sec=1)
            old = os.environ.pop("OPENAI_API_KEY", None)
            try:
                result = engine.run_intent("hello")
                self.assertFalse(result.ok)
                self.assertEqual(result.error_type, "missing_api_key")
            finally:
                if old is not None:
                    os.environ["OPENAI_API_KEY"] = old

    def test_run_intent_timeout(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "fake-codex.sh"
            fake.write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

            old = os.environ.get("OPENAI_API_KEY")
            os.environ["OPENAI_API_KEY"] = "dummy"
            try:
                engine = CodexCliEngine(workspace_dir=root, command=str(fake), timeout_sec=1)
                result = engine.run_intent("hello")
                self.assertFalse(result.ok)
                self.assertEqual(result.error_type, "timeout")
            finally:
                if old is None:
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = old


if __name__ == "__main__":
    unittest.main()

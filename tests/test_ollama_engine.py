from __future__ import annotations

import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib import error as urllib_error

from kernel.engine.ollama_cli import OllamaEngine


class OllamaEngineTests(unittest.TestCase):
    def test_health_check_missing_binary(self):
        with tempfile.TemporaryDirectory() as td:
            engine = OllamaEngine(
                workspace_dir=Path(td),
                command="definitely-missing-ollama",
                model="llama3.1:8b",
                timeout_sec=1,
            )
            result = engine.health_check()
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, "binary_not_found")

    def test_health_check_model_not_found(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "fake-ollama.sh"
            fake.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"list\" ]; then\n"
                "  echo \"NAME ID SIZE MODIFIED\"\n"
                "  echo \"other:latest abc 1GB now\"\n"
                "  exit 0\n"
                "fi\n"
                "echo \"unexpected\"\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

            engine = OllamaEngine(
                workspace_dir=root,
                command=str(fake),
                model="llama3.1:8b",
                timeout_sec=1,
            )
            result = engine.health_check()
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, "model_not_found")

    def test_run_intent_success_via_http(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "fake-ollama.sh"
            fake.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"list\" ]; then\n"
                "  echo \"NAME ID SIZE MODIFIED\"\n"
                "  echo \"llama3.1:8b abc 1GB now\"\n"
                "  exit 0\n"
                "fi\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

            engine = OllamaEngine(
                workspace_dir=root,
                command=str(fake),
                model="llama3.1:8b",
                timeout_sec=1,
            )
            response = mock.Mock()
            response.read.return_value = b'{"response":"HEALTH_OK","done":true}'
            response.__enter__ = mock.Mock(return_value=response)
            response.__exit__ = mock.Mock(return_value=False)

            with mock.patch("kernel.engine.ollama_cli.urllib_request.urlopen", return_value=response) as mocked:
                result = engine.run_intent("hello")
            self.assertTrue(result.ok)
            self.assertIn("HEALTH_OK", result.content)
            request = mocked.call_args.args[0]
            self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/generate")

    def test_run_intent_reports_service_unreachable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "fake-ollama.sh"
            fake.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"list\" ]; then\n"
                "  echo \"NAME ID SIZE MODIFIED\"\n"
                "  echo \"llama3.1:8b abc 1GB now\"\n"
                "  exit 0\n"
                "fi\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

            engine = OllamaEngine(
                workspace_dir=root,
                command=str(fake),
                model="llama3.1:8b",
                timeout_sec=1,
            )
            with mock.patch(
                "kernel.engine.ollama_cli.urllib_request.urlopen",
                side_effect=urllib_error.URLError("connection refused"),
            ):
                result = engine.run_intent("hello")
            self.assertFalse(result.ok)
            self.assertEqual(result.error_type, "service_unreachable")

    def test_run_intent_reports_api_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "fake-ollama.sh"
            fake.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"list\" ]; then\n"
                "  echo \"NAME ID SIZE MODIFIED\"\n"
                "  echo \"llama3.1:8b abc 1GB now\"\n"
                "  exit 0\n"
                "fi\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

            engine = OllamaEngine(
                workspace_dir=root,
                command=str(fake),
                model="llama3.1:8b",
                timeout_sec=1,
            )
            response = mock.Mock()
            response.read.return_value = b'{"error":"model warming up"}'
            response.__enter__ = mock.Mock(return_value=response)
            response.__exit__ = mock.Mock(return_value=False)

            with mock.patch("kernel.engine.ollama_cli.urllib_request.urlopen", return_value=response):
                result = engine.run_intent("hello")
            self.assertFalse(result.ok)
            self.assertEqual(result.error_type, "api_error")
            self.assertIn("model warming up", result.error_message)

    def test_health_check_uses_api_tags(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "fake-ollama.sh"
            fake.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"list\" ]; then\n"
                "  echo \"NAME ID SIZE MODIFIED\"\n"
                "  echo \"llama3.1:8b abc 1GB now\"\n"
                "  exit 0\n"
                "fi\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

            engine = OllamaEngine(
                workspace_dir=root,
                command=str(fake),
                model="llama3.1:8b",
                timeout_sec=1,
            )
            response = mock.Mock()
            response.read.return_value = b'{"models":[]}'
            response.__enter__ = mock.Mock(return_value=response)
            response.__exit__ = mock.Mock(return_value=False)

            with mock.patch("kernel.engine.ollama_cli.urllib_request.urlopen", return_value=response) as mocked:
                result = engine.health_check()
            self.assertTrue(result.ok)
            self.assertEqual(result.reason, "ok")
            self.assertEqual(result.detail, "Ollama server is reachable.")
            request = mocked.call_args.args[0]
            self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/tags")

    def test_health_check_reports_service_unreachable_from_api_tags(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "fake-ollama.sh"
            fake.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"list\" ]; then\n"
                "  echo \"NAME ID SIZE MODIFIED\"\n"
                "  echo \"llama3.1:8b abc 1GB now\"\n"
                "  exit 0\n"
                "fi\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

            engine = OllamaEngine(
                workspace_dir=root,
                command=str(fake),
                model="llama3.1:8b",
                timeout_sec=1,
            )
            with (
                mock.patch.object(engine, "_model_exists", return_value=True),
                mock.patch(
                    "kernel.engine.ollama_cli.urllib_request.urlopen",
                    side_effect=urllib_error.URLError("connection refused"),
                ),
            ):
                result = engine.health_check()
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, "service_unreachable")


if __name__ == "__main__":
    unittest.main()

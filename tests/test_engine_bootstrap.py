from __future__ import annotations

import os
import json
import stat
import tempfile
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from kernel.engine.bootstrap import _default_ollama_start_cmd, _wait_for_ollama_health, ensure_provider_ready
from kernel.engine.base import HealthCheckResult
from kernel.engine.ollama_cli import OllamaEngine
from workspace.manager import WorkspaceManager


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@contextmanager
def _fake_ollama_http_server(*, response_text: str = "HEALTH_OK"):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path != "/api/tags":
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps({"models": []}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802
            if self.path != "/api/generate":
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", "0"))
            _ = self.rfile.read(length)
            body = json.dumps({"response": response_text, "done": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


class EngineBootstrapTests(unittest.TestCase):
    def test_wait_for_ollama_health_retries_until_ready(self) -> None:
        class FakeEngine:
            def __init__(self) -> None:
                self.calls = 0

            def health_check(self) -> HealthCheckResult:
                self.calls += 1
                if self.calls < 3:
                    return HealthCheckResult(ok=False, reason="not_ready", detail="warming up")
                return HealthCheckResult(ok=True, reason="ok", detail="ready")

        engine = FakeEngine()
        result = _wait_for_ollama_health(engine, timeout_sec=3, poll_interval_sec=0)
        self.assertTrue(result.ok)
        self.assertGreaterEqual(engine.calls, 3)

    def test_ollama_bootstrap_installs_and_pulls_model(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            workspace = root / "ws"
            workspace.mkdir()
            wm = WorkspaceManager(str(workspace))

            install_cmd = (
                "cat > "
                + str(bin_dir / "ollama")
                + " <<'EOF'\n"
                + "#!/bin/sh\n"
                + "cmd=\"$1\"\n"
                + "shift || true\n"
                + "case \"$cmd\" in\n"
                + "  list)\n"
                + "    printf 'NAME            ID\\nsmollm2:135m-instruct-q5_K_M fake\\n'\n"
                + "    ;;\n"
                + "  pull)\n"
                + "    printf 'pulled %s\\n' \"$1\"\n"
                + "    ;;\n"
                + "  run)\n"
                + "    printf 'HEALTH_OK\\n'\n"
                + "    ;;\n"
                + "  *) exit 2 ;;\n"
                + "esac\n"
                + "EOF\n"
                + "chmod +x "
                + str(bin_dir / "ollama")
            )

            old_env = os.environ.copy()
            try:
                with _fake_ollama_http_server() as ollama_host:
                    os.environ["PATH"] = f"{bin_dir}:{old_env.get('PATH', '')}"
                    os.environ["AGENTOS_OLLAMA_INSTALL_CMD"] = install_cmd
                    os.environ["AGENTOS_OLLAMA_START_CMD"] = "true"
                    os.environ["AGENTOS_OLLAMA_PULL_CMD"] = "ollama pull smollm2:135m-instruct-q5_K_M"
                    os.environ["OLLAMA_HOST"] = ollama_host
                    payload = ensure_provider_ready(wm, "ollama")
            finally:
                os.environ.clear()
                os.environ.update(old_env)

            self.assertTrue(payload.ok)
            self.assertTrue(payload.bootstrap_attempted)
            self.assertEqual(payload.install_strategy, "official_install_script")

    def test_codex_bootstrap_requires_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wm = WorkspaceManager(td)
            wm.spec.setdefault("kernel_engine", {}).setdefault("codex", {})["command"] = str(root / "missing-codex")
            wm.save_spec()
            payload = ensure_provider_ready(wm, "codex")
            self.assertFalse(payload.ok)
            self.assertEqual(payload.reason, "binary_not_found")

    def test_codex_bootstrap_uses_npm_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            workspace = root / "ws"
            workspace.mkdir()
            wm = WorkspaceManager(str(workspace))
            wm.spec.setdefault("kernel_engine", {}).setdefault("codex", {})["command"] = "missing-codex"
            wm.save_spec()

            _write_exec(
                bin_dir / "npm",
                "#!/bin/sh\nprintf 'npm ok\\n'\n",
            )
            install_cmd = (
                "cat > "
                + str(bin_dir / "missing-codex")
                + " <<'EOF'\n"
                + "#!/bin/sh\n"
                + "out=''\n"
                + "while [ \"$#\" -gt 0 ]; do\n"
                + "  if [ \"$1\" = \"--output-last-message\" ]; then shift; out=\"$1\"; fi\n"
                + "  shift || true\n"
                + "done\n"
                + "printf 'HEALTH_OK' > \"$out\"\n"
                + "printf 'HEALTH_OK\\n'\n"
                + "EOF\n"
                + "chmod +x "
                + str(bin_dir / "missing-codex")
            )

            old_env = os.environ.copy()
            try:
                os.environ["PATH"] = f"{bin_dir}:{old_env.get('PATH', '')}"
                os.environ["OPENAI_API_KEY"] = "test-openai-key"
                os.environ["AGENTOS_CODEX_INSTALL_CMD"] = install_cmd
                payload = ensure_provider_ready(wm, "codex")
            finally:
                os.environ.clear()
                os.environ.update(old_env)

            self.assertTrue(payload.ok)
            self.assertTrue(payload.bootstrap_attempted)
            self.assertEqual(payload.install_strategy, "npm_global_install")

    def test_ollama_bundled_local_path_starts_without_install_or_pull(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            workspace = root / "ws"
            workspace.mkdir()
            models = root / "models"
            manifest = models / "manifests/registry.ollama.ai/library/smollm2/135m-instruct-q5_K_M"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                '{"config":{"digest":"sha256:abc"},"layers":[]}',
                encoding="utf-8",
            )
            blobs = models / "blobs"
            blobs.mkdir(parents=True, exist_ok=True)
            (blobs / "sha256-abc").write_text("blob", encoding="utf-8")

            install_marker = root / "install-marker"
            pull_marker = root / "pull-marker"
            _write_exec(
                bin_dir / "ollama",
                "#!/bin/sh\n"
                "cmd=\"$1\"\n"
                "shift || true\n"
                "case \"$cmd\" in\n"
                "  list)\n"
                "    printf 'NAME            ID\\nsmollm2:135m-instruct-q5_K_M fake\\n'\n"
                "    ;;\n"
                "  run)\n"
                "    printf 'HEALTH_OK\\n'\n"
                "    ;;\n"
                "  serve)\n"
                "    printf 'serving\\n'\n"
                "    ;;\n"
                "  pull)\n"
                f"    touch {pull_marker}\n"
                "    ;;\n"
                "  *) exit 2 ;;\n"
                "esac\n",
            )
            wm = WorkspaceManager(str(workspace))

            old_env = os.environ.copy()
            try:
                with _fake_ollama_http_server() as ollama_host:
                    os.environ["PATH"] = f"{bin_dir}:{old_env.get('PATH', '')}"
                    os.environ["OLLAMA_MODELS"] = str(models)
                    os.environ["AGENTOS_OLLAMA_INSTALL_CMD"] = f"touch {install_marker}"
                    os.environ["AGENTOS_OLLAMA_START_CMD"] = "true"
                    os.environ["OLLAMA_HOST"] = ollama_host
                    payload = ensure_provider_ready(wm, "ollama", allow_bootstrap=False)
            finally:
                os.environ.clear()
                os.environ.update(old_env)

            self.assertTrue(payload.ok)
            self.assertFalse(payload.bootstrap_attempted)
            self.assertIn(payload.install_strategy, {"already_available", "bundled_local"})
            self.assertFalse(install_marker.exists())
            self.assertFalse(pull_marker.exists())

    def test_ollama_bundled_local_prefers_agentos_service_unit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "ws"
            workspace.mkdir()
            wm = WorkspaceManager(str(workspace))
            engine = OllamaEngine(
                workspace_dir=wm.workspace_dir,
                command=wm.ollama_command,
                timeout_sec=wm.ollama_timeout_sec,
                model=wm.ollama_model,
            )
            cmd = _default_ollama_start_cmd(
                wm,
                engine,
                wm.workspace_dir / "artifacts" / "kernel-engine" / "ollama-serve.log",
            )
            self.assertIn("systemctl start agentos-ollama.service", cmd)
            self.assertIn("systemctl start ollama.service", cmd)
            self.assertLess(cmd.index("systemctl start agentos-ollama.service"), cmd.index("systemctl start ollama.service"))


if __name__ == "__main__":
    unittest.main()

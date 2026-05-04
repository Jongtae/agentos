from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import yaml


@contextmanager
def _fake_ollama_http_server(*, response_text: str = "HEALTH_OK", generate_failures_before_success: int = 0):
    state = {"remaining_failures": max(0, generate_failures_before_success)}

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
            if state["remaining_failures"] > 0:
                state["remaining_failures"] -= 1
                body = json.dumps({"error": "model warming up"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
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


class KernelEngineAvailabilityScriptTests(unittest.TestCase):
    def test_script_reports_bootstrapped_ollama(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "spec.yaml").write_text(
                yaml.dump(
                    {
                        "kernel_engine": {
                            "provider": "ollama",
                            "mode": "single",
                            "ollama": {
                                "command": "ollama",
                                "timeout_sec": 10,
                                "model": "smollm2:135m-instruct-q5_K_M",
                                "auto_bootstrap": True,
                            },
                        }
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

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

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
            env["AGENTOS_OLLAMA_INSTALL_CMD"] = install_cmd
            env["AGENTOS_OLLAMA_START_CMD"] = "true"
            env["AGENTOS_OLLAMA_PULL_CMD"] = "ollama pull smollm2:135m-instruct-q5_K_M"
            with _fake_ollama_http_server() as ollama_host:
                env["OLLAMA_HOST"] = ollama_host
                result = subprocess.run(
                    ["python3", "scripts/kernel_engine_availability.py", "--workspace", str(workspace), "--json"],
                    cwd=str(Path(__file__).resolve().parents[1]),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout.strip())
            self.assertTrue(payload["summary"]["provider_ready"])
            self.assertTrue(payload["summary"]["first_prompt_success"])

    def test_script_reports_bundled_local_without_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            workspace = root / "workspace"
            workspace.mkdir()
            models = root / "models"
            manifest = models / "manifests/registry.ollama.ai/library/smollm2/135m-instruct-q5_K_M"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text('{"config":{"digest":"sha256:abc"},"layers":[]}', encoding="utf-8")
            blobs = models / "blobs"
            blobs.mkdir(parents=True, exist_ok=True)
            (blobs / "sha256-abc").write_text("blob", encoding="utf-8")
            (workspace / "spec.yaml").write_text(
                yaml.dump(
                    {
                        "kernel_engine": {
                            "provider": "ollama",
                            "mode": "single",
                            "ollama": {
                                "command": "ollama",
                                "timeout_sec": 10,
                                "model": "smollm2:135m-instruct-q5_K_M",
                                "auto_bootstrap": True,
                            },
                        }
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            (bin_dir / "ollama").write_text(
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
                "  *) exit 2 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            (bin_dir / "ollama").chmod(0o755)

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
            env["OLLAMA_MODELS"] = str(models)
            with _fake_ollama_http_server() as ollama_host:
                env["OLLAMA_HOST"] = ollama_host
                result = subprocess.run(
                    [
                        "python3",
                        "scripts/kernel_engine_availability.py",
                        "--workspace",
                        str(workspace),
                        "--json",
                        "--no-bootstrap",
                    ],
                    cwd=str(Path(__file__).resolve().parents[1]),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout.strip())
            self.assertTrue(payload["summary"]["provider_ready"])
            self.assertFalse(payload["bootstrap_attempted"])
            self.assertTrue(payload["summary"]["first_prompt_success"])

    def test_script_writes_non_empty_output_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            workspace = root / "workspace"
            workspace.mkdir()
            output = root / "artifacts" / "engine.json"
            (workspace / "spec.yaml").write_text(
                yaml.dump(
                    {
                        "kernel_engine": {
                            "provider": "ollama",
                            "mode": "single",
                            "ollama": {
                                "command": "ollama",
                                "timeout_sec": 10,
                                "model": "smollm2:135m-instruct-q5_K_M",
                                "auto_bootstrap": True,
                            },
                        }
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            (bin_dir / "ollama").write_text(
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
                "  *) exit 2 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            (bin_dir / "ollama").chmod(0o755)

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
            with _fake_ollama_http_server() as ollama_host:
                env["OLLAMA_HOST"] = ollama_host
                result = subprocess.run(
                    [
                        "python3",
                        "scripts/kernel_engine_availability.py",
                        "--workspace",
                        str(workspace),
                        "--json",
                        "--no-bootstrap",
                        "--output",
                        str(output),
                    ],
                    cwd=str(Path(__file__).resolve().parents[1]),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(payload["summary"]["usable_runtime_entry"])

    def test_script_retries_first_prompt_until_model_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            workspace = root / "workspace"
            workspace.mkdir()
            models = root / "models"
            manifest = models / "manifests/registry.ollama.ai/library/smollm2/135m-instruct-q5_K_M"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text('{"config":{"digest":"sha256:abc"},"layers":[]}', encoding="utf-8")
            blobs = models / "blobs"
            blobs.mkdir(parents=True, exist_ok=True)
            (blobs / "sha256-abc").write_text("blob", encoding="utf-8")
            (workspace / "spec.yaml").write_text(
                yaml.dump(
                    {
                        "kernel_engine": {
                            "provider": "ollama",
                            "mode": "single",
                            "ollama": {
                                "command": "ollama",
                                "timeout_sec": 10,
                                "model": "smollm2:135m-instruct-q5_K_M",
                                "auto_bootstrap": True,
                            },
                        }
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            (bin_dir / "ollama").write_text(
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
                "  *) exit 2 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            (bin_dir / "ollama").chmod(0o755)

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
            env["OLLAMA_MODELS"] = str(models)
            with _fake_ollama_http_server(generate_failures_before_success=2) as ollama_host:
                env["OLLAMA_HOST"] = ollama_host
                result = subprocess.run(
                    [
                        "python3",
                        "scripts/kernel_engine_availability.py",
                        "--workspace",
                        str(workspace),
                        "--json",
                        "--no-bootstrap",
                    ],
                    cwd=str(Path(__file__).resolve().parents[1]),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout.strip())
            self.assertTrue(payload["summary"]["first_prompt_success"])
            self.assertEqual(payload["first_prompt_attempts"], 3)


if __name__ == "__main__":
    unittest.main()

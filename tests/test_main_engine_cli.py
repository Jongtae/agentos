from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import yaml


class MainEngineCliTests(unittest.TestCase):
    def _make_workspace(self, root: Path, codex_cmd: str) -> Path:
        ws = root / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        spec = {
            "name": "cli-test",
            "ai_model": {"provider": "openai", "model": "gpt-4o-mini"},
            "kernel_engine": {
                "provider": "",
                "mode": "single",
                "codex": {"command": codex_cmd, "timeout_sec": 5, "model": ""},
            },
            "tools": {"bash": True, "file": True, "web": True},
            "permissions": {"require_approval": True},
            "memory": {"checkpointer": "sqlite", "db_path": "./data/session.sqlite", "store_path": "./data/memory.sqlite"},
            "runtime": {"max_steps": 12, "max_message_window": 20, "workspace_root": "./"},
        }
        (ws / "spec.yaml").write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")
        return ws

    def _run_main(self, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["python3", "src/main.py", *args],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_set_engine_codex_success_with_fake_binary(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "fake-codex.sh"
            fake.write_text("#!/bin/sh\necho HEALTH_OK\n", encoding="utf-8")
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            ws = self._make_workspace(root, str(fake))

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            env["OPENAI_API_KEY"] = "dummy"
            result = self._run_main(["--workspace", str(ws), "--set-engine", "codex"], env)

            self.assertEqual(result.returncode, 0)
            self.assertIn("health check passed", result.stdout)

    def test_set_engine_ollama_bootstraps_missing_binary(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            ws = self._make_workspace(root, "codex")
            port_file = root / "ollama-port"
            server_script = root / "fake_ollama_http.py"
            server_script.write_text(
                "import json\n"
                "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n"
                "from pathlib import Path\n"
                "class Handler(BaseHTTPRequestHandler):\n"
                "    def do_GET(self):\n"
                "        body = json.dumps({'models': [{'name': 'smollm2:135m-instruct-q5_K_M'}]}).encode()\n"
                "        self.send_response(200); self.send_header('Content-Type', 'application/json'); "
                "self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)\n"
                "    def do_POST(self):\n"
                "        body = json.dumps({'response': 'HEALTH_OK', 'done': True}).encode()\n"
                "        self.send_response(200); self.send_header('Content-Type', 'application/json'); "
                "self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)\n"
                "    def log_message(self, *args): return\n"
                "server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)\n"
                f"Path({str(port_file)!r}).write_text(str(server.server_address[1]), encoding='utf-8')\n"
                "server.serve_forever()\n",
                encoding="utf-8",
            )
            server = subprocess.Popen(["python3", str(server_script)])

            def stop_server():
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)

            self.addCleanup(stop_server)
            for _ in range(50):
                if port_file.exists():
                    break
                time.sleep(0.1)
            self.assertTrue(port_file.exists())

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
            env["OLLAMA_HOST"] = f"http://127.0.0.1:{port_file.read_text(encoding='utf-8')}"
            env["AGENTOS_OLLAMA_INSTALL_CMD"] = install_cmd
            env["AGENTOS_OLLAMA_START_CMD"] = "true"
            env["AGENTOS_OLLAMA_PULL_CMD"] = "ollama pull smollm2:135m-instruct-q5_K_M"
            result = self._run_main(["--workspace", str(ws), "--set-engine", "ollama"], env)

            self.assertEqual(result.returncode, 0)
            self.assertIn("Bootstrap strategy", result.stdout)

    def test_set_engine_stub_provider_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = self._make_workspace(root, "codex")

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            result = self._run_main(["--workspace", str(ws), "--set-engine", "claude"], env)

            self.assertEqual(result.returncode, 2)
            self.assertIn("not implemented", result.stdout)

    def test_set_engine_none_enables_guide_mode(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = self._make_workspace(root, "codex")

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            result = self._run_main(["--workspace", str(ws), "--set-engine", "none"], env)

            self.assertEqual(result.returncode, 0)
            self.assertIn("guide mode", result.stdout)

    def test_json_flag_requires_doctor_or_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = self._make_workspace(root, "codex")

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            result = self._run_main(["--workspace", str(ws), "--json"], env)

            self.assertEqual(result.returncode, 2)
            self.assertIn("--json is only valid", result.stdout)
            self.assertIn("--trace-status", result.stdout)

    def test_trace_status_missing_file_returns_non_zero(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = self._make_workspace(root, "codex")

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            result = self._run_main(["--workspace", str(ws), "--trace-status"], env)

            self.assertEqual(result.returncode, 1)
            self.assertIn("No runtime trace file found", result.stdout)

    def test_trace_status_json_output_when_trace_exists(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = self._make_workspace(root, "codex")
            trace = ws / "artifacts" / "runtime_trace.jsonl"
            trace.parent.mkdir(parents=True, exist_ok=True)
            trace.write_text(
                "\n".join(
                    [
                        '{"timestamp_utc":"2026-01-01T00:00:00Z","event":"run_start","payload":{}}',
                        '{"timestamp_utc":"2026-01-01T00:00:01Z","event":"approval_requested","payload":{}}',
                        '{"timestamp_utc":"2026-01-01T00:00:02Z","event":"approval_decision","payload":{"approved":true}}',
                        '{"timestamp_utc":"2026-01-01T00:00:03Z","event":"run_end","payload":{}}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            result = self._run_main(["--workspace", str(ws), "--trace-status", "--json"], env)

            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout.strip())
            self.assertTrue(payload["trace_exists"])
            self.assertGreaterEqual(payload["event_count"], 4)
            self.assertEqual(payload["approval_counters"]["requested"], 1)
            self.assertEqual(payload["approval_counters"]["approved"], 1)
            self.assertIn("approval_anomaly", payload)
            self.assertFalse(payload["approval_anomaly"]["anomaly_detected"])

    def test_preflight_json_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = self._make_workspace(root, "missing-codex-binary")

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            result = self._run_main(["--workspace", str(ws), "--preflight", "--json"], env)

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout.strip())
            self.assertIn("ready", payload)
            self.assertFalse(payload["ready"])

    def test_doctor_file_writes_json_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = self._make_workspace(root, "missing-codex-binary")
            out = root / "artifacts" / "doctor.json"

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            result = self._run_main(
                ["--workspace", str(ws), "--doctor", "--doctor-file", str(out)],
                env,
            )

            self.assertEqual(result.returncode, 1)
            self.assertTrue(out.exists())
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("reason", payload)
            self.assertEqual(payload["reason"], "binary_not_found")

    def test_status_file_writes_json_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = self._make_workspace(root, "missing-codex-binary")
            out = root / "artifacts" / "status.json"

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            result = self._run_main(
                ["--workspace", str(ws), "--status", "--status-file", str(out)],
                env,
            )

            self.assertEqual(result.returncode, 1)
            self.assertTrue(out.exists())
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("engine_reason", payload)
            self.assertEqual(payload["engine_reason"], "binary_not_found")

    def test_doctor_file_requires_doctor(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = self._make_workspace(root, "missing-codex-binary")

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            result = self._run_main(
                ["--workspace", str(ws), "--doctor-file", str(root / "doctor.json")],
                env,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("--doctor-file is only valid with --doctor.", result.stdout)

    def test_status_file_requires_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = self._make_workspace(root, "missing-codex-binary")

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            result = self._run_main(
                ["--workspace", str(ws), "--status-file", str(root / "status.json")],
                env,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("--status-file is only valid with --status.", result.stdout)

    def test_preflight_file_writes_json_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = self._make_workspace(root, "missing-codex-binary")
            out = root / "artifacts" / "preflight.json"

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            result = self._run_main(
                ["--workspace", str(ws), "--preflight", "--preflight-file", str(out)],
                env,
            )

            self.assertEqual(result.returncode, 1)
            self.assertTrue(out.exists())
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("ready", payload)
            self.assertFalse(payload["ready"])

    def test_preflight_file_requires_preflight(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = self._make_workspace(root, "missing-codex-binary")

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            result = self._run_main(
                ["--workspace", str(ws), "--preflight-file", str(root / "preflight.json")],
                env,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("--preflight-file is only valid with --preflight.", result.stdout)

    def test_no_tui_phase2_runner_flag_shows_banner(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "fake-codex.sh"
            fake.write_text(
                "#!/bin/sh\n"
                "set -eu\n"
                "out=''\n"
                "prompt=''\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  case \"$1\" in\n"
                "    --output-last-message) shift; out=\"$1\" ;;\n"
                "    *) prompt=\"$1\" ;;\n"
                "  esac\n"
                "  shift\n"
                "done\n"
                "if echo \"$prompt\" | grep -q 'Reply with exactly: HEALTH_OK'; then msg='HEALTH_OK'; "
                "else msg='{\"summary\":\"noop\",\"steps\":[]}'; fi\n"
                "if [ -n \"$out\" ]; then printf \"%s\" \"$msg\" > \"$out\"; fi\n"
                "printf \"%s\\n\" \"$msg\"\n",
                encoding="utf-8",
            )
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            ws = self._make_workspace(root, str(fake))

            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            env["OPENAI_API_KEY"] = "dummy"
            env["AGENTOS_USE_AGENT_RUNNER"] = "1"

            result = subprocess.run(
                ["python3", "src/main.py", "--workspace", str(ws), "--no-tui"],
                cwd=str(Path(__file__).resolve().parents[1]),
                env=env,
                input="2\nexit\n",
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("Phase2 runner: agent_runner (skeleton)", result.stdout)

    def test_no_tui_percent_prefix_runs_shell_escape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = self._make_workspace(root, "codex")
            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            setup = self._run_main(["--workspace", str(ws), "--set-engine", "none"], env)
            self.assertEqual(setup.returncode, 0)

            result = subprocess.run(
                ["python3", "src/main.py", "--workspace", str(ws), "--no-tui"],
                cwd=str(Path(__file__).resolve().parents[1]),
                env=env,
                input="% pwd\nexit\n",
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("This prompt is for talking to AgentOS.", result.stdout)
            self.assertIn(str(ws), result.stdout)

    def test_no_tui_shell_keyword_runs_shell_escape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = self._make_workspace(root, "codex")
            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            setup = self._run_main(["--workspace", str(ws), "--set-engine", "none"], env)
            self.assertEqual(setup.returncode, 0)

            result = subprocess.run(
                ["python3", "src/main.py", "--workspace", str(ws), "--no-tui"],
                cwd=str(Path(__file__).resolve().parents[1]),
                env=env,
                input="shell printf hello\nexit\n",
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("hello", result.stdout)
            self.assertIn("Use `% <command>` only when you want a Linux shell command.", result.stdout)


if __name__ == "__main__":
    unittest.main()

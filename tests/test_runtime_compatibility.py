from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


class RuntimeCompatibilityTests(unittest.TestCase):
    def _make_workspace(self, root: Path, codex_cmd: str) -> Path:
        ws = root / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        spec = {
            "name": "compat-test",
            "ai_model": {"provider": "openai", "model": "gpt-4o-mini"},
            "kernel_engine": {
                "provider": "",
                "mode": "single",
                "codex": {"command": codex_cmd, "timeout_sec": 5, "model": ""},
            },
            "tools": {"bash": True, "file": True, "web": True},
            "permissions": {"require_approval": True},
            "memory": {
                "checkpointer": "sqlite",
                "db_path": "./data/session.sqlite",
                "store_path": "./data/memory.sqlite",
            },
            "runtime": {"max_steps": 12, "max_message_window": 20, "workspace_root": "./"},
        }
        (ws / "spec.yaml").write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")
        return ws

    def _make_fake_codex(self, root: Path) -> Path:
        fake = root / "fake-codex.sh"
        fake.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "out_file=''\n"
            "prompt=''\n"
            "while [ \"$#\" -gt 0 ]; do\n"
            "  case \"$1\" in\n"
            "    --output-last-message) shift; out_file=\"$1\" ;;\n"
            "    *) prompt=\"$1\" ;;\n"
            "  esac\n"
            "  shift\n"
            "done\n"
            "if echo \"$prompt\" | grep -q 'Reply with exactly: HEALTH_OK'; then\n"
            "  msg='HEALTH_OK'\n"
            "elif echo \"$prompt\" | grep -q 'planning engine for AgentOS'; then\n"
            "  msg='{\"summary\":\"list files\",\"steps\":[{\"tool_name\":\"file_list\",\"description\":\"list root\",\"args\":{\"path\":\".\"},\"is_destructive\":false}]}'\n"
            "else\n"
            "  msg='{\"summary\":\"noop\",\"steps\":[]}'\n"
            "fi\n"
            "if [ -n \"$out_file\" ]; then printf \"%s\" \"$msg\" > \"$out_file\"; fi\n"
            "printf \"%s\\n\" \"$msg\"\n",
            encoding="utf-8",
        )
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        return fake

    def _run_session(self, ws: Path, use_agent_runner: bool) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["PYTHONPATH"] = "src"
        env["OPENAI_API_KEY"] = "dummy"
        if use_agent_runner:
            env["AGENTOS_USE_AGENT_RUNNER"] = "1"
        else:
            env.pop("AGENTOS_USE_AGENT_RUNNER", None)

        return subprocess.run(
            ["python3", "src/main.py", "--workspace", str(ws), "--no-tui"],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env,
            input="2\nlist files in this directory\nexit\n",
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_phase1_and_phase2_paths_are_compatible(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = self._make_fake_codex(root)
            ws1 = self._make_workspace(root / "p1", str(fake))
            ws2 = self._make_workspace(root / "p2", str(fake))

            phase1 = self._run_session(ws1, use_agent_runner=False)
            phase2 = self._run_session(ws2, use_agent_runner=True)

            self.assertEqual(phase1.returncode, 0)
            self.assertEqual(phase2.returncode, 0)
            self.assertIn("AI:", phase1.stdout)
            self.assertIn("AI:", phase2.stdout)
            self.assertIn("spec.yaml", phase1.stdout)
            self.assertIn("spec.yaml", phase2.stdout)
            self.assertIn("Phase2 runner: agent_runner (skeleton)", phase2.stdout)


if __name__ == "__main__":
    unittest.main()

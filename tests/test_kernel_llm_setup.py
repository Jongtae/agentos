import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "kernel_llm_setup.py"


class KernelLLMSetupTests(unittest.TestCase):
    def run_setup(self, *args, home: Path, workspace: Path) -> dict:
        env = os.environ.copy()
        env["HOME"] = str(home)
        proc = subprocess.run(
            ["python3", str(SCRIPT), "--workspace", str(workspace), *args, "--json"],
            cwd=str(ROOT),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return json.loads(proc.stdout)

    def test_default_status_reports_ollama_and_model(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            payload = self.run_setup(home=root / "home", workspace=root / "ws")
        self.assertEqual(payload["schema_version"], "agentos-llm-setup.v1")
        self.assertEqual(payload["provider"], "ollama")
        self.assertEqual(payload["selected_model"], "smollm2:135m-instruct-q5_K_M")
        self.assertEqual(payload["codex_model"], "gpt-4o-mini")

    def test_set_codex_forces_gpt_4o_mini_and_writes_key_to_user_env(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            workspace = root / "ws"
            payload = self.run_setup(
                "--set-provider",
                "codex",
                "--openai-api-key",
                "test-openai-key-placeholder",
                home=home,
                workspace=workspace,
            )
            env_text = (home / ".config" / "agentos" / "env").read_text(encoding="utf-8")
            spec_text = (workspace / "spec.yaml").read_text(encoding="utf-8")
        self.assertEqual(payload["provider"], "codex")
        self.assertEqual(payload["selected_model"], "gpt-4o-mini")
        self.assertNotIn("test-openai-key-placeholder", json.dumps(payload))
        self.assertIn("OPENAI_API_KEY=test-openai-key-placeholder", env_text)
        self.assertIn("provider: codex", spec_text)
        self.assertIn("model: gpt-4o-mini", spec_text)

    def test_set_guide_maps_to_none(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            payload = self.run_setup("--set-provider", "guide", home=root / "home", workspace=root / "ws")
        self.assertEqual(payload["provider"], "none")
        self.assertTrue(payload["provider_ready"])


if __name__ == "__main__":
    unittest.main()

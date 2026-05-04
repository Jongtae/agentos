from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from workspace.manager import WorkspaceManager
from kernel.engine.router import EngineRouter
from kernel.engine.stubs import ClaudeEngineStub, GeminiEngineStub


class WorkspaceManagerTests(unittest.TestCase):
    def test_legacy_spec_merges_kernel_engine_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            spec_path = root / "spec.yaml"
            spec_path.write_text(
                yaml.dump(
                    {
                        "name": "legacy",
                        "ai_model": {"provider": "openai", "model": "gpt-4o-mini"},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            wm = WorkspaceManager(str(root))
            self.assertEqual(wm.kernel_engine_provider, "")
            self.assertEqual(wm.kernel_engine_mode, "single")
            self.assertEqual(wm.codex_command, "codex")
            self.assertEqual(wm.codex_model, "gpt-4o-mini")
            self.assertEqual(wm.ollama_command, "ollama")
            self.assertEqual(wm.ollama_model, "smollm2:135m-instruct-q5_K_M")
            self.assertGreaterEqual(wm.codex_timeout_sec, 1)
            self.assertGreaterEqual(wm.ollama_timeout_sec, 1)

    def test_unknown_kernel_provider_raises(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            spec_path = root / "spec.yaml"
            spec_path.write_text(
                yaml.dump(
                    {
                        "kernel_engine": {
                            "provider": "unknown",
                            "mode": "single",
                            "codex": {"command": "codex", "timeout_sec": 90},
                        }
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                WorkspaceManager(str(root))

    def test_set_kernel_engine_provider_persists(self):
        with tempfile.TemporaryDirectory() as td:
            wm = WorkspaceManager(td)
            wm.set_kernel_engine_provider("codex")
            wm2 = WorkspaceManager(td)
            self.assertEqual(wm2.kernel_engine_provider, "codex")

    def test_set_kernel_engine_provider_supports_ollama_and_none(self):
        with tempfile.TemporaryDirectory() as td:
            wm = WorkspaceManager(td)
            wm.set_kernel_engine_provider("ollama")
            self.assertEqual(WorkspaceManager(td).kernel_engine_provider, "ollama")
            wm.set_kernel_engine_provider("none")
            self.assertEqual(WorkspaceManager(td).kernel_engine_provider, "none")

    def test_empty_codex_model_falls_back_to_gpt_4o_mini(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            spec_path = root / "spec.yaml"
            spec_path.write_text(
                yaml.dump(
                    {
                        "kernel_engine": {
                            "provider": "codex",
                            "mode": "single",
                            "codex": {"command": "codex", "timeout_sec": 90, "model": ""},
                        }
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            wm = WorkspaceManager(str(root))
            self.assertEqual(wm.codex_model, "gpt-4o-mini")

    def test_default_network_allowlist_is_available(self):
        with tempfile.TemporaryDirectory() as td:
            wm = WorkspaceManager(td)
            self.assertIn("localhost", wm.web_allowlist)
            self.assertIn("127.0.0.1", wm.web_allowlist)

    def test_require_approval_locked_on_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            spec_path = root / "spec.yaml"
            spec_path.write_text(
                yaml.dump({"permissions": {"require_approval": False}}, sort_keys=False),
                encoding="utf-8",
            )
            wm = WorkspaceManager(str(root))
            self.assertTrue(wm.require_approval)

    def test_require_approval_can_be_disabled_with_explicit_unsafe_env(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            spec_path = root / "spec.yaml"
            spec_path.write_text(
                yaml.dump({"permissions": {"require_approval": False}}, sort_keys=False),
                encoding="utf-8",
            )
            old = os.environ.get("AGENTOS_ALLOW_UNSAFE_APPROVAL_OFF")
            try:
                os.environ["AGENTOS_ALLOW_UNSAFE_APPROVAL_OFF"] = "1"
                wm = WorkspaceManager(str(root))
                self.assertFalse(wm.require_approval)
            finally:
                if old is None:
                    os.environ.pop("AGENTOS_ALLOW_UNSAFE_APPROVAL_OFF", None)
                else:
                    os.environ["AGENTOS_ALLOW_UNSAFE_APPROVAL_OFF"] = old


class EngineRouterTests(unittest.TestCase):
    def test_router_maps_provider(self):
        router = EngineRouter(
            mode="single",
            engines={
                "claude": ClaudeEngineStub(),
                "gemini": GeminiEngineStub(),
            },
        )
        self.assertEqual(router.get_engine("claude").name, "claude")

    def test_unknown_provider_raises(self):
        router = EngineRouter(mode="single", engines={"claude": ClaudeEngineStub()})
        with self.assertRaises(ValueError):
            router.get_engine("codex")


if __name__ == "__main__":
    unittest.main()

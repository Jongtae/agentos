from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from kernel.runtime.agent_runner import AgentRunner, is_agent_runner_enabled
from kernel.runtime.checkpoint_saver import JsonCheckpointSaver


class _DummyRuntime:
    def __init__(self):
        self.value = 0

    def run(self, user_input: str) -> str:
        return f"ran:{user_input}"


class _FailingRuntime:
    def run(self, user_input: str) -> str:
        raise RuntimeError("boom")


class AgentRunnerTests(unittest.TestCase):
    def test_flag_disabled_by_default(self):
        old = os.environ.pop("AGENTOS_USE_AGENT_RUNNER", None)
        try:
            self.assertFalse(is_agent_runner_enabled())
        finally:
            if old is not None:
                os.environ["AGENTOS_USE_AGENT_RUNNER"] = old

    def test_flag_enabled_values(self):
        old = os.environ.get("AGENTOS_USE_AGENT_RUNNER")
        try:
            os.environ["AGENTOS_USE_AGENT_RUNNER"] = "1"
            self.assertTrue(is_agent_runner_enabled())
            os.environ["AGENTOS_USE_AGENT_RUNNER"] = "true"
            self.assertTrue(is_agent_runner_enabled())
        finally:
            if old is None:
                os.environ.pop("AGENTOS_USE_AGENT_RUNNER", None)
            else:
                os.environ["AGENTOS_USE_AGENT_RUNNER"] = old

    def test_runner_delegates_and_preserves_attrs(self):
        rt = _DummyRuntime()
        runner = AgentRunner(rt)

        self.assertEqual(runner.run("hello"), "ran:hello")
        self.assertEqual(runner.runner_mode, "phase2-skeleton")

        runner.value = 42
        self.assertEqual(rt.value, 42)

    def test_runner_saves_checkpoint_on_success(self):
        with tempfile.TemporaryDirectory() as td:
            saver = JsonCheckpointSaver(Path(td) / "cp.json")
            runner = AgentRunner(_DummyRuntime(), checkpoint_saver=saver)
            out = runner.run("hello")
            self.assertEqual(out, "ran:hello")
            cp = saver.load_checkpoint()
            self.assertIsNotNone(cp)
            self.assertEqual(cp["status"], "completed")
            self.assertEqual(cp["user_input"], "hello")

    def test_runner_saves_checkpoint_on_failure(self):
        with tempfile.TemporaryDirectory() as td:
            saver = JsonCheckpointSaver(Path(td) / "cp.json")
            runner = AgentRunner(_FailingRuntime(), checkpoint_saver=saver)
            with self.assertRaises(RuntimeError):
                runner.run("hello")
            cp = saver.load_checkpoint()
            self.assertIsNotNone(cp)
            self.assertEqual(cp["status"], "failed")
            self.assertIn("error", cp)


if __name__ == "__main__":
    unittest.main()

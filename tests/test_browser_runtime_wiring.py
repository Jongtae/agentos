from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from main import build_runtime


class _FakeLLMResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    def invoke(self, messages):
        _ = messages
        return _FakeLLMResponse('{"summary":"noop","steps":[]}')


class _FakeWM:
    def __init__(self, workspace_dir: Path, browser_enabled_in_spec: bool):
        self.workspace_dir = workspace_dir
        self.spec = {
            "tools": {
                "bash": True,
                "file": True,
                "web": True,
                "browser": browser_enabled_in_spec,
            }
        }
        self._memory_path = workspace_dir / "data" / "memory.sqlite"

    @property
    def memory_store_path(self) -> str:
        return str(self._memory_path)

    @property
    def require_approval(self) -> bool:
        return True

    @property
    def max_steps(self) -> int:
        return 5


class BrowserRuntimeWiringTests(unittest.TestCase):
    def test_browser_tool_is_off_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            wm = _FakeWM(Path(td), browser_enabled_in_spec=True)
            with patch.dict(os.environ, {}, clear=True):
                runtime, _, _ = build_runtime(wm, planner_backend=_FakeLLM())
            self.assertNotIn("browser_run", runtime._executor.available_tools)

    def test_browser_tool_is_enabled_with_flag_and_spec(self):
        with tempfile.TemporaryDirectory() as td:
            wm = _FakeWM(Path(td), browser_enabled_in_spec=True)
            with patch.dict(os.environ, {"AGENTOS_ENABLE_BROWSER_TOOL": "1"}, clear=True):
                runtime, _, _ = build_runtime(wm, planner_backend=_FakeLLM())
            self.assertIn("browser_run", runtime._executor.available_tools)

    def test_browser_tool_not_enabled_when_spec_disables_it(self):
        with tempfile.TemporaryDirectory() as td:
            wm = _FakeWM(Path(td), browser_enabled_in_spec=False)
            with patch.dict(os.environ, {"AGENTOS_ENABLE_BROWSER_TOOL": "1"}, clear=True):
                runtime, _, _ = build_runtime(wm, planner_backend=_FakeLLM())
            self.assertNotIn("browser_run", runtime._executor.available_tools)


if __name__ == "__main__":
    unittest.main()

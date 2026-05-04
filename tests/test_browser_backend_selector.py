from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from kernel.tools.browser_tool import BrowserExecutorTool, resolve_browser_backend


class BrowserBackendSelectorTests(unittest.TestCase):
    def test_default_backend_is_worker(self):
        with patch.dict(os.environ, {}, clear=True):
            backend = resolve_browser_backend()
        self.assertEqual(backend.requested, "worker")
        self.assertEqual(backend.selected, "worker")
        self.assertEqual(backend.fallback_reason, "")

    def test_stub_backend_selected(self):
        with patch.dict(os.environ, {"AGENTOS_BROWSER_BACKEND": "stub"}, clear=True):
            backend = resolve_browser_backend()
            tool = BrowserExecutorTool()
        self.assertEqual(backend.selected, "stub")
        self.assertEqual(tool.backend.selected, "stub")

    def test_playwright_backend_falls_back_to_worker(self):
        with patch.dict(os.environ, {"AGENTOS_BROWSER_BACKEND": "playwright"}, clear=True):
            with patch("kernel.tools.browser_tool._is_playwright_available", return_value=False):
                backend = resolve_browser_backend()
                tool = BrowserExecutorTool()
        self.assertEqual(backend.requested, "playwright")
        self.assertEqual(backend.selected, "worker")
        self.assertEqual(backend.fallback_reason, "playwright_unavailable")
        self.assertEqual(tool.backend.selected, "worker")

    def test_playwright_backend_selected_when_dependency_available(self):
        with patch.dict(os.environ, {"AGENTOS_BROWSER_BACKEND": "playwright"}, clear=True):
            with patch("kernel.tools.browser_tool._is_playwright_available", return_value=True):
                backend = resolve_browser_backend()
            self.assertEqual(backend.selected, "playwright")
            self.assertEqual(backend.fallback_reason, "")

    def test_invalid_backend_falls_back_to_worker(self):
        with patch.dict(os.environ, {"AGENTOS_BROWSER_BACKEND": "unknown"}, clear=True):
            backend = resolve_browser_backend()
        self.assertEqual(backend.requested, "unknown")
        self.assertEqual(backend.selected, "worker")
        self.assertEqual(backend.fallback_reason, "invalid_backend")


if __name__ == "__main__":
    unittest.main()

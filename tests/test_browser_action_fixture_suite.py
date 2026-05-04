from __future__ import annotations

import sys
import unittest
from pathlib import Path

from kernel.tools.browser_tool import BrowserIsolationRequest, BrowserWorkerIsolationBoundary


class BrowserActionFixtureSuiteTests(unittest.TestCase):
    def test_action_matrix_fixtures(self):
        worker = Path(__file__).resolve().parents[1] / "scripts" / "browser_worker_stub.py"
        boundary = BrowserWorkerIsolationBoundary(worker_cmd=[sys.executable, str(worker)], timeout_sec=2)

        cases = [
            ("navigate", "fixture:navigate_ok", {"url": "https://example.com"}),
            ("click", "fixture:click_ok", {"url": "https://example.com", "selector": "#login"}),
            ("fill", "fixture:fill_ok", {"url": "https://example.com", "selector": "#email", "value": "a@b.com"}),
            ("screenshot", "fixture:screenshot_ok", {"url": "https://example.com"}),
            ("extract_text", "fixture:extract_text_ok", {"url": "https://example.com", "selector": "h1"}),
        ]

        for action, marker, fields in cases:
            with self.subTest(action=action):
                result = boundary.run(BrowserIsolationRequest(action=action, **fields))
                self.assertTrue(result.ok)
                self.assertIn(marker, result.detail)


if __name__ == "__main__":
    unittest.main()

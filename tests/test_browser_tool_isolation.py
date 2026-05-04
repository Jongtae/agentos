from __future__ import annotations

import sys
import unittest
from pathlib import Path

from kernel.tools.browser_tool import (
    BrowserIsolationRequest,
    BrowserToolIsolationStub,
    BrowserWorkerIsolationBoundary,
)


class BrowserToolIsolationTests(unittest.TestCase):
    def test_stub_is_disabled(self):
        stub = BrowserToolIsolationStub()
        self.assertEqual(stub.name, "browser_isolated")
        self.assertFalse(stub.is_enabled())

    def test_validate_returns_disabled_error(self):
        stub = BrowserToolIsolationStub()
        result = stub.validate(BrowserIsolationRequest(action="navigate", url="https://example.com"))
        self.assertFalse(result.ok)
        self.assertIn("not enabled", result.detail)

    def test_run_tool_returns_error_string(self):
        stub = BrowserToolIsolationStub()
        output = stub.run_tool({"action": "navigate", "url": "https://example.com"})
        self.assertTrue(output.startswith("[error]"))

    def test_worker_boundary_runs_via_subprocess(self):
        worker = Path(__file__).resolve().parents[1] / "scripts" / "browser_worker_stub.py"
        boundary = BrowserWorkerIsolationBoundary(worker_cmd=[sys.executable, str(worker)], timeout_sec=2)
        result = boundary.run(BrowserIsolationRequest(action="navigate", url="https://example.com"))
        self.assertTrue(result.ok)
        self.assertIn("fixture:navigate_ok", result.detail)

    def test_worker_boundary_timeout(self):
        worker = Path(__file__).resolve().parents[1] / "scripts" / "browser_worker_stub.py"
        boundary = BrowserWorkerIsolationBoundary(worker_cmd=[sys.executable, str(worker)], timeout_sec=1)
        result = boundary.run(BrowserIsolationRequest(action="navigate", url="https://example.com?sleep=2"))
        self.assertFalse(result.ok)
        self.assertIn("timed out", result.detail)

    def test_worker_boundary_blocks_localhost_navigation(self):
        worker = Path(__file__).resolve().parents[1] / "scripts" / "browser_worker_stub.py"
        boundary = BrowserWorkerIsolationBoundary(worker_cmd=[sys.executable, str(worker)], timeout_sec=2)
        result = boundary.run(BrowserIsolationRequest(action="navigate", url="http://localhost:3000"))
        self.assertFalse(result.ok)
        self.assertIn("blocked", result.detail)

    def test_worker_boundary_requires_approval_for_cross_domain(self):
        worker = Path(__file__).resolve().parents[1] / "scripts" / "browser_worker_stub.py"
        boundary = BrowserWorkerIsolationBoundary(worker_cmd=[sys.executable, str(worker)], timeout_sec=2)
        first = boundary.run(BrowserIsolationRequest(action="navigate", url="https://example.com"))
        self.assertTrue(first.ok)
        second = boundary.run(BrowserIsolationRequest(action="navigate", url="https://another.example.org"))
        self.assertFalse(second.ok)
        self.assertIn("approval_required", second.detail)


if __name__ == "__main__":
    unittest.main()

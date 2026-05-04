from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from kernel.policies.approval_rules import classify_browser_navigation


class BrowserNavigationPolicyTests(unittest.TestCase):
    def test_initial_navigation_allowed(self):
        d = classify_browser_navigation("", "https://example.com")
        self.assertEqual(d.state, "allowed")

    def test_same_domain_allowed(self):
        d = classify_browser_navigation("https://example.com/page", "https://example.com/other")
        self.assertEqual(d.state, "allowed")

    def test_cross_domain_requires_approval(self):
        d = classify_browser_navigation("https://example.com", "https://another.example.org")
        self.assertEqual(d.state, "approval_required")

    def test_localhost_blocked(self):
        d = classify_browser_navigation("", "http://localhost:3000")
        self.assertEqual(d.state, "blocked")

    def test_non_http_scheme_blocked(self):
        d = classify_browser_navigation("", "file:///tmp/test")
        self.assertEqual(d.state, "blocked")

    def test_allowlist_allows_cross_domain_without_approval(self):
        with patch.dict(
            os.environ,
            {"AGENTOS_BROWSER_DOMAIN_ALLOWLIST": "openai.com,example.org"},
            clear=False,
        ):
            d = classify_browser_navigation("https://example.com", "https://chat.openai.com")
        self.assertEqual(d.state, "allowed")
        self.assertIn("allowlisted domain", d.reason)

    def test_denylist_blocks_target_domain(self):
        with patch.dict(
            os.environ,
            {"AGENTOS_BROWSER_DOMAIN_DENYLIST": "admin.internal,evil.com"},
            clear=False,
        ):
            d = classify_browser_navigation("https://example.com", "https://api.evil.com")
        self.assertEqual(d.state, "blocked")
        self.assertIn("denylisted domain", d.reason)


if __name__ == "__main__":
    unittest.main()

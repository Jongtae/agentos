from __future__ import annotations

import unittest

from kernel.tools.web_tool import WebTool, _host_matches_rule


class WebToolAllowlistTests(unittest.TestCase):
    def test_host_rule_matches_subdomain(self):
        self.assertTrue(_host_matches_rule("api.openai.com", "openai.com"))
        self.assertTrue(_host_matches_rule("openai.com", "openai.com"))
        self.assertFalse(_host_matches_rule("example.com", "openai.com"))

    def test_run_blocks_disallowed_domain_before_network_call(self):
        tool = WebTool(domain_allowlist=["openai.com"])
        out = tool.run({"url": "https://example.com"})
        self.assertIn("not in the allowlist", out)

    def test_allowlist_accepts_host_with_port(self):
        tool = WebTool(domain_allowlist=["127.0.0.1"])
        out = tool.run({"url": "http://127.0.0.1:9/"})
        self.assertNotIn("not in the allowlist", out)


if __name__ == "__main__":
    unittest.main()

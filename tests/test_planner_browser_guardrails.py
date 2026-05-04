from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from kernel.planner.planner import Planner


class _CaptureLLM:
    def __init__(self, response_payload: dict):
        self._response = json.dumps(response_payload)
        self.system_prompt = ""

    def invoke(self, messages):
        self.system_prompt = getattr(messages[0], "content", "")
        return SimpleNamespace(content=self._response)


class PlannerBrowserGuardrailsTests(unittest.TestCase):
    def test_prompt_excludes_browser_when_not_available(self):
        llm = _CaptureLLM({"summary": "noop", "steps": []})
        planner = Planner(llm, available_tools=["bash", "file_read", "web_fetch"])

        planner.plan("list files")

        self.assertIn("- bash", llm.system_prompt)
        self.assertIn("- web_fetch", llm.system_prompt)
        self.assertNotIn("browser_run", llm.system_prompt)

    def test_parse_drops_browser_when_not_available(self):
        llm = _CaptureLLM(
            {
                "summary": "mixed plan",
                "steps": [
                    {
                        "tool_name": "browser_run",
                        "description": "navigate",
                        "args": {"action": "navigate", "url": "https://example.com"},
                        "is_destructive": False,
                    },
                    {
                        "tool_name": "bash",
                        "description": "pwd",
                        "args": {"command": "pwd"},
                        "is_destructive": False,
                    },
                ],
            }
        )
        planner = Planner(llm, available_tools=["bash", "file_read", "web_fetch"])

        plan = planner.plan("inspect workspace")

        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].tool_name, "bash")

    def test_parse_keeps_browser_when_available(self):
        llm = _CaptureLLM(
            {
                "summary": "browser plan",
                "steps": [
                    {
                        "tool_name": "browser_run",
                        "description": "navigate",
                        "args": {"action": "navigate", "url": "https://example.com"},
                        "is_destructive": False,
                    }
                ],
            }
        )
        planner = Planner(llm, available_tools=["bash", "web_fetch", "browser_run"])

        plan = planner.plan("open site")

        self.assertIn("browser_run", llm.system_prompt)
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].tool_name, "browser_run")


if __name__ == "__main__":
    unittest.main()

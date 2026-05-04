from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from kernel.intent_dispatch import build_intent_dispatch_report, classify_intent
from kernel.operator_activity import build_activity_feed_payload


class KernelIntentDispatchTests(unittest.TestCase):
    def test_start_and_greeting_do_not_trigger_web_search(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            for message, expected in (("/start", "telegram_start"), ("hi", "greeting"), ("안녕", "greeting")):
                payload = build_intent_dispatch_report(
                    workspace,
                    source="telegram",
                    message_text=message,
                    chat_id="1001",
                    send_reply=False,
                )
                self.assertEqual(payload["intent"], expected)
                self.assertFalse(payload["web_search_used"])
                self.assertTrue(payload["proof"]["ok"])

    def test_workspace_request_uses_local_workspace_search(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / "documents").mkdir()
            (workspace / "spec.yaml").write_text("name: demo\n", encoding="utf-8")
            payload = build_intent_dispatch_report(
                workspace,
                source="operator",
                message_text="workspace 파일 목록 보여줘",
            )
            self.assertEqual(payload["intent"], "local_workspace_search")
            self.assertFalse(payload["web_search_used"])
            self.assertIn("spec.yaml", payload["response"])

    def test_search_request_classifies_as_web_search_summary(self) -> None:
        intent = classify_intent("search AgentOS roadmap and summarize", source="telegram")
        self.assertEqual(intent["intent"], "web_search_summary")
        self.assertEqual(intent["capability"], "research_brief_response")

    def test_activity_feed_records_human_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            build_intent_dispatch_report(workspace, source="telegram", message_text="hi", chat_id="1001")
            feed = build_activity_feed_payload(workspace)
            messages = [event["human_message"] for event in feed["events"]]
            self.assertIn("Telegram received: hi", messages)
            self.assertIn("Understood as: greeting", messages)
            self.assertIn("Replied without web search", messages)
            raw = (workspace / "artifacts" / "os_events.jsonl").read_text(encoding="utf-8")
            for line in raw.splitlines():
                json.loads(line)


if __name__ == "__main__":
    unittest.main()

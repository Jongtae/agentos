from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from kernel.memory.summarizer import is_memory_summarizer_enabled, ScaffoldMemoryWindowSummarizer
from kernel.planner.planner import Plan
from kernel.runtime.loop import KernelRuntime


class _FakeSelector:
    def select(self, query, memory):
        _ = query, memory
        return "selected-context"


class _FakePlanner:
    def __init__(self):
        self.last_context = None

    def plan(self, intent, context=""):
        _ = intent
        self.last_context = context
        return Plan(summary="ok", steps=[])


class _FakeExecutor:
    def execute(self, step):
        _ = step
        return "done"


class _FakePolicy:
    def is_blocked(self, step):
        _ = step
        return False

    def requires_approval(self, step):
        _ = step
        return False


class _RecordingSummarizer:
    def __init__(self, enabled, replacement):
        self._enabled = enabled
        self._replacement = replacement
        self.calls = 0

    def is_enabled(self):
        return self._enabled

    def compact_message_window(self, user_input, context, memory):
        _ = user_input, context, memory
        self.calls += 1
        return self._replacement


class MemorySummarizerTests(unittest.TestCase):
    def test_flag_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_memory_summarizer_enabled())

    def test_flag_enabled_values(self):
        for value in ("1", "true", "yes", "on"):
            with patch.dict(os.environ, {"AGENTOS_USE_MEMORY_SUMMARIZER": value}, clear=True):
                self.assertTrue(is_memory_summarizer_enabled())

    def test_runtime_does_not_run_summarizer_when_disabled(self):
        planner = _FakePlanner()
        summarizer = _RecordingSummarizer(enabled=False, replacement="should-not-be-used")
        runtime = KernelRuntime(
            planner=planner,
            executor=_FakeExecutor(),
            context_selector=_FakeSelector(),
            policy=_FakePolicy(),
            approver_fn=lambda _: True,
            memory=object(),
            memory_summarizer=summarizer,
        )

        runtime.run("hello")
        self.assertEqual(summarizer.calls, 0)
        self.assertEqual(planner.last_context, "selected-context")

    def test_runtime_runs_summarizer_when_enabled(self):
        planner = _FakePlanner()
        summarizer = _RecordingSummarizer(enabled=True, replacement="compacted-context")
        runtime = KernelRuntime(
            planner=planner,
            executor=_FakeExecutor(),
            context_selector=_FakeSelector(),
            policy=_FakePolicy(),
            approver_fn=lambda _: True,
            memory=object(),
            memory_summarizer=summarizer,
        )

        runtime.run("hello")
        self.assertEqual(summarizer.calls, 1)
        self.assertEqual(planner.last_context, "compacted-context")

    def test_scaffold_compacts_long_context(self):
        summarizer = ScaffoldMemoryWindowSummarizer(max_chars=120, max_lines=3)
        context = (
            "Recent relevant context:\n"
            "- [bash] regular line one\n"
            "- [bash] regular line two\n"
            "- [bash] IMPORTANT security warning line\n"
            "- [bash] regular line three\n"
            "- [bash] regular line four\n"
        )
        compacted = summarizer.compact_message_window("hi", context, memory=object())
        self.assertLessEqual(len(compacted), 120)
        self.assertIn("security warning", compacted.lower())

    def test_scaffold_metrics_report_compaction_ratio_and_retention(self):
        summarizer = ScaffoldMemoryWindowSummarizer(max_chars=90, max_lines=2)
        original = (
            "Recent relevant context:\n"
            "- [bash] IMPORTANT keep this\n"
            "- [bash] normal line 1\n"
            "- [bash] normal line 2\n"
            "- [bash] normal line 3\n"
        )
        compacted = summarizer.compact_message_window("hello", original, memory=object())
        metrics = summarizer.metrics(original, compacted)
        self.assertLessEqual(metrics["compaction_ratio"], 1.0)
        self.assertGreaterEqual(metrics["critical_lines_retained"], 1)


if __name__ == "__main__":
    unittest.main()

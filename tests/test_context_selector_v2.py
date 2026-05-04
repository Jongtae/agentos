from __future__ import annotations

import os
import unittest
from datetime import datetime
from unittest.mock import patch

from kernel.context.selector import ContextSelector
from kernel.context.selector_v2 import (
    ContextSelectorV2CompatAdapter,
    LegacySelectorV2Bridge,
    is_context_selector_v2_enabled,
)
from kernel.memory.store import MemoryItem


class _FakeStore:
    def __init__(self, items: list[MemoryItem]):
        self._items = items

    def recent(self, limit: int = 100) -> list[MemoryItem]:
        return self._items[:limit]


class ContextSelectorV2Tests(unittest.TestCase):
    def test_flag_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_context_selector_v2_enabled())

    def test_flag_enabled_values(self):
        for value in ("1", "true", "yes", "on"):
            with patch.dict(os.environ, {"AGENTOS_USE_CONTEXT_SELECTOR_V2": value}, clear=True):
                self.assertTrue(is_context_selector_v2_enabled())

    def test_bridge_parity_with_legacy_selector(self):
        now = datetime.now()
        store = _FakeStore(
            [
                MemoryItem(1, "deploy status", "", "bash", 0.5, now),
                MemoryItem(2, "readme update", "", "file_read", 0.4, now),
            ]
        )
        legacy = ContextSelector(top_k=2)
        v2_adapter = ContextSelectorV2CompatAdapter(LegacySelectorV2Bridge(legacy), top_k=2)

        legacy_out = legacy.select("deploy", store)
        v2_out = v2_adapter.select("deploy", store)
        self.assertEqual(legacy_out, v2_out)


if __name__ == "__main__":
    unittest.main()

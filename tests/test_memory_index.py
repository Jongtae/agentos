from __future__ import annotations

import unittest
from unittest.mock import patch
from datetime import datetime
import tempfile
from pathlib import Path

from kernel.context.selector import ContextSelector
from kernel.memory.index import (
    MemoryIndexHit,
    NoopMemoryIndex,
    TokenEmbeddingMemoryIndex,
    build_memory_index_from_env,
)
from kernel.memory.store import MemoryItem


class _FakeStore:
    def __init__(self, items: list[MemoryItem]):
        self._items = items

    def recent(self, limit: int = 100) -> list[MemoryItem]:
        return self._items[:limit]


class _EnabledIndex:
    @property
    def name(self) -> str:
        return "enabled-fake"

    def is_enabled(self) -> bool:
        return True

    def rebuild(self, items: list[MemoryItem]) -> None:
        _ = items

    def query(self, text: str, limit: int = 20) -> list[MemoryIndexHit]:
        _ = text, limit
        return [MemoryIndexHit(memory_id=2, score=5.0)]


class MemoryIndexTests(unittest.TestCase):
    def test_noop_index_contract(self):
        index = NoopMemoryIndex()
        self.assertEqual(index.name, "noop")
        self.assertFalse(index.is_enabled())
        index.rebuild([])
        self.assertEqual(index.query("hello"), [])

    def test_selector_fallback_unchanged_with_noop_index(self):
        now = datetime.now()
        store = _FakeStore(
            [
                MemoryItem(1, "deploy succeeded", "", "bash", 0.5, now),
                MemoryItem(2, "disk cleanup", "", "bash", 0.5, now),
            ]
        )
        selector_default = ContextSelector(top_k=2)
        selector_noop = ContextSelector(top_k=2, memory_index=NoopMemoryIndex())

        out_default = selector_default.select("deploy", store)
        out_noop = selector_noop.select("deploy", store)
        self.assertEqual(out_default, out_noop)

    def test_selector_uses_enabled_index_hits(self):
        now = datetime.now()
        store = _FakeStore(
            [
                MemoryItem(1, "deploy status", "", "bash", 0.5, now),
                MemoryItem(2, "unrelated item", "", "bash", 0.5, now),
            ]
        )
        selector = ContextSelector(top_k=1, memory_index=_EnabledIndex())

        out = selector.select("deploy", store)
        self.assertIn("unrelated item", out)

    def test_token_index_returns_ranked_hits(self):
        now = datetime.now()
        items = [
            MemoryItem(1, "kernel onboarding and setup flow", "", "bash", 0.5, now),
            MemoryItem(2, "weather update and forecast", "", "web_fetch", 0.5, now),
            MemoryItem(3, "kernel setup and runtime integration", "", "file_write", 0.5, now),
        ]
        index = TokenEmbeddingMemoryIndex()
        index.rebuild(items)

        hits = index.query("kernel setup", limit=2)
        self.assertEqual(len(hits), 2)
        self.assertIn(hits[0].memory_id, (1, 3))
        self.assertIn(hits[1].memory_id, (1, 3))

    def test_build_memory_index_from_env_defaults_to_noop(self):
        with patch.dict("os.environ", {}, clear=True):
            index = build_memory_index_from_env()
        self.assertIsInstance(index, NoopMemoryIndex)

    def test_build_memory_index_from_env_token(self):
        with patch.dict("os.environ", {"AGENTOS_MEMORY_INDEX_BACKEND": "token"}, clear=True):
            index = build_memory_index_from_env()
        self.assertIsInstance(index, TokenEmbeddingMemoryIndex)

    def test_token_index_save_and_load_file(self):
        now = datetime.now()
        items = [
            MemoryItem(1, "kernel setup", "", "bash", 0.5, now),
            MemoryItem(2, "weather report", "", "web_fetch", 0.5, now),
        ]
        index = TokenEmbeddingMemoryIndex()
        index.rebuild(items)

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "index.json"
            index.save_to_file(p)
            loaded = TokenEmbeddingMemoryIndex.load_from_file(p)
            self.assertEqual(
                [h.memory_id for h in index.query("kernel", limit=2)],
                [h.memory_id for h in loaded.query("kernel", limit=2)],
            )


if __name__ == "__main__":
    unittest.main()

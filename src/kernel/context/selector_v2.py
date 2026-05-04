"""
Context selector v2 contract and compatibility bridge.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from kernel.memory.store import MemoryStore


def is_context_selector_v2_enabled() -> bool:
    raw = os.environ.get("AGENTOS_USE_CONTEXT_SELECTOR_V2", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class SelectorRequest:
    query: str
    top_k: int = 5


@dataclass(frozen=True)
class SelectorResult:
    context: str


class ContextSelectorV2(Protocol):
    def select(self, request: SelectorRequest, memory: MemoryStore) -> SelectorResult:
        ...


class LegacySelectorV2Bridge:
    """
    Wrap current selector implementation with the v2 contract.
    """

    def __init__(self, legacy_selector):
        self._legacy_selector = legacy_selector

    def select(self, request: SelectorRequest, memory: MemoryStore) -> SelectorResult:
        context = self._legacy_selector.select(request.query, memory)
        return SelectorResult(context=context)


class ContextSelectorV2CompatAdapter:
    """
    Exposes v2 selector behind current runtime `select(query, memory) -> str` API.
    """

    def __init__(self, selector_v2: ContextSelectorV2, top_k: int = 5):
        self._selector_v2 = selector_v2
        self._top_k = top_k

    def select(self, query: str, memory: MemoryStore) -> str:
        result = self._selector_v2.select(
            SelectorRequest(query=query, top_k=self._top_k),
            memory,
        )
        return result.context


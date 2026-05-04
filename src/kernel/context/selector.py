"""
ContextSelector — selects relevant memory items for a given query.

Phase 1: keyword Jaccard similarity (no embeddings needed)
Phase 3: replace _semantic() with embedding cosine similarity

Score = semantic(0.5) + recency(0.3) + importance(0.2)
"""
from __future__ import annotations

import math
from datetime import datetime

from kernel.memory.index import NoopMemoryIndex, MemoryIndex
from kernel.memory.store import MemoryItem, MemoryStore


class ContextSelector:
    def __init__(
        self,
        top_k: int = 5,
        embedder=None,
        memory_index: MemoryIndex | None = None,
    ):
        self._top_k = top_k
        self._embedder = embedder   # None → keyword fallback (Phase 1)
        self._memory_index = memory_index or NoopMemoryIndex()

    def select(self, query: str, memory: MemoryStore) -> str:
        """
        Return a string of relevant memory items to inject into the Planner prompt.
        Empty string if memory has nothing useful.
        """
        candidates = memory.recent(limit=100)
        if not candidates:
            return ""

        indexed_scores = self._query_index_scores(query, candidates)
        scored = [(self._score(query, item, indexed_scores), item) for item in candidates]
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [item for score, item in scored[:self._top_k] if score > 0.0]

        if not top:
            return ""

        parts = [f"- [{item.tool_name}] {item.summary}" for item in top]
        return "Recent relevant context:\n" + "\n".join(parts)

    # ──────────────────────────────────────────
    # Scoring components
    # ──────────────────────────────────────────

    def _score(self, query: str, item: MemoryItem, indexed_scores: dict[int, float]) -> float:
        return (
            self._semantic(query, item) * 0.5
            + self._recency(item)       * 0.3
            + item.importance           * 0.2
            + indexed_scores.get(item.id, 0.0) * 0.2
        )

    def _semantic(self, query: str, item: MemoryItem) -> float:
        if self._embedder is not None:
            # Phase 3: cosine similarity on embeddings
            return _cosine(
                self._embedder.embed(query),
                self._embedder.embed(item.summary),
            )
        # Phase 1 fallback: Jaccard on word sets
        q = set(query.lower().split())
        i = set(item.summary.lower().split())
        if not q or not i:
            return 0.0
        return len(q & i) / len(q | i)

    def _query_index_scores(self, query: str, candidates: list[MemoryItem]) -> dict[int, float]:
        if not self._memory_index.is_enabled():
            return {}
        self._memory_index.rebuild(candidates)
        candidate_ids = {item.id for item in candidates}
        hits = self._memory_index.query(query, limit=max(self._top_k * 3, 20))
        return {
            hit.memory_id: hit.score
            for hit in hits
            if hit.memory_id in candidate_ids and hit.score > 0
        }

    @staticmethod
    def _recency(item: MemoryItem) -> float:
        """Logarithmic time decay. 0h→1.0, 1h→0.5, 24h→0.17"""
        age_hours = (datetime.now() - item.created_at).total_seconds() / 3600
        return 1.0 / (1.0 + math.log1p(age_hours))


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0

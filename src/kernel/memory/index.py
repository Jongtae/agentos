"""
Memory index extension point (Phase 3 prep).

This module defines a retrieval contract that can later be backed by
embeddings/vector stores without changing runtime caller code.
"""
from __future__ import annotations

import math
import os
import re
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from kernel.memory.store import MemoryItem


@dataclass(frozen=True)
class MemoryIndexHit:
    memory_id: int
    score: float


class MemoryIndex(Protocol):
    @property
    def name(self) -> str:
        ...

    def is_enabled(self) -> bool:
        ...

    def rebuild(self, items: list[MemoryItem]) -> None:
        ...

    def query(self, text: str, limit: int = 20) -> list[MemoryIndexHit]:
        ...


class NoopMemoryIndex:
    """
    Default index implementation.
    Always disabled and returns no retrieval hits.
    """

    @property
    def name(self) -> str:
        return "noop"

    def is_enabled(self) -> bool:
        return False

    def rebuild(self, items: list[MemoryItem]) -> None:
        _ = items

    def query(self, text: str, limit: int = 20) -> list[MemoryIndexHit]:
        _ = text, limit
        return []


class TokenEmbeddingMemoryIndex:
    """
    Dependency-free embedding-like index using token frequency vectors + cosine.
    Enabled for Phase 4 productionization without external vector DB dependencies.
    """

    def __init__(self):
        self._vectors: dict[int, Counter[str]] = {}
        self._norms: dict[int, float] = {}

    @property
    def name(self) -> str:
        return "token_embedding"

    def is_enabled(self) -> bool:
        return True

    def rebuild(self, items: list[MemoryItem]) -> None:
        vectors: dict[int, Counter[str]] = {}
        norms: dict[int, float] = {}
        for item in items:
            vec = _token_vector(item.summary)
            vectors[item.id] = vec
            norms[item.id] = _norm(vec)
        self._vectors = vectors
        self._norms = norms

    def query(self, text: str, limit: int = 20) -> list[MemoryIndexHit]:
        qvec = _token_vector(text)
        qnorm = _norm(qvec)
        if not qvec or qnorm == 0:
            return []

        scored: list[MemoryIndexHit] = []
        for memory_id, vec in self._vectors.items():
            dnorm = self._norms.get(memory_id, 0.0)
            if dnorm == 0:
                continue
            score = _cosine(qvec, qnorm, vec, dnorm)
            if score > 0:
                scored.append(MemoryIndexHit(memory_id=memory_id, score=score))

        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:limit]

    def save_to_file(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "backend": self.name,
            "vectors": {
                str(memory_id): dict(vec)
                for memory_id, vec in self._vectors.items()
            },
        }
        target.write_text(json.dumps(payload, ensure_ascii=True))

    @classmethod
    def load_from_file(cls, path: str | Path):
        target = Path(path)
        data = json.loads(target.read_text())
        if data.get("backend") != "token_embedding":
            raise ValueError("unsupported backend payload")
        vectors_raw = data.get("vectors")
        if not isinstance(vectors_raw, dict):
            raise ValueError("vectors payload is required")

        idx = cls()
        vectors: dict[int, Counter[str]] = {}
        norms: dict[int, float] = {}
        for memory_id_raw, vec_raw in vectors_raw.items():
            memory_id = int(memory_id_raw)
            if not isinstance(vec_raw, dict):
                raise ValueError("invalid vector payload")
            vec = Counter({str(k): int(v) for k, v in vec_raw.items() if int(v) > 0})
            vectors[memory_id] = vec
            norms[memory_id] = _norm(vec)
        idx._vectors = vectors
        idx._norms = norms
        return idx


def build_memory_index_from_env():
    """
    Build memory index backend from environment config.
    Default is noop for backward compatibility.
    """
    backend = os.environ.get("AGENTOS_MEMORY_INDEX_BACKEND", "").strip().lower()
    if backend in ("token", "token_embedding", "local"):
        return TokenEmbeddingMemoryIndex()
    return NoopMemoryIndex()


def try_load_token_index(path: str | Path):
    try:
        return TokenEmbeddingMemoryIndex.load_from_file(path)
    except Exception:
        return None


def _token_vector(text: str) -> Counter[str]:
    words = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    return Counter(words)


def _norm(vec: Counter[str]) -> float:
    return math.sqrt(sum(v * v for v in vec.values()))


def _cosine(a: Counter[str], anorm: float, b: Counter[str], bnorm: float) -> float:
    dot = 0.0
    small, other = (a, b) if len(a) <= len(b) else (b, a)
    for token, val in small.items():
        dot += val * other.get(token, 0)
    return dot / (anorm * bnorm) if anorm and bnorm else 0.0

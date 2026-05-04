"""
Memory summarizer scaffold for Phase 3 message window compaction.
"""
from __future__ import annotations

import os
import re
from typing import Protocol


def is_memory_summarizer_enabled() -> bool:
    raw = os.environ.get("AGENTOS_USE_MEMORY_SUMMARIZER", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


class MemoryWindowSummarizer(Protocol):
    def is_enabled(self) -> bool:
        ...

    def compact_message_window(self, user_input: str, context: str, memory) -> str:
        ...


class NoopMemoryWindowSummarizer:
    def is_enabled(self) -> bool:
        return False

    def compact_message_window(self, user_input: str, context: str, memory) -> str:
        _ = user_input, memory
        return context


class ScaffoldMemoryWindowSummarizer:
    """
    Feature-flagged deterministic compaction implementation.
    Preserves critical lines while reducing context size.
    """

    _CRITICAL_PATTERNS = (
        r"\[error\]",
        r"\[blocked\]",
        r"\[aborted\]",
        r"important",
        r"security",
        r"risk",
    )

    def __init__(self, max_chars: int = 1200, max_lines: int = 8):
        self._max_chars = max_chars
        self._max_lines = max_lines

    def is_enabled(self) -> bool:
        return True

    def compact_message_window(self, user_input: str, context: str, memory) -> str:
        _ = user_input, memory
        if not context or len(context) <= self._max_chars:
            return context

        lines = [line.strip() for line in context.splitlines() if line.strip()]
        if not lines:
            return context

        header = lines[0]
        body = lines[1:] if len(lines) > 1 else []
        if not body:
            return context[: self._max_chars]

        critical_lines = [line for line in body if self._is_critical(line)]
        selected: list[str] = []

        for line in critical_lines:
            if line not in selected:
                selected.append(line)

        for line in body:
            if len(selected) >= self._max_lines:
                break
            if line not in selected:
                selected.append(line)

        compacted = header + "\n" + "\n".join(selected)
        if len(compacted) > self._max_chars:
            compacted = compacted[: self._max_chars - 15].rstrip() + "\n[truncated]"

        # Guardrail: if original had critical lines, ensure at least one survives.
        if critical_lines and not any(self._is_critical(line) for line in compacted.splitlines()):
            keep = critical_lines[0]
            compacted = f"{header}\n{keep}"
            if len(compacted) > self._max_chars:
                compacted = compacted[: self._max_chars]

        return compacted

    def metrics(self, original: str, compacted: str) -> dict:
        original_len = len(original)
        compacted_len = len(compacted)
        ratio = (compacted_len / original_len) if original_len else 1.0
        original_critical = [line for line in original.splitlines() if self._is_critical(line)]
        retained = sum(
            1 for line in original_critical
            if line in compacted
        )
        return {
            "original_chars": original_len,
            "compacted_chars": compacted_len,
            "compaction_ratio": round(ratio, 4),
            "critical_lines_original": len(original_critical),
            "critical_lines_retained": retained,
        }

    def _is_critical(self, line: str) -> bool:
        lowered = line.lower()
        return any(re.search(p, lowered) for p in self._CRITICAL_PATTERNS)

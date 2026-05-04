"""
MemoryStore — global, persistent memory backed by SQLite.
Completely separate from LangGraph's checkpoint mechanism.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class MemoryItem:
    id: int
    summary: str        # short text for context selection scoring
    detail: str         # full result content
    tool_name: str
    importance: float   # 0.0 ~ 1.0
    created_at: datetime


class MemoryStore:
    """
    SQLite-backed global memory.

    This is NOT LangGraph's SqliteSaver.
    This stores domain knowledge: execution results, facts, preferences.
    LangGraph's checkpoint stores graph node execution state — different things.
    """

    def __init__(self, db_path: str):
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ──────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    summary     TEXT    NOT NULL,
                    detail      TEXT    DEFAULT '',
                    tool_name   TEXT    DEFAULT '',
                    importance  REAL    DEFAULT 0.5,
                    created_at  TEXT    NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_created ON memory(created_at DESC)"
            )

    # ──────────────────────────────────────────
    # Write
    # ──────────────────────────────────────────

    def save_result(
        self,
        step,                   # kernel.planner.planner.Step
        result: str,
        importance: float = 0.5,
    ) -> None:
        summary = f"[{step.tool_name}] {step.description} → {result[:120]}"
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO memory (summary, detail, tool_name, importance, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (summary, result, step.tool_name, importance, datetime.now().isoformat()),
            )

    def save_fact(self, summary: str, detail: str = "", importance: float = 0.7) -> None:
        """Save an arbitrary fact (not tied to a tool step)."""
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO memory (summary, detail, tool_name, importance, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (summary, detail, "fact", importance, datetime.now().isoformat()),
            )

    # ──────────────────────────────────────────
    # Read
    # ──────────────────────────────────────────

    def recent(self, limit: int = 100) -> list[MemoryItem]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, summary, detail, tool_name, importance, created_at "
                "FROM memory ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_item(r) for r in rows]

    def search(self, query: str, limit: int = 20) -> list[MemoryItem]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, summary, detail, tool_name, importance, created_at "
                "FROM memory WHERE summary LIKE ? ORDER BY id DESC LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        return [_row_to_item(r) for r in rows]

    def count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]


def _row_to_item(row: sqlite3.Row) -> MemoryItem:
    return MemoryItem(
        id=row["id"],
        summary=row["summary"],
        detail=row["detail"],
        tool_name=row["tool_name"],
        importance=row["importance"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )

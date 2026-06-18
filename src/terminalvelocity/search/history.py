"""Query history store for TerminalVelocity."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(slots=True)
class QueryHistoryEntry:
    id: int
    query: str
    scope: str
    result_count: int
    executed_at: str


class QueryHistoryStore:
    """Persist and recall recently executed search queries."""

    def __init__(self, database_path: str | Path = ":memory:") -> None:
        self.connection = sqlite3.connect(str(database_path))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS query_history ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  query TEXT NOT NULL,"
            "  scope TEXT NOT NULL DEFAULT 'all',"
            "  result_count INTEGER NOT NULL DEFAULT 0,"
            "  executed_at TEXT NOT NULL"
            ")"
        )
        self.connection.commit()

    def record(self, query: str, scope: str, result_count: int) -> None:
        """Save a query execution. Empty queries are ignored."""
        if not query.strip():
            return
        now = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            "INSERT INTO query_history(query, scope, result_count, executed_at) VALUES (?, ?, ?, ?)",
            (query, scope, result_count, now),
        )
        self.connection.commit()

    def list(self, limit: int = 50) -> list[QueryHistoryEntry]:
        """Return recent queries, newest first."""
        rows = self.connection.execute(
            "SELECT id, query, scope, result_count, executed_at FROM query_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [QueryHistoryEntry(**dict(row)) for row in rows]

    def clear(self) -> None:
        self.connection.execute("DELETE FROM query_history")
        self.connection.commit()

    def close(self) -> None:
        # TODO(resource-management): close() exists but is never called in the
        # main application path (TerminalVelocityApp holds the store for its
        # lifetime and does not call close() on shutdown).  Either call close()
        # in the app's on_unmount hook or implement __enter__/__exit__ so the
        # store can be used as a context manager.
        self.connection.close()

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from terminalvelocity.search.parser import SearchQuery, parse_query


@dataclass(slots=True)
class SavedQuery:
    name: str
    query: str
    description: str | None
    created_at: str
    updated_at: str


class SavedQueryStore:
    """Persist, retrieve, and manage user-defined saved search queries."""

    def __init__(self, database_path: str | Path = ":memory:") -> None:
        self.connection = sqlite3.connect(str(database_path))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("CREATE TABLE IF NOT EXISTS saved_queries (name TEXT PRIMARY KEY, query TEXT NOT NULL, description TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> SavedQueryStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def save(self, name: str, query: str | SearchQuery, description: str | None = None) -> SavedQuery:
        text = query.raw_query if isinstance(query, SearchQuery) else query
        parse_query(text)
        now = datetime.now(UTC).isoformat()
        self.connection.execute("INSERT INTO saved_queries(name, query, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET query = excluded.query, description = excluded.description, updated_at = excluded.updated_at", (name, text, description, now, now))
        self.connection.commit()
        return self.get(name)

    def get(self, name: str) -> SavedQuery | None:
        row = self.connection.execute("SELECT name, query, description, created_at, updated_at FROM saved_queries WHERE name = ?", (name,)).fetchone()
        return SavedQuery(**dict(row)) if row else None

    def list(self) -> list[SavedQuery]:
        return [SavedQuery(**dict(row)) for row in self.connection.execute("SELECT name, query, description, created_at, updated_at FROM saved_queries ORDER BY name ASC").fetchall()]

    def delete(self, name: str) -> None:
        self.connection.execute("DELETE FROM saved_queries WHERE name = ?", (name,))
        self.connection.commit()

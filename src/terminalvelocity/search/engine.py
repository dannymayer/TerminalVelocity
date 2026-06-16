from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from terminalvelocity.models import NormalizedEvent
from terminalvelocity.search.filters import resolve_time_range
from terminalvelocity.search.parser import FIELD_NAMES, SearchQuery, parse_query

COLUMNS: Sequence[str] = ("event_id", "timestamp", "provider", "service", "tenant_id", "actor", "action", "target", "result", "severity", "correlation_id", "request_id", "raw_json")


class SearchEngine:
    def __init__(self, database_path: str | Path = ":memory:") -> None:
        self.connection = sqlite3.connect(str(database_path))
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                provider TEXT,
                service TEXT,
                tenant_id TEXT,
                actor TEXT,
                action TEXT,
                target TEXT,
                result TEXT,
                severity TEXT,
                correlation_id TEXT,
                request_id TEXT,
                raw_json TEXT NOT NULL,
                indexed_at TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(event_id UNINDEXED, search_text, tokenize='unicode61');
            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def index_events(self, events: Iterable[NormalizedEvent]) -> int:
        indexed_at = datetime.now(timezone.utc).isoformat()
        count = 0
        for event in events:
            event_id = event.stable_id()
            self.connection.execute("DELETE FROM events_fts WHERE event_id = ?", (event_id,))
            self.connection.execute(
                "INSERT OR REPLACE INTO events (event_id, timestamp, provider, service, tenant_id, actor, action, target, result, severity, correlation_id, request_id, raw_json, indexed_at, archived) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (event_id, event.timestamp.isoformat(), event.provider, event.service, event.tenant_id, event.actor, event.action, event.target, event.result, event.severity, event.correlation_id, event.request_id, event.raw_json(), indexed_at),
            )
            self.connection.execute("INSERT INTO events_fts(event_id, search_text) VALUES (?, ?)", (event_id, self._build_search_text(event)))
            count += 1
        self.connection.commit()
        return count

    def delete_events(self, event_ids: Iterable[str]) -> None:
        ids = list(event_ids)
        if not ids:
            return
        placeholders = ", ".join("?" for _ in ids)
        self.connection.execute(f"DELETE FROM events WHERE event_id IN ({placeholders})", ids)
        self.connection.execute(f"DELETE FROM events_fts WHERE event_id IN ({placeholders})", ids)
        self.connection.commit()

    def search(self, query: SearchQuery | str, *, limit: int = 100, include_archived: bool = False) -> list[NormalizedEvent]:
        if isinstance(query, str):
            query = parse_query(query)
        base = "FROM events e"
        where: list[str] = []
        params: list[object] = []
        if query.free_text:
            base += " JOIN events_fts f ON e.event_id = f.event_id"
            where.append("f.search_text MATCH ?")
            params.append(_fts_query(query.free_text))
        if not include_archived:
            where.append("e.archived = 0")
        since, until = resolve_time_range(query)
        if since:
            where.append("e.timestamp >= ?")
            params.append(since.isoformat())
        if until:
            where.append("e.timestamp <= ?")
            params.append(until.isoformat())
        for field_filter in query.field_filters:
            if field_filter.field not in FIELD_NAMES:
                raise ValueError(f"Unsupported filter field: {field_filter.field}")
            where.append(f"LOWER(COALESCE(e.{field_filter.field}, '')) = ?")
            params.append(field_filter.value.casefold())
        sql = f"SELECT {', '.join(f'e.{column}' for column in COLUMNS)} {base}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        order = "LOWER(COALESCE(e.provider, ''))" if query.sort_by == "provider" else ("CASE LOWER(COALESCE(e.severity, '')) WHEN 'critical' THEN 5 WHEN 'high' THEN 4 WHEN 'medium' THEN 3 WHEN 'warning' THEN 2 WHEN 'low' THEN 1 WHEN 'informational' THEN 0 WHEN 'info' THEN 0 ELSE -1 END" if query.sort_by == "severity" else "e.timestamp")
        sql += f" ORDER BY {order} {'DESC' if query.sort_desc else 'ASC'}, e.timestamp DESC LIMIT ?"
        rows = self.connection.execute(sql, [*params, limit]).fetchall()
        return [NormalizedEvent(timestamp=row['timestamp'], provider=row['provider'], service=row['service'], tenant_id=row['tenant_id'], actor=row['actor'], action=row['action'], target=row['target'], result=row['result'], severity=row['severity'], correlation_id=row['correlation_id'], request_id=row['request_id'], raw=json.loads(row['raw_json'])) for row in rows]

    @staticmethod
    def _build_search_text(event: NormalizedEvent) -> str:
        return " ".join(part for part in [event.provider, event.service, event.tenant_id, event.actor, event.action, event.target, event.result, event.severity, event.correlation_id, event.request_id, event.raw_json()] if part)


def _fts_query(terms: Sequence[str]) -> str:
    return " AND ".join(f'"{term.replace("\"", "\"\"")}"' for term in terms)

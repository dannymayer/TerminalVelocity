from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from terminalvelocity.models import NormalizedEvent
from terminalvelocity.search.engine import SearchEngine
from terminalvelocity.search.filters import resolve_time_range
from terminalvelocity.search.parser import FIELD_NAMES, SearchQuery, parse_query


class IndexManager:
    def __init__(self, database_path: str | Path = ":memory:", archive_dir: str | Path = "archives", hot_window: timedelta = timedelta(days=1)) -> None:
        self.engine = SearchEngine(database_path)
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.hot_window = hot_window
        self.engine.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS ingestion_state (provider TEXT PRIMARY KEY, checkpoint TEXT, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS archives (archive_id TEXT PRIMARY KEY, path TEXT NOT NULL, created_at TEXT NOT NULL, event_count INTEGER NOT NULL, min_timestamp TEXT, max_timestamp TEXT);
            CREATE TABLE IF NOT EXISTS archived_event_metadata (event_id TEXT PRIMARY KEY, archive_id TEXT NOT NULL, timestamp TEXT NOT NULL, provider TEXT, service TEXT, tenant_id TEXT, actor TEXT, action TEXT, target TEXT, result TEXT, severity TEXT, correlation_id TEXT, request_id TEXT, FOREIGN KEY(archive_id) REFERENCES archives(archive_id));
            """
        )
        self.engine.connection.commit()

    def ingest(self, events: Iterable[NormalizedEvent], provider: str | None = None) -> int:
        event_list = list(events)
        count = self.engine.index_events(event_list)
        if provider and event_list:
            self.update_checkpoint(provider, max(event.timestamp for event in event_list).isoformat())
        self.archive_expired_events()
        return count

    def update_checkpoint(self, provider: str, checkpoint: str) -> None:
        self.engine.connection.execute("INSERT INTO ingestion_state(provider, checkpoint, updated_at) VALUES (?, ?, ?) ON CONFLICT(provider) DO UPDATE SET checkpoint = excluded.checkpoint, updated_at = excluded.updated_at", (provider, checkpoint, datetime.now(timezone.utc).isoformat()))
        self.engine.connection.commit()

    def get_checkpoint(self, provider: str) -> str | None:
        row = self.engine.connection.execute("SELECT checkpoint FROM ingestion_state WHERE provider = ?", (provider,)).fetchone()
        return row[0] if row else None

    def archive_expired_events(self, now: datetime | None = None) -> str | None:
        now = now or datetime.now(timezone.utc)
        cutoff = now - self.hot_window
        rows = self.engine.connection.execute("SELECT * FROM events WHERE archived = 0 AND timestamp < ? ORDER BY timestamp ASC", (cutoff.isoformat(),)).fetchall()
        if not rows:
            return None
        archive_id = f"archive-{now.strftime('%Y%m%d%H%M%S')}"
        archive_path = self.archive_dir / f"{archive_id}.jsonl.gz"
        with gzip.open(archive_path, "wt", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(dict(row), sort_keys=True) + "\n")
        self.engine.connection.execute("INSERT INTO archives(archive_id, path, created_at, event_count, min_timestamp, max_timestamp) VALUES (?, ?, ?, ?, ?, ?)", (archive_id, str(archive_path), now.isoformat(), len(rows), rows[0]["timestamp"], rows[-1]["timestamp"]))
        self.engine.connection.executemany("INSERT OR REPLACE INTO archived_event_metadata(event_id, archive_id, timestamp, provider, service, tenant_id, actor, action, target, result, severity, correlation_id, request_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [(row["event_id"], archive_id, row["timestamp"], row["provider"], row["service"], row["tenant_id"], row["actor"], row["action"], row["target"], row["result"], row["severity"], row["correlation_id"], row["request_id"]) for row in rows])
        self.engine.delete_events([row["event_id"] for row in rows])
        self.engine.connection.commit()
        return str(archive_path)

    def search_hot(self, query: SearchQuery | str, limit: int = 100):
        return self.engine.search(query, limit=limit)

    def search_archived_metadata(self, query: SearchQuery | str, limit: int = 100) -> list[dict[str, str | None]]:
        if isinstance(query, str):
            query = parse_query(query)
        where: list[str] = []
        params: list[object] = []
        since, until = resolve_time_range(query)
        if since:
            where.append("timestamp >= ?")
            params.append(since.isoformat())
        if until:
            where.append("timestamp <= ?")
            params.append(until.isoformat())
        for field_filter in query.field_filters:
            if field_filter.field not in FIELD_NAMES:
                raise ValueError(f"Unsupported filter field: {field_filter.field}")
            where.append(f"LOWER(COALESCE({field_filter.field}, '')) = ?")
            params.append(field_filter.value.casefold())
        sql = "SELECT * FROM archived_event_metadata"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        rows = self.engine.connection.execute(sql, [*params, limit]).fetchall()
        return [dict(row) for row in rows]

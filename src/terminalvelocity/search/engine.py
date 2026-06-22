from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from terminalvelocity.models import NormalizedEvent
from terminalvelocity.search.filters import resolve_time_range
from terminalvelocity.search.parser import FIELD_NAMES, SearchQuery, parse_query

COLUMNS: Sequence[str] = (
    "event_id",
    "timestamp",
    "provider",
    "service",
    "tenant_id",
    "actor",
    "action",
    "target",
    "result",
    "severity",
    "correlation_id",
    "request_id",
    "raw_json",
)


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
            CREATE TABLE IF NOT EXISTS event_tags (
                event_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (event_id, tag)
            );
            CREATE INDEX IF NOT EXISTS idx_event_tags_tag ON event_tags(tag);
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> SearchEngine:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def index_events(self, events: Iterable[NormalizedEvent]) -> int:
        indexed_at = datetime.now(UTC).isoformat()
        count = 0
        with self.connection:
            for event in events:
                event_id = event.stable_id()
                self.connection.execute("DELETE FROM events_fts WHERE event_id = ?", (event_id,))
                self.connection.execute(
                    "INSERT OR REPLACE INTO events (event_id, timestamp, provider, service, tenant_id, actor, action, target, result, severity, correlation_id, request_id, raw_json, indexed_at, archived) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                    (
                        event_id,
                        event.timestamp.isoformat(),
                        event.provider,
                        event.service,
                        event.tenant_id,
                        event.actor,
                        event.action,
                        event.target,
                        event.result,
                        event.severity,
                        event.correlation_id,
                        event.request_id,
                        event.raw_json(),
                        indexed_at,
                    ),
                )
                self.connection.execute(
                    "INSERT INTO events_fts(event_id, search_text) VALUES (?, ?)",
                    (event_id, self._build_search_text(event)),
                )
                count += 1
        return count

    def delete_events(self, event_ids: Iterable[str]) -> None:
        ids = list(event_ids)
        if not ids:
            return
        placeholders = ", ".join("?" for _ in ids)
        self.connection.execute(f"DELETE FROM events WHERE event_id IN ({placeholders})", ids)
        self.connection.execute(f"DELETE FROM events_fts WHERE event_id IN ({placeholders})", ids)
        self.connection.commit()

    def archive_old_events(self, cutoff_hours: int = 168) -> int:
        """Mark events older than *cutoff_hours* as archived. Returns the count archived."""
        cutoff = (datetime.now(UTC) - timedelta(hours=cutoff_hours)).isoformat()
        cursor = self.connection.execute(
            "UPDATE events SET archived = 1 WHERE archived = 0 AND timestamp < ?",
            (cutoff,),
        )
        self.connection.commit()
        return cursor.rowcount

    def tag_event(self, event_id: str, tag: str) -> None:
        """Attach a tag label to an event."""
        now = datetime.now(UTC).isoformat()
        self.connection.execute(
            "INSERT OR IGNORE INTO event_tags(event_id, tag, created_at) VALUES (?, ?, ?)",
            (event_id, tag.lower().strip(), now),
        )
        self.connection.commit()

    def untag_event(self, event_id: str, tag: str) -> None:
        """Remove a tag label from an event."""
        self.connection.execute(
            "DELETE FROM event_tags WHERE event_id = ? AND tag = ?",
            (event_id, tag.lower().strip()),
        )
        self.connection.commit()

    def get_event_tags(self, event_id: str) -> list[str]:
        """Return all tags for an event, sorted alphabetically."""
        rows = self.connection.execute(
            "SELECT tag FROM event_tags WHERE event_id = ? ORDER BY tag ASC",
            (event_id,),
        ).fetchall()
        return [row["tag"] for row in rows]

    def list_tags(self) -> list[str]:
        """Return all distinct tags in use, sorted alphabetically."""
        rows = self.connection.execute("SELECT DISTINCT tag FROM event_tags ORDER BY tag ASC").fetchall()
        return [row["tag"] for row in rows]

    def search(
        self, query: SearchQuery | str, *, limit: int = 100, include_archived: bool = False
    ) -> list[NormalizedEvent]:
        if isinstance(query, str):
            query = parse_query(query)
        # Respect include_archived from the query object OR the parameter
        show_archived = include_archived or query.include_archived
        base = "FROM events e"
        where: list[str] = []
        params: list[object] = []
        if query.free_text:
            base += " JOIN events_fts f ON e.event_id = f.event_id"
            where.append("f.search_text MATCH ?")
            params.append(_fts_query(query.free_text))
        if query.tags:
            for tag in query.tags:
                base += " JOIN event_tags t{i} ON e.event_id = t{i}.event_id".format(i=len(params))
                where.append(f"t{len(params)}.tag = ?")
                params.append(tag.lower().strip())
        if not show_archived:
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
        # TODO(readability): extract the ORDER BY expression building into a
        # dedicated helper method.  The current single-line ternary chain is
        # hard to follow and extend (e.g. adding a new sort key requires
        # modifying a deeply nested expression).
        order = (
            "LOWER(COALESCE(e.provider, ''))"
            if query.sort_by == "provider"
            else (
                "CASE LOWER(COALESCE(e.severity, '')) WHEN 'critical' THEN 5 WHEN 'high' THEN 4 WHEN 'medium' THEN 3 WHEN 'warning' THEN 2 WHEN 'low' THEN 1 WHEN 'informational' THEN 0 WHEN 'info' THEN 0 ELSE -1 END"
                if query.sort_by == "severity"
                else "e.timestamp"
            )
        )
        sql += f" ORDER BY {order} {'DESC' if query.sort_desc else 'ASC'}, e.timestamp DESC LIMIT ?"
        rows = self.connection.execute(sql, [*params, limit]).fetchall()
        # TODO(readability): expand the row-to-NormalizedEvent mapping into a
        # named helper (e.g. _row_to_event) so this line is not 180+ chars and
        # is easier to maintain when the schema changes.
        return [
            NormalizedEvent(
                timestamp=row["timestamp"],
                provider=row["provider"],
                service=row["service"],
                tenant_id=row["tenant_id"],
                actor=row["actor"],
                action=row["action"],
                target=row["target"],
                result=row["result"],
                severity=row["severity"],
                correlation_id=row["correlation_id"],
                request_id=row["request_id"],
                raw=json.loads(row["raw_json"]),
            )
            for row in rows
        ]

    @staticmethod
    def _build_search_text(event: NormalizedEvent) -> str:
        # TODO(readability): extract to a named helper that lists each field
        # explicitly instead of relying on a long positional tuple — easier to
        # extend when the schema gains new searchable fields.
        return " ".join(
            part
            for part in [
                event.provider,
                event.service,
                event.tenant_id,
                event.actor,
                event.action,
                event.target,
                event.result,
                event.severity,
                event.correlation_id,
                event.request_id,
                event.raw_json(),
            ]
            if part
        )


def _fts_query(terms: Sequence[str]) -> str:
    return " AND ".join(f'"{term.replace('"', '""')}"' for term in terms)

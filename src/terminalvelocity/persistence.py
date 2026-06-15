"""SQLite persistence for provider checkpoints and raw event cache."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schema import NormalizedEvent


@dataclass(slots=True, frozen=True)
class CachedEventRecord:
    """Cached raw event row read back from SQLite."""

    event_id: str
    event: NormalizedEvent
    raw: dict[str, Any]
    inserted_at: datetime


class PersistenceStore:
    """Manage durable checkpoints and an optional raw-event cache."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.db_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._initialize_schema()

    def close(self) -> None:
        """Close the SQLite connection."""
        self._connection.close()

    def __enter__(self) -> "PersistenceStore":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _initialize_schema(self) -> None:
        """Create Phase 0 persistence tables if they do not exist yet."""
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                provider TEXT NOT NULL,
                service TEXT NOT NULL,
                checkpoint TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (provider, service)
            );

            CREATE TABLE IF NOT EXISTS raw_event_cache (
                event_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                service TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                correlation_id TEXT,
                request_id TEXT,
                normalized_json TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                inserted_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_raw_event_cache_provider_service_time
                ON raw_event_cache (provider, service, timestamp DESC);
            """
        )
        self._connection.commit()

    def get_checkpoint(self, provider: str, service: str) -> str | None:
        """Return the last stored checkpoint for a provider/service pair."""
        row = self._connection.execute(
            "SELECT checkpoint FROM checkpoints WHERE provider = ? AND service = ?",
            (provider, service),
        ).fetchone()
        if row is None:
            return None
        return str(row["checkpoint"]) if row["checkpoint"] is not None else None

    def set_checkpoint(
        self,
        provider: str,
        service: str,
        checkpoint: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Upsert a provider/service checkpoint with optional metadata."""
        timestamp = datetime.now(timezone.utc).isoformat()
        metadata_json = json.dumps(metadata or {}, sort_keys=True)
        self._connection.execute(
            """
            INSERT INTO checkpoints (provider, service, checkpoint, metadata_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(provider, service) DO UPDATE SET
                checkpoint = excluded.checkpoint,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (provider, service, checkpoint, metadata_json, timestamp),
        )
        self._connection.commit()

    def cache_event(self, event: NormalizedEvent, raw_event: dict[str, Any] | None = None) -> str:
        """Persist a raw event and its normalized projection for replay/debugging."""
        event_id = event.cache_key()
        inserted_at = datetime.now(timezone.utc).isoformat()
        payload = raw_event or event.raw
        self._connection.execute(
            """
            INSERT OR REPLACE INTO raw_event_cache (
                event_id,
                provider,
                service,
                tenant_id,
                timestamp,
                correlation_id,
                request_id,
                normalized_json,
                raw_json,
                inserted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event.provider,
                event.service,
                event.tenant_id,
                event.timestamp.isoformat(),
                event.correlation_id,
                event.request_id,
                event.model_dump_json(),
                json.dumps(payload, sort_keys=True, default=str),
                inserted_at,
            ),
        )
        self._connection.commit()
        return event_id

    def fetch_cached_events(
        self,
        *,
        provider: str | None = None,
        service: str | None = None,
        limit: int = 100,
    ) -> list[CachedEventRecord]:
        """Return cached events, optionally filtered by provider or service."""
        clauses: list[str] = []
        parameters: list[Any] = []
        if provider is not None:
            clauses.append("provider = ?")
            parameters.append(provider)
        if service is not None:
            clauses.append("service = ?")
            parameters.append(service)

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = (
            "SELECT event_id, normalized_json, raw_json, inserted_at "
            f"FROM raw_event_cache {where_clause} ORDER BY timestamp DESC LIMIT ?"
        )
        parameters.append(limit)
        rows = self._connection.execute(query, parameters).fetchall()
        return [
            CachedEventRecord(
                event_id=str(row["event_id"]),
                event=NormalizedEvent.model_validate_json(row["normalized_json"]),
                raw=json.loads(row["raw_json"]),
                inserted_at=datetime.fromisoformat(row["inserted_at"]),
            )
            for row in rows
        ]

    def purge_cache(self, older_than: datetime) -> int:
        """Delete cached rows older than the supplied UTC timestamp."""
        cutoff = older_than.astimezone(timezone.utc).isoformat()
        cursor = self._connection.execute(
            "DELETE FROM raw_event_cache WHERE timestamp < ?",
            (cutoff,),
        )
        self._connection.commit()
        return int(cursor.rowcount)

    def trim_cache(self, max_events: int) -> int:
        """Keep only the newest max_events rows in the raw event cache."""
        cursor = self._connection.execute(
            """
            DELETE FROM raw_event_cache
            WHERE event_id IN (
                SELECT event_id
                FROM raw_event_cache
                ORDER BY timestamp DESC
                LIMIT -1 OFFSET ?
            )
            """,
            (max_events,),
        )
        self._connection.commit()
        return int(cursor.rowcount)

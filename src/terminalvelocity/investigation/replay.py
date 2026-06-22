from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from terminalvelocity.models import NormalizedEvent


@dataclass(slots=True)
class RecordedEvent:
    """An event captured with a replay offset."""

    offset_seconds: float
    event: NormalizedEvent


@dataclass(slots=True)
class IngestionSession:
    """A recorded ingestion session that can be serialized and replayed."""

    session_id: str
    started_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    events: list[RecordedEvent] = field(default_factory=list)
    ended_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the session into a JSON-serializable dictionary."""

        return {
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "metadata": self.metadata,
            "events": [
                {
                    "offset_seconds": item.offset_seconds,
                    "event": item.event.model_dump(mode="json"),
                }
                for item in self.events
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> IngestionSession:
        """Reconstruct a session from serialized data."""

        return cls(
            session_id=payload["session_id"],
            started_at=_parse_datetime(payload["started_at"]),
            ended_at=_parse_datetime(payload["ended_at"]) if payload.get("ended_at") else None,
            metadata=dict(payload.get("metadata", {})),
            events=[
                RecordedEvent(
                    offset_seconds=float(item["offset_seconds"]),
                    event=NormalizedEvent.model_validate(item["event"]),
                )
                for item in payload.get("events", [])
            ],
        )


@dataclass(slots=True)
class ReplayFrame:
    """A replayable frame that includes the schedule offset."""

    scheduled_at: datetime
    delay: timedelta
    event: NormalizedEvent


class SessionRecorder:
    """Record ingestion sessions for later replay and debugging."""

    def start_session(
        self,
        *,
        session_id: str | None = None,
        started_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> IngestionSession:
        """Create a new empty ingestion session."""

        return IngestionSession(
            session_id=session_id or str(uuid4()),
            started_at=started_at or datetime.now(UTC),
            metadata=dict(metadata or {}),
        )

    def record_event(
        self,
        session: IngestionSession,
        event: NormalizedEvent,
        *,
        observed_at: datetime | None = None,
    ) -> RecordedEvent:
        """Append an event to a session using an observation timestamp."""

        observed_time = observed_at or event.timestamp
        offset = max((observed_time - session.started_at).total_seconds(), 0.0)
        recorded = RecordedEvent(offset_seconds=offset, event=event)
        session.events.append(recorded)
        return recorded

    def finalize(self, session: IngestionSession, *, ended_at: datetime | None = None) -> IngestionSession:
        """Mark a session as completed."""

        session.ended_at = ended_at or datetime.now(UTC)
        return session

    def save(self, session: IngestionSession, destination: str | Path) -> Path:
        """Persist a session as JSON."""

        destination_path = Path(destination)
        destination_path.write_text(json.dumps(session.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return destination_path

    def load(self, source: str | Path) -> IngestionSession:
        """Load a previously recorded session."""

        return IngestionSession.from_dict(json.loads(Path(source).read_text(encoding="utf-8")))


class SessionReplayer:
    """Replay recorded sessions in timestamp order."""

    def replay(self, session: IngestionSession, *, speed: float = 1.0) -> list[ReplayFrame]:
        """Return scheduled replay frames for a session."""

        if speed <= 0:
            raise ValueError("speed must be greater than zero")
        frames: list[ReplayFrame] = []
        previous_offset = 0.0
        for item in sorted(session.events, key=lambda recorded: recorded.offset_seconds):
            scheduled_at = session.started_at + timedelta(seconds=item.offset_seconds / speed)
            delay = timedelta(seconds=(item.offset_seconds - previous_offset) / speed)
            frames.append(ReplayFrame(scheduled_at=scheduled_at, delay=delay, event=item.event))
            previous_offset = item.offset_seconds
        return frames

    def iter_events(self, session: IngestionSession, *, speed: float = 1.0) -> Iterable[NormalizedEvent]:
        """Yield replayed events in order."""

        for frame in self.replay(session, speed=speed):
            yield frame.event


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)

"""Minimal schema stubs for the self-contained Phase 1 TUI review branch."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
import json


@dataclass(slots=True, frozen=True)
class NormalizedEvent:
    """Common event shape used by the Phase 1 TUI mock workflow."""

    timestamp: datetime
    provider: str
    service: str
    actor: str
    action: str
    target: str
    result: str
    severity: str
    correlation_id: str
    request_id: str
    raw: dict[str, Any]

    def __post_init__(self) -> None:
        timestamp = self.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        else:
            timestamp = timestamp.astimezone(UTC)
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "result", self.result.lower())
        object.__setattr__(self, "severity", self.severity.lower())

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["timestamp"] = self.timestamp.isoformat()
        return record

    def normalized_json(self) -> str:
        return json.dumps(self.to_record(), indent=2, sort_keys=True)

    def raw_json(self) -> str:
        return json.dumps(self.raw, indent=2, sort_keys=True, default=str)

    def searchable_text(self) -> str:
        raw_blob = json.dumps(self.raw, sort_keys=True, default=str)
        fields = [
            self.timestamp.isoformat(),
            self.provider,
            self.service,
            self.actor,
            self.action,
            self.target,
            self.result,
            self.severity,
            self.correlation_id,
            self.request_id,
            raw_blob,
        ]
        return " ".join(fields).lower()


@dataclass(slots=True, frozen=True)
class ProviderStatus:
    """Small provider status model for the Phase 1 TUI sidebar."""

    provider: str
    service: str
    state: str
    lag_seconds: int
    error_count: int
    enabled: bool
    total_events: int

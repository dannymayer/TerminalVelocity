<<<<<<< HEAD
"""Schema stubs included so the Phase 1 search branch is reviewable on its own."""
=======
"""Shared schema models for TerminalVelocity providers."""
>>>>>>> origin/main

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NormalizedEvent(BaseModel):
    """Cross-provider event structure used by search and correlation features."""

    model_config = ConfigDict(extra="allow")

    timestamp: datetime
    provider: str
    service: str
    tenant_id: str | None = None
    actor: str | None = None
    action: str
    target: str | None = None
    result: Literal["success", "failure"] | str | None = None
    severity: str | None = None
    correlation_id: str | None = None
    request_id: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _normalize_timestamp(cls, value: datetime | str) -> datetime:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @field_validator("result", mode="before")
    @classmethod
    def _normalize_result(cls, value: str | None) -> str | None:
        return value.lower() if isinstance(value, str) else value

<<<<<<< HEAD
    def raw_json(self) -> str:
        return json.dumps(self.raw, sort_keys=True, default=str)

=======
    @field_validator("severity", mode="before")
    @classmethod
    def _normalize_severity(cls, value: str | None) -> str | None:
        return value.lower() if isinstance(value, str) else value

    def to_record(self) -> dict[str, Any]:
        record = self.model_dump(mode="json")
        record["timestamp"] = self.timestamp.isoformat()
        return record

    def normalized_json(self) -> str:
        return json.dumps(self.to_record(), indent=2, sort_keys=True)

    def raw_json(self) -> str:
        return json.dumps(self.raw, sort_keys=True, default=str)

    def searchable_text(self) -> str:
        raw_blob = json.dumps(self.raw, sort_keys=True, default=str)
        fields = [
            self.timestamp.isoformat(),
            self.provider,
            self.service,
            self.actor or "",
            self.action,
            self.target or "",
            self.result or "",
            self.severity or "",
            self.correlation_id or "",
            self.request_id or "",
            raw_blob,
        ]
        return " ".join(fields).lower()

>>>>>>> origin/main
    def stable_id(self) -> str:
        payload = {
            "timestamp": self.timestamp.isoformat(),
            "provider": self.provider,
            "service": self.service,
            "tenant_id": self.tenant_id,
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "result": self.result,
            "severity": self.severity,
            "correlation_id": self.correlation_id,
            "request_id": self.request_id,
            "raw": self.raw,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def cache_key(self) -> str:
        return self.stable_id()


<<<<<<< HEAD
class ProviderCheckpoint(BaseModel):
    """Minimal checkpoint schema kept for review branch compatibility."""
=======
class ProviderStatus(BaseModel):
    """Small provider status model for the Phase 1 TUI sidebar."""

    provider: str
    service: str
    state: str
    lag_seconds: int
    error_count: int
    enabled: bool
    total_events: int


class ProviderCheckpoint(BaseModel):
    """Tracks polling state for a provider."""
>>>>>>> origin/main

    provider: str
    cursor: str | None = None
    last_event_time: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

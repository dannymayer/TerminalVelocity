"""Shared schema models for TerminalVelocity providers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NormalizedEvent(BaseModel):
    timestamp: datetime
    provider: str
    service: str
    tenant_id: str | None = None
    actor: str | None = None
    action: str
    target: str | None = None
    result: str | None = None
    severity: str | None = None
    correlation_id: str | None = None
    request_id: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ProviderCheckpoint(BaseModel):
    provider: str
    cursor: str | None = None
    last_event_time: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

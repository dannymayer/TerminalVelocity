"""Normalized event schema shared by all TerminalVelocity providers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ActorType(StrEnum):
    """Supported actor identities for normalized events."""

    USER = "user"
    APPLICATION = "application"
    SERVICE_PRINCIPAL = "service_principal"
    SERVICE = "service"
    UNKNOWN = "unknown"


class ResultType(StrEnum):
    """Common success/failure states across providers."""

    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    """Shared severity vocabulary for normalized events."""

    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Actor(BaseModel):
    """Identity that initiated the normalized event."""

    model_config = ConfigDict(extra="forbid")

    type: ActorType = ActorType.UNKNOWN
    id: str | None = None
    display_name: str | None = None
    user_principal_name: str | None = None
    app_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Target(BaseModel):
    """Resource or object acted upon by the event."""

    model_config = ConfigDict(extra="forbid")

    type: str | None = None
    id: str | None = None
    display_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedEvent(BaseModel):
    """Canonical event shape consumed by the TUI and persistence layers."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    provider: str
    service: str
    tenant_id: str
    actor: Actor | None = None
    action: str
    target: Target | None = None
    result: ResultType = ResultType.UNKNOWN
    severity: Severity | None = None
    correlation_id: str | None = None
    request_id: str | None = None
    raw: dict[str, Any]

    @field_validator("timestamp")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        """Ensure persisted timestamps are always timezone-aware."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @field_validator("provider", "service", "tenant_id", "action")
    @classmethod
    def require_text(cls, value: str) -> str:
        """Reject blank text for core event fields."""
        normalized = value.strip()
        if not normalized:
            msg = "Core event fields cannot be blank."
            raise ValueError(msg)
        return normalized

    def cache_key(self) -> str:
        """Return a stable cache key derived from normalized and raw payload data."""
        payload = {
            "timestamp": self.timestamp.isoformat(),
            "provider": self.provider,
            "service": self.service,
            "tenant_id": self.tenant_id,
            "correlation_id": self.correlation_id,
            "request_id": self.request_id,
            "action": self.action,
            "raw": self.raw,
        }
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return sha256(encoded).hexdigest()

    @classmethod
    def from_raw(cls, payload: Mapping[str, Any]) -> "NormalizedEvent":
        """Validate a provider-produced event mapping."""
        return cls.model_validate(dict(payload))

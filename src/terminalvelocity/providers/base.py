"""Abstract provider interfaces for Microsoft 365 log adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from terminalvelocity.schema import NormalizedEvent

RawEvent = Mapping[str, Any]


class ProviderError(RuntimeError):
    """Raised when a provider fails to connect, fetch, or normalize events."""


@dataclass(slots=True)
class FetchRequest:
    """Windowed fetch request passed to provider adapters."""

    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = 500
    checkpoint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Provider(ABC):
    """Contract that every log provider adapter must implement."""

    provider: str
    service: str

    def __init__(self, *, tenant_id: str, settings: Mapping[str, Any] | None = None) -> None:
        self.tenant_id = tenant_id
        self.settings = dict(settings or {})

    @abstractmethod
    def connect(self) -> None:
        """Establish connectivity or initialize tokens before fetching events."""

    @abstractmethod
    def fetch(self, request: FetchRequest) -> Iterable[RawEvent]:
        """Return raw provider events for the supplied window or checkpoint."""

    @abstractmethod
    def normalize(self, event: RawEvent) -> NormalizedEvent:
        """Map a provider-specific event into the normalized event schema."""

    @abstractmethod
    def checkpoint(self, event: RawEvent) -> str | None:
        """Return a durable checkpoint value for the supplied raw event."""

    def fetch_normalized(self, request: FetchRequest) -> list[NormalizedEvent]:
        """Fetch and normalize a provider batch with shared plumbing."""
        return [self.normalize(event) for event in self.fetch(request)]

"""Ingestion metrics and lag tracking utilities."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class ProviderMetrics:
    """Mutable counters for a single provider ingestion stream."""

    fetched_events: int = 0
    normalized_events: int = 0
    error_count: int = 0
    retry_count: int = 0
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error_message: str | None = None
    latest_event_timestamp: datetime | None = None

    def record_fetch(self, count: int) -> None:
        self.fetched_events += count
        self.last_success_at = datetime.now(UTC)

    def record_normalized(self, count: int = 1, *, latest_event_timestamp: datetime | None = None) -> None:
        self.normalized_events += count
        self.last_success_at = datetime.now(UTC)
        if latest_event_timestamp is not None and (
            self.latest_event_timestamp is None or latest_event_timestamp >= self.latest_event_timestamp
        ):
            self.latest_event_timestamp = latest_event_timestamp

    def record_error(self, message: str) -> None:
        self.error_count += 1
        self.last_error_at = datetime.now(UTC)
        self.last_error_message = message

    def record_retry(self, attempts: int = 1) -> None:
        self.retry_count += attempts

    def lag_seconds(self, *, now: datetime | None = None) -> float | None:
        if self.latest_event_timestamp is None:
            return None
        reference = now or datetime.now(UTC)
        return max(0.0, (reference - self.latest_event_timestamp).total_seconds())

    def error_rate(self) -> float:
        total = self.normalized_events + self.error_count
        if total == 0:
            return 0.0
        return self.error_count / total


@dataclass(slots=True)
class IngestionMetrics:
    """Registry of provider ingestion metrics."""

    providers: dict[str, ProviderMetrics] = field(default_factory=dict)

    def for_provider(self, provider: str) -> ProviderMetrics:
        return self.providers.setdefault(provider, ProviderMetrics())

    def record_fetch(self, provider: str, count: int) -> None:
        self.for_provider(provider).record_fetch(count)

    def record_normalized(self, provider: str, count: int = 1, *, latest_event_timestamp: datetime | None = None) -> None:
        self.for_provider(provider).record_normalized(count=count, latest_event_timestamp=latest_event_timestamp)

    def record_error(self, provider: str, error: Exception | str) -> None:
        self.for_provider(provider).record_error(str(error))

    def record_retry(self, provider: str, attempts: int = 1) -> None:
        self.for_provider(provider).record_retry(attempts=attempts)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        snapshot: dict[str, dict[str, Any]] = {}
        for provider, metrics in self.providers.items():
            data = asdict(metrics)
            data["lag_seconds"] = metrics.lag_seconds()
            data["error_rate"] = metrics.error_rate()
            snapshot[provider] = data
        return snapshot

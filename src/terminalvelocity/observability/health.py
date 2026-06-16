"""Provider health checks backed by connectivity and ingestion metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable

from terminalvelocity.observability.metrics import IngestionMetrics
from terminalvelocity.providers.base import BaseProvider


@dataclass(slots=True)
class ProviderHealth:
    """Health snapshot for a provider adapter."""

    provider: str
    ok: bool
    lag_seconds: float | None
    error_rate: float
    details: dict[str, object]


class ProviderHealthChecker:
    """Run connectivity and metrics-based health checks for providers."""

    def __init__(
        self,
        metrics: IngestionMetrics,
        *,
        max_lag: timedelta = timedelta(hours=1),
        max_error_rate: float = 0.25,
    ) -> None:
        self.metrics = metrics
        self.max_lag = max_lag
        self.max_error_rate = max_error_rate

    def check_provider(self, provider: BaseProvider) -> ProviderHealth:
        metric = self.metrics.for_provider(provider.provider_name)
        details: dict[str, object] = {"service": provider.service_name}
        connectivity_ok = False
        try:
            connectivity_ok = provider.connect()
        except Exception as exc:
            details["connection_error"] = str(exc)
        lag_seconds = metric.lag_seconds()
        error_rate = metric.error_rate()
        lag_ok = lag_seconds is None or lag_seconds <= self.max_lag.total_seconds()
        error_ok = error_rate <= self.max_error_rate
        ok = bool(connectivity_ok and lag_ok and error_ok)
        details.update(
            {
                "last_success_at": metric.last_success_at.isoformat() if metric.last_success_at else None,
                "last_error_at": metric.last_error_at.isoformat() if metric.last_error_at else None,
                "last_error_message": metric.last_error_message,
            }
        )
        return ProviderHealth(
            provider=provider.provider_name,
            ok=ok,
            lag_seconds=lag_seconds,
            error_rate=error_rate,
            details=details,
        )

    def check_all(self, providers: Iterable[BaseProvider]) -> dict[str, ProviderHealth]:
        return {provider.provider_name: self.check_provider(provider) for provider in providers}

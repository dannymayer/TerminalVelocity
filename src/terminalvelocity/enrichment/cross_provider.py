"""Cross-provider event correlation and enrichment helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable

from terminalvelocity.schema import NormalizedEvent


@dataclass(slots=True)
class CorrelatedEventGroup:
    """A set of events linked by actor, target, and time proximity."""

    key: str
    actor: str | None
    target: str | None
    providers: tuple[str, ...]
    events: tuple[NormalizedEvent, ...]


class CrossProviderEnricher:
    """Correlate events across providers by actor, target, and time window."""

    def __init__(self, *, time_window: timedelta = timedelta(minutes=10)) -> None:
        self.time_window = time_window

    def correlate(self, events: Iterable[NormalizedEvent]) -> list[CorrelatedEventGroup]:
        ordered = sorted(events, key=lambda item: item.timestamp)
        groups: list[CorrelatedEventGroup] = []
        buckets: dict[str, list[NormalizedEvent]] = {}
        for event in ordered:
            actor = (event.actor or "").lower() or None
            target = (event.target or "").lower() or None
            base_key = f"{actor or '*'}|{target or '*'}"
            existing = buckets.setdefault(base_key, [])
            existing.append(event)

        for base_key, grouped_events in buckets.items():
            window_events: list[NormalizedEvent] = []
            for event in grouped_events:
                if not window_events:
                    window_events = [event]
                    continue
                if event.timestamp - window_events[-1].timestamp <= self.time_window:
                    window_events.append(event)
                    continue
                groups.append(self._build_group(base_key, window_events))
                window_events = [event]
            if window_events:
                groups.append(self._build_group(base_key, window_events))
        return groups

    def enrich(self, events: Iterable[NormalizedEvent]) -> list[NormalizedEvent]:
        groups = self.correlate(events)
        enriched: dict[str, NormalizedEvent] = {}
        for group in groups:
            event_ids = [event.cache_key() for event in group.events]
            providers = sorted({event.provider for event in group.events})
            for event in group.events:
                related_ids = [event_id for event_id in event_ids if event_id != event.cache_key()]
                enriched[event.cache_key()] = event.model_copy(
                    update={
                        "related_event_ids": related_ids,
                        "related_provider_count": max(0, len(providers) - 1),
                        "related_providers": providers,
                        "correlation_cluster": group.key,
                    }
                )
        return [enriched.get(event.cache_key(), event) for event in events]

    @staticmethod
    def _build_group(base_key: str, events: list[NormalizedEvent]) -> CorrelatedEventGroup:
        start = events[0].timestamp.isoformat()
        end = events[-1].timestamp.isoformat()
        return CorrelatedEventGroup(
            key=f"{base_key}|{start}|{end}",
            actor=events[0].actor,
            target=events[0].target,
            providers=tuple(sorted({event.provider for event in events})),
            events=tuple(events),
        )

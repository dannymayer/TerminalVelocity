"""Cross-provider event correlation and enrichment helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta

from terminalvelocity.schema import NormalizedEvent

# Provider identifiers used for targeted correlation rules
_IDENTITY_PROTECTION_PROVIDER = "identity_protection"
_ENTRA_ID_PROVIDER = "entra_id"


@dataclass(slots=True)
class CorrelatedEventGroup:
    """A set of events linked by actor, target, and time proximity."""

    key: str
    actor: str | None
    target: str | None
    providers: tuple[str, ...]
    events: tuple[NormalizedEvent, ...]


class CrossProviderEnricher:
    """Correlate events across providers by actor, target, and time window.

    In addition to the generic actor/target bucket correlation, a targeted rule
    links Identity Protection risk detections to Entra ID sign-in events that
    share the same ``correlation_id`` or ``request_id``.  Matched sign-in events
    receive ``_tv_risk_linked = True`` and ``_tv_risk_event_ids`` in their extra
    fields so that downstream investigation tools (pivot, timeline) can surface
    the risk context alongside the sign-in record.
    """

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
        event_list = list(events)
        groups = self.correlate(event_list)
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

        # Targeted rule: link Identity Protection risk detections to Entra sign-in events
        result_list = [enriched.get(event.cache_key(), event) for event in event_list]
        return self._link_risk_detections(result_list)

    def _link_risk_detections(self, events: list[NormalizedEvent]) -> list[NormalizedEvent]:
        """Cross-correlate Identity Protection risk detections with Entra sign-in events.

        Joins on shared ``correlation_id`` or ``request_id`` values so that a
        risky sign-in event is annotated with the risk detection IDs that fired
        for the same request.
        """
        # Build index: correlation_id / request_id → risk detection cache keys
        risk_index: dict[str, list[str]] = {}
        for event in events:
            if event.provider != _IDENTITY_PROTECTION_PROVIDER:
                continue
            for ref_id in filter(None, (event.correlation_id, event.request_id)):
                risk_index.setdefault(ref_id, []).append(event.cache_key())

        if not risk_index:
            return events

        linked: list[NormalizedEvent] = []
        for event in events:
            if event.provider != _ENTRA_ID_PROVIDER or event.action != "sign-in":
                linked.append(event)
                continue
            matching_risk_ids: list[str] = []
            for ref_id in filter(None, (event.correlation_id, event.request_id)):
                matching_risk_ids.extend(risk_index.get(ref_id, []))
            if matching_risk_ids:
                linked.append(event.model_copy(update={
                    "_tv_risk_linked": True,
                    "_tv_risk_event_ids": list(dict.fromkeys(matching_risk_ids)),
                }))
            else:
                linked.append(event)
        return linked

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

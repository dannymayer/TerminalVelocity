from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from terminalvelocity.models import NormalizedEvent


@dataclass(slots=True)
class CorrelatedGroup:
    key: str
    events: list[NormalizedEvent]


class EventCorrelator:
    def group_by_correlation(self, events: Iterable[NormalizedEvent]) -> list[CorrelatedGroup]:
        groups: dict[str, list[NormalizedEvent]] = defaultdict(list)
        for event in events:
            key = event.correlation_id or event.request_id
            if key:
                groups[key].append(event)
        return [
            CorrelatedGroup(key=key, events=sorted(group, key=lambda item: item.timestamp))
            for key, group in groups.items()
        ]

    def pivot_from_event(self, seed: NormalizedEvent, events: Iterable[NormalizedEvent]) -> list[NormalizedEvent]:
        return sorted([event for event in events if self._is_related(seed, event)], key=lambda item: item.timestamp)

    def pivot_by_actor(self, actor: str, events: Iterable[NormalizedEvent]) -> list[NormalizedEvent]:
        return sorted(
            [event for event in events if (event.actor or "").casefold() == actor.casefold()],
            key=lambda item: item.timestamp,
        )

    def pivot_by_target(self, target: str, events: Iterable[NormalizedEvent]) -> list[NormalizedEvent]:
        return sorted(
            [event for event in events if (event.target or "").casefold() == target.casefold()],
            key=lambda item: item.timestamp,
        )

    @staticmethod
    def _is_related(seed: NormalizedEvent, event: NormalizedEvent) -> bool:
        correlation_keys = {value for value in (seed.correlation_id, seed.request_id) if value}
        return bool(
            bool(correlation_keys.intersection({event.correlation_id, event.request_id}))
            or (seed.actor and event.actor and seed.actor.casefold() == event.actor.casefold())
            or (seed.target and event.target and seed.target.casefold() == event.target.casefold())
        )

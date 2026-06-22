from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta

from terminalvelocity.models import NormalizedEvent


@dataclass(slots=True)
class PivotRelation:
    """A related event and the reason it was selected."""

    relation: str
    event: NormalizedEvent


class PivotAnalyzer:
    """Find actor, target, and session pivots from a seed event."""

    def __init__(self, window: timedelta = timedelta(hours=1)) -> None:
        self.window = window

    def related_to_event(self, seed: NormalizedEvent, events: Iterable[NormalizedEvent]) -> list[PivotRelation]:
        """Return events related to the seed event within the investigation window."""

        relations: list[PivotRelation] = []
        for event in sorted(events, key=lambda item: item.timestamp):
            reason = self._relation(seed, event)
            if reason is not None:
                relations.append(PivotRelation(relation=reason, event=event))
        return relations

    def pivot_by_actor(self, actor: str, events: Iterable[NormalizedEvent]) -> list[NormalizedEvent]:
        """Return events matching an actor, ordered by timestamp."""

        return sorted(
            [event for event in events if event.actor and event.actor.casefold() == actor.casefold()],
            key=lambda item: item.timestamp,
        )

    def pivot_by_target(self, target: str, events: Iterable[NormalizedEvent]) -> list[NormalizedEvent]:
        """Return events matching a target, ordered by timestamp."""

        return sorted(
            [event for event in events if event.target and event.target.casefold() == target.casefold()],
            key=lambda item: item.timestamp,
        )

    def pivot_by_session(self, session_id: str, events: Iterable[NormalizedEvent]) -> list[NormalizedEvent]:
        """Return events matching a correlation or request identifier."""

        session_key = session_id.casefold()
        return sorted(
            [
                event
                for event in events
                if (event.correlation_id and event.correlation_id.casefold() == session_key)
                or (event.request_id and event.request_id.casefold() == session_key)
            ],
            key=lambda item: item.timestamp,
        )

    def _relation(self, seed: NormalizedEvent, event: NormalizedEvent) -> str | None:
        if abs(event.timestamp - seed.timestamp) > self.window:
            return None
        session_values = {value.casefold() for value in (seed.correlation_id, seed.request_id) if value}
        event_values = {value.casefold() for value in (event.correlation_id, event.request_id) if value}
        if session_values.intersection(event_values):
            return 'session'
        if seed.actor and event.actor and seed.actor.casefold() == event.actor.casefold():
            return 'actor'
        if seed.target and event.target and seed.target.casefold() == event.target.casefold():
            return 'target'
        return None

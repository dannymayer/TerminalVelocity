from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from terminalvelocity.models import NormalizedEvent


@dataclass(slots=True)
class InvestigationTimeline:
    """A correlated incident timeline built from normalized events."""

    timeline_id: str
    events: list[NormalizedEvent]
    correlation_ids: tuple[str, ...] = field(default_factory=tuple)
    actors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def start(self) -> datetime:
        """Return the timestamp of the first event in the timeline."""

        return self.events[0].timestamp

    @property
    def end(self) -> datetime:
        """Return the timestamp of the last event in the timeline."""

        return self.events[-1].timestamp

    @property
    def duration(self) -> timedelta:
        """Return the elapsed time covered by the timeline."""

        return self.end - self.start


class TimelineBuilder:
    """Group events into incident timelines using session IDs, actors, and time windows."""

    def __init__(self, window: timedelta = timedelta(minutes=15)) -> None:
        self.window = window

    def build(self, events: Iterable[NormalizedEvent]) -> list[InvestigationTimeline]:
        """Build ordered timelines from normalized events."""

        ordered_events = sorted(events, key=lambda event: event.timestamp)
        if not ordered_events:
            return []

        timelines: list[InvestigationTimeline] = []
        pending_by_key: dict[str, InvestigationTimeline] = {}

        for index, event in enumerate(ordered_events, start=1):
            keys = self._timeline_keys(event)
            timeline = self._resolve_timeline(event, keys, pending_by_key)
            if timeline is None:
                timeline_id = self._timeline_id(event, index)
                timeline = InvestigationTimeline(timeline_id=timeline_id, events=[])
                timelines.append(timeline)
            timeline.events.append(event)
            self._refresh_metadata(timeline)
            for key in self._timeline_keys(event):
                pending_by_key[key] = timeline

        return sorted(timelines, key=lambda timeline: timeline.start)

    def _resolve_timeline(
        self,
        event: NormalizedEvent,
        keys: set[str],
        pending_by_key: dict[str, InvestigationTimeline],
    ) -> InvestigationTimeline | None:
        for key in keys:
            timeline = pending_by_key.get(key)
            if timeline is not None and event.timestamp - timeline.end <= self.window:
                return timeline
        return None

    @staticmethod
    def _timeline_id(event: NormalizedEvent, index: int) -> str:
        if event.correlation_id:
            return f'corr:{event.correlation_id}'
        if event.request_id:
            return f'req:{event.request_id}'
        if event.actor:
            return f'actor:{event.actor.casefold()}:{index}'
        return f'timeline:{index}'

    @staticmethod
    def _timeline_keys(event: NormalizedEvent) -> set[str]:
        keys: set[str] = set()
        if event.correlation_id:
            keys.add(f'corr:{event.correlation_id}')
        if event.request_id:
            keys.add(f'req:{event.request_id}')
        if event.actor:
            keys.add(f'actor:{event.actor.casefold()}')
        return keys

    @staticmethod
    def _refresh_metadata(timeline: InvestigationTimeline) -> None:
        correlation_ids = {
            value
            for event in timeline.events
            for value in (event.correlation_id, event.request_id)
            if value
        }
        actors = {event.actor for event in timeline.events if event.actor}
        timeline.correlation_ids = tuple(sorted(correlation_ids))
        timeline.actors = tuple(sorted(actors))

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta

from terminalvelocity.models import NormalizedEvent

PRIVILEGED_TERMS = ("admin", "role", "privilege", "elevat", "grant", "assign")


@dataclass(slots=True)
class AnomalyMarker:
    kind: str
    description: str
    events: list[NormalizedEvent]


class AnomalyDetector:
    def detect(self, events: Iterable[NormalizedEvent], *, burst_window: timedelta = timedelta(minutes=5), burst_threshold: int = 5) -> list[AnomalyMarker]:
        event_list = sorted(events, key=lambda event: event.timestamp)
        return self._burst_failures(event_list, burst_window, burst_threshold) + self._rare_actions(event_list) + self._privileged_operations(event_list)

    def _burst_failures(self, events: list[NormalizedEvent], window: timedelta, threshold: int) -> list[AnomalyMarker]:
        failures_by_actor: dict[str, list[NormalizedEvent]] = defaultdict(list)
        for event in events:
            if (event.result or "").casefold() == "failure" and event.actor:
                failures_by_actor[event.actor.casefold()].append(event)
        anomalies: list[AnomalyMarker] = []
        for actor, actor_events in failures_by_actor.items():
            for start_index, start_event in enumerate(actor_events):
                end_index = start_index
                while end_index < len(actor_events) and actor_events[end_index].timestamp - start_event.timestamp <= window:
                    end_index += 1
                window_events = actor_events[start_index:end_index]
                if len(window_events) >= threshold:
                    anomalies.append(AnomalyMarker(kind="burst_failures", description=f"{len(window_events)} failures for {actor} within {window}", events=window_events))
                    break
        return anomalies

    def _rare_actions(self, events: list[NormalizedEvent]) -> list[AnomalyMarker]:
        # TODO(false-positives): flagging every action seen only once produces
        # a high volume of noise on sparse or freshly-ingested datasets.  Consider
        # requiring a minimum total event count before activating this heuristic,
        # or using a baseline frequency threshold (e.g. < 1 % of total events)
        # rather than an absolute count of 1.
        counts = Counter((event.provider, event.action) for event in events if event.action)
        return [AnomalyMarker(kind="rare_action", description=f"Rare action detected: {event.action}", events=[event]) for event in events if event.action and counts[(event.provider, event.action)] == 1]

    def _privileged_operations(self, events: list[NormalizedEvent]) -> list[AnomalyMarker]:
        markers = []
        for event in events:
            haystack = " ".join(part for part in [event.action, event.target, event.raw_json()] if part).casefold()
            if any(term in haystack for term in PRIVILEGED_TERMS):
                markers.append(AnomalyMarker(kind="privileged_operation", description=f"Privileged operation detected: {event.action or event.target}", events=[event]))
        return markers

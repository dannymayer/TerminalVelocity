from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Iterable

from terminalvelocity.models import NormalizedEvent
from terminalvelocity.search.parser import SearchQuery

RELATIVE_TIME = re.compile(r"^(?P<amount>\d+)(?P<unit>[smhdw])$", re.IGNORECASE)
SEVERITY_ORDER = {"critical": 5, "high": 4, "medium": 3, "warning": 2, "low": 1, "informational": 0, "info": 0}


def parse_time_expression(expression: str, now: datetime | None = None) -> datetime:
    now = _ensure_utc(now or datetime.now(timezone.utc))
    value = expression.strip()
    match = RELATIVE_TIME.match(value)
    if match:
        amount = int(match.group("amount"))
        unit = match.group("unit").lower()
        delta = {"s": timedelta(seconds=amount), "m": timedelta(minutes=amount), "h": timedelta(hours=amount), "d": timedelta(days=amount), "w": timedelta(weeks=amount)}[unit]
        return now - delta
    if value.lower() == "now":
        return now
    return _ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def resolve_time_range(query: SearchQuery, now: datetime | None = None) -> tuple[datetime | None, datetime | None]:
    now = _ensure_utc(now or datetime.now(timezone.utc))
    return (
        parse_time_expression(query.since, now=now) if query.since else None,
        parse_time_expression(query.until, now=now) if query.until else None,
    )


def matches_event(event: NormalizedEvent, query: SearchQuery, now: datetime | None = None) -> bool:
    since, until = resolve_time_range(query, now=now)
    if since and event.timestamp < since:
        return False
    if until and event.timestamp > until:
        return False
    for field_filter in query.field_filters:
        candidate = getattr(event, field_filter.field)
        if candidate is None or str(candidate).casefold() != field_filter.value.casefold():
            return False
    return True


def filter_events(events: Iterable[NormalizedEvent], query: SearchQuery, now: datetime | None = None) -> list[NormalizedEvent]:
    return [event for event in events if matches_event(event, query, now=now)]


def sort_events(events: Iterable[NormalizedEvent], sort_by: str = "timestamp", descending: bool | None = None) -> list[NormalizedEvent]:
    descending = descending if descending is not None else sort_by in {"timestamp", "severity"}
    return sorted(events, key=lambda event: _sort_key(event, sort_by), reverse=descending)


def _sort_key(event: NormalizedEvent, sort_by: str):
    if sort_by == "timestamp":
        return event.timestamp
    if sort_by == "severity":
        return SEVERITY_ORDER.get((event.severity or "").lower(), -1)
    return (getattr(event, sort_by) or "").casefold()


def _ensure_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

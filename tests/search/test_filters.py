from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from terminalvelocity.models import NormalizedEvent
from terminalvelocity.search.filters import filter_events, parse_time_expression, sort_events
from terminalvelocity.search.parser import parse_query


class SearchFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
        self.events = [
            NormalizedEvent(timestamp=self.now - timedelta(minutes=5), provider="defender", service="identity", actor="user@contoso.com", action="SignIn", result="failure", severity="high", target="device-1", raw={"message": "failed sign in"}),
            NormalizedEvent(timestamp=self.now - timedelta(hours=2), provider="entra", service="identity", actor="admin@contoso.com", action="GrantRole", result="success", severity="critical", target="Global Administrator", raw={"message": "role assigned"}),
            NormalizedEvent(timestamp=self.now - timedelta(minutes=30), provider="defender", service="identity", actor="user@contoso.com", action="SignIn", result="success", severity="low", target="device-2", raw={"message": "successful sign in"}),
        ]

    def test_parses_relative_and_absolute_time_expressions(self) -> None:
        self.assertEqual(parse_time_expression("15m", now=self.now), self.now - timedelta(minutes=15))
        self.assertEqual(parse_time_expression("2025-01-01T10:00:00Z", now=self.now), datetime(2025, 1, 1, 10, 0, tzinfo=UTC))

    def test_filters_by_time_and_field_values(self) -> None:
        filtered = filter_events(self.events, parse_query("provider:defender result:failure since:1h"), now=self.now)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].target, "device-1")

    def test_sorts_by_severity_and_provider(self) -> None:
        by_severity = sort_events(self.events, sort_by="severity")
        by_provider = sort_events(self.events, sort_by="provider", descending=False)
        self.assertEqual(by_severity[0].severity, "critical")
        self.assertEqual([event.provider for event in by_provider], ["defender", "defender", "entra"])

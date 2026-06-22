from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from terminalvelocity.models import NormalizedEvent
from terminalvelocity.search.engine import SearchEngine


class SearchEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = SearchEngine()
        now = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
        self.events = [
            NormalizedEvent(timestamp=now - timedelta(minutes=10), provider="defender", service="identity", actor="user@contoso.com", action="PasswordReset", result="failure", severity="high", target="account-1", correlation_id="corr-1", raw={"message": "password reset failed for user"}),
            NormalizedEvent(timestamp=now - timedelta(minutes=8), provider="entra", service="identity", actor="admin@contoso.com", action="GrantRole", result="success", severity="critical", target="Global Administrator", raw={"message": "global admin granted"}),
        ]
        self.engine.index_events(self.events)

    def tearDown(self) -> None:
        self.engine.close()

    def test_searches_free_text_and_field_filters(self) -> None:
        results = self.engine.search('password reset provider:defender result:failure')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].action, "PasswordReset")

    def test_sorts_by_provider(self) -> None:
        results = self.engine.search('sort:provider')
        self.assertEqual([event.provider for event in results], ["defender", "entra"])

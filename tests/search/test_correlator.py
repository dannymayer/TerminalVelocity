from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from terminalvelocity.models import NormalizedEvent
from terminalvelocity.search.correlator import EventCorrelator


class CorrelatorTests(unittest.TestCase):
    def setUp(self) -> None:
        now = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
        self.events = [
            NormalizedEvent(timestamp=now - timedelta(minutes=4), provider="defender", service="identity", actor="user@contoso.com", action="SignIn", target="device-1", result="failure", correlation_id="corr-1", raw={"step": 1}),
            NormalizedEvent(timestamp=now - timedelta(minutes=3), provider="defender", service="identity", actor="user@contoso.com", action="MFAChallenge", target="device-1", result="success", correlation_id="corr-1", raw={"step": 2}),
            NormalizedEvent(timestamp=now - timedelta(minutes=2), provider="entra", service="identity", actor="user@contoso.com", action="TokenIssued", target="session-99", result="success", request_id="req-9", raw={"step": 3}),
            NormalizedEvent(timestamp=now - timedelta(minutes=1), provider="defender", service="identity", actor="other@contoso.com", action="AlertOpened", target="device-2", result="success", correlation_id="corr-2", raw={"step": 4}),
        ]
        self.correlator = EventCorrelator()

    def test_groups_events_by_correlation_or_request_id(self) -> None:
        groups = {group.key: group.events for group in self.correlator.group_by_correlation(self.events)}
        self.assertEqual(len(groups["corr-1"]), 2)
        self.assertEqual(len(groups["req-9"]), 1)
        self.assertEqual(len(groups["corr-2"]), 1)

    def test_pivots_from_event_to_related_actor_target_and_session(self) -> None:
        related = self.correlator.pivot_from_event(self.events[0], self.events)
        self.assertEqual([event.action for event in related], ["SignIn", "MFAChallenge", "TokenIssued"])

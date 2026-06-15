from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from terminalvelocity.investigation.pivot import PivotAnalyzer
from terminalvelocity.models import NormalizedEvent


class PivotAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
        self.events = [
            NormalizedEvent(timestamp=now, provider='entra', service='identity', actor='user@contoso.com', action='SignIn', target='device-1', result='failure', correlation_id='corr-1', raw={'step': 1}),
            NormalizedEvent(timestamp=now + timedelta(minutes=5), provider='entra', service='identity', actor='user@contoso.com', action='MFAChallenge', target='device-1', result='success', request_id='corr-1', raw={'step': 2}),
            NormalizedEvent(timestamp=now + timedelta(minutes=10), provider='defender', service='endpoint', actor='other@contoso.com', action='AlertOpened', target='device-1', result='success', raw={'step': 3}),
            NormalizedEvent(timestamp=now + timedelta(hours=2), provider='defender', service='endpoint', actor='user@contoso.com', action='LateActivity', target='device-2', result='success', raw={'step': 4}),
        ]
        self.analyzer = PivotAnalyzer(window=timedelta(minutes=30))

    def test_finds_related_actor_target_and_session_events(self) -> None:
        relations = self.analyzer.related_to_event(self.events[0], self.events)
        self.assertEqual(
            [(item.relation, item.event.action) for item in relations],
            [('session', 'SignIn'), ('session', 'MFAChallenge'), ('target', 'AlertOpened')],
        )

    def test_pivots_by_specific_dimensions(self) -> None:
        self.assertEqual(len(self.analyzer.pivot_by_actor('user@contoso.com', self.events)), 3)
        self.assertEqual(len(self.analyzer.pivot_by_target('device-1', self.events)), 3)
        self.assertEqual(len(self.analyzer.pivot_by_session('corr-1', self.events)), 2)

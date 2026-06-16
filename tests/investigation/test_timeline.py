from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from terminalvelocity.investigation.timeline import TimelineBuilder
from terminalvelocity.models import NormalizedEvent


class TimelineBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
        self.events = [
            NormalizedEvent(timestamp=now, provider='entra', service='identity', actor='user@contoso.com', action='SignIn', target='device-1', result='failure', correlation_id='corr-1', raw={'step': 1}),
            NormalizedEvent(timestamp=now + timedelta(minutes=2), provider='entra', service='identity', actor='user@contoso.com', action='TokenIssued', target='device-1', result='success', request_id='req-1', raw={'step': 2}),
            NormalizedEvent(timestamp=now + timedelta(minutes=4), provider='defender', service='endpoint', actor='user@contoso.com', action='DeviceAccess', target='device-1', result='success', raw={'step': 3}),
            NormalizedEvent(timestamp=now + timedelta(minutes=30), provider='defender', service='endpoint', actor='other@contoso.com', action='AlertOpened', target='device-9', result='success', correlation_id='corr-2', raw={'step': 4}),
        ]

    def test_groups_related_events_into_timelines(self) -> None:
        timelines = TimelineBuilder(window=timedelta(minutes=10)).build(self.events)
        self.assertEqual(len(timelines), 2)
        self.assertEqual([event.action for event in timelines[0].events], ['SignIn', 'TokenIssued', 'DeviceAccess'])
        self.assertEqual(timelines[0].correlation_ids, ('corr-1', 'req-1'))
        self.assertEqual(timelines[0].actors, ('user@contoso.com',))
        self.assertEqual(timelines[1].timeline_id, 'corr:corr-2')

    def test_splits_actor_activity_outside_time_window(self) -> None:
        timelines = TimelineBuilder(window=timedelta(minutes=1)).build(self.events[:3])
        self.assertEqual(len(timelines), 3)

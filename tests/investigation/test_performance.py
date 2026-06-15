from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from terminalvelocity.investigation.performance import LRUResultCache, batched_events, deduplicate_events, paginate_sequence
from terminalvelocity.models import NormalizedEvent


class PerformanceHelpersTests(unittest.TestCase):
    def test_lru_cache_evicts_least_recent_entry(self) -> None:
        cache = LRUResultCache[int](capacity=2)
        cache.set('a', 1)
        cache.set('b', 2)
        self.assertEqual(cache.get('a'), 1)
        cache.set('c', 3)
        self.assertIsNone(cache.get('b'))
        self.assertEqual(cache.get('c'), 3)

    def test_paginates_and_batches_events(self) -> None:
        page = paginate_sequence([1, 2, 3, 4, 5], page=2, page_size=2)
        self.assertEqual(page.items, [3, 4])
        self.assertTrue(page.has_next)
        self.assertTrue(page.has_previous)

        now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
        events = [
            NormalizedEvent(timestamp=now + timedelta(minutes=index), provider='entra', service='identity', actor='user@contoso.com', action=f'Action{index}', target='device-1', result='success', raw={'step': index})
            for index in range(3)
        ]
        batches = list(batched_events(events, batch_size=2))
        self.assertEqual([len(batch) for batch in batches], [2, 1])

    def test_deduplicates_large_result_sets(self) -> None:
        now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
        event = NormalizedEvent(timestamp=now, provider='entra', service='identity', actor='user@contoso.com', action='SignIn', target='device-1', result='success', raw={'step': 1})
        deduplicated = deduplicate_events([event, event])
        self.assertEqual(len(deduplicated), 1)

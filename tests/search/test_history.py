"""Tests for the query history store."""

from __future__ import annotations

import unittest

from terminalvelocity.search.history import QueryHistoryStore


class QueryHistoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = QueryHistoryStore()  # in-memory

    def tearDown(self) -> None:
        self.store.close()

    def test_record_and_list(self) -> None:
        self.store.record("provider:defender", "24h", 5)
        entries = self.store.list()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].query, "provider:defender")
        self.assertEqual(entries[0].scope, "24h")
        self.assertEqual(entries[0].result_count, 5)

    def test_empty_query_not_recorded(self) -> None:
        self.store.record("", "all", 0)
        self.store.record("   ", "all", 0)
        self.assertEqual(self.store.list(), [])

    def test_list_newest_first(self) -> None:
        self.store.record("query-one", "all", 1)
        self.store.record("query-two", "all", 2)
        entries = self.store.list()
        self.assertEqual(entries[0].query, "query-two")
        self.assertEqual(entries[1].query, "query-one")

    def test_clear(self) -> None:
        self.store.record("some query", "1h", 3)
        self.store.clear()
        self.assertEqual(self.store.list(), [])

    def test_limit(self) -> None:
        for i in range(10):
            self.store.record(f"query-{i}", "all", i)
        self.assertEqual(len(self.store.list(limit=5)), 5)

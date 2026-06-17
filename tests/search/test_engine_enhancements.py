"""Tests for the enhanced SearchEngine: tagging and archival."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from terminalvelocity.models import NormalizedEvent
from terminalvelocity.search.engine import SearchEngine


def _make_event(
    *,
    provider: str = "entra",
    service: str = "audit",
    actor: str = "user@contoso.com",
    action: str = "sign-in",
    result: str = "success",
    severity: str = "low",
    minutes_ago: int = 10,
) -> NormalizedEvent:
    ts = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return NormalizedEvent(
        timestamp=ts,
        provider=provider,
        service=service,
        actor=actor,
        action=action,
        result=result,
        severity=severity,
        raw={},
    )


class SearchEngineTaggingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = SearchEngine()
        self.event = _make_event()
        self.engine.index_events([self.event])
        self.event_id = self.event.stable_id()

    def tearDown(self) -> None:
        self.engine.close()

    def test_tag_and_retrieve(self) -> None:
        self.engine.tag_event(self.event_id, "relevant")
        tags = self.engine.get_event_tags(self.event_id)
        self.assertIn("relevant", tags)

    def test_untag_removes_tag(self) -> None:
        self.engine.tag_event(self.event_id, "relevant")
        self.engine.untag_event(self.event_id, "relevant")
        self.assertEqual(self.engine.get_event_tags(self.event_id), [])

    def test_list_tags(self) -> None:
        self.engine.tag_event(self.event_id, "relevant")
        self.engine.tag_event(self.event_id, "false-positive")
        tags = self.engine.list_tags()
        self.assertIn("relevant", tags)
        self.assertIn("false-positive", tags)

    def test_search_by_tag(self) -> None:
        self.engine.tag_event(self.event_id, "incident-42")
        results = self.engine.search("tag:incident-42")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].action, "sign-in")

    def test_tag_filter_no_match(self) -> None:
        results = self.engine.search("tag:nonexistent")
        self.assertEqual(results, [])

    def test_multiple_tags_on_same_event(self) -> None:
        self.engine.tag_event(self.event_id, "alpha")
        self.engine.tag_event(self.event_id, "beta")
        # Query by either tag should return the event
        self.assertEqual(len(self.engine.search("tag:alpha")), 1)
        self.assertEqual(len(self.engine.search("tag:beta")), 1)


class SearchEngineArchivalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = SearchEngine()
        now = datetime.now(timezone.utc)
        self.recent = _make_event(minutes_ago=60)
        self.old = NormalizedEvent(
            timestamp=now - timedelta(hours=500),
            provider="intune",
            service="audit",
            actor="svc@contoso.com",
            action="policy-sync",
            result="success",
            severity="low",
            raw={},
        )
        self.engine.index_events([self.recent, self.old])

    def tearDown(self) -> None:
        self.engine.close()

    def test_archive_old_events(self) -> None:
        archived = self.engine.archive_old_events(cutoff_hours=168)
        self.assertEqual(archived, 1)

    def test_archived_excluded_from_default_search(self) -> None:
        self.engine.archive_old_events(cutoff_hours=168)
        results = self.engine.search("provider:intune", limit=100)
        self.assertEqual(len(results), 0)

    def test_show_archived_includes_archived(self) -> None:
        self.engine.archive_old_events(cutoff_hours=168)
        results = self.engine.search("show:archived provider:intune", limit=100)
        self.assertEqual(len(results), 1)

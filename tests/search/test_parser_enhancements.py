"""Tests for the enhanced query parser: tag: and show: modifiers."""

from __future__ import annotations

import unittest

from terminalvelocity.search.parser import parse_query, QuerySyntaxError


class ParserTagTests(unittest.TestCase):
    def test_tag_filter_parsed(self) -> None:
        q = parse_query("tag:relevant")
        self.assertEqual(q.tags, ["relevant"])
        self.assertEqual(q.free_text, [])

    def test_multiple_tags_parsed(self) -> None:
        q = parse_query("tag:relevant tag:false-positive")
        self.assertEqual(sorted(q.tags), ["false-positive", "relevant"])

    def test_tag_combined_with_free_text(self) -> None:
        q = parse_query("sign-in tag:incident-42")
        self.assertEqual(q.free_text, ["sign-in"])
        self.assertEqual(q.tags, ["incident-42"])

    def test_show_archived_sets_flag(self) -> None:
        q = parse_query("show:archived")
        self.assertTrue(q.include_archived)

    def test_show_all_sets_flag(self) -> None:
        q = parse_query("show:all")
        self.assertTrue(q.include_archived)

    def test_show_archived_combined(self) -> None:
        q = parse_query("provider:defender show:archived")
        self.assertTrue(q.include_archived)
        self.assertEqual(q.field_values("provider"), ["defender"])

    def test_unrecognised_show_value_ignored(self) -> None:
        q = parse_query("show:something")
        self.assertFalse(q.include_archived)

    def test_defaults_not_archived(self) -> None:
        q = parse_query("anything")
        self.assertFalse(q.include_archived)
        self.assertEqual(q.tags, [])

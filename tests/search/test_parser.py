from __future__ import annotations

import unittest

from terminalvelocity.search.parser import QuerySyntaxError, parse_query


class QueryParserTests(unittest.TestCase):
    def test_parses_free_text_fields_and_sort(self) -> None:
        query = parse_query(
            "failed login provider:defender result:failure actor:user@contoso.com since:1h sort:severity"
        )
        self.assertEqual(query.free_text, ["failed", "login"])
        self.assertEqual(query.field_values("provider"), ["defender"])
        self.assertEqual(query.field_values("result"), ["failure"])
        self.assertEqual(query.field_values("actor"), ["user@contoso.com"])
        self.assertEqual(query.since, "1h")
        self.assertEqual(query.sort_by, "severity")
        self.assertTrue(query.sort_desc)

    def test_parses_quoted_free_text_and_last_alias(self) -> None:
        query = parse_query('"privileged role change" provider:entra last:15m sort:provider')
        self.assertEqual(query.free_text, ["privileged role change"])
        self.assertEqual(query.field_values("provider"), ["entra"])
        self.assertEqual(query.since, "15m")
        self.assertEqual(query.sort_by, "provider")
        self.assertFalse(query.sort_desc)

    def test_rejects_unknown_filter_fields(self) -> None:
        with self.assertRaises(QuerySyntaxError):
            parse_query("unknown:value result:failure")

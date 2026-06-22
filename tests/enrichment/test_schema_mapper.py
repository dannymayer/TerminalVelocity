"""Tests for the SchemaMapper and schema normalization helpers."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from terminalvelocity.enrichment.schema_mapper import (
    SchemaMapper,
    _normalize_id,
    extract_first,
    normalize_actor,
    normalize_result,
    normalize_severity,
    normalize_target,
    normalize_timestamp,
)


class ExtractFirstTests(unittest.TestCase):
    def test_simple_key(self) -> None:
        self.assertEqual(extract_first({"a": "x"}, "a"), "x")

    def test_first_non_empty_wins(self) -> None:
        self.assertEqual(extract_first({"a": "", "b": "y"}, "a", "b"), "y")

    def test_dotted_path(self) -> None:
        payload = {"user": {"id": "abc"}}
        self.assertEqual(extract_first(payload, "user.id"), "abc")

    def test_missing_returns_none(self) -> None:
        self.assertIsNone(extract_first({}, "missing"))

    def test_list_index(self) -> None:
        payload = {"items": ["first", "second"]}
        self.assertEqual(extract_first(payload, "items.0"), "first")

    def test_empty_dict_returns_none(self) -> None:
        self.assertIsNone(extract_first({"key": {}}, "key"))

    def test_empty_list_returns_none(self) -> None:
        self.assertIsNone(extract_first({"key": []}, "key"))


class NormalizeTimestampTests(unittest.TestCase):
    def test_iso_string_with_z(self) -> None:
        result = normalize_timestamp("2024-01-15T10:30:00Z")
        self.assertEqual(result.tzinfo, UTC)
        self.assertEqual(result.year, 2024)

    def test_datetime_without_tz_gets_utc(self) -> None:
        naive = datetime(2024, 6, 1, 12, 0, 0)
        result = normalize_timestamp(naive)
        self.assertEqual(result.tzinfo, UTC)

    def test_none_returns_default(self) -> None:
        default = datetime(2024, 1, 1, tzinfo=UTC)
        result = normalize_timestamp(None, default=default)
        self.assertEqual(result, default)

    def test_none_without_default_returns_recent(self) -> None:
        before = datetime.now(UTC)
        result = normalize_timestamp(None)
        after = datetime.now(UTC)
        self.assertGreaterEqual(result, before)
        self.assertLessEqual(result, after)


class NormalizeResultTests(unittest.TestCase):
    def test_success_variants(self) -> None:
        for val in ("success", "succeeded", "ok", "allowed", "completed"):
            with self.subTest(val=val):
                self.assertEqual(normalize_result(val), "success")

    def test_failure_variants(self) -> None:
        for val in ("failure", "failed", "error", "denied", "blocked"):
            with self.subTest(val=val):
                self.assertEqual(normalize_result(val), "failure")

    def test_passthrough_unknown(self) -> None:
        self.assertEqual(normalize_result("pending"), "pending")

    def test_none_returns_none(self) -> None:
        self.assertIsNone(normalize_result(None))


class NormalizeSeverityTests(unittest.TestCase):
    def test_informational_maps_to_info(self) -> None:
        self.assertEqual(normalize_severity("informational"), "info")

    def test_severe_maps_to_critical(self) -> None:
        self.assertEqual(normalize_severity("severe"), "critical")

    def test_case_insensitive(self) -> None:
        self.assertEqual(normalize_severity("HIGH"), "high")

    def test_none_returns_none(self) -> None:
        self.assertIsNone(normalize_severity(None))


class NormalizeActorTests(unittest.TestCase):
    def test_plain_string(self) -> None:
        self.assertEqual(normalize_actor("user@corp.com"), "user@corp.com")

    def test_dict_prefers_upn(self) -> None:
        d = {"userPrincipalName": "upn@corp.com", "displayName": "Display"}
        self.assertEqual(normalize_actor(d), "upn@corp.com")

    def test_dict_falls_back_to_id(self) -> None:
        d = {"id": "some-id"}
        self.assertEqual(normalize_actor(d), "some-id")

    def test_none_returns_none(self) -> None:
        self.assertIsNone(normalize_actor(None))


class NormalizeTargetTests(unittest.TestCase):
    def test_plain_string(self) -> None:
        self.assertEqual(normalize_target("resource/123"), "resource/123")

    def test_dict_prefers_display_name(self) -> None:
        self.assertEqual(normalize_target({"displayName": "Name", "id": "id-1"}), "Name")

    def test_list_joins_items(self) -> None:
        self.assertEqual(normalize_target(["a", "b", "c"]), "a, b, c")

    def test_empty_list_returns_none(self) -> None:
        self.assertIsNone(normalize_target([]))

    def test_none_returns_none(self) -> None:
        self.assertIsNone(normalize_target(None))


class NormalizeIdTests(unittest.TestCase):
    def test_plain_string(self) -> None:
        self.assertEqual(_normalize_id("abc-123"), "abc-123")

    def test_int_becomes_string(self) -> None:
        self.assertEqual(_normalize_id(42), "42")

    def test_none_returns_none(self) -> None:
        self.assertIsNone(_normalize_id(None))

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(_normalize_id(""))

    def test_dict_not_expanded(self) -> None:
        # _normalize_id should NOT expand dicts like normalize_target does
        result = _normalize_id({"id": "uuid-1"})
        self.assertEqual(result, "{'id': 'uuid-1'}")


class SchemaMapperTests(unittest.TestCase):
    def _make_mapper(self) -> SchemaMapper:
        return SchemaMapper(provider="entra", service="signin", tenant_id="tenant-1")

    def test_basic_mapping(self) -> None:
        mapper = self._make_mapper()
        payload = {
            "createdDateTime": "2024-03-01T12:00:00Z",
            "userPrincipalName": "user@corp.com",
            "appDisplayName": "Office 365",
            "operationType": "signIn",
            "status": {"errorCode": 0},
            "correlationId": "corr-abc",
            "id": "req-xyz",
        }
        event = mapper.map_event(
            payload,
            timestamp_paths=["createdDateTime"],
            actor_paths=["userPrincipalName"],
            action_paths=["operationType"],
            target_paths=["appDisplayName"],
            correlation_paths=["correlationId"],
            request_paths=["id"],
        )
        self.assertEqual(event.provider, "entra")
        self.assertEqual(event.service, "signin")
        self.assertEqual(event.actor, "user@corp.com")
        self.assertEqual(event.action, "signIn")
        self.assertEqual(event.target, "Office 365")
        # IDs should be plain strings, not dict-expanded
        self.assertEqual(event.correlation_id, "corr-abc")
        self.assertEqual(event.request_id, "req-xyz")

    def test_correlation_id_not_expanded_as_target(self) -> None:
        """Verify the bug fix: correlation_id uses _normalize_id, not normalize_target."""
        mapper = self._make_mapper()
        payload = {
            "createdDateTime": "2024-03-01T12:00:00Z",
            "userPrincipalName": "user@corp.com",
            "operationType": "signIn",
            "appDisplayName": "App",
            "correlationId": "flat-id-string",
        }
        event = mapper.map_event(
            payload,
            timestamp_paths=["createdDateTime"],
            actor_paths=["userPrincipalName"],
            action_paths=["operationType"],
            target_paths=["appDisplayName"],
            correlation_paths=["correlationId"],
        )
        self.assertEqual(event.correlation_id, "flat-id-string")

    def test_missing_optional_fields_are_none(self) -> None:
        mapper = self._make_mapper()
        payload = {
            "createdDateTime": "2024-01-01T00:00:00Z",
            "actor": "a@b.com",
            "op": "login",
            "res": "ok",
        }
        event = mapper.map_event(
            payload,
            timestamp_paths=["createdDateTime"],
            actor_paths=["actor"],
            action_paths=["op"],
            target_paths=["missingTarget"],
        )
        self.assertIsNone(event.target)
        self.assertIsNone(event.correlation_id)
        self.assertIsNone(event.request_id)

    def test_tenant_from_payload(self) -> None:
        mapper = SchemaMapper(provider="entra", service="signin")
        payload = {
            "createdDateTime": "2024-01-01T00:00:00Z",
            "actor": "a@b.com",
            "op": "login",
            "tenantId": "override-tenant",
        }
        event = mapper.map_event(
            payload,
            timestamp_paths=["createdDateTime"],
            actor_paths=["actor"],
            action_paths=["op"],
            target_paths=[],
        )
        self.assertEqual(event.tenant_id, "override-tenant")

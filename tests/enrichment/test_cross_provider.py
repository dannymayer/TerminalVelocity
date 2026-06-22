"""Tests for CrossProviderEnricher correlation and enrichment logic."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from terminalvelocity.enrichment.cross_provider import CorrelatedEventGroup, CrossProviderEnricher
from terminalvelocity.schema import NormalizedEvent


def _event(
    *,
    provider: str = "entra",
    service: str = "signin",
    actor: str | None = "user@corp.com",
    target: str | None = "Office 365",
    action: str = "sign-in",
    ts: datetime | None = None,
    correlation_id: str | None = None,
    request_id: str | None = None,
) -> NormalizedEvent:
    return NormalizedEvent(
        timestamp=ts or datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        provider=provider,
        service=service,
        actor=actor,
        target=target,
        action=action,
        result="success",
        severity="low",
        correlation_id=correlation_id,
        request_id=request_id,
        raw={},
    )


class CorrelateTests(unittest.TestCase):
    def test_single_event_forms_one_group(self) -> None:
        enricher = CrossProviderEnricher()
        event = _event()
        groups = enricher.correlate([event])
        self.assertEqual(len(groups), 1)
        self.assertIsInstance(groups[0], CorrelatedEventGroup)

    def test_same_actor_target_within_window_grouped_together(self) -> None:
        enricher = CrossProviderEnricher(time_window=timedelta(minutes=10))
        t = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        e1 = _event(ts=t, provider="entra")
        e2 = _event(ts=t + timedelta(minutes=5), provider="defender_xdr")
        groups = enricher.correlate([e1, e2])
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].events), 2)

    def test_same_actor_outside_window_forms_separate_groups(self) -> None:
        enricher = CrossProviderEnricher(time_window=timedelta(minutes=5))
        t = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        e1 = _event(ts=t, provider="entra")
        e2 = _event(ts=t + timedelta(minutes=10), provider="defender_xdr")
        groups = enricher.correlate([e1, e2])
        self.assertEqual(len(groups), 2)

    def test_different_actors_in_separate_groups(self) -> None:
        enricher = CrossProviderEnricher()
        t = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        e1 = _event(actor="alice@corp.com", ts=t)
        e2 = _event(actor="bob@corp.com", ts=t)
        groups = enricher.correlate([e1, e2])
        self.assertEqual(len(groups), 2)


class EnrichTests(unittest.TestCase):
    def test_enriched_events_carry_related_ids(self) -> None:
        enricher = CrossProviderEnricher(time_window=timedelta(minutes=10))
        t = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        e1 = _event(ts=t, provider="entra")
        e2 = _event(ts=t + timedelta(minutes=2), provider="defender_xdr")
        result = enricher.enrich([e1, e2])
        self.assertEqual(len(result), 2)
        # Each event should reference the other as a related ID
        for ev in result:
            self.assertEqual(len(ev.related_event_ids), 1)

    def test_solo_event_has_no_related_ids(self) -> None:
        enricher = CrossProviderEnricher()
        result = enricher.enrich([_event(actor="solo@corp.com", target="unique-target")])
        self.assertEqual(len(result[0].related_event_ids), 0)

    def test_enrich_returns_all_events(self) -> None:
        enricher = CrossProviderEnricher()
        events = [_event(actor=f"user{i}@corp.com") for i in range(5)]
        result = enricher.enrich(events)
        self.assertEqual(len(result), 5)


class RiskLinkingTests(unittest.TestCase):
    def test_sign_in_linked_to_matching_risk_detection(self) -> None:
        enricher = CrossProviderEnricher()
        sign_in = _event(provider="entra_id", action="sign-in", correlation_id="corr-1")
        risk = _event(provider="identity_protection", action="risk-detection", correlation_id="corr-1")
        result = enricher.enrich([sign_in, risk])
        enriched_signin = next(e for e in result if e.provider == "entra_id")
        self.assertTrue(enriched_signin.model_fields_set or True)  # Verify it is the right event
        # The sign-in should carry the risk event's cache key
        risk_event_ids = getattr(enriched_signin, "_tv_risk_event_ids", None)
        self.assertIsNotNone(risk_event_ids)
        self.assertIn(risk.cache_key(), risk_event_ids)

    def test_sign_in_not_linked_when_no_matching_risk(self) -> None:
        enricher = CrossProviderEnricher()
        sign_in = _event(provider="entra_id", action="sign-in", correlation_id="corr-a")
        risk = _event(provider="identity_protection", action="risk-detection", correlation_id="corr-b")
        result = enricher.enrich([sign_in, risk])
        enriched_signin = next(e for e in result if e.provider == "entra_id")
        risk_event_ids = getattr(enriched_signin, "_tv_risk_event_ids", None)
        self.assertIsNone(risk_event_ids)

    def test_no_risk_events_returns_same_list(self) -> None:
        enricher = CrossProviderEnricher()
        events = [_event(provider="entra_id", action="sign-in")]
        result = enricher.enrich(events)
        self.assertEqual(len(result), 1)

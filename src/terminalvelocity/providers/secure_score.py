"""Microsoft Secure Score provider — daily posture snapshots and control-level changes."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from terminalvelocity.providers.base import BaseProviderAdapter, ProviderCheckpoint, isoformat_z
from terminalvelocity.schema import NormalizedEvent


def _score_delta_severity(delta: float | None) -> str | None:
    """Map a score delta (negative = degradation) to a severity label."""
    if delta is None:
        return None
    if delta <= -10:
        return "critical"
    if delta <= -5:
        return "high"
    if delta < 0:
        return "medium"
    return "info"


class SecureScoreProvider(BaseProviderAdapter):
    """Surface Microsoft Secure Score snapshots and control profile changes.

    Required app permission: SecurityEvents.Read.All
    """

    provider_name = "secure_score"
    provider_scope = "https://graph.microsoft.com/.default"
    connection_test_url = "https://graph.microsoft.com/v1.0/security/secureScores"
    connection_test_params = {"$top": 1}  # noqa: RUF012

    async def fetch(self, start_time: datetime | None = None, end_time: datetime | None = None) -> list[NormalizedEvent]:
        start, end, checkpoint = await self.resolve_window(start_time, end_time)

        score_snapshots = [item async for item in self._iterate_collection(
            "https://graph.microsoft.com/v1.0/security/secureScores",
            scope=self.provider_scope,
            params={
                "$filter": f"createdDateTime ge {isoformat_z(start)} and createdDateTime le {isoformat_z(end)}",
                "$top": 90,
            },
        )]

        control_profiles = [item async for item in self._iterate_collection(
            "https://graph.microsoft.com/v1.0/security/secureScoreControlProfiles",
            scope=self.provider_scope,
            params={"$top": 200},
        )]
        for item in control_profiles:
            item["_tv_source"] = "control_profile"

        raw_events = score_snapshots + control_profiles
        self.cache_raw_payloads(raw_events)
        events = [self.normalize(item) for item in raw_events]
        last_event_time = max((event.timestamp for event in events), default=checkpoint.last_event_time or end.astimezone(UTC))
        await self.checkpoint(ProviderCheckpoint(
            provider=self.provider_name,
            cursor=isoformat_z(end),
            last_event_time=last_event_time,
            metadata={
                "snapshot_count": len(score_snapshots),
                "control_profile_count": len(control_profiles),
            },
        ))
        return events

    def normalize(self, payload: Mapping[str, Any]) -> NormalizedEvent:
        if payload.get("_tv_source") == "control_profile":
            updated = payload.get("lastModifiedDateTime") or payload.get("deprecated") or datetime.now(UTC).isoformat()
            return NormalizedEvent(
                timestamp=updated,
                provider=self.provider_name,
                service="Microsoft Secure Score",
                tenant_id=self.tenant_id,
                actor=None,
                action="SecureScoreControlProfile",
                target=payload.get("title") or payload.get("id"),
                result="success" if payload.get("implementationStatus") in {"implemented", "thirdParty", "customerManagedOperations"} else None,
                severity=payload.get("rank") and "info",
                correlation_id=payload.get("id"),
                request_id=payload.get("id"),
                raw=dict(payload),
            )

        # Score snapshot
        current = payload.get("currentScore")
        max_score = payload.get("maxScore")
        average = payload.get("averageComparativeScores")
        delta: float | None = None
        if isinstance(average, list) and average:
            peer_avg = next((item.get("averageScore") for item in average if item.get("basis") == "AllTenants"), None)
            if peer_avg is not None and current is not None:
                try:
                    delta = float(current) - float(peer_avg)
                except (TypeError, ValueError):
                    delta = None

        score_str = f"{current}/{max_score}" if max_score else str(current)
        return NormalizedEvent(
            timestamp=payload.get("createdDateTime") or datetime.now(UTC).isoformat(),
            provider=self.provider_name,
            service="Microsoft Secure Score",
            tenant_id=payload.get("tenantId") or self.tenant_id,
            actor=None,
            action="SecureScoreSnapshot",
            target=f"tenant score: {score_str}",
            result="success",
            severity=_score_delta_severity(delta),
            correlation_id=payload.get("id"),
            request_id=payload.get("id"),
            raw=dict(payload),
        )

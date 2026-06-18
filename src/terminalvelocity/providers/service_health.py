"""Microsoft 365 Service Health provider — service incidents, advisories, and health overviews."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from terminalvelocity.providers.base import BaseProviderAdapter, ProviderCheckpoint, isoformat_z, map_result
from terminalvelocity.schema import NormalizedEvent

# Map M365 service health status strings to result/severity
_STATUS_TO_RESULT: dict[str, str] = {
    "serviceRestored": "success",
    "postIncidentReviewPublished": "success",
    "resolved": "success",
    "serviceDegradation": "failure",
    "serviceInterruption": "failure",
    "extendedRecovery": "failure",
    "investigating": "failure",
    "restoringService": "failure",
    "verifyingService": "failure",
    "falsePositive": "success",
}

_STATUS_TO_SEVERITY: dict[str, str] = {
    "serviceInterruption": "critical",
    "extendedRecovery": "high",
    "serviceDegradation": "high",
    "investigating": "medium",
    "restoringService": "medium",
    "verifyingService": "low",
    "serviceRestored": "info",
}


class ServiceHealthProvider(BaseProviderAdapter):
    """Fetch active M365 service incidents, advisories, and health overviews.

    Required app permission: ServiceHealth.Read.All
    """

    provider_name = "service_health"
    provider_scope = "https://graph.microsoft.com/.default"
    connection_test_url = "https://graph.microsoft.com/v1.0/admin/serviceAnnouncement/healthOverviews"
    connection_test_params = {"$top": 1}

    async def fetch(self, start_time: datetime | None = None, end_time: datetime | None = None) -> list[NormalizedEvent]:
        start, end, checkpoint = await self.resolve_window(start_time, end_time)
        time_filter = f"lastModifiedDateTime ge {isoformat_z(start)} and lastModifiedDateTime le {isoformat_z(end)}"

        issues = [item async for item in self._iterate_collection(
            "https://graph.microsoft.com/v1.0/admin/serviceAnnouncement/issues",
            scope=self.provider_scope,
            params={"$filter": time_filter, "$top": 100},
        )]

        overviews = [item async for item in self._iterate_collection(
            "https://graph.microsoft.com/v1.0/admin/serviceAnnouncement/healthOverviews",
            scope=self.provider_scope,
            params={"$top": 100},
        )]
        for item in overviews:
            item["_tv_source"] = "health_overview"

        raw_events = issues + overviews
        self.cache_raw_payloads(raw_events)
        events = [self.normalize(item) for item in raw_events]
        last_event_time = max((event.timestamp for event in events), default=checkpoint.last_event_time or end.astimezone(UTC))
        await self.checkpoint(ProviderCheckpoint(
            provider=self.provider_name,
            cursor=isoformat_z(end),
            last_event_time=last_event_time,
            metadata={
                "issue_count": len(issues),
                "overview_count": len(overviews),
            },
        ))
        return events

    def normalize(self, payload: Mapping[str, Any]) -> NormalizedEvent:
        if payload.get("_tv_source") == "health_overview":
            status = str(payload.get("status") or "")
            return NormalizedEvent(
                timestamp=datetime.now(UTC).isoformat(),
                provider=self.provider_name,
                service=str(payload.get("service") or "Microsoft 365"),
                tenant_id=self.tenant_id,
                actor=None,
                action="ServiceHealthOverview",
                target=str(payload.get("service") or payload.get("id") or "Microsoft 365"),
                result=_STATUS_TO_RESULT.get(status) or map_result(status),
                severity=_STATUS_TO_SEVERITY.get(status, "info"),
                correlation_id=payload.get("id"),
                request_id=payload.get("id"),
                raw=dict(payload),
            )

        # Service issue / advisory
        classification = str(payload.get("classification") or "incident").lower()
        status = str(payload.get("status") or "")
        severity = _STATUS_TO_SEVERITY.get(status) or ("critical" if classification == "incident" else "medium")
        return NormalizedEvent(
            timestamp=payload.get("lastModifiedDateTime") or payload.get("startDateTime") or datetime.now(UTC).isoformat(),
            provider=self.provider_name,
            service=str(payload.get("service") or "Microsoft 365"),
            tenant_id=self.tenant_id,
            actor=None,
            action=str(payload.get("title") or payload.get("impactDescription") or "service-issue"),
            target=str(payload.get("service") or payload.get("id") or "Microsoft 365"),
            result=_STATUS_TO_RESULT.get(status) or map_result(status),
            severity=severity,
            correlation_id=payload.get("id"),
            request_id=payload.get("id"),
            raw=dict(payload),
        )

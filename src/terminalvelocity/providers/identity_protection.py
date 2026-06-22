"""Entra Identity Protection provider — risk detections, risky users, risky service principals."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from terminalvelocity.providers.base import BaseProviderAdapter, ProviderCheckpoint, isoformat_z, map_result
from terminalvelocity.schema import NormalizedEvent


class IdentityProtectionProvider(BaseProviderAdapter):
    """Fetch risk detections, risky users, and risky service principals from Entra Identity Protection.

    Required app permissions:
        IdentityRiskEvent.Read.All
        IdentityRiskyUser.Read.All
    """

    provider_name = "identity_protection"
    provider_scope = "https://graph.microsoft.com/.default"
    connection_test_url = "https://graph.microsoft.com/v1.0/identityProtection/riskDetections"
    connection_test_params = {"$top": 1}  # noqa: RUF012

    async def fetch(
        self, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> list[NormalizedEvent]:
        start, end, checkpoint = await self.resolve_window(start_time, end_time)
        time_filter = f"detectedDateTime ge {isoformat_z(start)} and detectedDateTime le {isoformat_z(end)}"

        # Risk detections (sign-in and non-sign-in risk events)
        risk_detections = [
            item
            async for item in self._iterate_collection(
                "https://graph.microsoft.com/v1.0/identityProtection/riskDetections",
                scope=self.provider_scope,
                params={"$filter": time_filter, "$top": 100},
            )
        ]

        # Risky users updated in the window
        risky_user_filter = (
            f"riskLastUpdatedDateTime ge {isoformat_z(start)} and riskLastUpdatedDateTime le {isoformat_z(end)}"
        )
        risky_users = [
            item
            async for item in self._iterate_collection(
                "https://graph.microsoft.com/v1.0/identityProtection/riskyUsers",
                scope=self.provider_scope,
                params={"$filter": risky_user_filter, "$top": 100},
            )
        ]

        # Risky service principals updated in the window
        risky_sp_filter = (
            f"riskLastUpdatedDateTime ge {isoformat_z(start)} and riskLastUpdatedDateTime le {isoformat_z(end)}"
        )
        risky_sps = [
            item
            async for item in self._iterate_collection(
                "https://graph.microsoft.com/v1.0/identityProtection/riskyServicePrincipals",
                scope=self.provider_scope,
                params={"$filter": risky_sp_filter, "$top": 100},
            )
        ]

        # Tag source for normalization dispatch
        for item in risk_detections:
            item["_tv_source"] = "riskDetection"
        for item in risky_users:
            item["_tv_source"] = "riskyUser"
        for item in risky_sps:
            item["_tv_source"] = "riskyServicePrincipal"

        raw_events = risk_detections + risky_users + risky_sps
        self.cache_raw_payloads(raw_events)
        events = [self.normalize(item) for item in raw_events]
        last_event_time = max(
            (event.timestamp for event in events), default=checkpoint.last_event_time or end.astimezone(UTC)
        )
        await self.checkpoint(
            ProviderCheckpoint(
                provider=self.provider_name,
                cursor=isoformat_z(end),
                last_event_time=last_event_time,
                metadata={
                    "sources": ["riskDetections", "riskyUsers", "riskyServicePrincipals"],
                    "risk_detection_count": len(risk_detections),
                    "risky_user_count": len(risky_users),
                    "risky_sp_count": len(risky_sps),
                },
            )
        )
        return events

    def normalize(self, payload: Mapping[str, Any]) -> NormalizedEvent:
        source = payload.get("_tv_source")

        if source == "riskyUser":
            return NormalizedEvent(
                timestamp=payload.get("riskLastUpdatedDateTime") or datetime.now(UTC).isoformat(),
                provider=self.provider_name,
                service="Microsoft Entra ID Identity Protection",
                tenant_id=self.tenant_id,
                actor=payload.get("userPrincipalName") or payload.get("userDisplayName") or payload.get("id"),
                action="risky-user-state-change",
                target=payload.get("userDisplayName") or payload.get("userPrincipalName"),
                result=map_result(payload.get("riskState")),
                severity=payload.get("riskLevel"),
                correlation_id=payload.get("id"),
                request_id=payload.get("id"),
                raw=dict(payload),
            )

        if source == "riskyServicePrincipal":
            return NormalizedEvent(
                timestamp=payload.get("riskLastUpdatedDateTime") or datetime.now(UTC).isoformat(),
                provider=self.provider_name,
                service="Microsoft Entra ID Identity Protection",
                tenant_id=self.tenant_id,
                actor=payload.get("displayName") or payload.get("appId") or payload.get("id"),
                action="risky-service-principal-state-change",
                target=payload.get("displayName") or payload.get("id"),
                result=map_result(payload.get("riskState")),
                severity=payload.get("riskLevel"),
                correlation_id=payload.get("id"),
                request_id=payload.get("id"),
                raw=dict(payload),
            )

        # riskDetection (default)
        return NormalizedEvent(
            timestamp=payload.get("detectedDateTime")
            or payload.get("lastUpdatedDateTime")
            or datetime.now(UTC).isoformat(),
            provider=self.provider_name,
            service="Microsoft Entra ID Identity Protection",
            tenant_id=payload.get("tenantId") or self.tenant_id,
            actor=payload.get("userPrincipalName") or payload.get("userDisplayName") or payload.get("userId"),
            action=str(payload.get("riskEventType") or payload.get("riskType") or "risk-detection"),
            target=payload.get("ipAddress")
            or payload.get("location", {}).get("city")
            or payload.get("resourceDisplayName"),
            result=map_result(payload.get("riskState") or payload.get("detectionTimingType")),
            severity=payload.get("riskLevel"),
            correlation_id=payload.get("correlationId") or payload.get("requestId"),
            request_id=payload.get("id"),
            raw=dict(payload),
        )

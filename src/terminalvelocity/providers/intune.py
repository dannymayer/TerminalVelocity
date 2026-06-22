from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from terminalvelocity.providers.base import (
    BaseProviderAdapter,
    ProviderCheckpoint,
    isoformat_z,
    join_display_names,
    map_result,
)
from terminalvelocity.schema import NormalizedEvent


class IntuneProvider(BaseProviderAdapter):
    provider_name = "intune"
    provider_scope = "https://graph.microsoft.com/.default"
    connection_test_url = "https://graph.microsoft.com/v1.0/deviceManagement/auditEvents"
    connection_test_params = {"$top": 1}  # noqa: RUF012

    async def fetch(
        self, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> list[NormalizedEvent]:
        start, end, checkpoint = await self.resolve_window(start_time, end_time)
        audit_events = [
            item
            async for item in self._iterate_collection(
                self.connection_test_url,
                scope=self.provider_scope,
                params={
                    "$filter": f"activityDateTime ge {isoformat_z(start)} and activityDateTime le {isoformat_z(end)}",
                    "$top": 100,
                },
            )
        ]
        remote_action_audits = [
            item
            async for item in self._iterate_collection(
                "https://graph.microsoft.com/v1.0/deviceManagement/remoteActionAudits",
                scope=self.provider_scope,
                params={
                    "$filter": f"actionDateTime ge {isoformat_z(start)} and actionDateTime le {isoformat_z(end)}",
                    "$top": 100,
                },
            )
        ]
        raw_events = audit_events + remote_action_audits
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
                metadata={"sources": ["deviceManagement/auditEvents", "deviceManagement/remoteActionAudits"]},
            )
        )
        return events

    def normalize(self, payload: Mapping[str, Any]) -> NormalizedEvent:
        if "actionName" in payload or "managedDeviceName" in payload:
            return NormalizedEvent(
                timestamp=payload["actionDateTime"],
                provider=self.provider_name,
                service="Microsoft Intune Remote Action",
                tenant_id=payload.get("tenantId") or self.tenant_id,
                actor=payload.get("userPrincipalName") or payload.get("userName") or payload.get("userId"),
                action=str(payload.get("actionName") or "remote-action"),
                target=payload.get("managedDeviceName") or payload.get("deviceName") or payload.get("managedDeviceId"),
                result=map_result(payload.get("actionState") or payload.get("status")),
                severity=payload.get("deviceStatus"),
                correlation_id=payload.get("correlationId"),
                request_id=payload.get("id"),
                raw=dict(payload),
            )
        actor = payload.get("actor") or {}
        resources = payload.get("resources") or []
        return NormalizedEvent(
            timestamp=payload["activityDateTime"],
            provider=self.provider_name,
            service="Microsoft Intune",
            tenant_id=payload.get("tenantId") or self.tenant_id,
            actor=actor.get("userPrincipalName")
            or actor.get("applicationDisplayName")
            or actor.get("userId")
            or actor.get("applicationId"),
            action=str(payload.get("activityType") or payload.get("displayName") or "unknown"),
            target=join_display_names(resources, "displayName", "resourceId") or payload.get("componentName"),
            result=map_result(
                payload.get("activityResult") or payload.get("result") or payload.get("activityOperationType")
            ),
            severity=payload.get("category"),
            correlation_id=payload.get("correlationId"),
            request_id=payload.get("id"),
            raw=dict(payload),
        )

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from terminalvelocity.providers.base import BaseProviderAdapter, ProviderCheckpoint, isoformat_z, join_display_names, map_result
from terminalvelocity.schema import NormalizedEvent


class EntraIdProvider(BaseProviderAdapter):
    provider_name = "entra_id"
    provider_scope = "https://graph.microsoft.com/.default"
    connection_test_url = "https://graph.microsoft.com/v1.0/auditLogs/signIns"
    connection_test_params = {"$top": 1}

    async def fetch(self, start_time: datetime | None = None, end_time: datetime | None = None) -> list[NormalizedEvent]:
        start, end, checkpoint = await self.resolve_window(start_time, end_time)
        sign_ins = [item async for item in self._iterate_collection("https://graph.microsoft.com/v1.0/auditLogs/signIns", scope=self.provider_scope, params={"$filter": f"createdDateTime ge {isoformat_z(start)} and createdDateTime le {isoformat_z(end)}", "$top": 100})]
        audits = [item async for item in self._iterate_collection("https://graph.microsoft.com/v1.0/auditLogs/directoryAudits", scope=self.provider_scope, params={"$filter": f"activityDateTime ge {isoformat_z(start)} and activityDateTime le {isoformat_z(end)}", "$top": 100})]
        raw_events = sign_ins + audits
        self.cache_raw_payloads(raw_events)
        events = [self.normalize(item) for item in raw_events]
        last_event_time = max((event.timestamp for event in events), default=checkpoint.last_event_time or end.astimezone(UTC))
        await self.checkpoint(ProviderCheckpoint(provider=self.provider_name, cursor=isoformat_z(end), last_event_time=last_event_time, metadata={"sources": ["signIns", "directoryAudits"]}))
        return events

    def normalize(self, payload: Mapping[str, Any]) -> NormalizedEvent:
        if "userPrincipalName" in payload or "conditionalAccessStatus" in payload:
            status = payload.get("status") or {}
            result = "success" if status.get("errorCode") in {0, None} else "failure"
            return NormalizedEvent(timestamp=payload["createdDateTime"], provider=self.provider_name, service="Microsoft Entra ID Sign-In", tenant_id=payload.get("tenantId") or self.tenant_id, actor=payload.get("userPrincipalName") or payload.get("appDisplayName") or payload.get("servicePrincipalName"), action="sign-in", target=payload.get("resourceDisplayName") or payload.get("ipAddress"), result=result, severity=payload.get("riskLevelAggregated") or payload.get("riskState"), correlation_id=payload.get("correlationId"), request_id=payload.get("id"), raw=dict(payload))
        initiated_by = payload.get("initiatedBy") or {}
        actor = (initiated_by.get("user") or {}).get("userPrincipalName") or (initiated_by.get("app") or {}).get("displayName")
        return NormalizedEvent(timestamp=payload["activityDateTime"], provider=self.provider_name, service=str(payload.get("loggedByService") or "Microsoft Entra ID Audit"), tenant_id=payload.get("tenantId") or self.tenant_id, actor=actor, action=str(payload.get("activityDisplayName") or "audit"), target=join_display_names(payload.get("targetResources") or [], "displayName", "userPrincipalName"), result=map_result(payload.get("result")), severity=payload.get("category"), correlation_id=payload.get("correlationId"), request_id=payload.get("id"), raw=dict(payload))

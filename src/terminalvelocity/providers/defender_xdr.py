from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from terminalvelocity.providers.base import BaseProviderAdapter, ProviderCheckpoint, isoformat_z, map_result
from terminalvelocity.schema import NormalizedEvent


class DefenderXdrProvider(BaseProviderAdapter):
    provider_name = "defender_xdr"
    provider_scope = "https://graph.microsoft.com/.default"

    def __init__(self, *, defender_scope: str = "https://api.securitycenter.microsoft.com/.default", defender_base_url: str = "https://api.securitycenter.microsoft.com/api", machine_ids: Sequence[str] | None = None, timeline_event_types: Sequence[str] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.defender_scope = defender_scope
        self.defender_base_url = defender_base_url.rstrip("/")
        self.machine_ids = list(machine_ids or [])
        self.timeline_event_types = list(timeline_event_types or [])
        self.connection_test_url = "https://graph.microsoft.com/v1.0/security/incidents"
        self.connection_test_params = {"$top": 1}

    async def connect(self) -> None:
        await self._get_access_token(self.provider_scope)
        await self._get_access_token(self.defender_scope)
        await self._request_json("GET", self.connection_test_url, scope=self.provider_scope, params=self.connection_test_params)

    async def fetch(self, start_time: datetime | None = None, end_time: datetime | None = None) -> list[NormalizedEvent]:
        start, end, checkpoint = await self.resolve_window(start_time, end_time)
        raw_events: list[dict[str, Any]] = []
        raw_events.extend([item async for item in self._iterate_collection("https://graph.microsoft.com/v1.0/security/incidents", scope=self.provider_scope, params={"$filter": f"lastUpdateDateTime ge {isoformat_z(start)} and lastUpdateDateTime le {isoformat_z(end)}", "$top": 100})])
        raw_events.extend([item async for item in self._iterate_collection("https://graph.microsoft.com/v1.0/security/alerts_v2", scope=self.provider_scope, params={"$filter": f"createdDateTime ge {isoformat_z(start)} and createdDateTime le {isoformat_z(end)}", "$top": 100})])
        machine_ids = self.machine_ids or await self._discover_machine_ids(start)
        for machine_id in machine_ids:
            params: dict[str, Any] = {"$top": 100, "fromValue": isoformat_z(start), "toValue": isoformat_z(end)}
            if self.timeline_event_types:
                params["eventType"] = ",".join(self.timeline_event_types)
            raw_events.extend([item async for item in self._iterate_collection(f"{self.defender_base_url}/machines/{machine_id}/timeline", scope=self.defender_scope, params=params)])
        self.cache_raw_payloads(raw_events)
        events = [self.normalize(item) for item in raw_events]
        last_event_time = max((event.timestamp for event in events), default=checkpoint.last_event_time or end.astimezone(UTC))
        await self.checkpoint(ProviderCheckpoint(provider=self.provider_name, cursor=isoformat_z(end), last_event_time=last_event_time, metadata={"machine_ids": machine_ids}))
        return events

    def normalize(self, payload: Mapping[str, Any]) -> NormalizedEvent:
        if "incidentId" in payload or payload.get("alerts"):
            return NormalizedEvent(timestamp=payload.get("lastUpdateDateTime") or payload.get("createdDateTime"), provider=self.provider_name, service="Microsoft Defender XDR Incident", tenant_id=self.tenant_id, actor=payload.get("assignedTo") or payload.get("lastUpdateSource"), action=f"incident:{payload.get('status', 'updated')}", target=payload.get("displayName") or payload.get("title"), result=map_result(payload.get("status") or payload.get("classification")), severity=payload.get("severity"), correlation_id=str(payload.get("incidentId") or payload.get("id") or "") or None, request_id=payload.get("id"), raw=dict(payload))
        if "serviceSource" in payload or "alertWebUrl" in payload:
            return NormalizedEvent(timestamp=payload.get("createdDateTime") or payload.get("lastUpdateDateTime"), provider=self.provider_name, service=str(payload.get("serviceSource") or "Microsoft Defender XDR Alert"), tenant_id=self.tenant_id, actor=payload.get("assignedTo") or payload.get("detectorId"), action=str(payload.get("category") or payload.get("title") or "alert"), target=payload.get("title") or payload.get("resource") or payload.get("hostStates"), result=map_result(payload.get("status") or payload.get("classification") or payload.get("determination")), severity=payload.get("severity"), correlation_id=payload.get("correlationId") or str(payload.get("incidentId") or "") or None, request_id=payload.get("id"), raw=dict(payload))
        return NormalizedEvent(timestamp=payload.get("timestamp") or payload.get("eventTime"), provider=self.provider_name, service="Microsoft Defender for Endpoint Timeline", tenant_id=self.tenant_id, actor=payload.get("initiatingProcessAccountName") or payload.get("accountName") or payload.get("initiatingProcessAccountUpn"), action=str(payload.get("eventType") or payload.get("actionType") or "timeline"), target=payload.get("fileName") or payload.get("processCommandLine") or payload.get("registryKey") or payload.get("remoteUrl") or payload.get("deviceName"), result=map_result(payload.get("status")), severity=payload.get("severity"), correlation_id=payload.get("reportId") or payload.get("correlationId"), request_id=payload.get("id"), raw=dict(payload))

    async def _discover_machine_ids(self, start_time: datetime) -> list[str]:
        machines = [item async for item in self._iterate_collection(f"{self.defender_base_url}/machines", scope=self.defender_scope, params={"$filter": f"lastSeen ge {isoformat_z(start_time)}", "$top": 100})]
        return [str(item["id"]) for item in machines if item.get("id")]

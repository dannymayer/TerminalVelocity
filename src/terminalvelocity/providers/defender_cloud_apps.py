"""Defender for Cloud Apps provider using Graph alerts and MCAS activities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from terminalvelocity.enrichment.schema_mapper import SchemaMapper, extract_first, normalize_result
from terminalvelocity.providers.base import BaseProvider, MCASClient, ProviderConnectionError
from terminalvelocity.schema import NormalizedEvent


class DefenderCloudAppsProvider(BaseProvider):
    """Collect Defender for Cloud Apps alerts from Graph and activities from MCAS."""

    provider_name = "defender_cloud_apps"
    service_name = "defender-cloud-apps"
    graph_alerts_path = "/v1.0/security/alerts_v2"
    mcas_activities_path = "/api/v1/activities/"

    def __init__(
        self,
        *,
        tenant_id: str,
        access_token: str,
        graph_client=None,
        mcas_client: MCASClient | None = None,
        mcas_api_token: str | None = None,
        mcas_base_url: str | None = None,
        raw_cache_path=None,
        checkpoint_state=None,
    ) -> None:
        super().__init__(
            tenant_id=tenant_id,
            access_token=access_token,
            graph_client=graph_client,
            raw_cache_path=raw_cache_path,
            checkpoint_state=checkpoint_state,
        )
        self.mcas_client = mcas_client
        if self.mcas_client is None and mcas_api_token and mcas_base_url:
            self.mcas_client = MCASClient(api_token=mcas_api_token, base_url=mcas_base_url)

    def connect(self) -> bool:
        try:
            self.graph_client.get(self.graph_alerts_path, params={"$top": 1})
            if self.mcas_client is not None:
                self.mcas_client.post(self.mcas_activities_path, {"limit": 1})
        except Exception as exc:  # pragma: no cover - defensive branch
            raise ProviderConnectionError("Unable to connect to Defender for Cloud Apps upstream APIs") from exc
        return True

    def fetch(self, *, since: datetime, until: datetime) -> list[dict[str, Any]]:
        graph_events = list(
            self.graph_client.iter_collection(
                self.graph_alerts_path,
                params={
                    "$top": 200,
                    "$filter": (
                        "serviceSource eq 'microsoftDefenderForCloudApps' "
                        f"and createdDateTime ge {self.ensure_utc(since).isoformat()} "
                        f"and createdDateTime le {self.ensure_utc(until).isoformat()}"
                    ),
                },
            )
        )
        for event in graph_events:
            event["_tv_source"] = "graph_alert"

        mcas_events: list[dict[str, Any]] = []
        if self.mcas_client is not None:
            payload = self.mcas_client.post(
                self.mcas_activities_path,
                {
                    "filters": {
                        "date": {
                            "gte": int(self.ensure_utc(since).timestamp() * 1000),
                            "lte": int(self.ensure_utc(until).timestamp() * 1000),
                        }
                    },
                    "limit": 500,
                    "sortField": "date",
                    "sortDirection": "asc",
                },
            )
            raw_items = payload.get("data", payload) if isinstance(payload, dict) else payload
            for item in raw_items or []:
                if isinstance(item, dict):
                    item["_tv_source"] = "mcas_activity"
                    mcas_events.append(item)

        combined = [*graph_events, *mcas_events]
        self._last_fetch_count = len(combined)
        self._write_raw_cache(combined)
        latest_event_time = max(
            (
                timestamp
                for timestamp in (
                    self.ensure_utc(event.get("createdDateTime") or event.get("eventDateTime") or event.get("timestamp") or event.get("date"))
                    for event in combined
                )
                if timestamp is not None
            ),
            default=until,
        )
        self._advance_checkpoint(
            last_event_time=latest_event_time,
            metadata={"graph_alert_count": len(graph_events), "mcas_activity_count": len(mcas_events)},
        )
        return combined

    def normalize(self, event: dict[str, Any]) -> NormalizedEvent:
        if event.get("_tv_source") == "mcas_activity":
            normalized = NormalizedEvent(
                timestamp=extract_first(event, "timestamp", "date", "created") or datetime.utcnow().isoformat(),
                provider=self.provider_name,
                service=self.service_name,
                tenant_id=self.tenant_id,
                actor=extract_first(event, "userName", "user.userPrincipalName", "user"),
                action=extract_first(event, "actionType", "activityType") or "CloudActivity",
                target=extract_first(event, "objectName", "appName", "deviceName", "ipAddress"),
                result=normalize_result(extract_first(event, "status", "result")),
                severity=extract_first(event, "severity"),
                correlation_id=extract_first(event, "id", "correlationId", "sessionId"),
                request_id=extract_first(event, "id", "requestId"),
                raw=event,
            )
            self._advance_checkpoint(last_event_time=normalized.timestamp)
            return normalized

        mapper = SchemaMapper(provider=self.provider_name, service=self.service_name, tenant_id=self.tenant_id)
        normalized = mapper.map_event(
            event,
            timestamp_paths=("createdDateTime", "eventDateTime"),
            actor_paths=("userStates.0.userPrincipalName", "userStates.0.accountName", "actorDisplayName"),
            action_paths=("title", "alertWebUrl", "category"),
            target_paths=("serviceSource", "detectionSource", "description"),
            result_paths=("status", "classification"),
            severity_paths=("severity",),
            correlation_paths=("incidentId", "id"),
            request_paths=("id",),
            raw=event,
        )
        self._advance_checkpoint(last_event_time=normalized.timestamp)
        return normalized

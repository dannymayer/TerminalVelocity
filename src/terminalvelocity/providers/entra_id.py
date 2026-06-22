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


class EntraIdProvider(BaseProviderAdapter):
    provider_name = "entra_id"
    provider_scope = "https://graph.microsoft.com/.default"
    connection_test_url = "https://graph.microsoft.com/v1.0/auditLogs/signIns"
    connection_test_params = {"$top": 1}  # noqa: RUF012

    async def fetch(self, start_time: datetime | None = None, end_time: datetime | None = None) -> list[NormalizedEvent]:
        start, end, checkpoint = await self.resolve_window(start_time, end_time)
        time_filter_created = f"createdDateTime ge {isoformat_z(start)} and createdDateTime le {isoformat_z(end)}"
        time_filter_activity = f"activityDateTime ge {isoformat_z(start)} and activityDateTime le {isoformat_z(end)}"

        sign_ins = [item async for item in self._iterate_collection(
            "https://graph.microsoft.com/v1.0/auditLogs/signIns",
            scope=self.provider_scope,
            params={"$filter": time_filter_created, "$top": 100},
        )]
        audits = [item async for item in self._iterate_collection(
            "https://graph.microsoft.com/v1.0/auditLogs/directoryAudits",
            scope=self.provider_scope,
            params={"$filter": time_filter_activity, "$top": 100},
        )]
        sp_sign_ins = [item async for item in self._iterate_collection(
            "https://graph.microsoft.com/v1.0/auditLogs/servicePrincipals",
            scope=self.provider_scope,
            params={"$filter": time_filter_created, "$top": 100},
        )]
        provisioning_logs = [item async for item in self._iterate_collection(
            "https://graph.microsoft.com/v1.0/auditLogs/provisioning",
            scope=self.provider_scope,
            params={"$filter": time_filter_activity, "$top": 100},
        )]

        raw_events = sign_ins + audits + sp_sign_ins + provisioning_logs
        self.cache_raw_payloads(raw_events)
        events = [self.normalize(item) for item in raw_events]
        last_event_time = max((event.timestamp for event in events), default=checkpoint.last_event_time or end.astimezone(UTC))
        await self.checkpoint(ProviderCheckpoint(
            provider=self.provider_name,
            cursor=isoformat_z(end),
            last_event_time=last_event_time,
            metadata={"sources": ["signIns", "directoryAudits", "servicePrincipals", "provisioning"]},
        ))
        return events

    def normalize(self, payload: Mapping[str, Any]) -> NormalizedEvent:
        # Service principal sign-in logs
        if "servicePrincipalId" in payload or "clientCredentialType" in payload:
            status = payload.get("status") or {}
            result = "success" if status.get("errorCode") in {0, None} else "failure"
            return NormalizedEvent(
                timestamp=payload["createdDateTime"],
                provider=self.provider_name,
                service="Microsoft Entra ID Service Principal Sign-In",
                tenant_id=payload.get("tenantId") or self.tenant_id,
                actor=payload.get("servicePrincipalName") or payload.get("servicePrincipalId"),
                action="sp-sign-in",
                target=payload.get("resourceDisplayName") or payload.get("resourceId"),
                result=result,
                severity=payload.get("riskLevel"),
                correlation_id=payload.get("correlationId"),
                request_id=payload.get("id"),
                raw=dict(payload),
            )

        # Provisioning logs
        if "jobId" in payload or "cycleId" in payload or "provisioningAction" in payload:
            initiated_by = payload.get("initiatedBy") or {}
            actor = (
                (initiated_by.get("user") or {}).get("userPrincipalName")
                or (initiated_by.get("servicePrincipal") or {}).get("displayName")
                or initiated_by.get("name")
            )
            source_system = (payload.get("sourceSystem") or {}).get("displayName") or ""
            target_system = (payload.get("targetSystem") or {}).get("displayName") or ""
            service_label = "Microsoft Entra ID Provisioning"
            if source_system or target_system:
                service_label = f"Microsoft Entra ID Provisioning ({source_system} → {target_system})"
            status_info = payload.get("statusInfo") or {}
            return NormalizedEvent(
                timestamp=payload["activityDateTime"],
                provider=self.provider_name,
                service=service_label,
                tenant_id=payload.get("tenantId") or self.tenant_id,
                actor=actor,
                action=str(payload.get("provisioningAction") or payload.get("action") or "provisioning"),
                target=(payload.get("targetIdentity") or {}).get("displayName") or (payload.get("targetIdentity") or {}).get("id"),
                result=map_result(status_info.get("status") or payload.get("result")),
                severity=payload.get("severity"),
                correlation_id=payload.get("correlationId") or payload.get("changeId"),
                request_id=payload.get("id"),
                raw=dict(payload),
            )

        # User sign-in logs — use riskLevelDuringSignIn preferentially for richer risk context
        if "userPrincipalName" in payload or "conditionalAccessStatus" in payload:
            status = payload.get("status") or {}
            result = "success" if status.get("errorCode") in {0, None} else "failure"
            severity = (
                payload.get("riskLevelDuringSignIn")
                or payload.get("riskLevelAggregated")
                or payload.get("riskState")
            )
            return NormalizedEvent(
                timestamp=payload["createdDateTime"],
                provider=self.provider_name,
                service="Microsoft Entra ID Sign-In",
                tenant_id=payload.get("tenantId") or self.tenant_id,
                actor=payload.get("userPrincipalName") or payload.get("appDisplayName") or payload.get("servicePrincipalName"),
                action="sign-in",
                target=payload.get("resourceDisplayName") or payload.get("ipAddress"),
                result=result,
                severity=severity,
                correlation_id=payload.get("correlationId"),
                request_id=payload.get("id"),
                raw=dict(payload),
            )

        # Directory audit logs
        initiated_by = payload.get("initiatedBy") or {}
        actor = (initiated_by.get("user") or {}).get("userPrincipalName") or (initiated_by.get("app") or {}).get("displayName")
        return NormalizedEvent(
            timestamp=payload["activityDateTime"],
            provider=self.provider_name,
            service=str(payload.get("loggedByService") or "Microsoft Entra ID Audit"),
            tenant_id=payload.get("tenantId") or self.tenant_id,
            actor=actor,
            action=str(payload.get("activityDisplayName") or "audit"),
            target=join_display_names(payload.get("targetResources") or [], "displayName", "userPrincipalName"),
            result=map_result(payload.get("result")),
            severity=payload.get("category"),
            correlation_id=payload.get("correlationId"),
            request_id=payload.get("id"),
            raw=dict(payload),
        )

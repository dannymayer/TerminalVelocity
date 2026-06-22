from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from terminalvelocity.providers.base import BaseProviderAdapter, ProviderCheckpoint, isoformat_z, map_result
from terminalvelocity.schema import NormalizedEvent

LOGGER = logging.getLogger(__name__)


class UnifiedAuditLogProvider(BaseProviderAdapter):
    provider_name = "unified_audit_log"
    provider_scope = "https://manage.office.com/.default"

    def __init__(
        self, *, content_types: Sequence[str] | None = None, auto_start_subscriptions: bool = False, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self.content_types = tuple(
            content_types
            or (
                "Audit.AzureActiveDirectory",
                "Audit.Exchange",
                "Audit.General",
                "Audit.SharePoint",
                "DLP.All",
                "Audit.PowerBI",
                "MicrosoftForms",
            )
        )
        self.auto_start_subscriptions = auto_start_subscriptions
        self.connection_test_url = self._management_url("subscriptions/list")

    async def connect(self) -> None:
        subscriptions = await self._request_json("GET", self.connection_test_url, scope=self.provider_scope)
        active_types = {item.get("contentType") for item in subscriptions if isinstance(item, dict)}
        if self.auto_start_subscriptions:
            for content_type in self.content_types:
                if content_type not in active_types:
                    LOGGER.info("Starting missing UAL subscription for %s", content_type)
                    await self._request(
                        "POST",
                        self._management_url("subscriptions/start"),
                        scope=self.provider_scope,
                        params={"contentType": content_type},
                    )
        LOGGER.info("Connected to %s", self.provider_name)

    async def fetch(
        self, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> list[NormalizedEvent]:
        start, end, checkpoint = await self.resolve_window(start_time, end_time)
        existing_markers = checkpoint.metadata.get("content_markers", {})
        next_markers = dict(existing_markers)
        events: list[NormalizedEvent] = []
        max_time = checkpoint.last_event_time
        for content_type in self.content_types:
            descriptors = (
                await self._request_json(
                    "GET",
                    self._management_url("subscriptions/content"),
                    scope=self.provider_scope,
                    params={"contentType": content_type, "startTime": isoformat_z(start), "endTime": isoformat_z(end)},
                )
                or []
            )
            descriptor_ids = [item.get("contentId") or item.get("contentUri") for item in descriptors]
            last_marker = existing_markers.get(content_type)
            process_new = last_marker is None or last_marker not in descriptor_ids
            for descriptor in descriptors:
                content_id = descriptor.get("contentId") or descriptor.get("contentUri")
                if not process_new:
                    if content_id == last_marker:
                        process_new = True
                    continue
                payload = await self._request_json("GET", descriptor["contentUri"], scope=self.provider_scope)
                raw_records = payload if isinstance(payload, list) else [payload]
                self.cache_raw_payloads(raw_records)
                for raw_record in raw_records:
                    event = self.normalize(raw_record)
                    events.append(event)
                    if max_time is None or event.timestamp > max_time:
                        max_time = event.timestamp
                if content_id:
                    next_markers[content_type] = content_id
        await self.checkpoint(
            ProviderCheckpoint(
                provider=self.provider_name,
                cursor=isoformat_z(end),
                last_event_time=max_time or end.astimezone(UTC),
                metadata={"content_markers": next_markers},
            )
        )
        return events

    def normalize(self, payload: Mapping[str, Any]) -> NormalizedEvent:
        workload = str(payload.get("Workload") or payload.get("RecordType") or "")
        operation = str(payload.get("Operation") or payload.get("Activity") or "unknown")

        # DLP policy match events
        if (
            workload == "SecurityComplianceCenter"
            or payload.get("RecordType") in {11, "DLP"}
            or "DlpSharePointClassificationInfo" in payload
            or "PolicyDetails" in payload
        ):
            policy_details = payload.get("PolicyDetails") or [{}]
            policy_name = (policy_details[0] if isinstance(policy_details, list) and policy_details else {}).get(
                "PolicyName"
            ) or operation
            sensitive_types = payload.get("SensitiveInfoTypeData") or payload.get("ClassificationRuleDetails") or []
            target = payload.get("ObjectId") or payload.get("ItemName") or payload.get("SiteUrl")
            return NormalizedEvent(
                timestamp=payload["CreationTime"],
                provider=self.provider_name,
                service="Microsoft Purview DLP",
                tenant_id=payload.get("OrganizationId") or self.tenant_id,
                actor=payload.get("UserId") or payload.get("UserKey"),
                action=policy_name,
                target=target,
                result=map_result(
                    payload.get("ResultStatus") or payload.get("EnforcementMode") or payload.get("Action")
                ),
                severity="high" if sensitive_types else None,
                correlation_id=payload.get("CorrelationId"),
                request_id=payload.get("Id") or payload.get("RequestId"),
                raw=dict(payload),
            )

        # Power BI events
        if workload == "PowerBI" or payload.get("RecordType") in {20, "PowerBIAudit"}:
            dataset = payload.get("DatasetName") or payload.get("ReportName") or payload.get("WorkspaceName")
            return NormalizedEvent(
                timestamp=payload["CreationTime"],
                provider=self.provider_name,
                service="Microsoft Power BI",
                tenant_id=payload.get("OrganizationId") or self.tenant_id,
                actor=payload.get("UserId") or payload.get("UserKey"),
                action=operation,
                target=dataset or payload.get("ObjectId"),
                result=map_result(payload.get("ResultStatus") or payload.get("Status")),
                severity=payload.get("Severity"),
                correlation_id=payload.get("CorrelationId"),
                request_id=payload.get("Id") or payload.get("RequestId"),
                raw=dict(payload),
            )

        # Microsoft Forms events
        if workload == "MicrosoftForms" or payload.get("RecordType") in {62, "MicrosoftForms"}:
            form_name = payload.get("FormName") or payload.get("ObjectId")
            return NormalizedEvent(
                timestamp=payload["CreationTime"],
                provider=self.provider_name,
                service="Microsoft Forms",
                tenant_id=payload.get("OrganizationId") or self.tenant_id,
                actor=payload.get("UserId") or payload.get("UserKey"),
                action=operation,
                target=form_name or payload.get("ItemName") or payload.get("SiteUrl"),
                result=map_result(payload.get("ResultStatus") or payload.get("Status")),
                severity=payload.get("Severity"),
                correlation_id=payload.get("CorrelationId"),
                request_id=payload.get("Id") or payload.get("RequestId"),
                raw=dict(payload),
            )

        # Default — all other UAL workloads
        return NormalizedEvent(
            timestamp=payload["CreationTime"],
            provider=self.provider_name,
            service=str(workload or "Microsoft Purview"),
            tenant_id=payload.get("OrganizationId") or self.tenant_id,
            actor=payload.get("UserId") or payload.get("UserKey") or payload.get("ClientIP"),
            action=operation,
            target=payload.get("ObjectId") or payload.get("ItemName") or payload.get("SiteUrl"),
            result=map_result(payload.get("ResultStatus") or payload.get("Status")),
            severity=payload.get("Severity"),
            correlation_id=payload.get("CorrelationId"),
            request_id=payload.get("Id") or payload.get("RequestId"),
            raw=dict(payload),
        )

    def _management_url(self, operation: str) -> str:
        return f"https://manage.office.com/api/v1.0/{self.tenant_id}/activity/feed/{operation}"

"""Exchange Online provider covering admin audit events and mail-flow traces."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from terminalvelocity.enrichment.schema_mapper import SchemaMapper, extract_first, normalize_result
from terminalvelocity.providers.base import AuditLogQueryProvider, ProviderConnectionError
from terminalvelocity.schema import NormalizedEvent


class ExchangeOnlineProvider(AuditLogQueryProvider):
    """Collect Exchange Online admin audit records plus mail-flow telemetry.

    Graph does not expose classic Exchange message trace directly, so this adapter
    supplements auditLog query data with the security collaboration
    ``/beta/security/collaboration/analyzedEmails`` feed as the closest Graph
    mail-flow signal that remains accessible through Microsoft Graph.
    """

    provider_name = "exchange_online"
    service_name = "exchange-online"
    service_filters = ("Exchange",)
    record_type_filters = (
        "exchangeAdmin",
        "exchangeAggregatedOperation",
        "exchangeItem",
    )
    message_trace_path = "/beta/security/collaboration/analyzedEmails"

    def connect(self) -> bool:
        if not super().connect():
            return False
        try:
            self.graph_client.get(self.message_trace_path, params={"$top": 1})
        except Exception as exc:  # pragma: no cover - defensive branch
            raise ProviderConnectionError("Exchange Online message trace endpoint is unreachable") from exc
        return True

    def fetch(self, *, since: datetime, until: datetime) -> list[dict[str, Any]]:
        records = super().fetch(since=since, until=until)
        message_trace_events = list(
            self.graph_client.iter_collection(
                self.message_trace_path,
                params={
                    "$top": 200,
                    "$filter": (
                        f"deliveredDateTime ge {self.ensure_utc(since).isoformat()} "
                        f"and deliveredDateTime le {self.ensure_utc(until).isoformat()}"
                    ),
                },
            )
        )
        for event in message_trace_events:
            event["_tv_source"] = "message_trace"
        combined = [*records, *message_trace_events]
        self._last_fetch_count = len(combined)
        self._write_raw_cache(message_trace_events)
        latest_event_time = max(
            (
                timestamp
                for timestamp in (
                    self.ensure_utc(event.get("createdDateTime") or event.get("activityDateTime") or event.get("deliveredDateTime"))
                    for event in combined
                )
                if timestamp is not None
            ),
            default=until,
        )
        self._advance_checkpoint(
            last_event_time=latest_event_time,
            metadata={"message_trace_count": len(message_trace_events)},
        )
        return combined

    def normalize(self, event: dict[str, Any]) -> NormalizedEvent:
        if event.get("_tv_source") == "message_trace":
            actor = extract_first(event, "recipient.emailAddress", "recipient.user.email", "recipient")
            sender = extract_first(event, "sender.emailAddress", "sender", "from.emailAddress")
            subject = extract_first(event, "subject")
            target = subject or sender
            status = extract_first(event, "status", "verdict")
            normalized = NormalizedEvent(
                timestamp=extract_first(event, "deliveredDateTime", "receivedDateTime") or datetime.utcnow().isoformat(),
                provider=self.provider_name,
                service=self.service_name,
                tenant_id=self.tenant_id,
                actor=actor,
                action="MessageTrace",
                target=target,
                result=normalize_result(status),
                severity=extract_first(event, "verdict"),
                correlation_id=extract_first(event, "networkMessageId", "id", "relatedCampaignId"),
                request_id=extract_first(event, "internetMessageId", "id"),
                raw=event,
            )
            self._advance_checkpoint(last_event_time=normalized.timestamp)
            return normalized

        audit_data = event.get("auditData", {})
        if isinstance(audit_data, str):
            try:
                audit_data = json.loads(audit_data)
            except json.JSONDecodeError:
                audit_data = {"auditData": audit_data}
        mapper = SchemaMapper(provider=self.provider_name, service=self.service_name, tenant_id=self.tenant_id)
        normalized = mapper.map_event(
            {**event, "auditData": audit_data},
            timestamp_paths=("createdDateTime", "activityDateTime", "auditData.CreationTime"),
            actor_paths=("userPrincipalName", "userId", "auditData.UserId", "initiatedBy.user.userPrincipalName"),
            action_paths=("operation", "activityDisplayName", "auditData.Operation"),
            target_paths=(
                "objectId",
                "auditData.ObjectId",
                "auditData.DestMailboxOwnerUPN",
                "auditData.Parameters.Name",
            ),
            result_paths=("resultStatus", "status.errorCode", "auditData.ResultStatus"),
            severity_paths=("auditData.Severity", "severity"),
            correlation_paths=("correlationId", "auditData.ExternalAccess", "auditData.ClientProcessName"),
            request_paths=("id", "requestId", "auditData.Id"),
            raw=event,
        )
        self._advance_checkpoint(last_event_time=normalized.timestamp)
        return normalized

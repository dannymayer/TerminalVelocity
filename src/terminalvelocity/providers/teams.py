"""Microsoft Teams audit and compliance provider backed by Graph auditLog queries."""

from __future__ import annotations

import json

from terminalvelocity.enrichment.schema_mapper import SchemaMapper, extract_first
from terminalvelocity.providers.base import AuditLogQueryProvider
from terminalvelocity.schema import NormalizedEvent


class TeamsProvider(AuditLogQueryProvider):
    """Collect Microsoft Teams admin, meeting, messaging, and compliance events."""

    provider_name = "teams"
    service_name = "microsoft-teams"
    service_filters = ("Teams",)
    record_type_filters = (
        "microsoftTeams",
        "microsoftTeamsAdmin",
        "microsoftTeamsDevice",
        "microsoftTeamsMessage",
    )

    def normalize(self, event: dict[str, object]) -> NormalizedEvent:
        audit_data = event.get("auditData", {})
        if isinstance(audit_data, str):
            try:
                audit_data = json.loads(audit_data)
            except json.JSONDecodeError:
                audit_data = {"auditData": audit_data}
        payload = {**event, "auditData": audit_data}
        mapper = SchemaMapper(provider=self.provider_name, service=self.service_name, tenant_id=self.tenant_id)
        normalized = mapper.map_event(
            payload,
            timestamp_paths=("createdDateTime", "activityDateTime", "auditData.CreationTime"),
            actor_paths=("userPrincipalName", "userId", "auditData.UserId", "auditData.Actor"),
            action_paths=("operation", "activityDisplayName", "auditData.Operation"),
            target_paths=(
                "auditData.TeamName",
                "auditData.ChannelName",
                "objectId",
                "auditData.ItemName",
            ),
            result_paths=("resultStatus", "auditData.ResultStatus", "status.errorCode"),
            severity_paths=("severity", "auditData.Severity"),
            correlation_paths=("correlationId", "auditData.CorrelationId", "auditData.CallId"),
            request_paths=("id", "requestId", "auditData.Id"),
            raw=payload,
        )
        if normalized.target and extract_first(payload, "auditData.ChannelName"):
            normalized = normalized.model_copy(
                update={
                    "target": f"{extract_first(payload, 'auditData.TeamName') or normalized.target}/{extract_first(payload, 'auditData.ChannelName')}",
                }
            )
        self._advance_checkpoint(last_event_time=normalized.timestamp)
        return normalized

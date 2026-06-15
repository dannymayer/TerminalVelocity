"""SharePoint and OneDrive audit provider backed by Graph auditLog queries."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from terminalvelocity.enrichment.schema_mapper import SchemaMapper, extract_first
from terminalvelocity.providers.base import AuditLogQueryProvider
from terminalvelocity.schema import NormalizedEvent


class SharePointOneDriveProvider(AuditLogQueryProvider):
    """Collect SharePoint and OneDrive file, sharing, and admin audit events."""

    provider_name = "sharepoint_onedrive"
    service_name = "sharepoint-onedrive"
    service_filters = ("SharePoint", "OneDrive")
    record_type_filters = (
        "sharePoint",
        "sharePointFileOperation",
        "sharePointSharingOperation",
        "oneDrive",
    )

    def normalize(self, event: dict[str, Any]) -> NormalizedEvent:
        audit_data = event.get("auditData", {})
        if isinstance(audit_data, str):
            try:
                audit_data = json.loads(audit_data)
            except json.JSONDecodeError:
                audit_data = {"auditData": audit_data}
        mapper = SchemaMapper(provider=self.provider_name, service=self.service_name, tenant_id=self.tenant_id)
        target = extract_first(
            {**event, "auditData": audit_data},
            "auditData.ObjectId",
            "auditData.SourceFileName",
            "auditData.SourceRelativeUrl",
            "objectId",
        )
        normalized = mapper.map_event(
            {**event, "auditData": audit_data},
            timestamp_paths=("createdDateTime", "activityDateTime", "auditData.CreationTime"),
            actor_paths=("userPrincipalName", "userId", "auditData.UserId"),
            action_paths=("operation", "activityDisplayName", "auditData.Operation"),
            target_paths=("auditData.ObjectId", "auditData.SourceRelativeUrl", "objectId"),
            result_paths=("resultStatus", "auditData.ResultStatus", "status.errorCode"),
            severity_paths=("severity", "auditData.Severity"),
            correlation_paths=("correlationId", "auditData.CorrelationId", "auditData.InterSystemsId"),
            request_paths=("id", "requestId", "auditData.Id"),
            raw=event,
        )
        if not normalized.target:
            normalized = normalized.model_copy(update={"target": target})
        self._advance_checkpoint(last_event_time=normalized.timestamp)
        return normalized

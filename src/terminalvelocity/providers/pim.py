"""Privileged Identity Management (PIM) provider — role activation, assignment, and approval events."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from terminalvelocity.providers.base import BaseProviderAdapter, ProviderCheckpoint, isoformat_z, map_result
from terminalvelocity.schema import NormalizedEvent

_PIM_STATUS_MAP: dict[str, str] = {
    "granted": "success",
    "provisionedlocally": "success",
    "provisionedinazuread": "success",
    "denied": "failure",
    "failed": "failure",
    "canceled": "failure",
    "revoked": "failure",
}


class PIMProvider(BaseProviderAdapter):
    """Fetch PIM role assignment requests, active assignments, and eligibility schedules.

    PIM events also flow through Entra directoryAudits (loggedByService=PIM), but
    this provider surfaces the richer dedicated PIM endpoints that include
    justification text, ticket numbers, approver identity, and schedule metadata.

    Required app permissions:
        PrivilegedEligibilitySchedule.Read.AzureADGroup
        RoleAssignmentSchedule.Read.Directory
    """

    provider_name = "pim"
    provider_scope = "https://graph.microsoft.com/.default"
    connection_test_url = (
        "https://graph.microsoft.com/v1.0/identityGovernance/privilegedAccess/aadRoles/roleAssignmentRequests"
    )
    connection_test_params = {"$top": 1}  # noqa: RUF012

    async def fetch(
        self, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> list[NormalizedEvent]:
        start, end, checkpoint = await self.resolve_window(start_time, end_time)
        time_filter = f"requestedDateTime ge {isoformat_z(start)} and requestedDateTime le {isoformat_z(end)}"

        # Role assignment requests (activation, deactivation, assignment, removal)
        requests = [
            item
            async for item in self._iterate_collection(
                "https://graph.microsoft.com/v1.0/identityGovernance/privilegedAccess/aadRoles/roleAssignmentRequests",
                scope=self.provider_scope,
                params={"$filter": time_filter, "$top": 100, "$expand": "roleDefinition,subject"},
            )
        ]
        for item in requests:
            item["_tv_source"] = "roleAssignmentRequest"

        # Current active role assignments (snapshot — no time filter available)
        assignments = [
            item
            async for item in self._iterate_collection(
                "https://graph.microsoft.com/v1.0/identityGovernance/privilegedAccess/aadRoles/roleAssignments",
                scope=self.provider_scope,
                params={"$top": 100, "$expand": "roleDefinition,subject"},
            )
        ]
        for item in assignments:
            item["_tv_source"] = "roleAssignment"

        raw_events = requests + assignments
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
                    "request_count": len(requests),
                    "assignment_count": len(assignments),
                },
            )
        )
        return events

    def normalize(self, payload: Mapping[str, Any]) -> NormalizedEvent:
        source = payload.get("_tv_source")

        role_def = payload.get("roleDefinition") or {}
        role_name = role_def.get("displayName") or payload.get("roleDefinitionId") or "Unknown Role"

        subject = payload.get("subject") or {}
        actor = (
            subject.get("userPrincipalName")
            or subject.get("displayName")
            or subject.get("id")
            or payload.get("subjectId")
        )

        if source == "roleAssignmentRequest":
            assignment_type = str(payload.get("assignmentState") or payload.get("type") or "")
            request_type = str(payload.get("requestType") or payload.get("action") or "role-request")
            reason = payload.get("reason") or payload.get("justification")
            ticket = payload.get("ticketInfo") or {}
            ticket_ref = ticket.get("ticketNumber") if isinstance(ticket, dict) else None

            action = f"pim:{request_type.lower()}"
            if assignment_type:
                action = f"pim:{request_type.lower()}:{assignment_type.lower()}"

            schedule = payload.get("schedule") or {}
            expiry = (schedule.get("expiration") or {}).get("endDateTime") if isinstance(schedule, dict) else None

            return NormalizedEvent(
                timestamp=payload.get("requestedDateTime") or datetime.now(UTC).isoformat(),
                provider=self.provider_name,
                service="Microsoft Entra ID PIM",
                tenant_id=self.tenant_id,
                actor=actor,
                action=action,
                target=role_name,
                result=_PIM_STATUS_MAP.get(str(payload.get("status") or payload.get("requestStatus") or "").lower())
                or map_result(payload.get("status") or payload.get("requestStatus")),
                severity="high" if "Global Administrator" in role_name else "medium",
                correlation_id=payload.get("id"),
                request_id=payload.get("id"),
                raw={
                    **dict(payload),
                    "_tv_reason": reason,
                    "_tv_ticket_ref": ticket_ref,
                    "_tv_expiry": expiry,
                },
            )

        # roleAssignment snapshot
        return NormalizedEvent(
            timestamp=payload.get("createdDateTime") or payload.get("startDateTime") or datetime.now(UTC).isoformat(),
            provider=self.provider_name,
            service="Microsoft Entra ID PIM",
            tenant_id=self.tenant_id,
            actor=actor,
            action="pim:active-assignment",
            target=role_name,
            result="success",
            severity="high" if "Global Administrator" in role_name else "low",
            correlation_id=payload.get("id"),
            request_id=payload.get("id"),
            raw=dict(payload),
        )

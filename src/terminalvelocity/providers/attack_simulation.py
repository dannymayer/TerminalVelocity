"""Attack Simulation Training provider — phishing simulation results per user."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from terminalvelocity.providers.base import BaseProviderAdapter, ProviderCheckpoint, isoformat_z, map_result
from terminalvelocity.schema import NormalizedEvent

# Map simulation event types to result classifications
_SIM_EVENT_TO_RESULT: dict[str, str] = {
    "CredentialsEntered": "failure",
    "CredentialHarvesting": "failure",
    "AttachmentOpened": "failure",
    "LinkClicked": "failure",
    "MacroEnabled": "failure",
    "OOFReplyBounce": "failure",
    "Reported": "success",
    "SimulationEmailSent": "success",
    "Simulated": "success",
}


def _compute_severity(sim_events: list[dict[str, Any]]) -> str | None:
    """Determine severity from the most damaging simulation event encountered."""
    critical_events = {"CredentialsEntered", "CredentialHarvesting", "MacroEnabled"}
    high_events = {"AttachmentOpened", "LinkClicked"}
    event_types = {str(e.get("simulationEventType") or e.get("eventName") or "") for e in sim_events}
    if event_types & critical_events:
        return "critical"
    if event_types & high_events:
        return "high"
    if event_types:
        return "low"
    return None


class AttackSimulationProvider(BaseProviderAdapter):
    """Fetch phishing/credential harvest simulation results from Attack Simulation Training.

    Required app permission: AttackSimulation.Read.All
    """

    provider_name = "attack_simulation"
    provider_scope = "https://graph.microsoft.com/.default"
    connection_test_url = "https://graph.microsoft.com/v1.0/security/attackSimulation/simulations"
    connection_test_params = {"$top": 1}  # noqa: RUF012

    async def fetch(self, start_time: datetime | None = None, end_time: datetime | None = None) -> list[NormalizedEvent]:
        start, end, checkpoint = await self.resolve_window(start_time, end_time)
        time_filter = f"launchDateTime ge {isoformat_z(start)} and launchDateTime le {isoformat_z(end)}"

        simulations = [item async for item in self._iterate_collection(
            "https://graph.microsoft.com/v1.0/security/attackSimulation/simulations",
            scope=self.provider_scope,
            params={"$filter": time_filter, "$top": 100},
        )]

        raw_events: list[dict[str, Any]] = []
        for simulation in simulations:
            sim_id = simulation.get("id")
            sim_name = simulation.get("displayName") or sim_id
            if not sim_id:
                continue
            users = [item async for item in self._iterate_collection(
                f"https://graph.microsoft.com/v1.0/security/attackSimulation/simulations/{sim_id}/simulationUsers",
                scope=self.provider_scope,
                params={"$top": 200},
            )]
            for user in users:
                user["_tv_simulation_id"] = sim_id
                user["_tv_simulation_name"] = sim_name
                user["_tv_simulation_technique"] = simulation.get("attackTechnique") or simulation.get("simulationAttackType")
                raw_events.append(user)

        self.cache_raw_payloads(raw_events)
        events = [self.normalize(item) for item in raw_events]
        last_event_time = max((event.timestamp for event in events), default=checkpoint.last_event_time or end.astimezone(UTC))
        await self.checkpoint(ProviderCheckpoint(
            provider=self.provider_name,
            cursor=isoformat_z(end),
            last_event_time=last_event_time,
            metadata={
                "simulation_count": len(simulations),
                "user_result_count": len(raw_events),
            },
        ))
        return events

    def normalize(self, payload: Mapping[str, Any]) -> NormalizedEvent:
        sim_events: list[dict[str, Any]] = payload.get("simulationEvents") or payload.get("events") or []
        sim_name = str(payload.get("_tv_simulation_name") or payload.get("simulationDisplayName") or "simulation")
        technique = str(payload.get("_tv_simulation_technique") or payload.get("attackTechnique") or "")

        # Determine most damaging event type for result mapping
        worst_result: str | None = None
        for sim_evt in sim_events:
            evt_type = str(sim_evt.get("simulationEventType") or sim_evt.get("eventName") or "")
            mapped = _SIM_EVENT_TO_RESULT.get(evt_type)
            if mapped == "failure":
                worst_result = "failure"
                break
            if mapped == "success" and worst_result is None:
                worst_result = "success"

        user_info = payload.get("simulationUser") or payload.get("user") or {}
        if isinstance(user_info, dict):
            actor = user_info.get("email") or user_info.get("userPrincipalName") or user_info.get("displayName")
        else:
            actor = str(user_info) if user_info else None
        actor = actor or payload.get("userPrincipalName") or payload.get("email")

        action = f"{sim_name}" + (f" ({technique})" if technique else "")

        return NormalizedEvent(
            timestamp=payload.get("reportedPhishDateTime") or payload.get("lastEventDateTime") or payload.get("assignedDateTime") or datetime.now(UTC).isoformat(),
            provider=self.provider_name,
            service="Microsoft Attack Simulation Training",
            tenant_id=self.tenant_id,
            actor=actor,
            action=action,
            target=sim_name,
            result=worst_result or map_result(payload.get("status") or payload.get("simulationUserStatus")),
            severity=_compute_severity(sim_events),
            correlation_id=payload.get("_tv_simulation_id") or payload.get("simulationId"),
            request_id=payload.get("id") or payload.get("userId"),
            raw=dict(payload),
        )

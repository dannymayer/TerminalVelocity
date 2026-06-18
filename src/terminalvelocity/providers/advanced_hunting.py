"""Microsoft 365 Defender Advanced Hunting provider — KQL queries across hunting tables."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from terminalvelocity.providers.base import BaseProviderAdapter, ProviderCheckpoint, isoformat_z, map_result
from terminalvelocity.schema import NormalizedEvent

# Default KQL queries covering the most useful threat-hunting tables.
# Each tuple is (table_name, kql_query_template) where {start} and {end} are
# replaced at fetch time with ISO 8601 UTC strings.
_DEFAULT_QUERIES: tuple[tuple[str, str], ...] = (
    (
        "IdentityLogonEvents",
        "IdentityLogonEvents"
        " | where Timestamp between (datetime({start}) .. datetime({end}))"
        " | project Timestamp, AccountUpn, AccountName, ActionType, Application, FailureReason,"
        "   IPAddress, DeviceName, ReportId",
    ),
    (
        "DeviceEvents",
        "DeviceEvents"
        " | where Timestamp between (datetime({start}) .. datetime({end}))"
        " | project Timestamp, DeviceName, ActionType, InitiatingProcessAccountUpn,"
        "   FileName, FolderPath, ProcessCommandLine, RemoteUrl, ReportId",
    ),
    (
        "EmailEvents",
        "EmailEvents"
        " | where Timestamp between (datetime({start}) .. datetime({end}))"
        " | project Timestamp, SenderFromAddress, RecipientEmailAddress, Subject,"
        "   DeliveryAction, ThreatTypes, ConfidenceLevel, NetworkMessageId, ReportId",
    ),
    (
        "CloudAppEvents",
        "CloudAppEvents"
        " | where Timestamp between (datetime({start}) .. datetime({end}))"
        " | project Timestamp, AccountId, AccountDisplayName, ActionType, Application,"
        "   ObjectName, IPAddress, ReportId",
    ),
)

# Fields used to extract normalized values per table
_TABLE_FIELD_MAP: dict[str, dict[str, tuple[str, ...]]] = {
    "IdentityLogonEvents": {
        "actor": ("AccountUpn", "AccountName"),
        "action": ("ActionType",),
        "target": ("Application", "DeviceName"),
        "result": ("FailureReason",),
        "correlation": ("ReportId",),
    },
    "DeviceEvents": {
        "actor": ("InitiatingProcessAccountUpn",),
        "action": ("ActionType",),
        "target": ("FileName", "ProcessCommandLine", "RemoteUrl", "DeviceName"),
        "result": (),
        "correlation": ("ReportId",),
    },
    "EmailEvents": {
        "actor": ("SenderFromAddress",),
        "action": ("DeliveryAction",),
        "target": ("Subject", "RecipientEmailAddress"),
        "result": ("ThreatTypes",),
        "correlation": ("NetworkMessageId", "ReportId"),
    },
    "CloudAppEvents": {
        "actor": ("AccountDisplayName", "AccountId"),
        "action": ("ActionType",),
        "target": ("ObjectName", "Application"),
        "result": (),
        "correlation": ("ReportId",),
    },
}


def _first_value(row: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        val = row.get(key)
        if val not in (None, "", [], {}):
            return str(val)
    return None


class AdvancedHuntingProvider(BaseProviderAdapter):
    """Run KQL queries against the Microsoft 365 Defender Advanced Hunting API.

    Accepts a list of (table_name, kql_template) pairs as ``queries``.  When
    omitted the built-in default queries covering IdentityLogonEvents,
    DeviceEvents, EmailEvents, and CloudAppEvents are used.

    Required app permission: ThreatHunting.Read.All
    """

    provider_name = "advanced_hunting"
    provider_scope = "https://graph.microsoft.com/.default"
    _hunting_url = "https://graph.microsoft.com/v1.0/security/runHuntingQuery"

    def __init__(
        self,
        *,
        queries: Sequence[tuple[str, str]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.queries: tuple[tuple[str, str], ...] = tuple(queries) if queries else _DEFAULT_QUERIES
        self.connection_test_url = self._hunting_url
        self.connection_test_params = None

    async def connect(self) -> None:
        # Validate by running a lightweight schema probe query
        await self._get_access_token(self.provider_scope)

    async def fetch(self, start_time: datetime | None = None, end_time: datetime | None = None) -> list[NormalizedEvent]:
        start, end, checkpoint = await self.resolve_window(start_time, end_time)
        start_str = isoformat_z(start)
        end_str = isoformat_z(end)

        raw_events: list[dict[str, Any]] = []
        for table_name, kql_template in self.queries:
            kql = kql_template.format(start=start_str, end=end_str)
            response = await self._request_json(
                "POST",
                self._hunting_url,
                scope=self.provider_scope,
                json={"Query": kql},
            )
            if not isinstance(response, dict):
                continue
            rows = response.get("results") or response.get("value") or []
            for row in rows:
                if isinstance(row, dict):
                    row["_tv_table"] = table_name
                    raw_events.append(row)

        self.cache_raw_payloads(raw_events)
        events = [self.normalize(item) for item in raw_events]
        last_event_time = max((event.timestamp for event in events), default=checkpoint.last_event_time or end.astimezone(UTC))
        await self.checkpoint(ProviderCheckpoint(
            provider=self.provider_name,
            cursor=isoformat_z(end),
            last_event_time=last_event_time,
            metadata={"row_count": len(raw_events), "tables": [q[0] for q in self.queries]},
        ))
        return events

    def normalize(self, payload: Mapping[str, Any]) -> NormalizedEvent:
        table = str(payload.get("_tv_table") or "UnknownTable")
        field_map = _TABLE_FIELD_MAP.get(table, {})

        actor = _first_value(payload, *(field_map.get("actor") or ("AccountUpn", "AccountId")))
        action_keys = field_map.get("action") or ("ActionType",)
        action = _first_value(payload, *action_keys) or table
        target = _first_value(payload, *(field_map.get("target") or ("ObjectName",)))
        result_raw = _first_value(payload, *(field_map.get("result") or ()))
        corr_keys = field_map.get("correlation") or ("ReportId",)
        correlation = _first_value(payload, *corr_keys)

        # EmailEvents: map delivery action to result
        if table == "EmailEvents":
            delivery = str(payload.get("DeliveryAction") or "").lower()
            if delivery in {"delivered", "deliveredtojunk"}:
                result = "success"
            elif delivery in {"blocked", "replaced"}:
                result = "failure"
            else:
                result = map_result(result_raw)
            severity = str(payload.get("ConfidenceLevel") or "").lower() or None
        else:
            result = map_result(result_raw)
            severity = None

        return NormalizedEvent(
            timestamp=payload.get("Timestamp") or datetime.now(UTC).isoformat(),
            provider=self.provider_name,
            service=f"Microsoft Defender Advanced Hunting ({table})",
            tenant_id=self.tenant_id,
            actor=actor,
            action=action,
            target=target,
            result=result,
            severity=severity,
            correlation_id=correlation,
            request_id=_first_value(payload, "ReportId", "NetworkMessageId"),
            raw=dict(payload),
        )

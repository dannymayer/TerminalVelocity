from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx

from terminalvelocity.providers import CheckpointStore, RawLogCache
from terminalvelocity.providers.defender_xdr import DefenderXdrProvider


def test_defender_xdr_fetches_incidents_alerts_and_timeline(state_dir) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        if path.endswith("/security/incidents"):
            return httpx.Response(200, json={"value": [{"id": "incident-id", "incidentId": 1001, "displayName": "Malware incident", "severity": "high", "status": "resolved", "lastUpdateDateTime": "2025-01-01T00:05:00Z"}]})
        if path.endswith("/security/alerts_v2"):
            return httpx.Response(200, json={"value": [{"id": "alert-id", "title": "Suspicious PowerShell", "serviceSource": "microsoftDefenderForEndpoint", "severity": "medium", "status": "inProgress", "createdDateTime": "2025-01-01T00:06:00Z"}]})
        if path.endswith("/api/machines"):
            return httpx.Response(200, json={"value": [{"id": "machine-1"}]})
        if path.endswith("/api/machines/machine-1/timeline"):
            return httpx.Response(200, json={"value": [{"id": "timeline-1", "eventTime": "2025-01-01T00:07:00Z", "eventType": "ProcessCreated", "initiatingProcessAccountName": "endpoint-user", "fileName": "powershell.exe", "reportId": "rep-1"}]})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    async def scenario() -> None:
        provider = DefenderXdrProvider(tenant_id="tenant-id", client_id="client-id", client_secret="client-secret", checkpoint_store=CheckpointStore(state_dir / "checkpoints"), raw_log_cache=RawLogCache(state_dir / "cache"), enable_raw_cache=True, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        await provider.connect()
        events = await provider.fetch(start_time=datetime(2025, 1, 1, tzinfo=UTC), end_time=datetime(2025, 1, 1, 1, tzinfo=UTC))
        assert len(events) == 3
        assert {event.service for event in events} == {"Microsoft Defender XDR Incident", "microsoftDefenderForEndpoint", "Microsoft Defender for Endpoint Timeline"}
        assert any(event.target == "powershell.exe" for event in events)
        checkpoint = await provider.get_checkpoint()
        assert checkpoint.metadata["machine_ids"] == ["machine-1"]
        await provider.close()

    asyncio.run(scenario())

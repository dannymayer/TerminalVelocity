from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx

from terminalvelocity.providers import CheckpointStore
from terminalvelocity.providers.intune import IntuneProvider


def test_intune_fetch_normalizes_graph_audit_events(state_dir) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        if path.endswith("/deviceManagement/auditEvents"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "audit-1",
                            "activityDateTime": "2025-01-01T00:10:00Z",
                            "activityType": "Update device compliance policy",
                            "activityResult": "success",
                            "category": "Policy",
                            "correlationId": "corr-2",
                            "actor": {"userPrincipalName": "admin@contoso.com"},
                            "resources": [{"displayName": "Windows baseline"}],
                        }
                    ]
                },
            )
        if path.endswith("/deviceManagement/remoteActionAudits"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "remote-1",
                            "actionDateTime": "2025-01-01T00:11:00Z",
                            "actionName": "remoteLock",
                            "actionState": "done",
                            "managedDeviceName": "laptop-01",
                            "userPrincipalName": "admin@contoso.com",
                        }
                    ]
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    async def scenario() -> None:
        provider = IntuneProvider(
            tenant_id="tenant-id",
            client_id="client-id",
            client_secret="client-secret",
            checkpoint_store=CheckpointStore(state_dir / "checkpoints"),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        await provider.connect()
        events = await provider.fetch(
            start_time=datetime(2025, 1, 1, tzinfo=UTC), end_time=datetime(2025, 1, 1, 1, tzinfo=UTC)
        )
        assert len(events) == 2
        audit_event = next(event for event in events if event.service == "Microsoft Intune")
        assert audit_event.actor == "admin@contoso.com"
        assert audit_event.target == "Windows baseline"
        remote_action_event = next(event for event in events if event.service == "Microsoft Intune Remote Action")
        assert remote_action_event.target == "laptop-01"
        checkpoint = await provider.get_checkpoint()
        assert checkpoint.metadata["sources"] == ["deviceManagement/auditEvents", "deviceManagement/remoteActionAudits"]
        await provider.close()

    asyncio.run(scenario())

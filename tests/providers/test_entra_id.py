from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx

from terminalvelocity.providers import CheckpointStore
from terminalvelocity.providers.entra_id import EntraIdProvider


def test_entra_id_fetch_normalizes_signin_and_audit_logs(state_dir) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        if path.endswith("/auditLogs/signIns"):
            return httpx.Response(200, json={"value": [{"id": "signin-1", "createdDateTime": "2025-01-01T00:08:00Z", "userPrincipalName": "user@contoso.com", "resourceDisplayName": "Microsoft Graph", "correlationId": "corr-3", "status": {"errorCode": 0}, "riskLevelAggregated": "none"}]})
        if path.endswith("/auditLogs/directoryAudits"):
            return httpx.Response(200, json={"value": [{"id": "audit-2", "activityDateTime": "2025-01-01T00:09:00Z", "activityDisplayName": "Add application", "category": "ApplicationManagement", "loggedByService": "Core Directory", "initiatedBy": {"app": {"displayName": "Terraform"}}, "targetResources": [{"displayName": "Contoso App"}], "result": "success"}]})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    async def scenario() -> None:
        provider = EntraIdProvider(tenant_id="tenant-id", client_id="client-id", client_secret="client-secret", checkpoint_store=CheckpointStore(state_dir / "checkpoints"), http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        await provider.connect()
        events = await provider.fetch(start_time=datetime(2025, 1, 1, tzinfo=UTC), end_time=datetime(2025, 1, 1, 1, tzinfo=UTC))
        assert len(events) == 2
        sign_in = next(event for event in events if event.action == "sign-in")
        assert sign_in.result == "success"
        audit = next(event for event in events if event.action == "Add application")
        assert audit.actor == "Terraform"
        assert audit.target == "Contoso App"
        await provider.close()

    asyncio.run(scenario())

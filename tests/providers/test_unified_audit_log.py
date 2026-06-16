from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import httpx

from terminalvelocity.providers import CheckpointStore, RawLogCache
from terminalvelocity.providers.unified_audit_log import UnifiedAuditLogProvider


def test_unified_audit_log_fetch_persists_checkpoint_and_raw_cache(state_dir) -> None:
    calls = {"content_uri": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        if path.endswith("/subscriptions/list"):
            return httpx.Response(200, json=[{"contentType": "Audit.General"}])
        if path.endswith("/subscriptions/content"):
            return httpx.Response(200, json=[{"contentId": "content-1", "contentUri": "https://manage.office.com/content/blob-1"}])
        if path == "/content/blob-1":
            calls["content_uri"] += 1
            return httpx.Response(200, json=[{"CreationTime": "2025-01-01T00:00:00Z", "Workload": "AzureActiveDirectory", "OrganizationId": "tenant-id", "UserId": "user@contoso.com", "Operation": "UserLoggedIn", "ObjectId": "portal.office.com", "ResultStatus": "Succeeded", "CorrelationId": "corr-1", "Id": "req-1"}])
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    async def scenario() -> None:
        provider = UnifiedAuditLogProvider(tenant_id="tenant-id", client_id="client-id", client_secret="client-secret", content_types=["Audit.General"], enable_raw_cache=True, checkpoint_store=CheckpointStore(state_dir / "checkpoints"), raw_log_cache=RawLogCache(state_dir / "cache"), http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        await provider.connect()
        events = await provider.fetch(start_time=datetime(2025, 1, 1, tzinfo=UTC), end_time=datetime(2025, 1, 1, 1, tzinfo=UTC))
        assert len(events) == 1
        assert events[0].result == "success"
        assert events[0].actor == "user@contoso.com"
        cache_file = next((state_dir / "cache" / "unified_audit_log").glob("*.jsonl"))
        payload = json.loads(cache_file.read_text(encoding="utf-8").splitlines()[0])
        assert payload["payload"]["Operation"] == "UserLoggedIn"
        second_events = await provider.fetch(start_time=datetime(2025, 1, 1, tzinfo=UTC), end_time=datetime(2025, 1, 1, 1, tzinfo=UTC))
        assert second_events == []
        checkpoint = await provider.get_checkpoint()
        assert checkpoint.metadata["content_markers"]["Audit.General"] == "content-1"
        assert calls["content_uri"] == 1
        await provider.close()

    asyncio.run(scenario())

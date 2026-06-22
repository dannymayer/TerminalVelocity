"""Integration tests for BaseProviderAdapter HTTP retry and token-refresh logic.

Uses httpx's mock transport so no real network calls are made.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from typing import Any

import httpx

from terminalvelocity.providers.base import (
    BaseProviderAdapter,
    ProviderAuthError,
    TransientProviderError,
)
from terminalvelocity.schema import NormalizedEvent

# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing
# ---------------------------------------------------------------------------


class _TestProvider(BaseProviderAdapter):
    provider_name = "test"

    async def fetch(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[NormalizedEvent]:
        return []

    def normalize(self, payload: Any) -> NormalizedEvent:  # type: ignore[override]
        return NormalizedEvent(
            timestamp=datetime.now(UTC),
            provider=self.provider_name,
            service="test",
            action="test",
            raw=payload,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _token_response(access_token: str = "tok-abc", expires_in: int = 3600) -> httpx.Response:
    return httpx.Response(
        200,
        json={"access_token": access_token, "expires_in": expires_in, "token_type": "Bearer"},
    )


def _make_provider(transport: httpx.MockTransport) -> _TestProvider:
    client = httpx.AsyncClient(transport=transport)
    return _TestProvider(
        tenant_id="tenant-1",
        client_id="client-1",
        client_secret="secret-1",
        http_client=client,
        max_retries=3,
    )


# ---------------------------------------------------------------------------
# Token acquisition tests
# ---------------------------------------------------------------------------


class TokenAcquisitionTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_token_acquisition(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _token_response("my-token")

        transport = httpx.MockTransport(handler=handler)
        provider = _make_provider(transport)
        token = await provider._get_access_token("https://graph.microsoft.com/.default")
        self.assertEqual(token, "my-token")

    async def test_token_cached_after_first_acquisition(self) -> None:
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return _token_response("cached-token")

        transport = httpx.MockTransport(handler=handler)
        provider = _make_provider(transport)
        scope = "https://graph.microsoft.com/.default"
        token1 = await provider._get_access_token(scope)
        token2 = await provider._get_access_token(scope)
        self.assertEqual(token1, token2)
        self.assertEqual(call_count, 1)  # Only one HTTP call

    async def test_expired_token_refreshed(self) -> None:
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return _token_response("fresh-token")

        transport = httpx.MockTransport(handler=handler)
        provider = _make_provider(transport)
        scope = "https://graph.microsoft.com/.default"

        # Inject an expired token directly into the cache
        past = datetime(2000, 1, 1, tzinfo=UTC)
        provider._access_tokens[scope] = ("old-token", past)

        token = await provider._get_access_token(scope)
        self.assertEqual(token, "fresh-token")
        self.assertEqual(call_count, 1)

    async def test_401_raises_provider_auth_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="Unauthorized")

        transport = httpx.MockTransport(handler=handler)
        provider = _make_provider(transport)
        with self.assertRaises(ProviderAuthError):
            await provider._get_access_token("https://graph.microsoft.com/.default")

    async def test_500_raises_transient_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Server Error")

        transport = httpx.MockTransport(handler=handler)
        provider = _make_provider(transport)
        with self.assertRaises((TransientProviderError, ProviderAuthError, Exception)):
            await provider._get_access_token("https://graph.microsoft.com/.default")


# ---------------------------------------------------------------------------
# HTTP request tests
# ---------------------------------------------------------------------------


class RequestJsonTests(unittest.IsolatedAsyncioTestCase):
    async def _provider_with_token(self, api_handler: Any) -> _TestProvider:
        """Return a provider with a pre-warmed token and the given API handler."""

        def handler(request: httpx.Request) -> httpx.Response:
            # First call is always the token endpoint
            if "oauth2" in str(request.url):
                return _token_response()
            return api_handler(request)

        transport = httpx.MockTransport(handler=handler)
        provider = _make_provider(transport)
        # Pre-warm the token cache
        await provider._get_access_token("https://graph.microsoft.com/.default")
        return provider

    async def test_successful_json_request(self) -> None:
        def api_handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"value": [{"id": "event-1"}]})

        provider = await self._provider_with_token(api_handler)
        result = await provider._request_json(
            "GET",
            "https://graph.microsoft.com/v1.0/auditLogs/signIns",
            scope="https://graph.microsoft.com/.default",
        )
        self.assertIsInstance(result, dict)
        self.assertIn("value", result)

    async def test_empty_response_returns_none(self) -> None:
        def api_handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(204)

        provider = await self._provider_with_token(api_handler)
        result = await provider._request_json(
            "GET",
            "https://graph.microsoft.com/v1.0/something",
            scope="https://graph.microsoft.com/.default",
        )
        self.assertIsNone(result)

    async def test_401_clears_token_cache(self) -> None:
        def api_handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="Unauthorized")

        provider = await self._provider_with_token(api_handler)
        scope = "https://graph.microsoft.com/.default"
        self.assertIn(scope, provider._access_tokens)

        with self.assertRaises(ProviderAuthError):
            await provider._request_json(
                "GET",
                "https://graph.microsoft.com/v1.0/something",
                scope=scope,
            )

        # Token cache should be cleared on 401
        self.assertNotIn(scope, provider._access_tokens)


# ---------------------------------------------------------------------------
# Pagination iterator tests
# ---------------------------------------------------------------------------


class IterateCollectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_page_collection(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            if "oauth2" in str(req.url):
                return _token_response()
            return httpx.Response(200, json={"value": [{"id": "1"}, {"id": "2"}]})

        transport = httpx.MockTransport(handler=handler)
        provider = _make_provider(transport)

        items = []
        async for item in provider._iterate_collection(
            "https://graph.microsoft.com/v1.0/events",
            scope="https://graph.microsoft.com/.default",
        ):
            items.append(item)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["id"], "1")

    async def test_paginated_collection_follows_next_link(self) -> None:
        page1_url = "https://graph.microsoft.com/v1.0/events"
        page2_url = "https://graph.microsoft.com/v1.0/events?$skiptoken=xyz"
        call_count = 0

        def handler(req: httpx.Request) -> httpx.Response:
            nonlocal call_count
            if "oauth2" in str(req.url):
                return _token_response()
            call_count += 1
            if str(req.url) == page1_url:
                return httpx.Response(
                    200,
                    json={"value": [{"id": "a"}], "@odata.nextLink": page2_url},
                )
            return httpx.Response(200, json={"value": [{"id": "b"}]})

        transport = httpx.MockTransport(handler=handler)
        provider = _make_provider(transport)

        items = []
        async for item in provider._iterate_collection(
            page1_url,
            scope="https://graph.microsoft.com/.default",
        ):
            items.append(item)

        self.assertEqual(len(items), 2)
        self.assertEqual(call_count, 2)

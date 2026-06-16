"""Base classes and shared utilities for provider adapters."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Mapping

import httpx
from tenacity import AsyncRetrying, before_sleep_log, retry_if_exception_type, stop_after_attempt

from terminalvelocity.schema import NormalizedEvent, ProviderCheckpoint

LOGGER = logging.getLogger(__name__)


class ProviderError(Exception):
    """Base provider exception."""


class ProviderAuthError(ProviderError):
    """Raised when authentication fails."""


class TransientProviderError(ProviderError):
    """Raised for retryable provider failures."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class CheckpointStore:
    """Simple JSON checkpoint persistence per provider."""

    def __init__(self, root: str | Path = ".terminalvelocity/checkpoints") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, provider: str) -> Path:
        return self.root / f"{provider}.json"

    def load(self, provider: str) -> ProviderCheckpoint:
        path = self._path(provider)
        if not path.exists():
            return ProviderCheckpoint(provider=provider)
        return ProviderCheckpoint.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, checkpoint: ProviderCheckpoint) -> ProviderCheckpoint:
        path = self._path(checkpoint.provider)
        path.write_text(checkpoint.model_dump_json(indent=2), encoding="utf-8")
        return checkpoint


class RawLogCache:
    """Optional JSONL raw payload cache for replay and troubleshooting."""

    def __init__(self, root: str | Path = ".terminalvelocity/raw-cache") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, provider: str, payloads: Iterable[Mapping[str, Any]]) -> Path:
        provider_dir = self.root / provider
        provider_dir.mkdir(parents=True, exist_ok=True)
        path = provider_dir / f"{datetime.now(UTC).date().isoformat()}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            for payload in payloads:
                handle.write(
                    json.dumps(
                        {
                            "cached_at": datetime.now(UTC).isoformat(),
                            "provider": provider,
                            "payload": dict(payload),
                        },
                        default=str,
                    )
                )
                handle.write("\n")
        return path


class ProviderAdapter(ABC):
    """Shared asynchronous provider interface."""

    @abstractmethod
    async def connect(self) -> None:
        """Authenticate and validate provider connectivity."""

    @abstractmethod
    async def fetch(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[NormalizedEvent]:
        """Fetch and normalize events for the requested time window."""

    @abstractmethod
    def normalize(self, payload: Mapping[str, Any]) -> NormalizedEvent:
        """Normalize a raw provider event."""

    @abstractmethod
    async def checkpoint(self, checkpoint: ProviderCheckpoint) -> ProviderCheckpoint:
        """Persist checkpoint state for the provider."""


class BaseProviderAdapter(ProviderAdapter):
    """Base implementation for HTTP-backed provider adapters."""

    provider_name = "base"
    provider_scope = "https://graph.microsoft.com/.default"
    connection_test_url: str | None = None
    connection_test_params: dict[str, Any] | None = None

    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        checkpoint_store: CheckpointStore | None = None,
        raw_log_cache: RawLogCache | None = None,
        enable_raw_cache: bool = False,
        http_client: httpx.AsyncClient | None = None,
        authority: str = "https://login.microsoftonline.com",
        timeout: float = 30.0,
        max_retries: int = 5,
        poll_window: timedelta = timedelta(minutes=15),
    ) -> None:
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.authority = authority.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.poll_window = poll_window
        self.checkpoint_store = checkpoint_store or CheckpointStore()
        self.raw_log_cache = raw_log_cache or RawLogCache()
        self.enable_raw_cache = enable_raw_cache
        self._access_tokens: dict[str, tuple[str, datetime]] = {}
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.AsyncClient(timeout=self.timeout)

    async def connect(self) -> None:
        await self._get_access_token(self.provider_scope)
        if self.connection_test_url:
            await self._request_json(
                "GET",
                self.connection_test_url,
                scope=self.provider_scope,
                params=self.connection_test_params,
            )
        LOGGER.info("Connected to provider %s", self.provider_name)

    async def close(self) -> None:
        if self._owns_client:
            await self.http_client.aclose()

    async def checkpoint(self, checkpoint: ProviderCheckpoint) -> ProviderCheckpoint:
        return self.checkpoint_store.save(checkpoint)

    async def get_checkpoint(self) -> ProviderCheckpoint:
        return self.checkpoint_store.load(self.provider_name)

    async def resolve_window(
        self,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> tuple[datetime, datetime, ProviderCheckpoint]:
        checkpoint = await self.get_checkpoint()
        end = ensure_utc(end_time or datetime.now(UTC))
        start = ensure_utc(start_time or checkpoint.last_event_time or (end - self.poll_window))
        if start > end:
            raise ProviderError(f"Invalid polling window for {self.provider_name}: {start} > {end}")
        return start, end, checkpoint

    async def _get_access_token(self, scope: str) -> str:
        cached = self._access_tokens.get(scope)
        now = datetime.now(UTC)
        if cached and cached[1] > now:
            return cached[0]

        token_url = f"{self.authority}/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
            "scope": scope,
        }
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type((httpx.TransportError, TransientProviderError)),
            stop=stop_after_attempt(self.max_retries),
            wait=_retry_wait,
            reraise=True,
            before_sleep=before_sleep_log(LOGGER, logging.WARNING),
        ):
            with attempt:
                response = await self.http_client.post(token_url, data=data)
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise TransientProviderError(
                        f"Transient token acquisition failure for {self.provider_name}: {response.status_code}",
                        retry_after=_retry_after_seconds(response.headers),
                    )
                if response.status_code >= 400:
                    raise ProviderAuthError(
                        f"Failed to acquire token for {self.provider_name}: {response.status_code} {response.text}"
                    )
                payload = response.json()
                expires_in = int(payload.get("expires_in", 3600))
                expires_at = now + timedelta(seconds=max(expires_in - 60, 60))
                token = payload["access_token"]
                self._access_tokens[scope] = (token, expires_at)
                return token
        raise ProviderAuthError(f"Failed to acquire token for {self.provider_name}")

    async def _request(
        self,
        method: str,
        url: str,
        *,
        scope: str,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type((httpx.TransportError, TransientProviderError)),
            stop=stop_after_attempt(self.max_retries),
            wait=_retry_wait,
            reraise=True,
            before_sleep=before_sleep_log(LOGGER, logging.WARNING),
        ):
            with attempt:
                token = await self._get_access_token(scope)
                request_headers = {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "User-Agent": "TerminalVelocity/0.1.0",
                }
                if headers:
                    request_headers.update(headers)
                response = await self.http_client.request(method, url, headers=request_headers, **kwargs)
                if response.status_code == 401:
                    self._access_tokens.pop(scope, None)
                    raise ProviderAuthError(f"Unauthorized request for {self.provider_name}: {url}")
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise TransientProviderError(
                        f"Transient provider failure for {self.provider_name}: {response.status_code} {url}",
                        retry_after=_retry_after_seconds(response.headers),
                    )
                response.raise_for_status()
                return response
        raise ProviderError(f"Unable to complete request for {self.provider_name}: {url}")

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        scope: str,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        response = await self._request(method, url, scope=scope, headers=headers, **kwargs)
        return None if not response.content else response.json()

    async def _iterate_collection(
        self,
        url: str,
        *,
        scope: str,
        params: Mapping[str, Any] | None = None,
        item_key: str = "value",
    ) -> AsyncIterator[dict[str, Any]]:
        next_url = url
        next_params: Mapping[str, Any] | None = params
        while next_url:
            payload = await self._request_json("GET", next_url, scope=scope, params=next_params)
            next_params = None
            if isinstance(payload, list):
                for item in payload:
                    yield item
                next_url = ""
            elif isinstance(payload, dict):
                items = payload.get(item_key)
                if isinstance(items, list):
                    for item in items:
                        yield item
                    next_url = payload.get("@odata.nextLink") or payload.get("NextPageUri") or ""
                else:
                    yield payload
                    next_url = ""
            else:
                next_url = ""

    def cache_raw_payloads(self, payloads: Iterable[Mapping[str, Any]]) -> None:
        if self.enable_raw_cache:
            self.raw_log_cache.append(self.provider_name, payloads)


def ensure_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def isoformat_z(value: datetime) -> str:
    return ensure_utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def map_result(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"0", "ok", "succeeded", "succeed", "success", "completed", "resolved", "done"}:
        return "success"
    if normalized in {"1", "error", "failed", "failure", "denied", "blocked"}:
        return "failure"
    return normalized or None


def join_display_names(items: Iterable[Mapping[str, Any]], *keys: str) -> str | None:
    values: list[str] = []
    for item in items:
        for key in keys:
            value = item.get(key)
            if value:
                values.append(str(value))
                break
    return None if not values else ", ".join(values)


def _retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    retry_after = headers.get("Retry-After")
    try:
        return None if retry_after is None else float(retry_after)
    except ValueError:
        return None


def _retry_wait(retry_state: Any) -> float:
    exception = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exception, TransientProviderError) and exception.retry_after is not None:
        return exception.retry_after
    return min(2 ** max(retry_state.attempt_number - 1, 0), 30)

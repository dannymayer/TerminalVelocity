"""Shared provider interfaces and lightweight HTTP clients for M365 ingestion.

This module defines **two** distinct provider base classes that serve different roles:

* :class:`BaseProvider` — **synchronous** polling adapter used by providers that rely on
  the Microsoft Purview Unified Audit Log query API (phase-3 providers).  It uses
  :class:`GraphAPIClient` (synchronous ``httpx``) and ``time.sleep()`` for poll-wait
  loops.  Subclass this when writing a new provider that calls
  ``/security/auditLog/queries``.

* :class:`BaseProviderAdapter` — **asynchronous** adapter for providers that call the
  Graph API directly via ``httpx.AsyncClient`` (phase-2 providers).  It handles token
  acquisition, retry logic via ``tenacity``, checkpointing, and optional raw-log caching.
  Subclass this when writing a new provider that needs async HTTP and built-in retry.

Both share the abstract :class:`ProviderAdapter` interface (``connect`` / ``fetch`` /
``normalize`` / ``checkpoint``), but their signatures differ slightly to accommodate sync
vs. async calling conventions.  Choose the right base for your provider based on whether
the upstream API requires the polling pattern (sync) or direct streaming (async).
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable, Iterator, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from terminalvelocity.schema import NormalizedEvent, ProviderCheckpoint

LOGGER = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
TERMINAL_QUERY_STATUSES = {"succeeded", "completed"}
PENDING_QUERY_STATUSES = {"notstarted", "queued", "running", "inprogress"}
FAILED_QUERY_STATUSES = {"failed", "cancelled", "canceled"}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ProviderError(Exception):
    """Base exception raised by provider adapters."""


class ProviderConnectionError(ProviderError):
    """Raised when a provider cannot connect to its upstream API."""


class ProviderFetchError(ProviderError):
    """Raised when a provider cannot fetch or poll records."""


class ProviderAuthError(ProviderError):
    """Raised when authentication fails."""


class TransientProviderError(ProviderError):
    """Raised for retryable provider failures."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class APIRequestError(ProviderError):
    """Raised for HTTP/API failures that survive retry handling."""

    def __init__(self, message: str, status_code: int | None = None, payload: Any | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


# ---------------------------------------------------------------------------
# Checkpoint & raw cache (async-style providers)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Synchronous JSON API client (used by phase-3 providers)
# ---------------------------------------------------------------------------

class JSONAPIClient:
    """Minimal JSON API client with tenacity-based retry and pagination."""

    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str],
        timeout: float = 30.0,
        opener: Any | None = None,
    ) -> None:
        from urllib import request as urllib_request
        self.base_url = base_url.rstrip("/")
        self.headers = dict(headers)
        self.timeout = timeout
        self._opener = opener or urllib_request.urlopen

    def _build_url(self, path: str, params: Mapping[str, Any] | None = None) -> str:
        from urllib import parse
        if path.startswith(("http://", "https://")):
            url = path
        else:
            url = f"{self.base_url}/{path.lstrip('/')}"
        if params:
            clean_params: dict[str, Any] = {
                key: value
                for key, value in params.items()
                if value is not None and value != [] and value != ()
            }
            if clean_params:
                query = parse.urlencode(clean_params, doseq=True, safe=":,$'()")
                separator = "&" if "?" in url else "?"
                url = f"{url}{separator}{query}"
        return url

    @staticmethod
    def _is_retryable_exception(exc: BaseException) -> bool:
        from urllib import error as urllib_error
        if isinstance(exc, APIRequestError) and exc.status_code in RETRYABLE_STATUS_CODES:
            return True
        if isinstance(exc, urllib_error.URLError):
            return True
        return False

    @retry(
        retry=retry_if_exception(_is_retryable_exception),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _request(self, method: str, path: str, *, params: Mapping[str, Any] | None = None, body: Any | None = None) -> Any:
        from urllib import error as urllib_error
        from urllib import request as urllib_request
        url = self._build_url(path, params)
        payload: bytes | None = None
        headers = dict(self.headers)
        if body is not None:
            payload = json.dumps(body, default=str).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        http_request = urllib_request.Request(url, data=payload, headers=headers, method=method.upper())
        try:
            with self._opener(http_request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return None
                return json.loads(raw)
        except urllib_error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            try:
                parsed_body = json.loads(response_body) if response_body else None
            except json.JSONDecodeError:
                parsed_body = response_body or None
            raise APIRequestError(
                f"{method.upper()} {url} failed with HTTP {exc.code}",
                status_code=exc.code,
                payload=parsed_body,
            ) from exc
        except urllib_error.URLError as exc:
            raise APIRequestError(f"{method.upper()} {url} failed: {exc.reason}") from exc

    def get(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, body: Mapping[str, Any]) -> Any:
        return self._request("POST", path, body=body)

    def delete(self, path: str) -> Any:
        try:
            return self._request("DELETE", path)
        except APIRequestError as exc:
            if exc.status_code == 404:
                return None
            raise

    def iter_collection(self, path: str, *, params: Mapping[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        next_path = path
        next_params = dict(params or {})
        while next_path:
            payload = self.get(next_path, params=next_params)
            next_params = {}
            if not isinstance(payload, dict):
                return
            for item in payload.get("value", []):
                if isinstance(item, dict):
                    yield item
            next_path = payload.get("@odata.nextLink")


class GraphAPIClient(JSONAPIClient):
    """Microsoft Graph client configured for bearer authentication."""

    def __init__(self, access_token: str, *, timeout: float = 30.0, base_url: str = "https://graph.microsoft.com") -> None:
        super().__init__(
            base_url=base_url,
            headers={
                "Authorization": "******",
                "Accept": "application/json",
                "User-Agent": "terminalvelocity/0.1.0",
            },
            timeout=timeout,
        )


class MCASClient(JSONAPIClient):
    """Microsoft Defender for Cloud Apps client using API token auth."""

    def __init__(self, api_token: str, *, base_url: str, timeout: float = 30.0) -> None:
        super().__init__(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Token {api_token}",
                "Accept": "application/json",
                "User-Agent": "terminalvelocity/0.1.0",
            },
            timeout=timeout,
        )


# ---------------------------------------------------------------------------
# Synchronous base provider (used by phase-3 providers)
# ---------------------------------------------------------------------------

class BaseProvider(ABC):
    """Synchronous provider base for time-window polling adapters (phase-3).

    Subclass this when your provider targets the Microsoft Purview Unified Audit Log
    query API (``/security/auditLog/queries``).  The polling loop uses ``time.sleep()``
    intentionally because it runs in a thread-pool executor, not directly on the asyncio
    event loop.

    For providers that call other Graph API endpoints asynchronously, use
    :class:`BaseProviderAdapter` instead.
    """

    provider_name = "provider"
    service_name = "service"

    def __init__(
        self,
        *,
        tenant_id: str,
        access_token: str,
        graph_client: GraphAPIClient | None = None,
        raw_cache_path: str | Path | None = None,
        checkpoint_state: ProviderCheckpoint | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.graph_client = graph_client or GraphAPIClient(access_token)
        self.raw_cache_path = Path(raw_cache_path) if raw_cache_path else None
        self._checkpoint = checkpoint_state or ProviderCheckpoint(provider=self.provider_name)
        self._last_fetch_count = 0

    @staticmethod
    def ensure_utc(value: datetime | str | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _write_raw_cache(self, events: Iterable[dict[str, Any]]) -> None:
        if self.raw_cache_path is None:
            return
        self.raw_cache_path.parent.mkdir(parents=True, exist_ok=True)
        fetched_at = datetime.now(UTC).isoformat()
        with self.raw_cache_path.open("a", encoding="utf-8") as handle:
            for event in events:
                entry = {
                    "provider": self.provider_name,
                    "service": self.service_name,
                    "fetched_at": fetched_at,
                    "payload": event,
                }
                handle.write(json.dumps(entry, default=str, sort_keys=True))
                handle.write("\n")

    def _advance_checkpoint(self, *, cursor: str | None = None, last_event_time: datetime | str | None = None, metadata: dict[str, Any] | None = None) -> None:
        if cursor is not None:
            self._checkpoint.cursor = cursor
        normalized_time = self.ensure_utc(last_event_time)
        if normalized_time is not None:
            current = self.ensure_utc(self._checkpoint.last_event_time)
            if current is None or normalized_time >= current:
                self._checkpoint.last_event_time = normalized_time
        if metadata:
            self._checkpoint.metadata.update(metadata)

    def checkpoint(self) -> ProviderCheckpoint:
        self._checkpoint.provider = self.provider_name
        self._checkpoint.metadata.update({
            "service": self.service_name,
            "last_fetch_count": self._last_fetch_count,
        })
        return self._checkpoint.model_copy(deep=True)

    @abstractmethod
    def connect(self) -> bool:
        """Validate API connectivity and permissions."""

    @abstractmethod
    def fetch(self, *, since: datetime, until: datetime) -> list[dict[str, Any]]:
        """Fetch raw events for the given time window."""

    @abstractmethod
    def normalize(self, event: dict[str, Any]) -> NormalizedEvent:
        """Map a raw event into the shared normalized schema."""


class AuditLogQueryProvider(BaseProvider):
    """Base implementation for Graph auditLog query-backed providers."""

    audit_query_path = "/v1.0/security/auditLog/queries"
    query_timeout = timedelta(minutes=5)
    query_poll_interval = 2.0
    record_type_filters: tuple[str, ...] = ()
    service_filters: tuple[str, ...] = ()
    operation_filters: tuple[str, ...] = ()

    def connect(self) -> bool:
        try:
            payload = self.graph_client.get("/v1.0/organization", params={"$select": "id"})
        except APIRequestError as exc:
            raise ProviderConnectionError(f"Unable to connect to Microsoft Graph for {self.provider_name}") from exc
        if isinstance(payload, dict) and payload.get("value"):
            return True
        raise ProviderConnectionError(f"No organization context returned for {self.provider_name}")

    def _build_audit_query_body(self, since: datetime, until: datetime) -> dict[str, Any]:
        body: dict[str, Any] = {
            "displayName": f"TerminalVelocity {self.provider_name} {until.isoformat()}",
            "filterStartDateTime": self.ensure_utc(since).isoformat(),
            "filterEndDateTime": self.ensure_utc(until).isoformat(),
        }
        if self.record_type_filters:
            body["recordTypeFilters"] = list(self.record_type_filters)
        if self.service_filters:
            body["serviceFilters"] = list(self.service_filters)
        if self.operation_filters:
            body["operationFilters"] = list(self.operation_filters)
        return body

    def _create_audit_query(self, since: datetime, until: datetime) -> str:
        payload = self.graph_client.post(self.audit_query_path, self._build_audit_query_body(since, until))
        if not isinstance(payload, dict) or "id" not in payload:
            raise ProviderFetchError(f"{self.provider_name} audit query creation did not return an id")
        return str(payload["id"])

    def _poll_audit_query(self, query_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.query_timeout.total_seconds()
        while time.monotonic() <= deadline:
            payload = self.graph_client.get(f"{self.audit_query_path}/{query_id}")
            if not isinstance(payload, dict):
                raise ProviderFetchError(f"{self.provider_name} audit query {query_id} returned an invalid payload")
            status = str(payload.get("status", "unknown")).strip().lower()
            if status in TERMINAL_QUERY_STATUSES:
                return payload
            if status in FAILED_QUERY_STATUSES:
                raise ProviderFetchError(f"{self.provider_name} audit query {query_id} failed with status {status}")
            if status not in PENDING_QUERY_STATUSES:
                raise ProviderFetchError(f"{self.provider_name} audit query {query_id} returned unexpected status {status}")
            # TODO(blocking): time.sleep() here blocks the calling thread for
            # the full poll interval.  If this synchronous provider is ever
            # called from an async context (e.g. via run_in_executor), consider
            # converting to asyncio.sleep() or moving the polling loop to an
            # async method.
            time.sleep(self.query_poll_interval)
        raise ProviderFetchError(f"{self.provider_name} audit query {query_id} timed out after {self.query_timeout}")

    def _fetch_audit_records(self, query_id: str) -> list[dict[str, Any]]:
        return list(self.graph_client.iter_collection(f"{self.audit_query_path}/{query_id}/records", params={"$top": 1000}))

    def fetch(self, *, since: datetime, until: datetime) -> list[dict[str, Any]]:
        query_id = self._create_audit_query(since, until)
        records: list[dict[str, Any]] = []
        try:
            self._poll_audit_query(query_id)
            records = self._fetch_audit_records(query_id)
            self._last_fetch_count = len(records)
            self._write_raw_cache(records)
            latest_event_time = max(
                (
                    timestamp
                    for timestamp in (
                        self.ensure_utc(record.get("createdDateTime") or record.get("activityDateTime"))
                        for record in records
                    )
                    if timestamp is not None
                ),
                default=until,
            )
            self._advance_checkpoint(
                cursor=query_id,
                last_event_time=latest_event_time,
                metadata={"query_id": query_id},
            )
            return records
        finally:
            self.graph_client.delete(f"{self.audit_query_path}/{query_id}")


# ---------------------------------------------------------------------------
# Async base provider adapter (used by phase-2 providers in main)
# ---------------------------------------------------------------------------

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
        cp = await self.get_checkpoint()
        end = ensure_utc(end_time or datetime.now(UTC))
        start = ensure_utc(start_time or cp.last_event_time or (end - self.poll_window))
        if start > end:
            raise ProviderError(f"Invalid polling window for {self.provider_name}: {start} > {end}")
        return start, end, cp

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
                await self._get_access_token(scope)
                request_headers = {
                    "Authorization": "******",
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


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

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

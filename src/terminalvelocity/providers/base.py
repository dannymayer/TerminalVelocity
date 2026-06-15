"""Shared provider interfaces and lightweight HTTP clients for M365 ingestion."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator, Mapping
from datetime import UTC, datetime, timedelta
import json
import time
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from terminalvelocity.schema import NormalizedEvent, ProviderCheckpoint


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
TERMINAL_QUERY_STATUSES = {"succeeded", "completed"}
PENDING_QUERY_STATUSES = {"notstarted", "queued", "running", "inprogress"}
FAILED_QUERY_STATUSES = {"failed", "cancelled", "canceled"}


class ProviderError(RuntimeError):
    """Base exception raised by provider adapters."""


class ProviderConnectionError(ProviderError):
    """Raised when a provider cannot connect to its upstream API."""


class ProviderFetchError(ProviderError):
    """Raised when a provider cannot fetch or poll records."""


class APIRequestError(ProviderError):
    """Raised for HTTP/API failures that survive retry handling."""

    def __init__(self, message: str, status_code: int | None = None, payload: Any | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


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
        self.base_url = base_url.rstrip("/")
        self.headers = dict(headers)
        self.timeout = timeout
        self._opener = opener or request.urlopen

    def _build_url(self, path: str, params: Mapping[str, Any] | None = None) -> str:
        if path.startswith("http://") or path.startswith("https://"):
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
        if isinstance(exc, APIRequestError) and exc.status_code in RETRYABLE_STATUS_CODES:
            return True
        if isinstance(exc, error.URLError):
            return True
        return False

    @retry(
        retry=retry_if_exception(_is_retryable_exception),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _request(self, method: str, path: str, *, params: Mapping[str, Any] | None = None, body: Any | None = None) -> Any:
        url = self._build_url(path, params)
        payload: bytes | None = None
        headers = dict(self.headers)
        if body is not None:
            payload = json.dumps(body, default=str).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        http_request = request.Request(url, data=payload, headers=headers, method=method.upper())
        try:
            with self._opener(http_request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return None
                return json.loads(raw)
        except error.HTTPError as exc:
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
        except error.URLError as exc:
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
                "Authorization": f"******",
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


class BaseProvider(ABC):
    """Common provider contract for time-window polling adapters."""

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
        last_payload: dict[str, Any] = {}
        while time.monotonic() <= deadline:
            payload = self.graph_client.get(f"{self.audit_query_path}/{query_id}")
            if not isinstance(payload, dict):
                raise ProviderFetchError(f"{self.provider_name} audit query {query_id} returned an invalid payload")
            last_payload = payload
            status = str(payload.get("status", "unknown")).strip().lower()
            if status in TERMINAL_QUERY_STATUSES:
                return payload
            if status in FAILED_QUERY_STATUSES:
                raise ProviderFetchError(f"{self.provider_name} audit query {query_id} failed with status {status}")
            if status not in PENDING_QUERY_STATUSES:
                raise ProviderFetchError(f"{self.provider_name} audit query {query_id} returned unexpected status {status}")
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

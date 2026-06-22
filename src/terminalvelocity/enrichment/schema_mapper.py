"""Schema normalization helpers for provider-specific payloads."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from terminalvelocity.schema import NormalizedEvent


def extract_first(payload: dict[str, Any], *paths: str) -> Any:
    """Return the first non-empty value found across dotted candidate paths."""

    for path in paths:
        current: Any = payload
        for part in path.split("."):
            if isinstance(current, list):
                if not part.isdigit() or int(part) >= len(current):
                    current = None
                    break
                current = current[int(part)]
                continue
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if current not in (None, "", [], {}):
            return current
    return None


def normalize_timestamp(value: Any, *, default: datetime | None = None) -> datetime:
    """Normalize timestamp values into timezone-aware UTC datetimes."""

    if value in (None, ""):
        value = default or datetime.now(UTC)
    if isinstance(value, datetime):
        timestamp = value
    else:
        text = str(value).replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(text)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def normalize_result(value: Any) -> str | None:
    """Map workload-specific status values to success/failure when possible."""

    if value in (None, ""):
        return None
    text = str(value).strip().lower()
    success_values = {"success", "succeeded", "ok", "allowed", "completed", "resolved", "deliver", "delivered", "pass"}
    failure_values = {"failure", "failed", "error", "denied", "blocked", "reject", "rejected", "timeout"}
    if text in success_values:
        return "success"
    if text in failure_values:
        return "failure"
    return text


def normalize_severity(value: Any) -> str | None:
    """Normalize severity labels into a smaller canonical set."""

    if value in (None, ""):
        return None
    text = str(value).strip().lower()
    mapping = {
        "informational": "info",
        "information": "info",
        "low": "low",
        "medium": "medium",
        "moderate": "medium",
        "high": "high",
        "critical": "critical",
        "severe": "critical",
    }
    return mapping.get(text, text)


def normalize_actor(value: Any) -> str | None:
    """Extract a human-meaningful actor identifier from common payload shapes."""

    if value in (None, ""):
        return None
    if isinstance(value, dict):
        return (
            value.get("userPrincipalName")
            or value.get("emailAddress")
            or value.get("displayName")
            or value.get("id")
        )
    return str(value)


def normalize_target(value: Any) -> str | None:
    """Convert target payload values into compact strings."""

    if value in (None, ""):
        return None
    if isinstance(value, dict):
        return (
            value.get("displayName")
            or value.get("emailAddress")
            or value.get("id")
            or value.get("name")
        )
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item not in (None, "")) or None
    return str(value)


def _normalize_id(value: Any) -> str | None:
    """Return a plain string identifier (correlation_id, request_id, etc.)."""
    if value in (None, ""):
        return None
    return str(value)


@dataclass(slots=True)
class SchemaMapper:
    """Map provider payloads into the shared normalized event schema."""

    provider: str
    service: str
    tenant_id: str | None = None

    def map_event(
        self,
        payload: dict[str, Any],
        *,
        timestamp_paths: Iterable[str],
        actor_paths: Iterable[str],
        action_paths: Iterable[str],
        target_paths: Iterable[str],
        result_paths: Iterable[str] = (),
        severity_paths: Iterable[str] = (),
        correlation_paths: Iterable[str] = (),
        request_paths: Iterable[str] = (),
        tenant_paths: Iterable[str] = ("tenantId", "organizationId"),
        raw: dict[str, Any] | None = None,
    ) -> NormalizedEvent:
        timestamp_value = extract_first(payload, *tuple(timestamp_paths))
        actor_value = extract_first(payload, *tuple(actor_paths))
        action_value = extract_first(payload, *tuple(action_paths)) or "Unknown"
        target_value = extract_first(payload, *tuple(target_paths))
        return NormalizedEvent(
            timestamp=normalize_timestamp(timestamp_value),
            provider=self.provider,
            service=self.service,
            tenant_id=extract_first(payload, *tuple(tenant_paths)) or self.tenant_id,
            actor=normalize_actor(actor_value),
            action=str(action_value),
            target=normalize_target(target_value),
            result=normalize_result(extract_first(payload, *tuple(result_paths))),
            severity=normalize_severity(extract_first(payload, *tuple(severity_paths))),
            correlation_id=_normalize_id(extract_first(payload, *tuple(correlation_paths))),
            request_id=_normalize_id(extract_first(payload, *tuple(request_paths))),
            raw=raw or payload,
        )

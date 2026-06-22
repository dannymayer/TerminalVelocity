"""File-based event ingestion for TerminalVelocity.

Supports JSONL (one NormalizedEvent per line), JSON arrays, and CSV exports.
An optional *field_mappings* dict remaps source-file keys to NormalizedEvent field names
before parsing, enabling ingestion of non-M365 log formats.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from terminalvelocity.schema import NormalizedEvent

LOGGER = logging.getLogger(__name__)

# Reject files larger than 256 MB to protect against memory exhaustion.
_MAX_FILE_BYTES = 256 * 1024 * 1024


class FileIngestionError(Exception):
    """Raised when a log file cannot be parsed or is unsupported."""


def ingest_file(
    path: str | Path,
    *,
    field_mappings: dict[str, str] | None = None,
    provider_override: str | None = None,
    service_override: str | None = None,
) -> list[NormalizedEvent]:
    """Load NormalizedEvents from a JSONL, JSON array, or CSV file.

    Args:
        path: Path to the input file.
        field_mappings: Optional dict mapping destination field names to source JSON keys.
            For example ``{"actor": "caller", "action": "operationName"}``.
        provider_override: Force all ingested events to use this provider name.
        service_override: Force all ingested events to use this service name.

    Returns:
        A list of NormalizedEvent objects parsed from the file.

    Raises:
        FileIngestionError: If the file is missing or cannot be parsed.
    """
    p = Path(path)
    if not p.exists():
        raise FileIngestionError(f"File not found: {path}")

    file_size = p.stat().st_size
    if file_size > _MAX_FILE_BYTES:
        raise FileIngestionError(
            f"File too large to ingest ({file_size / 1024 / 1024:.1f} MB > "
            f"{_MAX_FILE_BYTES // 1024 // 1024} MB limit): {path}"
        )

    suffix = p.suffix.lower()

    if suffix == ".csv":
        events = _ingest_csv(p, field_mappings=field_mappings)
    elif suffix == ".jsonl":
        events = _ingest_jsonl(p, field_mappings=field_mappings)
    elif suffix == ".json":
        events = _ingest_json(p, field_mappings=field_mappings)
    else:
        # Auto-detect: try JSONL first (line-delimited), then JSON array
        try:
            events = _ingest_jsonl(p, field_mappings=field_mappings)
        except (json.JSONDecodeError, FileIngestionError, ValueError) as jsonl_exc:
            LOGGER.debug("JSONL parse failed for %s (%s), trying JSON array", path, jsonl_exc)
            try:
                events = _ingest_json(p, field_mappings=field_mappings)
            except (json.JSONDecodeError, ValueError) as exc:
                raise FileIngestionError(f"Cannot parse {path}: unsupported or unrecognised format") from exc

    if provider_override or service_override:
        events = [
            event.model_copy(
                update={
                    k: v
                    for k, v in {
                        "provider": provider_override,
                        "service": service_override,
                    }.items()
                    if v
                }
            )
            for event in events
        ]
    return events


# ---------------------------------------------------------------------------
# Internal format parsers
# ---------------------------------------------------------------------------


def _ingest_jsonl(path: Path, *, field_mappings: dict[str, str] | None = None) -> list[NormalizedEvent]:
    events: list[NormalizedEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        payload: dict[str, Any] = json.loads(line)
        events.append(_parse_payload(payload, field_mappings=field_mappings))
    if not events:
        raise FileIngestionError(f"No events found in JSONL file: {path}")
    return events


def _ingest_json(path: Path, *, field_mappings: dict[str, str] | None = None) -> list[NormalizedEvent]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [_parse_payload(item, field_mappings=field_mappings) for item in data]
    if isinstance(data, dict):
        return [_parse_payload(data, field_mappings=field_mappings)]
    raise FileIngestionError(f"Unexpected JSON root type in {path}: {type(data).__name__}")


def _ingest_csv(path: Path, *, field_mappings: dict[str, str] | None = None) -> list[NormalizedEvent]:
    events: list[NormalizedEvent] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            payload: dict[str, Any] = {k: v for k, v in row.items() if v not in (None, "")}
            # Attempt to deserialise a JSON-encoded "raw" column
            if "raw" in payload and isinstance(payload["raw"], str):
                try:
                    payload["raw"] = json.loads(payload["raw"])
                except (json.JSONDecodeError, ValueError):
                    pass
            events.append(_parse_payload(payload, field_mappings=field_mappings))
    return events


def _parse_payload(
    payload: dict[str, Any],
    *,
    field_mappings: dict[str, str] | None = None,
) -> NormalizedEvent:
    """Convert a raw dict to NormalizedEvent, applying optional field remapping."""
    if field_mappings:
        remapped: dict[str, Any] = dict(payload)
        for dst, src in field_mappings.items():
            if src in payload and dst not in remapped:
                remapped[dst] = payload[src]
        payload = remapped

    # If the dict already has the required NormalizedEvent structure, validate directly
    required = {"timestamp", "provider", "service", "action"}
    if required.issubset(payload.keys()):
        try:
            return NormalizedEvent.model_validate(payload)
        except Exception:
            pass  # fall through to best-effort mapping

    # Best-effort mapping from common field name variants
    now = datetime.now(UTC).isoformat()
    return NormalizedEvent(
        timestamp=payload.get("timestamp")
        or payload.get("time")
        or payload.get("createdDateTime")
        or payload.get("eventTimestamp")
        or now,
        provider=payload.get("provider") or payload.get("source") or "imported",
        service=payload.get("service") or payload.get("category") or "imported",
        actor=payload.get("actor") or payload.get("user") or payload.get("userPrincipalName") or payload.get("caller"),
        action=payload.get("action")
        or payload.get("operation")
        or payload.get("operationName")
        or payload.get("activityDisplayName")
        or "unknown",
        target=payload.get("target") or payload.get("resource") or payload.get("objectId") or payload.get("resourceId"),
        result=payload.get("result") or payload.get("status"),
        severity=payload.get("severity") or payload.get("level"),
        correlation_id=payload.get("correlation_id") or payload.get("correlationId"),
        request_id=payload.get("request_id") or payload.get("id"),
        raw=payload,
    )

"""Normalization and enrichment helpers for provider events."""

from terminalvelocity.enrichment.cross_provider import CorrelatedEventGroup, CrossProviderEnricher
from terminalvelocity.enrichment.schema_mapper import (
    SchemaMapper,
    extract_first,
    normalize_actor,
    normalize_result,
    normalize_severity,
    normalize_target,
    normalize_timestamp,
)

__all__ = [
    "CorrelatedEventGroup",
    "CrossProviderEnricher",
    "SchemaMapper",
    "extract_first",
    "normalize_actor",
    "normalize_result",
    "normalize_severity",
    "normalize_target",
    "normalize_timestamp",
]

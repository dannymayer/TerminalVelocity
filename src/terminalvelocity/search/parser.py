from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

FIELD_NAMES = {"timestamp", "provider", "service", "tenant_id", "actor", "action", "target", "result", "severity", "correlation_id", "request_id"}
SORT_ALIASES = {"time": "timestamp", "timestamp": "timestamp", "severity": "severity", "provider": "provider"}
FIELD_TOKEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:.*$")
DEFAULT_SORT_DIRECTION = {"timestamp": True, "severity": True, "provider": False}


class QuerySyntaxError(ValueError):
    pass


@dataclass(slots=True)
class FieldFilter:
    field: str
    value: str


@dataclass(slots=True)
class SearchQuery:
    raw_query: str = ""
    free_text: list[str] = field(default_factory=list)
    field_filters: list[FieldFilter] = field(default_factory=list)
    since: str | None = None
    until: str | None = None
    sort_by: str = "timestamp"
    sort_desc: bool = True
    tags: list[str] = field(default_factory=list)
    include_archived: bool = False

    def field_values(self, name: str) -> list[str]:
        return [item.value for item in self.field_filters if item.field == name]


def parse_query(query: str) -> SearchQuery:
    parsed = SearchQuery(raw_query=query)
    if not query.strip():
        return parsed
    for token in shlex.split(query):
        if FIELD_TOKEN.match(token):
            name, value = token.split(":", 1)
            name = name.lower()
            if not value:
                raise QuerySyntaxError(f"Missing value for field '{name}'")
            if name in {"since", "after", "last"}:
                parsed.since = value
                continue
            if name in {"until", "before"}:
                parsed.until = value
                continue
            if name == "sort":
                parsed.sort_by, parsed.sort_desc = _parse_sort(value)
                continue
            if name == "tag":
                parsed.tags.append(value)
                continue
            if name == "show":
                if value.lower() in {"archived", "all"}:
                    parsed.include_archived = True
                continue
            if name not in FIELD_NAMES:
                raise QuerySyntaxError(f"Unsupported field '{name}'")
            parsed.field_filters.append(FieldFilter(field=name, value=value))
            continue
        parsed.free_text.append(token)
    return parsed


def _parse_sort(value: str) -> tuple[str, bool]:
    direction: bool | None = None
    if value.startswith("-"):
        direction = True
        value = value[1:]
    elif value.startswith("+"):
        direction = False
        value = value[1:]
    sort_by = SORT_ALIASES.get(value.lower())
    if sort_by is None:
        raise QuerySyntaxError(f"Unsupported sort field '{value}'")
    return sort_by, DEFAULT_SORT_DIRECTION[sort_by] if direction is None else direction

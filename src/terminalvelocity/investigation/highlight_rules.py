from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from terminalvelocity.models import NormalizedEvent


class HighlightRule(BaseModel):
    """A configurable rule that highlights or alerts on matching events."""

    model_config = ConfigDict(extra='forbid')

    name: str
    match: dict[str, Any] = Field(default_factory=dict)
    highlight: str
    alert: bool = False

    def matches_event(self, event: NormalizedEvent) -> bool:
        """Return True when all configured match criteria match the event."""

        # TODO(feature): match logic is strict AND across all fields with no
        # support for OR semantics (e.g. "severity is high OR critical").
        # Consider extending HighlightRule to accept a list of values per
        # field (already partially supported via Sequence), and/or add a
        # top-level "any_of" key to allow OR-chaining of entire conditions.
        for field_name, expected in self.match.items():
            actual = getattr(event, field_name, None)
            if isinstance(expected, Sequence) and not isinstance(expected, str):
                if all(not _matches_value(actual, item) for item in expected):
                    return False
                continue
            if not _matches_value(actual, expected):
                return False
        return True


class HighlightMatch(BaseModel):
    """A matched highlight rule and its resulting styling metadata."""

    rule_name: str
    highlight: str
    alert: bool


class HighlightRuleEngine:
    """Load and evaluate YAML highlight and alert rules."""

    def __init__(self, rules: Sequence[HighlightRule]) -> None:
        self.rules = list(rules)

    @classmethod
    def from_yaml(cls, payload: str) -> HighlightRuleEngine:
        """Create a rule engine from a YAML string."""

        data = yaml.safe_load(payload) or {}
        return cls._from_mapping(data)

    @classmethod
    def from_path(cls, path: str | Path) -> HighlightRuleEngine:
        """Create a rule engine from a YAML file on disk."""

        return cls.from_yaml(Path(path).read_text(encoding='utf-8'))

    @classmethod
    def _from_mapping(cls, data: Mapping[str, Any]) -> HighlightRuleEngine:
        rules = [HighlightRule.model_validate(item) for item in data.get('rules', [])]
        return cls(rules)

    def evaluate(self, event: NormalizedEvent) -> list[HighlightMatch]:
        """Return all rule matches for an event."""

        return [
            HighlightMatch(rule_name=rule.name, highlight=rule.highlight, alert=rule.alert)
            for rule in self.rules
            if rule.matches_event(event)
        ]

    def should_alert(self, event: NormalizedEvent) -> bool:
        """Return True when any matching rule is configured to alert."""

        return any(match.alert for match in self.evaluate(event))


def _matches_value(actual: Any, expected: Any) -> bool:
    if actual is None:
        return expected is None
    if isinstance(actual, str) and isinstance(expected, str):
        return actual.casefold() == expected.casefold()
    return actual == expected

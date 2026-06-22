"""Investigation workflow tools for TerminalVelocity."""

from terminalvelocity.investigation.export import EventExporter
from terminalvelocity.investigation.highlight_rules import HighlightMatch, HighlightRule, HighlightRuleEngine
from terminalvelocity.investigation.performance import (
    LRUResultCache,
    PagedResult,
    batched_events,
    deduplicate_events,
    paginate_iterable,
    paginate_sequence,
)
from terminalvelocity.investigation.pivot import PivotAnalyzer, PivotRelation
from terminalvelocity.investigation.replay import (
    IngestionSession,
    RecordedEvent,
    ReplayFrame,
    SessionRecorder,
    SessionReplayer,
)
from terminalvelocity.investigation.timeline import InvestigationTimeline, TimelineBuilder

__all__ = [
    "EventExporter",
    "HighlightMatch",
    "HighlightRule",
    "HighlightRuleEngine",
    "IngestionSession",
    "InvestigationTimeline",
    "LRUResultCache",
    "PagedResult",
    "PivotAnalyzer",
    "PivotRelation",
    "RecordedEvent",
    "ReplayFrame",
    "SessionRecorder",
    "SessionReplayer",
    "TimelineBuilder",
    "batched_events",
    "deduplicate_events",
    "paginate_iterable",
    "paginate_sequence",
]

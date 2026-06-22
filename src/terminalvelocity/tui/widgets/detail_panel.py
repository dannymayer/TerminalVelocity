"""Detail panel: normalized fields, correlation chain, and raw JSON."""

from __future__ import annotations

import json

from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static, TabbedContent, TabPane

from terminalvelocity.schema import NormalizedEvent
from terminalvelocity.tui.themes import PROVIDER_COLORS, PROVIDER_SHORT


class DetailPanel(Widget):
    """Shows selected event metadata, correlation chain, and JSON payloads."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._all_events: list[NormalizedEvent] = []

    def compose(self) -> ComposeResult:
        yield Static("Event detail", classes="panel-title")
        yield Static("Select a row to inspect.", id="detail-summary")
        with TabbedContent(initial="normalized"):
            with TabPane("Normalized", id="normalized"):
                with VerticalScroll():
                    yield Static(id="normalized-json", classes="detail-json")
            with TabPane("Chain", id="chain"):
                with VerticalScroll():
                    yield Static(id="chain-view", classes="detail-json")
            with TabPane("Raw JSON", id="raw"):
                with VerticalScroll():
                    yield Static(id="raw-json", classes="detail-json")

    def set_event_context(self, events: list[NormalizedEvent]) -> None:
        """Store the full current event list so the chain tab can find related events."""
        self._all_events = list(events)

    def clear(self) -> None:
        self.query_one("#detail-summary", Static).update("No event matches the current filters.")
        empty = Syntax("{}", "json", word_wrap=True)
        self.query_one("#normalized-json", Static).update(empty)
        self.query_one("#raw-json", Static).update(empty)
        self.query_one("#chain-view", Static).update(Text("No event selected.", style="#64748b"))

    def show_event(self, event: NormalizedEvent | None) -> None:
        if event is None:
            self.clear()
            return

        summary = (
            f"{event.timestamp.isoformat()} • {event.provider}/{event.service} • "
            f"{event.actor} → {event.target} • {event.result}/{event.severity}"
        )
        self.query_one("#detail-summary", Static).update(summary)

        normalized_json = json.dumps(event.to_record(), indent=2, sort_keys=True)
        self.query_one("#normalized-json", Static).update(
            Syntax(normalized_json, "json", word_wrap=True)
        )
        self.query_one("#raw-json", Static).update(
            Syntax(event.raw_json(), "json", word_wrap=True)
        )
        self.query_one("#chain-view", Static).update(self._build_chain_view(event))

    def _build_chain_view(self, event: NormalizedEvent) -> Text:
        chain = self._find_related(event)
        if not chain:
            content = Text()
            if event.correlation_id:
                content.append(f"Correlation: {event.correlation_id}\n", style="bold #93c5fd")
                content.append("No other linked events in current view.", style="#64748b")
            else:
                content.append("No correlation ID — event is standalone.", style="#64748b")
            return content

        content = Text()
        content.append("Correlation: ", style="#64748b")
        content.append(f"{event.correlation_id}", style="bold #93c5fd")
        content.append(f"  {len(chain)} linked\n\n", style="#64748b")

        for ev in sorted(chain, key=lambda e: e.timestamp, reverse=True):
            short = PROVIDER_SHORT.get(ev.provider, ev.provider.upper()[:8])
            badge_style = PROVIDER_COLORS.get(ev.provider, "white on #475569")
            row = Text()
            row.append(f" {short} ", style=badge_style)
            row.append("  ")
            row.append(ev.timestamp.strftime("%H:%M:%S"), style="#64748b")
            row.append("  ")
            sev_color = {
                "critical": "#dc2626",
                "high": "#f97316",
                "medium": "#facc15",
                "low": "#86efac",
            }.get((ev.severity or "").lower(), "#94a3b8")
            row.append("● ", style=f"bold {sev_color}")
            row.append(ev.action, style="#cbd5e1")
            content.append_text(row)
            content.append("\n")

        return content

    def _find_related(self, event: NormalizedEvent) -> list[NormalizedEvent]:
        if not event.correlation_id or not self._all_events:
            return []
        key = event.cache_key()
        return [
            e for e in self._all_events
            if e.correlation_id == event.correlation_id and e.cache_key() != key
        ]

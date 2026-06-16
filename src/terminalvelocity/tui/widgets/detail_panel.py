"""Detail panel showing normalized and raw event JSON."""

from __future__ import annotations

import json

from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static, TabbedContent, TabPane
from textual.widget import Widget

from terminalvelocity.schema import NormalizedEvent


class DetailPanel(Widget):
    """Shows selected event metadata and JSON payloads."""

    def compose(self) -> ComposeResult:
        yield Static("Event detail", classes="panel-title")
        yield Static("Select a row to inspect normalized and raw JSON.", id="detail-summary")
        with TabbedContent(initial="normalized"):
            with TabPane("Normalized", id="normalized"):
                with VerticalScroll():
                    yield Static(id="normalized-json", classes="detail-json")
            with TabPane("Raw JSON", id="raw"):
                with VerticalScroll():
                    yield Static(id="raw-json", classes="detail-json")

    def clear(self) -> None:
        self.query_one("#detail-summary", Static).update("No event matches the current filters.")
        empty = Syntax("{}", "json", word_wrap=True)
        self.query_one("#normalized-json", Static).update(empty)
        self.query_one("#raw-json", Static).update(empty)

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
        self.query_one("#normalized-json", Static).update(Syntax(normalized_json, "json", word_wrap=True))
        self.query_one("#raw-json", Static).update(Syntax(event.raw_json(), "json", word_wrap=True))

"""Top-level query and scope controls."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Input, Select, Static
from textual.widget import Widget

TIME_SCOPE_OPTIONS = [
    ("All time", "all"),
    ("Last 15m", "15m"),
    ("Last 1h", "1h"),
    ("Last 6h", "6h"),
    ("Last 24h", "24h"),
]


class QueryBar(Widget):
    """Search box, time scope selector, and status line."""

    class FilterChanged(Message):
        def __init__(self, query: str, scope: str) -> None:
            self.query = query
            self.scope = scope
            super().__init__()

    def compose(self) -> ComposeResult:
        yield Static("Query + scope", id="query-title")
        with Horizontal(id="query-controls"):
            yield Input(placeholder="Search events or field:value (provider:defender result:failure)", id="query-input")
            yield Select(TIME_SCOPE_OPTIONS, value="24h", allow_blank=False, id="time-scope")
        yield Static("Ready", id="query-status")

    def on_input_changed(self, _: Input.Changed) -> None:
        self.post_message(self.FilterChanged(self.query, self.scope))

    def on_select_changed(self, _: Select.Changed) -> None:
        self.post_message(self.FilterChanged(self.query, self.scope))

    @property
    def query(self) -> str:
        return self.query_one("#query-input", Input).value.strip()

    @property
    def scope(self) -> str:
        value = self.query_one("#time-scope", Select).value
        return "24h" if value is Select.BLANK else str(value)

    def focus_query(self) -> None:
        self.query_one("#query-input", Input).focus()

    def update_status(self, *, result_count: int, total_count: int, scope: str, mode: str, last_export: str | None) -> None:
        export_text = last_export or "not exported"
        status = (
            f"Results {result_count}/{total_count} • Scope {scope} • Mode {mode} "
            f"• / query • j/k rows • d detail • e/c export • Last export {export_text}"
        )
        self.query_one("#query-status", Static).update(status)

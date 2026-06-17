"""Center event table."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.message import Message
from textual.widgets import DataTable
from textual.widget import Widget

from terminalvelocity.schema import NormalizedEvent
from terminalvelocity.tui.themes import provider_badge, result_badge, severity_badge

_HIGHLIGHT_STYLES: dict[str, str] = {
    "red": "white on #dc2626",
    "yellow": "black on #facc15",
    "magenta": "white on #a855f7",
    "orange": "black on #f97316",
    "green": "black on #22c55e",
    "blue": "white on #3b82f6",
    "cyan": "black on #06b6d4",
}


class EventTable(Widget):
    """Tabular event list with row-selection notifications and highlight rules support."""

    class EventHighlighted(Message):
        def __init__(self, event: NormalizedEvent | None) -> None:
            self.event = event
            super().__init__()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._events: list[NormalizedEvent] = []
        self._highlight_engine = None  # HighlightRuleEngine | None
        self._show_correlation = False

    def compose(self) -> ComposeResult:
        yield DataTable(id="events-grid")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        self._rebuild_columns(table)

    def _rebuild_columns(self, table: DataTable) -> None:
        table.clear(columns=True)
        table.add_column("Time", width=20)
        table.add_column("Provider", width=16)
        table.add_column("Actor", width=22)
        table.add_column("Action", width=22)
        table.add_column("Result", width=10)
        table.add_column("Severity", width=10)
        if self._show_correlation:
            table.add_column("Corr.", width=7)

    def set_highlight_engine(self, engine) -> None:
        """Attach a HighlightRuleEngine for per-row styling."""
        self._highlight_engine = engine

    def set_show_correlation(self, show: bool) -> None:
        """Toggle the cross-provider correlation column."""
        self._show_correlation = show

    def set_events(self, events: list[NormalizedEvent]) -> None:
        self._events = list(events)
        table = self.query_one(DataTable)
        self._rebuild_columns(table)
        for index, event in enumerate(self._events):
            # Determine row highlight color from rules engine
            row_style: str | None = None
            if self._highlight_engine is not None:
                matches = self._highlight_engine.evaluate(event)
                if matches:
                    row_style = _HIGHLIGHT_STYLES.get(matches[0].highlight)

            def _styled(widget: Text, style: str | None) -> Text:
                if style:
                    widget.stylize(style)
                return widget

            actor_text = _styled(Text(event.actor or "—", overflow="ellipsis", no_wrap=True), row_style)
            action_text = _styled(Text(f"{event.service}:{event.action}", overflow="ellipsis", no_wrap=True), row_style)
            time_text = _styled(Text(event.timestamp.strftime("%Y-%m-%d %H:%M:%S")), row_style)

            row_cells: list = [
                time_text,
                provider_badge(event.provider),
                actor_text,
                action_text,
                result_badge(event.result or "—"),
                severity_badge(event.severity or "—"),
            ]
            if self._show_correlation:
                related_count = getattr(event, "related_provider_count", 0) or 0
                corr_text = Text(f"+{related_count}" if related_count else "—", style="#94a3b8" if not related_count else "#60a5fa")
                row_cells.append(corr_text)

            table.add_row(*row_cells, key=str(index))

        if self._events:
            table.move_cursor(row=0, animate=False, scroll=True)
            self.post_message(self.EventHighlighted(self._events[0]))
        else:
            self.post_message(self.EventHighlighted(None))

    def current_event(self) -> NormalizedEvent | None:
        table = self.query_one(DataTable)
        row = table.cursor_row
        if 0 <= row < len(self._events):
            return self._events[row]
        return None

    def focus_table(self) -> None:
        self.query_one(DataTable).focus()

    def move_up(self) -> None:
        table = self.query_one(DataTable)
        if table.row_count:
            table.action_cursor_up()
            self.post_message(self.EventHighlighted(self.current_event()))

    def move_down(self) -> None:
        table = self.query_one(DataTable)
        if table.row_count:
            table.action_cursor_down()
            self.post_message(self.EventHighlighted(self.current_event()))

    def move_top(self) -> None:
        table = self.query_one(DataTable)
        if table.row_count:
            table.move_cursor(row=0, animate=False)
            self.post_message(self.EventHighlighted(self.current_event()))

    def move_bottom(self) -> None:
        table = self.query_one(DataTable)
        if table.row_count:
            table.move_cursor(row=table.row_count - 1, animate=False)
            self.post_message(self.EventHighlighted(self.current_event()))

    @property
    def row_count(self) -> int:
        """Number of rows currently displayed in the inner DataTable."""
        return self.query_one(DataTable).row_count

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if 0 <= event.cursor_row < len(self._events):
            self.post_message(self.EventHighlighted(self._events[event.cursor_row]))

"""Center event table."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.message import Message
from textual.widgets import DataTable
from textual.widget import Widget

from terminalvelocity.schema import NormalizedEvent
from terminalvelocity.tui.themes import provider_badge, result_badge, severity_badge


class EventTable(Widget):
    """Tabular event list with row-selection notifications."""

    class EventHighlighted(Message):
        def __init__(self, event: NormalizedEvent | None) -> None:
            self.event = event
            super().__init__()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._events: list[NormalizedEvent] = []

    def compose(self) -> ComposeResult:
        yield DataTable(id="events-grid")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("Time", width=20)
        table.add_column("Provider", width=16)
        table.add_column("Actor", width=24)
        table.add_column("Action", width=24)
        table.add_column("Result", width=12)
        table.add_column("Severity", width=12)

    def set_events(self, events: list[NormalizedEvent]) -> None:
        self._events = list(events)
        table = self.query_one(DataTable)
        table.clear(columns=False)
        for index, event in enumerate(self._events):
            table.add_row(
                event.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                provider_badge(event.provider),
                Text(event.actor, overflow="ellipsis", no_wrap=True),
                Text(f"{event.service}:{event.action}", overflow="ellipsis", no_wrap=True),
                result_badge(event.result),
                severity_badge(event.severity),
                key=str(index),
            )
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

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if 0 <= event.cursor_row < len(self._events):
            self.post_message(self.EventHighlighted(self._events[event.cursor_row]))

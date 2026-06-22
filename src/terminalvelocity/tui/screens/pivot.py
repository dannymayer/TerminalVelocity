"""Pivot screen: show events related to the currently selected event (key: p)."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Static

from terminalvelocity.investigation.pivot import PivotAnalyzer
from terminalvelocity.schema import NormalizedEvent
from terminalvelocity.tui.themes import provider_badge, result_badge, severity_badge


class PivotScreen(ModalScreen[NormalizedEvent | None]):
    """Modal that shows all events related to a seed event via actor/target/session."""

    BINDINGS = [  # noqa: RUF012
        Binding("escape", "close", "Close"),
        Binding("enter", "select_event", "Jump to event"),
        Binding("j,down", "cursor_down", "Next", show=False),
        Binding("k,up", "cursor_up", "Prev", show=False),
    ]

    CSS = """
    PivotScreen {
        align: center middle;
    }
    #pivot-dialog {
        width: 90%;
        height: 80%;
        border: round #60a5fa;
        background: #020617;
        padding: 1;
    }
    #pivot-title {
        color: #93c5fd;
        text-style: bold;
        margin-bottom: 1;
    }
    #pivot-subtitle {
        color: #94a3b8;
        margin-bottom: 1;
    }
    """

    def __init__(self, seed: NormalizedEvent, all_events: list[NormalizedEvent]) -> None:
        super().__init__()
        self._seed = seed
        self._all_events = all_events
        self._analyzer = PivotAnalyzer()
        self._pivot_events: list[NormalizedEvent] = []

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical
        with Vertical(id="pivot-dialog"):
            yield Static("Pivot: Related Events", id="pivot-title")
            yield Static("", id="pivot-subtitle")
            yield DataTable(id="pivot-table", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        relations = self._analyzer.related_to_event(self._seed, self._all_events)
        self._pivot_events = [r.event for r in relations if r.event.stable_id() != self._seed.stable_id()]

        actor = self._seed.actor or "—"
        target = self._seed.target or "—"
        self.query_one("#pivot-subtitle", Static).update(
            f"Seed: {self._seed.action} | actor={actor} | target={target} | "
            f"{len(self._pivot_events)} related event(s)"
        )

        table = self.query_one(DataTable)
        table.add_column("Time", width=20)
        table.add_column("Provider", width=14)
        table.add_column("Actor", width=22)
        table.add_column("Action", width=22)
        table.add_column("Result", width=10)
        table.add_column("Sev", width=10)
        table.add_column("Via", width=10)

        relation_map = {r.event.stable_id(): r.relation for r in relations}
        for event in self._pivot_events:
            via = relation_map.get(event.stable_id(), "")
            table.add_row(
                event.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                provider_badge(event.provider),
                Text(event.actor or "—", overflow="ellipsis", no_wrap=True),
                Text(f"{event.service}:{event.action}", overflow="ellipsis", no_wrap=True),
                result_badge(event.result or "—"),
                severity_badge(event.severity or "—"),
                Text(via, style="#94a3b8"),
            )

    def action_close(self) -> None:
        self.dismiss(None)

    def action_select_event(self) -> None:
        table = self.query_one(DataTable)
        row = table.cursor_row
        if 0 <= row < len(self._pivot_events):
            self.dismiss(self._pivot_events[row])

    def action_cursor_down(self) -> None:
        self.query_one(DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(DataTable).action_cursor_up()

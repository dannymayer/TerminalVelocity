"""Anomaly screen: display detected anomalies from the current result set (key: a)."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Static

from terminalvelocity.schema import NormalizedEvent
from terminalvelocity.search.anomaly import AnomalyDetector, AnomalyMarker

_KIND_STYLES = {
    "burst_failures": "white on #dc2626",
    "rare_action": "black on #facc15",
    "privileged_operation": "white on #7c3aed",
}


class AnomalyScreen(ModalScreen[None]):
    """Modal listing anomalies detected in the current filtered result set."""

    BINDINGS = [  # noqa: RUF012
        Binding("escape", "close", "Close"),
        Binding("j,down", "cursor_down", "Next", show=False),
        Binding("k,up", "cursor_up", "Prev", show=False),
    ]

    CSS = """
    AnomalyScreen {
        align: center middle;
    }
    #anomaly-dialog {
        width: 90%;
        height: 80%;
        border: round #f97316;
        background: #020617;
        padding: 1;
    }
    #anomaly-title {
        color: #fdba74;
        text-style: bold;
        margin-bottom: 1;
    }
    #anomaly-subtitle {
        color: #94a3b8;
        margin-bottom: 1;
    }
    """

    def __init__(self, events: list[NormalizedEvent]) -> None:
        super().__init__()
        self._events = events
        self._markers: list[AnomalyMarker] = []

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical

        with Vertical(id="anomaly-dialog"):
            yield Static("⚠ Anomaly Detection Results", id="anomaly-title")
            yield Static("", id="anomaly-subtitle")
            yield DataTable(id="anomaly-table", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        detector = AnomalyDetector()
        self._markers = detector.detect(self._events)

        self.query_one("#anomaly-subtitle", Static).update(
            f"{len(self._markers)} anomaly marker(s) detected across {len(self._events)} event(s)"
        )

        table = self.query_one(DataTable)
        table.add_column("Kind", width=22)
        table.add_column("Description", width=50)
        table.add_column("Events", width=8, key="events")

        for marker in self._markers:
            kind_text = Text(f" {marker.kind} ")
            kind_text.stylize(_KIND_STYLES.get(marker.kind, "white on #475569"))
            table.add_row(
                kind_text,
                Text(marker.description, overflow="ellipsis", no_wrap=True),
                Text(str(len(marker.events)), style="#94a3b8"),
            )

        if not self._markers:
            self.query_one("#anomaly-subtitle", Static).update("No anomalies detected in the current result set.")

    def action_close(self) -> None:
        self.dismiss(None)

    def action_cursor_down(self) -> None:
        self.query_one(DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(DataTable).action_cursor_up()

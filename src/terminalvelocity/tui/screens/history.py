"""Query history screen: browse and reload previously executed queries (ctrl+r)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Static

from terminalvelocity.search.history import QueryHistoryEntry, QueryHistoryStore


class HistoryScreen(ModalScreen[str | None]):
    """Modal showing recent search query history.

    Dismisses with the selected query string to reload into the query bar,
    or ``None`` if cancelled.
    """

    BINDINGS = [  # noqa: RUF012
        Binding("escape", "close", "Close"),
        Binding("enter", "load_selected", "Load"),
        Binding("ctrl+l", "clear_history", "Clear history"),
        Binding("j,down", "cursor_down", "Next", show=False),
        Binding("k,up", "cursor_up", "Prev", show=False),
    ]

    CSS = """
    HistoryScreen {
        align: center middle;
    }
    #history-dialog {
        width: 80%;
        height: 75%;
        border: round #64748b;
        background: #020617;
        padding: 1;
    }
    #history-title {
        color: #94a3b8;
        text-style: bold;
        margin-bottom: 1;
    }
    #history-hint {
        color: #475569;
        height: 1;
        margin-top: 1;
    }
    """

    def __init__(self, store: QueryHistoryStore) -> None:
        super().__init__()
        self._store = store
        self._entries: list[QueryHistoryEntry] = []

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical
        with Vertical(id="history-dialog"):
            yield Static("Query History", id="history-title")
            yield DataTable(id="history-table", cursor_type="row", zebra_stripes=True)
            yield Static("enter=load  ctrl+l=clear  esc=close", id="history-hint")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        self._entries = self._store.list()
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.add_column("Query", width=42)
        table.add_column("Scope", width=8)
        table.add_column("Results", width=10)
        table.add_column("Executed", width=20)
        for entry in self._entries:
            table.add_row(entry.query, entry.scope, str(entry.result_count), entry.executed_at[:19])

    def action_close(self) -> None:
        self.dismiss(None)

    def action_load_selected(self) -> None:
        table = self.query_one(DataTable)
        row = table.cursor_row
        if 0 <= row < len(self._entries):
            self.dismiss(self._entries[row].query)

    def action_clear_history(self) -> None:
        self._store.clear()
        self._refresh()

    def action_cursor_down(self) -> None:
        self.query_one(DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(DataTable).action_cursor_up()

"""Saved queries screen: list, load, and save named search queries (key: s)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Input, Label, Static

from terminalvelocity.search.saved_queries import SavedQuery, SavedQueryStore


class SavedQueriesScreen(ModalScreen[str | None]):
    """Modal for managing saved search queries.

    Dismisses with the selected query string to load into the query bar,
    or ``None`` if cancelled.
    """

    BINDINGS = [  # noqa: RUF012
        Binding("escape", "close", "Close"),
        Binding("enter", "load_selected", "Load"),
        Binding("ctrl+s", "save_current", "Save"),
        Binding("ctrl+d", "delete_selected", "Delete"),
        Binding("j,down", "cursor_down", "Next", show=False),
        Binding("k,up", "cursor_up", "Prev", show=False),
    ]

    CSS = """
    SavedQueriesScreen {
        align: center middle;
    }
    #sq-dialog {
        width: 80%;
        height: 75%;
        border: round #818cf8;
        background: #020617;
        padding: 1;
    }
    #sq-title {
        color: #a5b4fc;
        text-style: bold;
        margin-bottom: 1;
    }
    #sq-save-row {
        height: 5;
        margin-top: 1;
        border-top: solid #334155;
        padding-top: 1;
    }
    #sq-name-input {
        width: 1fr;
    }
    #sq-hint {
        color: #94a3b8;
        height: 1;
        margin-top: 1;
    }
    """

    def __init__(self, store: SavedQueryStore, current_query: str = "") -> None:
        super().__init__()
        self._store = store
        self._current_query = current_query
        self._queries: list[SavedQuery] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="sq-dialog"):
            yield Static("Saved Queries", id="sq-title")
            yield DataTable(id="sq-table", cursor_type="row", zebra_stripes=True)
            with Horizontal(id="sq-save-row"):
                yield Label("Name: ")
                yield Input(placeholder="Enter name to save current query…", id="sq-name-input")
            yield Static("enter=load  ctrl+s=save  ctrl+d=delete  esc=close", id="sq-hint")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_table()

    def _refresh_table(self) -> None:
        self._queries = self._store.list()
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.add_column("Name", width=24)
        table.add_column("Query", width=40)
        table.add_column("Saved", width=20)
        for sq in self._queries:
            table.add_row(sq.name, sq.query, sq.updated_at[:19])

    def action_close(self) -> None:
        self.dismiss(None)

    def action_load_selected(self) -> None:
        table = self.query_one(DataTable)
        row = table.cursor_row
        if 0 <= row < len(self._queries):
            self.dismiss(self._queries[row].query)

    def action_save_current(self) -> None:
        name = self.query_one("#sq-name-input", Input).value.strip()
        if not name or not self._current_query.strip():
            return
        self._store.save(name, self._current_query)
        self.query_one("#sq-name-input", Input).value = ""
        self._refresh_table()

    def action_delete_selected(self) -> None:
        table = self.query_one(DataTable)
        row = table.cursor_row
        if 0 <= row < len(self._queries):
            self._store.delete(self._queries[row].name)
            self._refresh_table()

    def action_cursor_down(self) -> None:
        self.query_one(DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(DataTable).action_cursor_up()

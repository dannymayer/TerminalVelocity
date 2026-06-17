"""Tag screen: apply or remove labels on the selected event (key: b)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Label, Static
from textual.containers import Horizontal, Vertical

from terminalvelocity.schema import NormalizedEvent
from terminalvelocity.search.engine import SearchEngine


class TagScreen(ModalScreen[None]):
    """Modal for viewing and editing tags on the currently selected event."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("enter", "apply_tag", "Apply"),
    ]

    CSS = """
    TagScreen {
        align: center middle;
    }
    #tag-dialog {
        width: 60%;
        height: auto;
        border: round #f472b6;
        background: #020617;
        padding: 1 2;
    }
    #tag-title {
        color: #f9a8d4;
        text-style: bold;
        margin-bottom: 1;
    }
    #tag-current {
        color: #94a3b8;
        margin-bottom: 1;
    }
    #tag-input-row {
        height: 3;
        margin-top: 1;
    }
    #tag-input {
        width: 1fr;
    }
    #tag-hint {
        color: #475569;
        height: 1;
        margin-top: 1;
    }
    """

    def __init__(self, event: NormalizedEvent, engine: SearchEngine) -> None:
        super().__init__()
        self._event = event
        self._engine = engine
        self._event_id = event.stable_id()

    def compose(self) -> ComposeResult:
        with Vertical(id="tag-dialog"):
            yield Static("Tag Event", id="tag-title")
            yield Static("", id="tag-current")
            with Horizontal(id="tag-input-row"):
                yield Label("Tag: ")
                yield Input(placeholder="add:label  or  remove:label", id="tag-input")
            yield Static("Prefix with 'remove:' to delete a tag. enter=apply  esc=close", id="tag-hint")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_current()

    def _refresh_current(self) -> None:
        tags = self._engine.get_event_tags(self._event_id)
        label = ", ".join(tags) if tags else "(none)"
        self.query_one("#tag-current", Static).update(
            f"Event: {self._event.action} [{self._event.provider}]  •  Tags: {label}"
        )

    def action_close(self) -> None:
        self.dismiss(None)

    def action_apply_tag(self) -> None:
        raw = self.query_one("#tag-input", Input).value.strip()
        if not raw:
            self.dismiss(None)
            return
        if raw.startswith("remove:"):
            tag = raw[len("remove:"):].strip()
            if tag:
                self._engine.untag_event(self._event_id, tag)
        else:
            tag = raw.lstrip("add:").strip()
            if tag:
                self._engine.tag_event(self._event_id, tag)
        self.query_one("#tag-input", Input).value = ""
        self._refresh_current()

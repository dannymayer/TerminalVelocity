"""Timeline screen: chronological actor/target view across providers (key: t)."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Static

from terminalvelocity.investigation.timeline import TimelineBuilder
from terminalvelocity.schema import NormalizedEvent
from terminalvelocity.tui.themes import provider_badge, result_badge, severity_badge


class TimelineScreen(ModalScreen[None]):
    """Modal showing a cross-provider chronological timeline for the selected event's actor."""

    BINDINGS = [  # noqa: RUF012
        Binding("escape", "close", "Close"),
        Binding("j,down", "cursor_down", "Next", show=False),
        Binding("k,up", "cursor_up", "Prev", show=False),
    ]

    CSS = """
    TimelineScreen {
        align: center middle;
    }
    #timeline-dialog {
        width: 92%;
        height: 82%;
        border: round #34d399;
        background: #020617;
        padding: 1;
    }
    #timeline-title {
        color: #6ee7b7;
        text-style: bold;
        margin-bottom: 1;
    }
    #timeline-subtitle {
        color: #94a3b8;
        margin-bottom: 1;
    }
    """

    def __init__(self, seed: NormalizedEvent, all_events: list[NormalizedEvent]) -> None:
        super().__init__()
        self._seed = seed
        self._all_events = all_events
        self._timeline_events: list[NormalizedEvent] = []

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical
        with Vertical(id="timeline-dialog"):
            yield Static("Timeline: Actor Activity", id="timeline-title")
            yield Static("", id="timeline-subtitle")
            yield DataTable(id="timeline-table", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        builder = TimelineBuilder()
        actor = self._seed.actor

        # Gather events for this actor across all providers
        if actor:
            relevant = [e for e in self._all_events if e.actor and e.actor.casefold() == actor.casefold()]
        else:
            relevant = list(self._all_events)

        timelines = builder.build(relevant)
        # Flatten all timelines into chronological order
        seen: set[str] = set()
        for tl in timelines:
            for ev in tl.events:
                eid = ev.stable_id()
                if eid not in seen:
                    seen.add(eid)
                    self._timeline_events.append(ev)

        subject = f'actor "{actor}"' if actor else "all events"
        self.query_one("#timeline-subtitle", Static).update(
            f"Timeline for {subject} — {len(self._timeline_events)} event(s) across "
            f"{len({e.provider for e in self._timeline_events})} provider(s)"
        )

        table = self.query_one(DataTable)
        table.add_column("Time", width=20)
        table.add_column("Provider", width=14)
        table.add_column("Service", width=14)
        table.add_column("Action", width=22)
        table.add_column("Target", width=20)
        table.add_column("Result", width=10)
        table.add_column("Sev", width=10)

        for event in self._timeline_events:
            table.add_row(
                event.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                provider_badge(event.provider),
                Text(event.service, overflow="ellipsis", no_wrap=True),
                Text(event.action, overflow="ellipsis", no_wrap=True),
                Text(event.target or "—", overflow="ellipsis", no_wrap=True),
                result_badge(event.result or "—"),
                severity_badge(event.severity or "—"),
            )

    def action_close(self) -> None:
        self.dismiss(None)

    def action_cursor_down(self) -> None:
        self.query_one(DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(DataTable).action_cursor_up()

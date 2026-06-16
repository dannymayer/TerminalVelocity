"""Provider status sidebar."""

from __future__ import annotations

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Static
from textual.widget import Widget

from terminalvelocity.schema import ProviderStatus
from terminalvelocity.tui.themes import provider_badge, state_badge


class ProviderPanel(Widget):
    """Displays provider availability, lag, and filtered counts."""

    def compose(self) -> ComposeResult:
        yield Static("Providers", classes="panel-title")
        yield Static(id="provider-body")

    def update_statuses(self, statuses: list[ProviderStatus], filtered_counts: dict[str, int]) -> None:
        table = Table.grid(expand=True)
        table.add_column("Provider", ratio=2)
        table.add_column("State", ratio=1)
        table.add_column("Count", justify="right")
        table.add_column("Lag", justify="right")
        table.add_column("Err", justify="right")
        for status in statuses:
            filtered = filtered_counts.get(status.provider, 0)
            count_text = Text(f"{filtered}/{status.total_events}")
            errors = Text(str(status.error_count), style="#fca5a5" if status.error_count else "#94a3b8")
            table.add_row(
                provider_badge(status.provider),
                state_badge(status.state),
                count_text,
                Text(f"{status.lag_seconds}s", style="#94a3b8"),
                errors,
            )
        footer = Text("Keyboard-first triage with live mock provider health.", style="#94a3b8")
        self.query_one("#provider-body", Static).update(Group(table, Text(""), footer))

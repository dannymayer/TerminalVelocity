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
    """Displays provider availability, lag, filtered counts, and anomaly badge."""

    def compose(self) -> ComposeResult:
        yield Static("Providers", classes="panel-title")
        yield Static(id="provider-body")

    def update_statuses(
        self,
        statuses: list[ProviderStatus],
        filtered_counts: dict[str, int],
        *,
        anomaly_count: int = 0,
        alert_count: int = 0,
    ) -> None:
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
        rows: list = [table, Text("")]
        if alert_count:
            alert_line = Text()
            alert_line.append(f" ⚑ {alert_count} alert rule match{'es' if alert_count != 1 else ''} ", style="white on #dc2626")
            rows.append(alert_line)
            rows.append(Text(""))
        if anomaly_count:
            anomaly_line = Text()
            anomaly_line.append(f" ⚠ {anomaly_count} anomaly marker{'s' if anomaly_count != 1 else ''} ", style="black on #f97316")
            rows.append(anomaly_line)
            rows.append(Text(""))
        rows.append(Text("p pivot  t timeline  a anomalies", style="#94a3b8"))
        self.query_one("#provider-body", Static).update(Group(*rows))

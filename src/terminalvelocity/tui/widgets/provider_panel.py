"""Provider status sidebar showing 14 M365 providers in 5 groups."""

from __future__ import annotations

from rich.console import Group as RichGroup
from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Static
from textual.widget import Widget

from terminalvelocity.schema import ProviderStatus
from terminalvelocity.tui.themes import (
    PROVIDER_COLORS,
    PROVIDER_GROUPS,
    PROVIDER_NAME,
    PROVIDER_SHORT,
    STATE_DOT_COLORS,
    provider_badge,
)


class ProviderPanel(Widget):
    """Displays all 14 M365 provider states, lag, counts, and anomaly/alert badges."""

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
        status_map = {s.provider: s for s in statuses}
        rows: list = []

        for group_name, providers in PROVIDER_GROUPS:
            # Group header
            header = Text(f" {group_name}", style="bold #475569")
            rows.append(header)

            for prov in providers:
                status = status_map.get(prov)
                state = status.state if status else "ok"
                lag_s = status.lag_seconds if status else 0
                err = status.error_count if status else 0
                count = filtered_counts.get(prov, 0)

                dot_color = STATE_DOT_COLORS.get(state, "#475569")
                short = PROVIDER_SHORT.get(prov, prov.upper()[:8])
                name = PROVIDER_NAME.get(prov, prov)
                badge_style = PROVIDER_COLORS.get(prov, "white on #475569")

                lag_str = _fmt_lag(lag_s, state)

                row = Text()
                row.append("● ", style=f"bold {dot_color}")
                badge = Text(f" {short} ")
                badge.stylize(badge_style)
                row.append_text(badge)
                row.append(f" {name:<20}", style="#cbd5e1")
                row.append(f"{lag_str:>5}", style="#64748b" if state == "ok" else "#fca5a5" if state == "error" else "#facc15")
                count_style = "bold #cbd5e1" if count else "#475569"
                row.append(f" {count:>3}", style=count_style)
                rows.append(row)

        rows.append(Text(""))

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
        self.query_one("#provider-body", Static).update(RichGroup(*rows))


def _fmt_lag(lag_seconds: int, state: str) -> str:
    if state == "error":
        return "err"
    if lag_seconds >= 3600:
        return f"{lag_seconds // 3600}h"
    if lag_seconds >= 60:
        return f"{lag_seconds // 60}m"
    return f"{lag_seconds}s"

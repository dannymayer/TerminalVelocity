"""Charts strip: event volume sparkline, severity mix, and stat tiles."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from rich.text import Text
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from terminalvelocity.schema import NormalizedEvent

_BLOCKS = " ▁▂▃▄▅▆▇█"


def _bar_char(fraction: float) -> str:
    idx = min(8, max(0, int(fraction * 9)))
    return _BLOCKS[idx]


class ChartsStrip(Widget):
    """Event volume bar chart, severity mix, and stat tiles rendered side-by-side."""

    DEFAULT_CSS = """
    ChartsStrip {
        height: 9;
        layout: horizontal;
        margin: 0 0 1 0;
    }
    #chart-volume {
        width: 3fr;
        border: round #334155;
        background: #111827;
        padding: 0 1;
    }
    #chart-severity {
        width: 2fr;
        margin-left: 1;
        border: round #334155;
        background: #111827;
        padding: 0 1;
    }
    #chart-stats {
        width: 26;
        margin-left: 1;
        border: round #334155;
        background: #111827;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="chart-volume")
        yield Static("", id="chart-severity")
        yield Static("", id="chart-stats")

    def update_charts(
        self,
        events: list[NormalizedEvent],
        total_count: int,
        alert_count: int,
        anomaly_count: int,
    ) -> None:
        self._render_volume(events)
        self._render_severity(events)
        self._render_stats(events, total_count, alert_count, anomaly_count)

    def _render_volume(self, events: list[NormalizedEvent]) -> None:
        now = datetime.now(tz=UTC)
        N = 28
        total_counts = [0] * N
        fail_counts = [0] * N

        for ev in events:
            delta_h = (now - ev.timestamp).total_seconds() / 3600
            bucket = N - 1 - min(N - 1, max(0, int(delta_h * N / 24)))
            total_counts[bucket] += 1
            if (ev.result or "").lower() in ("failure", "atrisk"):
                fail_counts[bucket] += 1

        max_t = max(total_counts) if any(total_counts) else 1
        ROWS = 5

        content = Text()
        title = Text("EVENT VOLUME · 24h", style="bold #93c5fd")
        title.append("  ▆ ", style="#3b82f6")
        title.append("total ", style="#64748b")
        title.append("▆ ", style="#dc2626")
        title.append("fail", style="#64748b")
        content.append_text(title)
        content.append("\n")

        for row in range(ROWS - 1, -1, -1):
            threshold_lo = row / ROWS
            threshold_hi = (row + 1) / ROWS
            for i in range(N):
                t_frac = total_counts[i] / max_t
                f_frac = fail_counts[i] / max_t
                if t_frac >= threshold_hi:
                    if f_frac >= threshold_hi:
                        content.append("█", style="#dc2626")
                    else:
                        content.append("█", style="#1d4ed8")
                elif t_frac > threshold_lo:
                    partial = (t_frac - threshold_lo) / max(0.001, threshold_hi - threshold_lo)
                    content.append(_bar_char(partial), style="#3b82f6")
                else:
                    content.append(" ")
            content.append("\n")

        # Timeline labels spaced across N chars
        mid = N // 2
        timeline = Text("-24h", style="#475569")
        timeline.append(" " * max(0, mid - 8))
        timeline.append("-12h", style="#475569")
        timeline.append(" " * max(0, N - mid - 3))
        timeline.append("now", style="#475569")
        content.append_text(timeline)

        self.query_one("#chart-volume", Static).update(content)

    def _render_severity(self, events: list[NormalizedEvent]) -> None:
        sev_counts: Counter[str] = Counter()
        for ev in events:
            if ev.severity:
                sev_counts[ev.severity.lower()] += 1

        max_s = max(sev_counts.values()) if sev_counts else 1
        BAR_W = 16

        content = Text("SEVERITY MIX\n", style="bold #93c5fd")
        sev_styles = [
            ("critical", "#dc2626"),
            ("high", "#f97316"),
            ("medium", "#facc15"),
            ("low", "#86efac"),
        ]
        for sev, color in sev_styles:
            count = sev_counts.get(sev, 0)
            bar_len = int(count / max_s * BAR_W) if max_s > 0 else 0
            line = Text()
            line.append(f"{sev:<9}", style="#94a3b8")
            line.append("█" * bar_len, style=color)
            line.append(" " * (BAR_W - bar_len))
            line.append(f" {count:>3}", style="bold #cbd5e1")
            content.append_text(line)
            content.append("\n")

        self.query_one("#chart-severity", Static).update(content)

    def _render_stats(
        self,
        events: list[NormalizedEvent],
        total_count: int,
        alert_count: int,
        anomaly_count: int,
    ) -> None:
        tiles = [
            ("EVENTS 24h", f"{total_count:,}", "#e2e8f0"),
            ("IN VIEW", str(len(events)), "#93c5fd"),
            ("ALERTS", str(alert_count), "#f87171"),
            ("ANOMALIES", str(anomaly_count), "#fdba74"),
        ]
        content = Text()
        for label, value, color in tiles:
            line = Text()
            line.append(f"  {label:<14}", style="#64748b")
            line.append(f"{value:>5}", style=f"bold {color}")
            content.append_text(line)
            content.append("\n")

        self.query_one("#chart-stats", Static).update(content)

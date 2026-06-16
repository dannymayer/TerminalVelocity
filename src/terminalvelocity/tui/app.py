"""Phase 1 core TUI application."""

from __future__ import annotations

import asyncio
import csv
import json
import random
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Markdown, Static

from terminalvelocity.schema import NormalizedEvent, ProviderStatus
from terminalvelocity.tui.keybindings import HELP_TEXT, KEY_BINDINGS
from terminalvelocity.tui.themes import APP_CSS
from terminalvelocity.tui.widgets.detail_panel import DetailPanel
from terminalvelocity.tui.widgets.event_table import EventTable
from terminalvelocity.tui.widgets.provider_panel import ProviderPanel
from terminalvelocity.tui.widgets.query_bar import QueryBar

PROVIDER_CATALOG = [
    ("entra", "signin"),
    ("defender", "incident"),
    ("intune", "device"),
    ("purview", "audit"),
]

ACTORS = [
    "alex@contoso.com",
    "jamie@contoso.com",
    "svc-sync@contoso.com",
    "soc-automation@contoso.com",
    "lee@contoso.com",
]

ACTIONS = {
    "entra": ["sign-in", "token-refresh", "mfa-challenge", "app-consent"],
    "defender": ["alert-opened", "device-isolated", "incident-updated", "malware-detected"],
    "intune": ["policy-sync", "device-enroll", "compliance-check", "script-run"],
    "purview": ["mailbox-search", "audit-export", "retention-change", "label-apply"],
}

TARGETS = {
    "entra": ["tenant", "service-principal", "user-session"],
    "defender": ["device-042", "host-db-01", "mailbox-ops"],
    "intune": ["device-129", "policy-baseline", "win11-fleet"],
    "purview": ["case-12", "mailbox-ceo", "site-legal"],
}

SEVERITIES = ["low", "medium", "high", "critical"]
RESULTS = ["success", "success", "success", "failure"]
TIME_SCOPES = {
    "all": None,
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
}


class HelpScreen(ModalScreen[None]):
    """Simple help modal opened with ?."""

    BINDINGS = [("escape", "close", "Close"), ("enter", "close", "Close"), ("question_mark", "close", "Close")]

    def compose(self) -> ComposeResult:
        yield Markdown(HELP_TEXT, id="help-dialog")

    def action_close(self) -> None:
        self.dismiss()


class TerminalVelocityApp(App[None]):
    """Keyboard-first Textual log triage UI backed by mock data."""

    CSS = APP_CSS
    BINDINGS = KEY_BINDINGS

    def __init__(self, *, seed: int = 365, count: int = 72) -> None:
        super().__init__()
        self.seed = seed
        self.count = count
        self.deep_detail = False
        self.last_export: str | None = None
        self.provider_statuses: list[ProviderStatus] = []
        self.events: list[NormalizedEvent] = []
        self.filtered_events: list[NormalizedEvent] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield QueryBar(id="query-bar")
        with Horizontal(id="workspace"):
            yield ProviderPanel(id="provider-panel")
            with Vertical(id="center-stack"):
                with Horizontal(id="overview-pane"):
                    yield EventTable(id="event-table")
                    yield DetailPanel(id="detail-right")
                yield DetailPanel(id="detail-bottom")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "TerminalVelocity"
        self.sub_title = "Phase 1 core TUI"
        self.events, self.provider_statuses = generate_mock_dataset(seed=self.seed, count=self.count)
        self.refresh_view()
        self.query_one(EventTable).focus_table()

    def action_focus_query(self) -> None:
        self.query_one(QueryBar).focus_query()

    def action_cursor_down(self) -> None:
        self.query_one(EventTable).move_down()

    def action_cursor_up(self) -> None:
        self.query_one(EventTable).move_up()

    def action_jump_top(self) -> None:
        self.query_one(EventTable).move_top()

    def action_jump_bottom(self) -> None:
        self.query_one(EventTable).move_bottom()

    def action_toggle_deep_detail(self) -> None:
        self.deep_detail = not self.deep_detail
        if self.deep_detail:
            self.add_class("deep-mode")
        else:
            self.remove_class("deep-mode")
        self.update_status_line()

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_export_json(self) -> None:
        path = self.export_filtered("json")
        self.notify(f"Exported {len(self.filtered_events)} rows to {path.name}")

    def action_export_csv(self) -> None:
        path = self.export_filtered("csv")
        self.notify(f"Exported {len(self.filtered_events)} rows to {path.name}")

    def on_query_bar_filter_changed(self, event: QueryBar.FilterChanged) -> None:
        del event
        self.refresh_view()

    def on_event_table_event_highlighted(self, event: EventTable.EventHighlighted) -> None:
        self.update_detail_panels(event.event)

    def refresh_view(self) -> None:
        self.filtered_events = self.apply_filters(self.query_one(QueryBar).query, self.query_one(QueryBar).scope)
        self.query_one(EventTable).set_events(self.filtered_events)
        counts = Counter(item.provider for item in self.filtered_events)
        self.query_one(ProviderPanel).update_statuses(self.provider_statuses, counts)
        self.update_status_line()
        if not self.filtered_events:
            self.update_detail_panels(None)

    def update_status_line(self) -> None:
        mode = "deep-detail" if self.deep_detail else "overview"
        bar = self.query_one(QueryBar)
        bar.update_status(
            result_count=len(self.filtered_events),
            total_count=len(self.events),
            scope=bar.scope,
            mode=mode,
            last_export=self.last_export,
        )

    def update_detail_panels(self, event: NormalizedEvent | None) -> None:
        self.query_one("#detail-right", DetailPanel).show_event(event)
        self.query_one("#detail-bottom", DetailPanel).show_event(event)

    def apply_filters(self, query: str, scope: str) -> list[NormalizedEvent]:
        cutoff = None
        delta = TIME_SCOPES.get(scope)
        if delta is not None:
            cutoff = datetime.now(tz=UTC) - delta
        tokens = [token for token in query.split() if token]
        filtered: list[NormalizedEvent] = []
        for event in self.events:
            if cutoff and event.timestamp < cutoff:
                continue
            if self.matches_tokens(event, tokens):
                filtered.append(event)
        filtered.sort(key=lambda item: item.timestamp, reverse=True)
        return filtered

    def matches_tokens(self, event: NormalizedEvent, tokens: Iterable[str]) -> bool:
        searchable = event.searchable_text()
        for token in tokens:
            if ":" in token:
                field, expected = token.split(":", 1)
                value = getattr(event, field, None)
                if value is None or expected.lower() not in str(value).lower():
                    return False
                continue
            if token.lower() not in searchable:
                return False
        return True

    def export_filtered(self, filetype: str, destination: Path | None = None) -> Path:
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        suffix = "json" if filetype == "json" else "csv"
        path = destination or Path.cwd() / f"terminalvelocity-export-{timestamp}.{suffix}"
        rows = [event.to_record() for event in self.filtered_events]
        if filetype == "json":
            path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
        else:
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "timestamp",
                        "provider",
                        "service",
                        "actor",
                        "action",
                        "target",
                        "result",
                        "severity",
                        "correlation_id",
                        "request_id",
                        "raw",
                    ],
                    extrasaction="ignore",
                )
                writer.writeheader()
                for row in rows:
                    row = dict(row)
                    row["raw"] = json.dumps(row["raw"], sort_keys=True)
                    writer.writerow(row)
        self.last_export = path.name
        self.update_status_line()
        return path


def generate_mock_dataset(*, seed: int, count: int) -> tuple[list[NormalizedEvent], list[ProviderStatus]]:
    rng = random.Random(seed)
    now = datetime.now(tz=UTC)
    events: list[NormalizedEvent] = []
    provider_counts: Counter[str] = Counter()
    for index in range(count):
        provider, service = PROVIDER_CATALOG[index % len(PROVIDER_CATALOG)]
        action = rng.choice(ACTIONS[provider])
        result = rng.choice(RESULTS)
        severity = "critical" if result == "failure" and rng.random() > 0.55 else rng.choice(SEVERITIES)
        actor = rng.choice(ACTORS)
        target = rng.choice(TARGETS[provider])
        timestamp = now - timedelta(minutes=rng.randint(0, 24 * 60), seconds=rng.randint(0, 59))
        correlation_id = f"corr-{seed}-{index:03d}"
        request_id = f"req-{seed}-{index:03d}"
        raw = {
            "ip": f"10.0.{rng.randint(1, 9)}.{rng.randint(10, 240)}",
            "tenant_id": "contoso-tenant",
            "actor": actor,
            "target": target,
            "provider": provider,
            "service": service,
            "action": action,
            "result": result,
            "severity": severity,
            "device_id": f"device-{rng.randint(100, 999)}",
            "risk_flags": [flag for flag in ("impossible-travel", "burst-failures", "admin-op") if rng.random() > 0.72],
        }
        events.append(
            NormalizedEvent(
                timestamp=timestamp,
                provider=provider,
                service=service,
                actor=actor,
                action=action,
                target=target,
                result=result,
                severity=severity,
                correlation_id=correlation_id,
                request_id=request_id,
                raw=raw,
            )
        )
        provider_counts[provider] += 1
    events.sort(key=lambda item: item.timestamp, reverse=True)
    statuses = [
        ProviderStatus(
            provider=provider,
            service=service,
            state="error" if provider == "defender" else "warn" if provider == "purview" else "ok",
            lag_seconds=rng.randint(10, 180) if provider != "purview" else rng.randint(120, 420),
            error_count=rng.randint(0, 2) if provider == "defender" else 0,
            enabled=True,
            total_events=provider_counts[provider],
        )
        for provider, service in PROVIDER_CATALOG
    ]
    return events, statuses


async def run_headless_smoke(*, seed: int = 365, count: int = 24) -> None:
    """Launch the app headlessly and exercise the key Phase 1 paths."""

    json_path = Path.cwd() / "smoke-export.json"
    csv_path = Path.cwd() / "smoke-export.csv"
    app = TerminalVelocityApp(seed=seed, count=count)
    try:
        async with app.run_test(headless=True, size=(160, 48)) as pilot:
            await pilot.pause()
            assert len(app.filtered_events) == count
            app.action_cursor_down()
            app.action_toggle_deep_detail()
            await pilot.pause()
            assert app.deep_detail is True
            app.action_show_help()
            await pilot.pause()
            assert len(app.screen_stack) > 1
            await pilot.press("escape")
            await pilot.pause()
            assert len(app.screen_stack) == 1
            app.export_filtered("json", json_path)
            app.export_filtered("csv", csv_path)
            await pilot.pause()
            assert json_path.exists() and csv_path.exists()
            app.query_one(QueryBar).query_one("#query-input").value = "result:failure"
            app.refresh_view()
            await pilot.pause()
            assert app.filtered_events
    finally:
        if json_path.exists():
            json_path.unlink()
        if csv_path.exists():
            csv_path.unlink()

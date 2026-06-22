"""TerminalVelocity core TUI application."""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import random
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Static

from terminalvelocity.config import AppConfig
from terminalvelocity.enrichment.cross_provider import CrossProviderEnricher
from terminalvelocity.investigation.export import EventExporter
from terminalvelocity.investigation.highlight_rules import HighlightRuleEngine
from terminalvelocity.schema import NormalizedEvent, ProviderStatus
from terminalvelocity.search.anomaly import AnomalyDetector
from terminalvelocity.search.engine import SearchEngine
from terminalvelocity.search.history import QueryHistoryStore
from terminalvelocity.search.saved_queries import SavedQueryStore
from terminalvelocity.tui.keybindings import HELP_TEXT, KEY_BINDINGS
from terminalvelocity.tui.themes import APP_CSS
from terminalvelocity.tui.widgets.charts_strip import ChartsStrip
from terminalvelocity.tui.widgets.detail_panel import DetailPanel
from terminalvelocity.tui.widgets.event_table import EventTable
from terminalvelocity.tui.widgets.provider_panel import ProviderPanel
from terminalvelocity.tui.widgets.query_bar import QueryBar

LOGGER = logging.getLogger(__name__)

# All 14 M365 providers matching the design
PROVIDER_CATALOG = [
    ("entra", "signin"),
    ("identity_protection", "risk"),
    ("pim", "role"),
    ("defender_xdr", "incident"),
    ("advanced_hunting", "DeviceEvents"),
    ("defender_cloud_apps", "activity"),
    ("intune", "device"),
    ("unified_audit_log", "DLP"),
    ("exchange_online", "trace"),
    ("sharepoint_onedrive", "sharing"),
    ("teams", "messaging"),
    ("secure_score", "posture"),
    ("service_health", "incident"),
    ("attack_simulation", "sim"),
]

ACTORS = [
    "alex@contoso.com",
    "jamie@contoso.com",
    "svc-sync@contoso.com",
    "soc-automation@contoso.com",
    "lee@contoso.com",
]

ACTIONS = {
    "entra": ["sign-in", "token-refresh", "mfa-challenge", "app-consent", "Add app role assignment"],
    "identity_protection": ["impossibleTravel risk detection", "unfamiliarFeatures risk detection", "riskySignIn"],
    "pim": ["Activate Global Administrator", "Deactivate Security Reader", "role-assignment-added"],
    "defender_xdr": [
        "Suspicious inbox rule after risky sign-in",
        "Defender alert · LSASS access",
        "incident-created",
        "alert-opened",
    ],
    "advanced_hunting": ["PowerShellExecution", "ProcessCreated", "NetworkConnectionEvents", "FileCreated"],
    "defender_cloud_apps": ["Mass download detected", "admin-quarantine", "policy-match"],
    "intune": ["policy-sync", "compliance-check failed", "device-enroll", "script-run"],
    "unified_audit_log": ["DLPRuleMatch · Credit Card", "ExportReport", "mailbox-search", "label-apply"],
    "exchange_online": ["New-InboxRule · forward to external", "MessageTrace · quarantined", "MessageTrace"],
    "sharepoint_onedrive": ["AnonymousLinkCreated", "FileDownloaded", "FileViewed", "SitePermissionModified"],
    "teams": ["ExternalAccessChanged", "MessageSent", "admin-policy-change"],
    "secure_score": ["SecureScoreSnapshot · -6 vs avg", "ControlProfileSync"],
    "service_health": ["EX_Advisory · mail delays", "SPO_Incident · degraded performance"],
    "attack_simulation": ["CredentialsEntered", "SimulationLaunched", "ReportedPhish"],
}

TARGETS = {
    "entra": ["Office 365", "Microsoft Graph", "sp/Graph", "tenant"],
    "identity_protection": ["—", "tenant"],
    "pim": ["role/Global Admin", "role/Sec Reader", "role/Exchange Admin"],
    "defender_xdr": ["mailbox/alex", "host-db-01", "device-042"],
    "advanced_hunting": ["host-db-01", "win11-fleet", "device-042"],
    "defender_cloud_apps": ["OneDrive/Finance", "SharePoint/Legal", "OneDrive/HR"],
    "intune": ["win11-fleet", "device-129", "policy-baseline"],
    "unified_audit_log": ["mail/outbound", "workspace/exec", "case-12"],
    "exchange_online": ["mailbox/alex", "mail/inbound", "mail/outbound"],
    "sharepoint_onedrive": ["site/legal", "site/finance", "site/marketing"],
    "teams": ["org/federation", "team/engineering", "team/finance"],
    "secure_score": ["tenant"],
    "service_health": ["Exchange Online", "SharePoint Online"],
    "attack_simulation": ["sim/Q2-Phish", "sim/Credential-Harvest"],
}

# Provider states matching the design prototype
_PROVIDER_STATES = {
    "entra": "ok",
    "identity_protection": "warn",
    "pim": "ok",
    "defender_xdr": "error",
    "advanced_hunting": "ok",
    "defender_cloud_apps": "ok",
    "intune": "ok",
    "unified_audit_log": "warn",
    "exchange_online": "ok",
    "sharepoint_onedrive": "ok",
    "teams": "ok",
    "secure_score": "ok",
    "service_health": "warn",
    "attack_simulation": "ok",
}

# Lag seconds matching the design prototype
_PROVIDER_LAGS = {
    "entra": 2,
    "identity_protection": 31,
    "pim": 5,
    "defender_xdr": 0,
    "advanced_hunting": 12,
    "defender_cloud_apps": 8,
    "intune": 44,
    "unified_audit_log": 118,
    "exchange_online": 9,
    "sharepoint_onedrive": 14,
    "teams": 6,
    "secure_score": 3600,
    "service_health": 40,
    "attack_simulation": 22,
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

_STORAGE_DIR = Path(".terminalvelocity")


class HelpScreen(ModalScreen[None]):
    """Simple help modal opened with ?."""

    BINDINGS = [("escape", "close", "Close"), ("enter", "close", "Close"), ("question_mark", "close", "Close")]  # noqa: RUF012

    def compose(self) -> ComposeResult:
        yield Static(HELP_TEXT, id="help-dialog")

    def action_close(self) -> None:
        self.dismiss()


class TerminalVelocityApp(App[None]):
    """Keyboard-first Textual log triage UI."""

    CSS = APP_CSS
    BINDINGS = KEY_BINDINGS

    def __init__(
        self,
        *,
        seed: int = 365,
        count: int = 72,
        config: AppConfig | None = None,
        live: bool = False,
        input_events: list[NormalizedEvent] | None = None,
        compare_hours: int | None = None,
        database_path: str | Path | None = None,
        log_file: str | Path | None = None,
    ) -> None:
        super().__init__()
        self.seed = seed
        self.count = count
        self.config = config or AppConfig()
        self.live = live
        self.compare_hours = compare_hours
        self.deep_detail = False
        self.detail_visible = True
        self.last_export: str | None = None
        self.provider_statuses: list[ProviderStatus] = []
        self.events: list[NormalizedEvent] = []
        self.filtered_events: list[NormalizedEvent] = []
        self._anomaly_count: int = 0
        self._alert_count: int = 0
        self._log_file: Path | None = Path(log_file) if log_file is not None else None

        _STORAGE_DIR.mkdir(exist_ok=True)

        db_path = database_path if database_path is not None else _STORAGE_DIR / "index.db"
        self.engine = SearchEngine(db_path)
        self.saved_queries = SavedQueryStore(_STORAGE_DIR / "saved_queries.db")
        self.query_history = QueryHistoryStore(_STORAGE_DIR / "history.db")
        self._exporter = EventExporter()
        self._enricher = CrossProviderEnricher()
        self._anomaly_detector = AnomalyDetector()

        self._highlight_engine: HighlightRuleEngine | None = None
        rules_path = self.config.highlight_rules_path or "config/highlight_rules.yaml"
        if Path(rules_path).exists():
            try:
                self._highlight_engine = HighlightRuleEngine.from_path(rules_path)
            except Exception as exc:
                LOGGER.warning("Failed to load highlight rules from %s: %s", rules_path, exc)

        self._input_events = input_events or []

    @property
    def detail_mode(self) -> str:
        return "deep" if self.deep_detail else "overview"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield QueryBar(id="query-bar")
        with Horizontal(id="workspace"):
            yield ProviderPanel(id="provider-panel")
            with Vertical(id="center-stack"):
                yield ChartsStrip(id="charts-strip")
                with Horizontal(id="overview-pane"):
                    yield EventTable(id="event-table")
                    yield DetailPanel(id="detail-right")
                yield DetailPanel(id="detail-bottom")
        yield Footer()

    async def on_mount(self) -> None:
        self.title = "TerminalVelocity"

        table = self.query_one(EventTable)
        if self._highlight_engine:
            table.set_highlight_engine(self._highlight_engine)
        table.set_show_correlation(True)

        if self._input_events:
            self.sub_title = "File ingestion mode"
            self.events = self._input_events
        elif self.live:
            self.sub_title = "Live \u2013 connecting to M365 providers\u2026"
            self.events = []
            self.set_interval(self.config.poll_interval_seconds, self._poll_providers)
            self._initial_poll_task = asyncio.create_task(self._poll_providers())
        else:
            self.sub_title = "Demo mode"
            self.events, self.provider_statuses = generate_mock_dataset(seed=self.seed, count=self.count)

        if self.events:
            enriched = self._enricher.enrich(self.events)
            self.engine.index_events(enriched)
            self.events = enriched

        if self.compare_hours is not None:
            self.query_one(QueryBar).set_query(f"since:{self.compare_hours}h")

        self.refresh_view()
        self.query_one(EventTable).focus_table()

    async def _poll_providers(self) -> None:
        from terminalvelocity.providers.registry import registry

        tenant_id = os.environ.get("TERMINALVELOCITY_TENANT_ID", "")
        client_id = os.environ.get("TERMINALVELOCITY_CLIENT_ID", "")
        client_secret = os.environ.get("TERMINALVELOCITY_CLIENT_SECRET", "")
        if not (tenant_id and client_id and client_secret):
            msg = "Live mode: set TERMINALVELOCITY_TENANT_ID/CLIENT_ID/CLIENT_SECRET"
            LOGGER.warning(msg)
            self.notify(msg, severity="warning")
            return

        enabled_names = (
            [p.name for p in self.config.providers if p.enabled] if self.config.providers else list(registry.names())
        )
        new_count = 0
        for name in enabled_names:
            try:
                provider = registry.create(
                    name,
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret,
                )
                raw_events: list[NormalizedEvent] = await provider.fetch()
                if raw_events:
                    enriched = self._enricher.enrich(raw_events)
                    self.engine.index_events(enriched)
                    self.events.extend(enriched)
                    new_count += len(enriched)
            except Exception as exc:
                LOGGER.error("Provider %s error: %s", name, exc, exc_info=True)
                self.notify(f"Provider {name} error: {exc}", severity="warning")

        if new_count:
            self.notify(f"Ingested {new_count} new event(s)")
            self.refresh_view()

    def on_unmount(self) -> None:
        """Close all database connections when the application exits."""
        self.engine.close()
        self.saved_queries.close()
        self.query_history.close()

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

    def action_toggle_detail_visible(self) -> None:
        self.detail_visible = not self.detail_visible
        for panel in self.query(DetailPanel):
            panel.display = self.detail_visible
        self.update_status_line()

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_export_json(self) -> None:
        path = self.export_filtered("json")
        self.notify(f"Exported {len(self.filtered_events)} rows to {path.name}")

    def action_export_csv(self) -> None:
        path = self.export_filtered("csv")
        self.notify(f"Exported {len(self.filtered_events)} rows to {path.name}")

    def action_export_markdown(self) -> None:
        path = self.export_filtered("markdown")
        self.notify(f"Markdown report: {path.name}")

    def action_show_pivot(self) -> None:
        from terminalvelocity.tui.screens.pivot import PivotScreen

        seed = self.query_one(EventTable).current_event()
        if seed is None:
            self.notify("No event selected for pivot", severity="warning")
            return

        def on_pivot_result(result: NormalizedEvent | None) -> None:
            if result is not None:
                self.update_detail_panels(result)

        self.push_screen(PivotScreen(seed, self.filtered_events), on_pivot_result)

    def action_show_timeline(self) -> None:
        from terminalvelocity.tui.screens.timeline import TimelineScreen

        seed = self.query_one(EventTable).current_event()
        if seed is None:
            self.notify("No event selected for timeline", severity="warning")
            return
        self.push_screen(TimelineScreen(seed, self.filtered_events))

    def action_show_anomalies(self) -> None:
        from terminalvelocity.tui.screens.anomaly import AnomalyScreen

        self.push_screen(AnomalyScreen(self.filtered_events))

    def action_show_saved_queries(self) -> None:
        from terminalvelocity.tui.screens.saved_queries import SavedQueriesScreen

        current_query = self.query_one(QueryBar).query

        def on_sq_result(result: str | None) -> None:
            if result is not None:
                self.query_one(QueryBar).set_query(result)
                self.refresh_view()

        self.push_screen(
            SavedQueriesScreen(self.saved_queries, current_query=current_query),
            on_sq_result,
        )

    def action_tag_event(self) -> None:
        from terminalvelocity.tui.screens.tag import TagScreen

        event = self.query_one(EventTable).current_event()
        if event is None:
            self.notify("No event selected for tagging", severity="warning")
            return
        self.push_screen(TagScreen(event, self.engine))

    def action_show_history(self) -> None:
        from terminalvelocity.tui.screens.history import HistoryScreen

        def on_history_result(result: str | None) -> None:
            if result is not None:
                self.query_one(QueryBar).set_query(result)
                self.refresh_view()

        self.push_screen(HistoryScreen(self.query_history), on_history_result)

    def action_show_logs(self) -> None:
        from terminalvelocity.tui.screens.log_viewer import LogViewerScreen

        self.push_screen(LogViewerScreen(self._log_file))

    def on_query_bar_filter_changed(self, event: QueryBar.FilterChanged) -> None:
        del event
        self.refresh_view()

    def on_event_table_event_highlighted(self, event: EventTable.EventHighlighted) -> None:
        self.update_detail_panels(event.event)

    def refresh_view(self) -> None:
        query_bar = self.query_one(QueryBar)
        query_text = query_bar.query_text
        scope = query_bar.scope

        self.filtered_events = self._search(query_text, scope)

        if query_text.strip():
            self.query_history.record(query_text, scope, len(self.filtered_events))

        markers = self._anomaly_detector.detect(self.filtered_events)
        self._anomaly_count = len(markers)

        self._alert_count = 0
        if self._highlight_engine:
            self._alert_count = sum(1 for e in self.filtered_events if self._highlight_engine.should_alert(e))

        counts = Counter(item.provider for item in self.filtered_events)
        self.query_one(ProviderPanel).update_statuses(
            self.provider_statuses,
            counts,
            anomaly_count=self._anomaly_count,
            alert_count=self._alert_count,
        )
        self.query_one(EventTable).set_events(self.filtered_events)

        # Update charts strip
        self.query_one(ChartsStrip).update_charts(
            events=self.filtered_events,
            total_count=len(self.events),
            alert_count=self._alert_count,
            anomaly_count=self._anomaly_count,
        )

        # Update detail context so Chain tab can find related events
        for panel in self.query(DetailPanel):
            panel.set_event_context(self.filtered_events)

        self.update_status_line()
        if not self.filtered_events:
            self.update_detail_panels(None)

    def _search(self, query: str, scope: str) -> list[NormalizedEvent]:
        parts = [query.strip()]
        if scope != "all":
            parts.append(f"since:{scope}")
        combined = " ".join(p for p in parts if p)
        try:
            return self.engine.search(combined, limit=10_000)
        except Exception:
            return apply_filters_fallback(self.events, query, scope)

    def update_status_line(self) -> None:
        mode = self.detail_mode
        bar = self.query_one(QueryBar)
        bar.update_status(
            result_count=len(self.filtered_events),
            total_count=len(self.events),
            scope=bar.scope,
            mode=mode,
            last_export=self.last_export,
            anomaly_count=self._anomaly_count,
            alert_count=self._alert_count,
        )

    def update_detail_panels(self, event: NormalizedEvent | None) -> None:
        for panel in self.query(DetailPanel):
            panel.show_event(event)

    def export_filtered(self, filetype: str, destination: Path | None = None) -> Path:
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        ext_map = {"json": "json", "csv": "csv", "markdown": "md"}
        suffix = ext_map.get(filetype, filetype)
        path = destination or Path.cwd() / f"terminalvelocity-export-{timestamp}.{suffix}"
        if filetype == "markdown":
            content = self._exporter.export_markdown_report(
                self.filtered_events,
                title="TerminalVelocity Incident Report",
            )
            path.write_text(content, encoding="utf-8")
        elif filetype == "json":
            rows = [event.to_record() for event in self.filtered_events]
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
                for row in [event.to_record() for event in self.filtered_events]:
                    row = dict(row)
                    row["raw"] = json.dumps(row["raw"], sort_keys=True)
                    writer.writerow(row)
        self.last_export = path.name
        self.update_status_line()
        return path

    def apply_filters(self, query: str, scope: str) -> list[NormalizedEvent]:
        """Legacy method kept for test compatibility — delegates to _search."""
        return self._search(query, scope)


# ---------------------------------------------------------------------------
# Standalone helpers
# ---------------------------------------------------------------------------


def apply_filters_fallback(
    events: list[NormalizedEvent],
    query: str,
    scope: str,
) -> list[NormalizedEvent]:
    cutoff = None
    delta = TIME_SCOPES.get(scope)
    if delta is not None:
        cutoff = datetime.now(tz=UTC) - delta
    tokens = [t for t in query.split() if t]
    filtered: list[NormalizedEvent] = []
    for event in events:
        if cutoff and event.timestamp < cutoff:
            continue
        if _matches_tokens(event, tokens):
            filtered.append(event)
    filtered.sort(key=lambda item: item.timestamp, reverse=True)
    return filtered


def _matches_tokens(event: NormalizedEvent, tokens: Iterable[str]) -> bool:
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


def filter_events(events: list[NormalizedEvent], query: str, scope: str) -> list[NormalizedEvent]:
    """Standalone filter used in tests and headless contexts."""
    return apply_filters_fallback(events, query, scope)


def _design_demo_events(now: datetime) -> list[NormalizedEvent]:
    """Return the 24 scenario events from the TerminalVelocity design prototype."""
    # All offsets relative to design reference time 14:23:41 UTC
    ref_sec = 14 * 3600 + 23 * 60 + 41

    def _ts(h: int, m: int, s: int) -> datetime:
        event_sec = h * 3600 + m * 60 + s
        return now - timedelta(seconds=max(0, ref_sec - event_sec))

    def _ev(
        h: int,
        m: int,
        s: int,
        provider: str,
        service: str,
        actor: str,
        action: str,
        target: str,
        result: str,
        severity: str,
        corr: str | None = None,
        ip: str = "10.0.0.1",
        risk_flags: list[str] | None = None,
    ) -> NormalizedEvent:
        return NormalizedEvent(
            timestamp=_ts(h, m, s),
            provider=provider,
            service=service,
            actor=actor,
            action=action,
            target=target,
            result=result,
            severity=severity,
            correlation_id=corr,
            raw={
                "ip": ip,
                "risk_flags": risk_flags or [],
                "tenant_id": "contoso-tenant",
            },
        )

    return [
        _ev(
            14,
            23,
            39,
            "defender_xdr",
            "incident",
            "alex@contoso.com",
            "Suspicious inbox rule after risky sign-in",
            "mailbox/alex",
            "failure",
            "critical",
            "INC-4471",
            "185.220.101.42",
            ["admin-op", "impossible-travel"],
        ),
        _ev(
            14,
            22,
            55,
            "exchange_online",
            "admin",
            "alex@contoso.com",
            "New-InboxRule · forward to external",
            "mailbox/alex",
            "failure",
            "high",
            "INC-4471",
            "185.220.101.42",
            ["rare-action"],
        ),
        _ev(
            14,
            21,
            10,
            "entra",
            "signin",
            "alex@contoso.com",
            "Sign-in",
            "Office 365",
            "success",
            "high",
            "INC-4471",
            "185.220.101.42",
            ["impossible-travel"],
        ),
        _ev(
            14,
            20,
            30,
            "entra",
            "signin",
            "alex@contoso.com",
            "Sign-in",
            "Office 365",
            "failure",
            "medium",
            "INC-4471",
            "185.220.101.42",
            ["burst-failures"],
        ),
        _ev(
            14,
            19,
            5,
            "identity_protection",
            "risk",
            "alex@contoso.com",
            "impossibleTravel risk detection",
            "—",
            "atrisk",
            "critical",
            "INC-4471",
            "185.220.101.42",
            ["impossible-travel"],
        ),
        _ev(
            14,
            18,
            40,
            "pim",
            "role",
            "jamie@contoso.com",
            "Activate Global Administrator",
            "role/Global Admin",
            "success",
            "critical",
            "PIM-228",
            "10.0.4.18",
            ["admin-op"],
        ),
        _ev(
            14,
            17,
            12,
            "attack_simulation",
            "sim",
            "lee@contoso.com",
            "CredentialsEntered",
            "sim/Q2-Phish",
            "failure",
            "critical",
            None,
            "10.0.2.55",
        ),
        _ev(
            14,
            15,
            48,
            "defender_cloud_apps",
            "activity",
            "svc-sync@contoso.com",
            "Mass download detected",
            "OneDrive/Finance",
            "failure",
            "high",
            None,
            "52.114.7.9",
        ),
        _ev(
            14,
            14,
            3,
            "advanced_hunting",
            "DeviceEvents",
            "svc-sync@contoso.com",
            "PowerShellExecution",
            "host-db-01",
            "success",
            "medium",
            None,
            "10.0.6.21",
        ),
        _ev(
            14,
            12,
            31,
            "sharepoint_onedrive",
            "sharing",
            "jamie@contoso.com",
            "AnonymousLinkCreated",
            "site/legal",
            "success",
            "medium",
            None,
            "10.0.3.7",
        ),
        _ev(
            14,
            10,
            9,
            "unified_audit_log",
            "DLP",
            "lee@contoso.com",
            "DLPRuleMatch · Credit Card",
            "mail/outbound",
            "failure",
            "high",
            None,
            "10.0.2.55",
        ),
        _ev(
            14,
            8,
            44,
            "intune",
            "device",
            "—",
            "compliance-check failed",
            "win11-fleet",
            "failure",
            "medium",
            None,
            "10.0.9.1",
        ),
        _ev(
            14,
            6,
            20,
            "teams",
            "admin",
            "soc-automation@contoso.com",
            "ExternalAccessChanged",
            "org/federation",
            "success",
            "medium",
            None,
            "10.0.1.5",
        ),
        _ev(
            14,
            4,
            55,
            "entra",
            "audit",
            "jamie@contoso.com",
            "Add app role assignment",
            "sp/Graph",
            "success",
            "low",
            None,
            "10.0.4.18",
        ),
        _ev(
            14,
            2,
            10,
            "secure_score",
            "posture",
            "—",
            "SecureScoreSnapshot · -6 vs avg",
            "tenant",
            "failure",
            "high",
            None,
            "—",
        ),
        _ev(
            14,
            0,
            31,
            "service_health",
            "incident",
            "—",
            "EX_Advisory · mail delays",
            "Exchange Online",
            "failure",
            "medium",
            None,
            "—",
        ),
        _ev(
            13,
            58,
            12,
            "entra",
            "signin",
            "svc-sync@contoso.com",
            "Sign-in",
            "Microsoft Graph",
            "success",
            "low",
            None,
            "10.0.6.21",
        ),
        _ev(13, 55, 40, "intune", "device", "—", "policy-sync", "win11-fleet", "success", "low", None, "10.0.9.1"),
        _ev(
            13,
            53,
            2,
            "exchange_online",
            "trace",
            "lee@contoso.com",
            "MessageTrace · quarantined",
            "mail/inbound",
            "failure",
            "medium",
            None,
            "10.0.2.55",
        ),
        _ev(
            13,
            50,
            19,
            "defender_xdr",
            "alert",
            "host-db-01",
            "Defender alert · LSASS access",
            "host-db-01",
            "failure",
            "high",
            None,
            "10.0.6.21",
        ),
        _ev(
            13,
            47,
            55,
            "pim",
            "role",
            "soc-automation@contoso.com",
            "Deactivate Security Reader",
            "role/Sec Reader",
            "success",
            "low",
            None,
            "10.0.1.5",
        ),
        _ev(
            13,
            45,
            11,
            "sharepoint_onedrive",
            "file",
            "alex@contoso.com",
            "FileDownloaded",
            "site/finance",
            "success",
            "low",
            None,
            "10.0.3.9",
        ),
        _ev(
            13,
            42,
            38,
            "unified_audit_log",
            "PowerBI",
            "jamie@contoso.com",
            "ExportReport",
            "workspace/exec",
            "success",
            "low",
            None,
            "10.0.4.18",
        ),
        _ev(
            13,
            40,
            2,
            "entra",
            "signin",
            "lee@contoso.com",
            "Sign-in",
            "Office 365",
            "success",
            "low",
            None,
            "10.0.2.55",
        ),
    ]


def generate_mock_dataset(*, seed: int, count: int) -> tuple[list[NormalizedEvent], list[ProviderStatus]]:
    now = datetime.now(tz=UTC)
    design_events = _design_demo_events(now)

    if count <= len(design_events):
        events = design_events[:count]
    else:
        rng = random.Random(seed)
        extra: list[NormalizedEvent] = []
        needed = count - len(design_events)
        for index in range(needed):
            provider, service = PROVIDER_CATALOG[index % len(PROVIDER_CATALOG)]
            action = rng.choice(ACTIONS[provider])
            result = rng.choice(RESULTS)
            severity = "critical" if result == "failure" and rng.random() > 0.55 else rng.choice(SEVERITIES)
            actor = rng.choice(ACTORS)
            target = rng.choice(TARGETS[provider])
            timestamp = now - timedelta(minutes=rng.randint(0, 23 * 60), seconds=rng.randint(0, 59))
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
                "risk_flags": [
                    flag for flag in ("impossible-travel", "burst-failures", "admin-op") if rng.random() > 0.72
                ],
            }
            extra.append(
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
        events = design_events + extra

    events.sort(key=lambda item: item.timestamp, reverse=True)

    # Build provider counts from the events
    provider_counts: Counter[str] = Counter(e.provider for e in events)

    statuses = [
        ProviderStatus(
            provider=provider,
            service=service,
            state=_PROVIDER_STATES.get(provider, "ok"),
            lag_seconds=_PROVIDER_LAGS.get(provider, 30),
            error_count=1 if _PROVIDER_STATES.get(provider) == "error" else 0,
            enabled=True,
            total_events=provider_counts[provider],
        )
        for provider, service in PROVIDER_CATALOG
    ]
    return events, statuses


def generate_mock_events(*, seed: int, count: int) -> list[NormalizedEvent]:
    """Return only the events portion of :func:`generate_mock_dataset`."""
    events, _ = generate_mock_dataset(seed=seed, count=count)
    return events


async def run_headless_smoke(*, seed: int = 365, count: int = 24) -> None:
    """Launch the app headlessly and exercise the key paths."""

    json_path = Path.cwd() / "smoke-export.json"
    csv_path = Path.cwd() / "smoke-export.csv"
    md_path = Path.cwd() / "smoke-export.md"
    app = TerminalVelocityApp(seed=seed, count=count, database_path=":memory:")
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
            app.export_filtered("markdown", md_path)
            await pilot.pause()
            assert json_path.exists() and csv_path.exists() and md_path.exists()
            app.query_one(QueryBar).query_one("#query-input").value = "result:failure"
            app.refresh_view()
            await pilot.pause()
            assert app.filtered_events
    finally:
        for p in (json_path, csv_path, md_path):
            if p.exists():
                p.unlink()

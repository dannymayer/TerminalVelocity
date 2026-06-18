"""Theme helpers and CSS for the TerminalVelocity TUI."""

from __future__ import annotations

from rich.text import Text

APP_CSS = """
Screen {
    layout: vertical;
    background: #0f172a;
    color: #e2e8f0;
}

Header {
    dock: top;
}

Footer {
    dock: bottom;
}

#query-bar {
    height: 7;
    margin: 1 1 0 1;
    padding: 0 1;
    border: round #334155;
    background: #111827;
}

#query-title {
    height: 1;
    color: #93c5fd;
    text-style: bold;
}

#query-controls {
    height: 3;
    align: left middle;
}

#query-input {
    width: 1fr;
    margin-right: 1;
}

#time-scope {
    width: 18;
}

#query-status {
    height: 2;
    color: #94a3b8;
}

#workspace {
    height: 1fr;
    margin: 1;
}

#provider-panel {
    width: 38;
    min-width: 32;
    padding: 0 1;
    border: round #334155;
    background: #111827;
}

#center-stack {
    width: 1fr;
    margin-left: 1;
}

#overview-pane {
    height: 1fr;
}

#event-table {
    width: 1fr;
    border: round #334155;
    background: #111827;
}

#detail-right,
#detail-bottom {
    border: round #334155;
    background: #111827;
}

#detail-right {
    width: 46;
    min-width: 40;
    margin-left: 1;
}

#detail-bottom {
    height: 18;
    margin-top: 1;
    display: none;
}

.deep-mode #detail-right {
    display: none;
}

.deep-mode #detail-bottom {
    display: block;
    height: 28;
}

#help-dialog {
    width: 72;
    height: 12;
    padding: 1 2;
    border: round #60a5fa;
    background: #020617;
}

.panel-title {
    color: #93c5fd;
    text-style: bold;
}

.detail-json {
    padding: 0 1;
}

#detail-summary {
    padding: 0 1;
    color: #cbd5e1;
}

#provider-body {
    height: 1fr;
}
"""

PROVIDER_COLORS: dict[str, str] = {
    "entra": "white on #2563eb",
    "identity_protection": "white on #3b82f6",
    "pim": "white on #6366f1",
    "defender_xdr": "black on #f59e0b",
    "advanced_hunting": "white on #f97316",
    "defender_cloud_apps": "white on #fb923c",
    "intune": "black on #22c55e",
    "unified_audit_log": "white on #7c3aed",
    "exchange_online": "white on #8b5cf6",
    "sharepoint_onedrive": "white on #a855f7",
    "teams": "white on #6d28d9",
    "secure_score": "black on #06b6d4",
    "service_health": "black on #14b8a6",
    "attack_simulation": "white on #ec4899",
    # Legacy names kept for backward compatibility
    "defender": "black on #f59e0b",
    "purview": "white on #7c3aed",
}

PROVIDER_SHORT: dict[str, str] = {
    "entra": "ENTRA",
    "identity_protection": "IDP",
    "pim": "PIM",
    "defender_xdr": "DEFENDER",
    "advanced_hunting": "HUNT",
    "defender_cloud_apps": "MCAS",
    "intune": "INTUNE",
    "unified_audit_log": "PURVIEW",
    "exchange_online": "EXO",
    "sharepoint_onedrive": "SPO",
    "teams": "TEAMS",
    "secure_score": "SCORE",
    "service_health": "HEALTH",
    "attack_simulation": "ATKSIM",
    # Legacy
    "defender": "DEFENDER",
    "purview": "PURVIEW",
}

PROVIDER_NAME: dict[str, str] = {
    "entra": "Entra ID",
    "identity_protection": "Identity Protection",
    "pim": "Privileged Identity Mgmt",
    "defender_xdr": "Defender XDR",
    "advanced_hunting": "Advanced Hunting",
    "defender_cloud_apps": "Defender Cloud Apps",
    "intune": "Intune",
    "unified_audit_log": "Purview · UAL",
    "exchange_online": "Exchange Online",
    "sharepoint_onedrive": "SharePoint / OneDrive",
    "teams": "Microsoft Teams",
    "secure_score": "Secure Score",
    "service_health": "Service Health",
    "attack_simulation": "Attack Simulation",
    # Legacy
    "defender": "Defender XDR",
    "purview": "Purview · UAL",
}

PROVIDER_GROUPS: list[tuple[str, list[str]]] = [
    ("IDENTITY & ACCESS", ["entra", "identity_protection", "pim"]),
    ("THREAT & HUNTING", ["defender_xdr", "advanced_hunting", "defender_cloud_apps"]),
    ("ENDPOINT", ["intune"]),
    ("COLLABORATION", ["unified_audit_log", "exchange_online", "sharepoint_onedrive", "teams"]),
    ("POSTURE & HEALTH", ["secure_score", "service_health", "attack_simulation"]),
]

RESULT_COLORS: dict[str, str] = {
    "success": "black on #22c55e",
    "failure": "white on #dc2626",
    "atrisk": "white on #f97316",
}

SEVERITY_COLORS: dict[str, str] = {
    "low": "black on #86efac",
    "medium": "black on #facc15",
    "high": "white on #f97316",
    "critical": "white on #dc2626",
}

STATE_COLORS: dict[str, str] = {
    "ok": "black on #22c55e",
    "warn": "black on #facc15",
    "error": "white on #dc2626",
}

STATE_DOT_COLORS: dict[str, str] = {
    "ok": "#22c55e",
    "warn": "#facc15",
    "error": "#dc2626",
}


def _badge(text: str, style: str) -> Text:
    badge = Text(f" {text} ")
    badge.stylize(style)
    return badge


def provider_badge(provider: str) -> Text:
    key = provider.lower()
    short = PROVIDER_SHORT.get(key, provider.upper()[:8])
    return _badge(short, PROVIDER_COLORS.get(key, "white on #475569"))


def result_badge(result: str) -> Text:
    key = (result or "").lower()
    return _badge((result or "—").upper(), RESULT_COLORS.get(key, "white on #475569"))


def severity_badge(severity: str) -> Text:
    return _badge((severity or "—").upper(), SEVERITY_COLORS.get((severity or "").lower(), "white on #475569"))


def state_badge(state: str) -> Text:
    return _badge(state.upper(), STATE_COLORS.get(state.lower(), "white on #475569"))

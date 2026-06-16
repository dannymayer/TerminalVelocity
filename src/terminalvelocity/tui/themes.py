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
    width: 34;
    min-width: 28;
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
    width: 44;
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

PROVIDER_COLORS = {
    "entra": "white on #2563eb",
    "defender": "black on #f59e0b",
    "intune": "black on #22c55e",
    "purview": "white on #7c3aed",
}

RESULT_COLORS = {
    "success": "black on #22c55e",
    "failure": "white on #dc2626",
}

SEVERITY_COLORS = {
    "low": "black on #86efac",
    "medium": "black on #facc15",
    "high": "white on #f97316",
    "critical": "white on #dc2626",
}

STATE_COLORS = {
    "ok": "black on #22c55e",
    "warn": "black on #facc15",
    "error": "white on #dc2626",
}


def _badge(text: str, style: str) -> Text:
    badge = Text(f" {text} ")
    badge.stylize(style)
    return badge


def provider_badge(provider: str) -> Text:
    return _badge(provider.upper(), PROVIDER_COLORS.get(provider.lower(), "white on #475569"))


def result_badge(result: str) -> Text:
    return _badge(result.upper(), RESULT_COLORS.get(result.lower(), "white on #475569"))


def severity_badge(severity: str) -> Text:
    return _badge(severity.upper(), SEVERITY_COLORS.get(severity.lower(), "white on #475569"))


def state_badge(state: str) -> Text:
    return _badge(state.upper(), STATE_COLORS.get(state.lower(), "white on #475569"))

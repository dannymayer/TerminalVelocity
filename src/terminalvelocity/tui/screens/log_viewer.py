"""Log viewer screen: browse the application log file (ctrl+l)."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Footer, RichLog, Static


class LogViewerScreen(ModalScreen[None]):
    """Modal that displays the contents of the application log file.

    Shows the most recent log entries so the user can review transient
    errors (e.g., M365 authentication failures) that disappeared before
    they could be read from the TUI notifications.
    """

    BINDINGS = [  # noqa: RUF012
        Binding("escape", "close", "Close"),
        Binding("ctrl+r", "refresh_log", "Refresh"),
        Binding("ctrl+c", "clear_log", "Clear log"),
        Binding("j,down", "scroll_down", "Down", show=False),
        Binding("k,up", "scroll_up", "Up", show=False),
        Binding("g", "scroll_home", "Top", show=False),
        Binding("G,end", "scroll_end", "Bottom", show=False),
    ]

    CSS = """
    LogViewerScreen {
        align: center middle;
    }
    #log-dialog {
        width: 90%;
        height: 85%;
        border: round #64748b;
        background: #020617;
        padding: 1;
    }
    #log-title {
        color: #94a3b8;
        text-style: bold;
        margin-bottom: 1;
    }
    #log-hint {
        color: #475569;
        height: 1;
        margin-top: 1;
    }
    #log-output {
        border: solid #1e293b;
        height: 1fr;
    }
    """

    # Number of lines to load from the end of the log file
    _TAIL_LINES = 500

    def __init__(self, log_file: Path | None) -> None:
        super().__init__()
        self._log_file = log_file

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical

        with Vertical(id="log-dialog"):
            yield Static("Application Log", id="log-title")
            yield RichLog(id="log-output", highlight=True, markup=False, wrap=True)
            yield Static("ctrl+r=refresh  ctrl+c=clear  esc=close", id="log-hint")
        yield Footer()

    def on_mount(self) -> None:
        self._load_log()

    def _log_path_label(self) -> str:
        if self._log_file is None:
            return "(no log file configured)"
        return str(self._log_file)

    def _load_log(self) -> None:
        log_widget = self.query_one("#log-output", RichLog)
        log_widget.clear()
        title_widget = self.query_one("#log-title", Static)

        if self._log_file is None or not self._log_file.exists():
            label = self._log_path_label()
            title_widget.update(f"Application Log — {label}")
            log_widget.write(
                "[dim]No log entries yet.[/dim]"
                if self._log_file
                else "[dim]Log file not configured. Pass --log-file or set log_file in config.[/dim]"
            )
            return

        try:
            lines = self._log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            title_widget.update("Application Log — error reading file")
            log_widget.write(f"[red]Could not read log file:[/red] {exc}")
            return

        tail = lines[-self._TAIL_LINES :]
        title_widget.update(f"Application Log — {self._log_file.name} ({len(lines)} line(s), showing last {len(tail)})")

        for line in tail:
            log_widget.write(_format_log_line(line))

        log_widget.scroll_end(animate=False)

    def action_close(self) -> None:
        self.dismiss(None)

    def action_refresh_log(self) -> None:
        self._load_log()

    def action_clear_log(self) -> None:
        if self._log_file and self._log_file.exists():
            try:
                self._log_file.write_text("", encoding="utf-8")
            except OSError:
                pass
        self._load_log()

    def action_scroll_down(self) -> None:
        self.query_one("#log-output", RichLog).scroll_down()

    def action_scroll_up(self) -> None:
        self.query_one("#log-output", RichLog).scroll_up()

    def action_scroll_home(self) -> None:
        self.query_one("#log-output", RichLog).scroll_home(animate=False)

    def action_scroll_end(self) -> None:
        self.query_one("#log-output", RichLog).scroll_end(animate=False)


def _format_log_line(line: str) -> str:
    """Apply lightweight colour hints to a log line based on its level."""
    upper = line.upper()
    if " [CRITICAL]" in upper or " [ERROR]" in upper:
        return f"[red]{line}[/red]"
    if " [WARNING]" in upper:
        return f"[yellow]{line}[/yellow]"
    if " [INFO]" in upper:
        return f"[cyan]{line}[/cyan]"
    return line

"""Keyboard bindings for the Phase 1 Textual interface."""

from textual.binding import Binding

KEY_BINDINGS = [
    Binding("slash", "focus_query", "Query"),
    Binding("j,down", "cursor_down", "Next", show=False),
    Binding("k,up", "cursor_up", "Prev", show=False),
    Binding("g", "jump_top", "Top", show=False),
    Binding("G,end", "jump_bottom", "Bottom", show=False),
    Binding("h", "focus_previous", "Prev panel", show=False),
    Binding("l", "focus_next", "Next panel", show=False),
    Binding("d,tab", "toggle_deep_detail", "Detail mode"),
    Binding("e", "export_json", "Export JSON"),
    Binding("c", "export_csv", "Export CSV"),
    Binding("question_mark", "show_help", "Help"),
    Binding("q", "quit", "Quit"),
]

HELP_TEXT = """
[b]TerminalVelocity Phase 1 core TUI[/b]

[cyan]/[/cyan] focus query   [cyan]j/k[/cyan] or arrows move rows
[cyan]h/l[/cyan] switch focus panels   [cyan]g/G[/cyan] jump top/bottom
[cyan]d[/cyan] toggle overview vs deep detail
[cyan]e[/cyan] export filtered rows to JSON   [cyan]c[/cyan] export filtered rows to CSV
[cyan]?[/cyan] show help   [cyan]q[/cyan] quit
""".strip()

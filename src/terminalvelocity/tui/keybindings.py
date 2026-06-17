"""Keyboard bindings for the TerminalVelocity TUI."""

from textual.binding import Binding

KEY_BINDINGS = [
    Binding("slash", "focus_query", "Query"),
    Binding("j,down", "cursor_down", "Next", show=False),
    Binding("k,up", "cursor_up", "Prev", show=False),
    Binding("g", "jump_top", "Top", show=False),
    Binding("G,end", "jump_bottom", "Bottom", show=False),
    Binding("h", "focus_previous", "Prev panel", show=False),
    Binding("l", "focus_next", "Next panel", show=False),
    Binding("z,tab", "toggle_deep_detail", "Deep detail"),
    Binding("d", "toggle_detail_visible", "Toggle detail"),
    Binding("e", "export_json", "Export JSON"),
    Binding("c", "export_csv", "Export CSV"),
    Binding("m", "export_markdown", "Export MD"),
    Binding("p", "show_pivot", "Pivot"),
    Binding("t", "show_timeline", "Timeline"),
    Binding("a", "show_anomalies", "Anomalies"),
    Binding("s", "show_saved_queries", "Saved queries"),
    Binding("b", "tag_event", "Tag event"),
    Binding("ctrl+r", "show_history", "History"),
    Binding("ctrl+l", "show_logs", "Logs"),
    Binding("question_mark", "show_help", "Help"),
    Binding("q", "quit", "Quit"),
]

HELP_TEXT = """
[b]TerminalVelocity — keyboard reference[/b]

[cyan]/[/cyan] focus query   [cyan]j/k[/cyan] or arrows move rows   [cyan]h/l[/cyan] switch panels
[cyan]g/G[/cyan] jump top/bottom   [cyan]z[/cyan] deep detail   [cyan]d[/cyan] toggle detail panel

[cyan]p[/cyan] pivot (related events)   [cyan]t[/cyan] timeline (actor history)
[cyan]a[/cyan] anomaly panel   [cyan]s[/cyan] saved queries   [cyan]b[/cyan] tag event
[cyan]ctrl+r[/cyan] query history

[cyan]e[/cyan] export JSON   [cyan]c[/cyan] export CSV   [cyan]m[/cyan] export Markdown report

[cyan]ctrl+r[/cyan] query history   [cyan]ctrl+l[/cyan] application log viewer

[b]Query syntax[/b]
  field:value   provider:defender result:failure severity:high
  since:24h  until:now  sort:severity  sort:-time
  tag:relevant  show:archived
  Free-text tokens are AND-matched against all fields.

[cyan]?[/cyan] show help   [cyan]q[/cyan] quit
""".strip()


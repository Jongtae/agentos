"""
MonitorPanel — right panel showing live tool execution status and memory stats.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static
from textual.reactive import reactive


ICONS = {
    "bash":       "🖥",
    "file_read":  "📖",
    "file_write": "✏️",
    "file_list":  "📂",
    "web_fetch":  "🌐",
    "fact":       "💡",
}

STATUS_ICONS = {
    "running": "⟳",
    "done":    "✓",
    "error":   "✗",
    "blocked": "🚫",
    "aborted": "⊘",
}


class MonitorPanel(Static):
    """Displays tool execution steps and memory stats."""

    DEFAULT_CSS = """
    MonitorPanel {
        width: 1fr;
        padding: 0 1;
        border-left: solid $primary-darken-2;
        overflow-y: auto;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._steps: list[dict] = []
        self._memory_count: int = 0
        self._total_steps: int = 0

    def on_mount(self) -> None:
        self._refresh_display()

    def set_memory_count(self, count: int) -> None:
        self._memory_count = count
        self._refresh_display()

    def add_step(self, index: int, tool_name: str, description: str) -> None:
        self._steps.append({
            "index": index,
            "tool": tool_name,
            "desc": description[:40],
            "status": "running",
        })
        self._total_steps = len(self._steps)
        self._refresh_display()

    def update_step(self, index: int, status: str) -> None:
        for s in self._steps:
            if s["index"] == index:
                s["status"] = status
                break
        self._refresh_display()

    def reset(self, total: int = 0) -> None:
        self._steps.clear()
        self._total_steps = total
        self._refresh_display()

    def _refresh_display(self) -> None:
        lines = ["[bold cyan]⚙ Tool Monitor[/]\n"]

        if self._steps:
            lines.append("[dim]─────────────────────────[/]")
            for s in self._steps[-12:]:  # show last 12
                icon = ICONS.get(s["tool"], "🔧")
                stat = STATUS_ICONS.get(s["status"], "?")
                color = {
                    "running": "yellow",
                    "done": "green",
                    "error": "red",
                    "blocked": "red",
                    "aborted": "dim",
                }.get(s["status"], "white")
                lines.append(
                    f"[{color}]{stat}[/] {icon} [{s['tool']}] {s['desc']}"
                )
            lines.append("")

        # Stats
        done = sum(1 for s in self._steps if s["status"] == "done")
        lines.append("[dim]─────────────────────────[/]")
        lines.append(f"[cyan]Memory:[/] {self._memory_count} items")
        if self._total_steps:
            lines.append(f"[cyan]Steps:[/]  {done}/{self._total_steps} complete")

        self.update("\n".join(lines))

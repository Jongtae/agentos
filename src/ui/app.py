"""
AIKernelApp — full-screen TUI for AgentOS.

Layout:
  ┌─────────────────────────────────────────┐
  │            AgentOS  v0.1                │
  ├──────────────────────┬──────────────────┤
  │  Output (left 2/3)   │  Monitor (1/3)   │
  │                      │                  │
  ├──────────────────────┴──────────────────┤
  │  ai> _                                  │
  └─────────────────────────────────────────┘

The ai> prompt is the OS, not a window inside it.
"""
from __future__ import annotations

import threading
from typing import Callable

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, RichLog, Input, Label, Static

from ui.panels.monitor_panel import MonitorPanel
from ui.theme import AGENTOS_CSS
from kernel.policies.approval_rules import ApprovalRequest
from version import APP_VERSION


class AIKernelApp(App):
    """AgentOS full-screen TUI application."""

    CSS = AGENTOS_CSS

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear_output", "Clear"),
    ]

    def __init__(
        self,
        runtime,            # KernelRuntime
        memory,             # MemoryStore
        workspace_name: str = "default",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._runtime = runtime
        self._memory = memory
        self._workspace_name = workspace_name
        self._pending_approval: ApprovalRequest | None = None
        self._approval_event = threading.Event()
        self._approval_result = False

        # Wire approval callback into runtime
        runtime._approve = self._handle_approval_sync

        # Wire monitor callbacks
        runtime._on_start = self._on_step_start
        runtime._on_done  = self._on_step_done

    # ──────────────────────────────────────────
    # Layout
    # ──────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-container"):
            yield RichLog(id="output-panel", highlight=True, markup=True, wrap=True)
            yield MonitorPanel(id="monitor-panel")
        with Horizontal(id="prompt-container"):
            yield Label("ai>", id="prompt-prefix")
            yield Input(placeholder="type your intent here...", id="prompt-input")
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"AgentOS — {self._workspace_name}"
        self.query_one("#prompt-input", Input).focus()
        self._update_memory_count()
        output = self.query_one("#output-panel", RichLog)
        output.write(
            f"[bold cyan]AgentOS[/] [dim]v{APP_VERSION}[/] — "
            f"workspace: [green]{self._workspace_name}[/]\n"
            "[dim]Type your intent. Press Ctrl+C to quit.[/]\n"
        )

    # ──────────────────────────────────────────
    # Input handling
    # ──────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        intent = event.value.strip()
        if not intent:
            return

        prompt_input = self.query_one("#prompt-input", Input)
        prompt_input.clear()
        prompt_input.placeholder = "thinking..."
        prompt_input.disabled = True

        output = self.query_one("#output-panel", RichLog)

        # Handle pending approval
        if self._pending_approval:
            approved = intent.lower() in ("yes", "y")
            self._approval_result = approved
            self._approval_event.set()
            self._pending_approval = None
            output.write(
                f"[{'green' if approved else 'red'}]"
                f"{'✓ Approved' if approved else '⊘ Aborted'}[/]\n"
            )
            self._restore_prompt()
            return

        # Handle built-in commands
        if intent.lower() in ("exit", "quit"):
            self.exit()
            return
        if intent.lower() == "clear":
            self.action_clear_output()
            self._restore_prompt()
            return

        output.write(f"[bold cyan]ai>[/] {intent}\n")
        monitor = self.query_one("#monitor-panel", MonitorPanel)
        monitor.reset()

        # Run in background thread (keeps UI responsive)
        def _run():
            try:
                result = self._runtime.run(intent)
                self.call_from_thread(self._show_result, result)
            except Exception as e:
                self.call_from_thread(self._show_error, str(e))

        threading.Thread(target=_run, daemon=True).start()

    # ──────────────────────────────────────────
    # Approval flow (called from background thread)
    # ──────────────────────────────────────────

    def _handle_approval_sync(self, request: ApprovalRequest) -> bool:
        """
        Called synchronously from the runtime thread.
        Blocks until the user responds via the TUI.
        """
        self._pending_approval = request
        self._approval_event.clear()

        self.call_from_thread(self._show_approval_prompt, request)

        self._approval_event.wait(timeout=120)  # 2 min timeout
        return self._approval_result

    def _show_approval_prompt(self, request: ApprovalRequest) -> None:
        output = self.query_one("#output-panel", RichLog)
        output.write(
            f"\n[bold yellow]⚠ APPROVAL REQUIRED[/]\n"
            f"[yellow]Tool:[/]    {request.tool_name}\n"
            f"[yellow]Action:[/]  {request.description}\n"
            f"[yellow]Command:[/] [dim]{request.command_or_path}[/]\n"
            f"[yellow]Risk:[/]    {request.risk_reason}\n"
            f"[bold]Type [green]yes[/green] to approve or [red]no[/red] to abort:[/]\n"
        )
        prompt_input = self.query_one("#prompt-input", Input)
        prompt_input.placeholder = "yes / no"
        prompt_input.disabled = False
        prompt_input.focus()

    # ──────────────────────────────────────────
    # Monitor callbacks (called from runtime thread)
    # ──────────────────────────────────────────

    def _on_step_start(self, index: int, step) -> None:
        self.call_from_thread(
            lambda: self.query_one("#monitor-panel", MonitorPanel)
            .add_step(index, step.tool_name, step.description)
        )

    def _on_step_done(self, index: int, step, result: str) -> None:
        status = "error" if result.startswith("[error]") else "done"
        self.call_from_thread(
            lambda: self.query_one("#monitor-panel", MonitorPanel)
            .update_step(index, status)
        )
        self._update_memory_count()

    # ──────────────────────────────────────────
    # Display helpers
    # ──────────────────────────────────────────

    def _show_result(self, result: str) -> None:
        output = self.query_one("#output-panel", RichLog)
        output.write(f"\n[bold green]AI:[/] {result}\n")
        self._restore_prompt()

    def _show_error(self, error: str) -> None:
        output = self.query_one("#output-panel", RichLog)
        output.write(f"\n[bold red]Error:[/] {error}\n")
        self._restore_prompt()

    def _restore_prompt(self) -> None:
        prompt_input = self.query_one("#prompt-input", Input)
        prompt_input.placeholder = "type your intent here..."
        prompt_input.disabled = False
        prompt_input.focus()

    def _update_memory_count(self) -> None:
        try:
            count = self._memory.count()
            self.call_from_thread(
                lambda: self.query_one("#monitor-panel", MonitorPanel)
                .set_memory_count(count)
            )
        except Exception:
            pass

    # ──────────────────────────────────────────
    # Actions
    # ──────────────────────────────────────────

    def action_clear_output(self) -> None:
        self.query_one("#output-panel", RichLog).clear()

    def action_quit(self) -> None:
        self.exit()

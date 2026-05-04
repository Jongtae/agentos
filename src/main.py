"""
AgentOS — main entry point.

Wires all components together and launches the TUI.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys

# ── bootstrap ──────────────────────────────────────────────
from config import load_env, get_workspace_path

load_env()

# ── internal imports ───────────────────────────────────────
from workspace.manager import WorkspaceManager
from doctor import run_doctor
from status import run_status
from trace_status import run_trace_status
from preflight import run_preflight
from diagnostics import snapshot_report, write_snapshot_file
from io_utils import scrub_payload
from version import APP_VERSION
from models.adapter import build_llm
from kernel.memory.store import MemoryStore
from kernel.memory.index import build_memory_index_from_env
from kernel.memory.summarizer import (
    NoopMemoryWindowSummarizer,
    ScaffoldMemoryWindowSummarizer,
    is_memory_summarizer_enabled,
)
from kernel.context.selector import ContextSelector
from kernel.context.selector_v2 import (
    ContextSelectorV2CompatAdapter,
    LegacySelectorV2Bridge,
    is_context_selector_v2_enabled,
)
from kernel.planner.planner import Planner
from kernel.runtime.executor import Executor
from kernel.runtime.loop import KernelRuntime
from kernel.runtime.trace import build_runtime_trace_writer
from kernel.runtime.agent_runner import AgentRunner, is_agent_runner_enabled
from kernel.runtime.checkpoint_saver import JsonCheckpointSaver
from kernel.policies.approval_rules import PolicyEngine
from kernel.engine import (
    CodexCliEngine,
    ClaudeEngineStub,
    EngineRouter,
    GeminiEngineStub,
    OllamaEngine,
    SetupGuideEngine,
    ensure_provider_ready,
)
from kernel.tools.bash_tool import BashTool
from kernel.tools.file_tool import DocumentAccessTool, FileReadTool, FileWriteTool, FileListTool
from kernel.tools.web_tool import WebTool
from kernel.tools.browser_tool import BrowserExecutorTool, is_browser_tool_enabled


def build_runtime(
    wm: WorkspaceManager,
    planner_backend=None,
) -> tuple[KernelRuntime, MemoryStore, WorkspaceManager]:
    """Assemble all components. Returns (runtime, memory, workspace_manager)."""
    workspace_dir = wm.workspace_dir

    # Planner backend: kernel engine adapter first, legacy LLM fallback second.
    planner_llm = planner_backend if planner_backend is not None else build_llm(wm.spec)

    # Memory
    memory = MemoryStore(wm.memory_store_path)

    # Context selector (v2 is opt-in and bridged to preserve runtime compatibility)
    selector = ContextSelector(top_k=5, memory_index=build_memory_index_from_env())
    if is_context_selector_v2_enabled():
        selector = ContextSelectorV2CompatAdapter(
            selector_v2=LegacySelectorV2Bridge(selector),
            top_k=5,
        )

    # Tools
    tools = []
    tool_spec = wm.spec.get("tools", {})
    if tool_spec.get("bash", True):
        tools.append(BashTool(workspace_dir))
    if tool_spec.get("file", True):
        tools.extend([
            DocumentAccessTool(workspace_dir),
            FileReadTool(workspace_dir),
            FileWriteTool(workspace_dir),
            FileListTool(workspace_dir),
        ])
    if tool_spec.get("web", True):
        tools.append(WebTool(workspace_dir=workspace_dir, domain_allowlist=getattr(wm, "web_allowlist", [])))
    if tool_spec.get("browser", False) and is_browser_tool_enabled():
        tools.append(BrowserExecutorTool())

    # Planner
    planner = Planner(planner_llm, available_tools=[tool.name for tool in tools])

    # Executor
    executor = Executor(tools)

    # Policy
    policy = PolicyEngine(require_approval=wm.require_approval)

    # Memory summarizer (Phase 3 scaffold, disabled by default)
    memory_summarizer = NoopMemoryWindowSummarizer()
    if is_memory_summarizer_enabled():
        memory_summarizer = ScaffoldMemoryWindowSummarizer()

    # Runtime (approval_fn and callbacks are injected later by the TUI)
    runtime = KernelRuntime(
        planner=planner,
        executor=executor,
        context_selector=selector,
        policy=policy,
        approver_fn=lambda _: True,  # placeholder; replaced by TUI
        memory=memory,
        trace_writer=build_runtime_trace_writer(workspace_dir),
        memory_summarizer=memory_summarizer,
        max_steps=wm.max_steps,
        workspace_dir=workspace_dir,
    )

    return runtime, memory, wm


def _apply_default_network_policy_env(wm: WorkspaceManager) -> None:
    """
    Apply safe network policy defaults from workspace spec when env is unset.
    Explicit environment variables always win.
    """
    if not os.environ.get("AGENTOS_BROWSER_DOMAIN_ALLOWLIST", "").strip():
        allowlist = ",".join(wm.browser_allowlist)
        if allowlist:
            os.environ["AGENTOS_BROWSER_DOMAIN_ALLOWLIST"] = allowlist


def _prompt_engine_selection(wm: WorkspaceManager) -> str:
    """
    Terminal-based first-boot wizard.
    We intentionally keep this path identical for TUI and no-TUI startup.
    """
    print("\n=== AgentOS Kernel Engine Setup ===")
    print("Select the kernel engine provider:")
    print("  1) ollama  (bundled local LLM, recommended)")
    print("  2) codex   (online, OpenAI API key required)")
    print("  3) later   (guide mode fallback)")

    attempts = 0
    choices = {
        "1": "ollama",
        "2": "codex",
        "3": "none",
        "ollama": "ollama",
        "codex": "codex",
        "later": "none",
        "none": "none",
    }

    while True:
        raw = input("engine> ").strip().lower()
        provider = choices.get(raw, "")
        if not provider:
            attempts += 1
            print(f"Invalid selection. Try again. (attempt {attempts})")
            continue

        wm.set_kernel_engine_provider(provider)
        print(f"Selected kernel engine: {provider}")
        return provider


def _resolve_kernel_engine(wm: WorkspaceManager):
    """
    Resolve selected engine and force onboarding fallback when unhealthy.
    """
    router = EngineRouter(
        mode=wm.kernel_engine_mode,
        engines={
            "codex": CodexCliEngine(
                workspace_dir=wm.workspace_dir,
                command=wm.codex_command,
                timeout_sec=wm.codex_timeout_sec,
                model=wm.codex_model,
            ),
            "ollama": OllamaEngine(
                workspace_dir=wm.workspace_dir,
                command=wm.ollama_command,
                timeout_sec=wm.ollama_timeout_sec,
                model=wm.ollama_model,
            ),
            "none": SetupGuideEngine(),
            "claude": ClaudeEngineStub(),
            "gemini": GeminiEngineStub(),
        },
    )

    while True:
        provider = wm.kernel_engine_provider
        if not provider:
            provider = _prompt_engine_selection(wm)

        engine = router.get_engine(provider)
        if provider == "none":
            return engine
        bootstrap = ensure_provider_ready(wm, provider)
        if bootstrap.ok:
            return engine

        print("\nKernel engine health check failed.")
        print(f"Reason: {bootstrap.reason}")
        if bootstrap.detail:
            print(f"Detail: {bootstrap.detail}")
        if bootstrap.bootstrap_attempted:
            print(f"Bootstrap strategy: {bootstrap.install_strategy}")
        print("Falling back to guide mode for this session.")
        wm.set_kernel_engine_provider("none")
        return router.get_engine("none")


def _build_engine_router(wm: WorkspaceManager) -> EngineRouter:
    return EngineRouter(
        mode=wm.kernel_engine_mode,
        engines={
            "codex": CodexCliEngine(
                workspace_dir=wm.workspace_dir,
                command=wm.codex_command,
                timeout_sec=wm.codex_timeout_sec,
                model=wm.codex_model,
            ),
            "ollama": OllamaEngine(
                workspace_dir=wm.workspace_dir,
                command=wm.ollama_command,
                timeout_sec=wm.ollama_timeout_sec,
                model=wm.ollama_model,
            ),
            "none": SetupGuideEngine(),
            "claude": ClaudeEngineStub(),
            "gemini": GeminiEngineStub(),
        },
    )


def _run_health_check(wm: WorkspaceManager, provider: str):
    router = _build_engine_router(wm)
    engine = router.get_engine(provider)
    return engine.health_check()


def _maybe_wrap_agent_runner(runtime, wm: WorkspaceManager):
    if not is_agent_runner_enabled():
        return runtime
    checkpoint_file = wm.workspace_dir / "data" / "checkpoints" / "agent_runner.json"
    saver = JsonCheckpointSaver(checkpoint_file)
    return AgentRunner(runtime, checkpoint_saver=saver)


def main() -> None:
    parser = argparse.ArgumentParser(description=f"AgentOS v{APP_VERSION} — AI Kernel OS")
    parser.add_argument(
        "--workspace",
        default=get_workspace_path(),
        help="Path to workspace directory",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    parser.add_argument(
        "--no-tui",
        action="store_true",
        help="Run in plain REPL mode (no TUI, for debugging)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {APP_VERSION}",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run environment diagnostics and exit",
    )
    parser.add_argument(
        "--doctor-file",
        help="Write --doctor report JSON to file",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print effective runtime status and exit",
    )
    parser.add_argument(
        "--status-file",
        help="Write --status report JSON to file",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Run startup readiness checks and exit",
    )
    parser.add_argument(
        "--preflight-file",
        help="Write --preflight report JSON to file",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Print combined diagnostics snapshot as JSON and exit",
    )
    parser.add_argument(
        "--snapshot-file",
        help="Write --snapshot JSON output to file",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Use JSON output for --doctor, --status, --preflight, or --trace-status",
    )
    parser.add_argument(
        "--trace-status",
        action="store_true",
        help="Print runtime trace summary and exit",
    )
    parser.add_argument(
        "--setup-engine",
        action="store_true",
        help="Run engine setup wizard and exit",
    )
    parser.add_argument(
        "--set-engine",
        choices=["ollama", "codex", "none", "claude", "gemini"],
        help="Set kernel engine provider non-interactively and exit",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    try:
        wm = WorkspaceManager(args.workspace)
        _apply_default_network_policy_env(wm)
        if args.snapshot:
            payload = snapshot_report(wm)
            if args.snapshot_file:
                write_snapshot_file(args.snapshot_file, payload)
            print(json.dumps(scrub_payload(payload), ensure_ascii=True))
            raise SystemExit(int(payload["exit_code"]))
        if args.snapshot_file:
            print("--snapshot-file is only valid with --snapshot.")
            raise SystemExit(2)
        if args.status:
            raise SystemExit(run_status(wm, as_json=args.json, output_file=args.status_file or ""))
        if args.status_file:
            print("--status-file is only valid with --status.")
            raise SystemExit(2)
        if args.trace_status:
            raise SystemExit(run_trace_status(wm, as_json=args.json))
        if args.preflight:
            raise SystemExit(run_preflight(wm, as_json=args.json, output_file=args.preflight_file or ""))
        if args.preflight_file:
            print("--preflight-file is only valid with --preflight.")
            raise SystemExit(2)
        if args.set_engine:
            if args.set_engine in ("claude", "gemini"):
                print(f"'{args.set_engine}' is not implemented yet in this prototype.")
                print("Use --set-engine ollama or --set-engine codex for now.")
                raise SystemExit(2)

            if args.set_engine == "none":
                wm.set_kernel_engine_provider("none")
                print("Kernel engine set to 'none' (guide mode).")
                print("Run --setup-engine or --set-engine ollama when ready.")
                raise SystemExit(0)

            wm.set_kernel_engine_provider(args.set_engine)
            bootstrap = ensure_provider_ready(wm, args.set_engine)
            if bootstrap.ok:
                print(f"Kernel engine set to '{args.set_engine}' and health check passed.")
                if bootstrap.bootstrap_attempted:
                    print(f"Bootstrap strategy: {bootstrap.install_strategy}")
                raise SystemExit(0)
            print(f"Kernel engine set to '{args.set_engine}', but health check failed.")
            print(f"Reason: {bootstrap.reason}")
            if bootstrap.detail:
                print(f"Detail: {bootstrap.detail}")
            if bootstrap.bootstrap_attempted:
                print(f"Bootstrap strategy: {bootstrap.install_strategy}")
            raise SystemExit(1)

        if args.setup_engine:
            provider = _prompt_engine_selection(wm)
            bootstrap = ensure_provider_ready(wm, provider)
            if bootstrap.ok:
                print("Engine setup completed.")
                if bootstrap.bootstrap_attempted:
                    print(f"Bootstrap strategy: {bootstrap.install_strategy}")
                raise SystemExit(0)
            print("Engine setup completed, but health check failed.")
            print(f"Reason: {bootstrap.reason}")
            if bootstrap.detail:
                print(f"Detail: {bootstrap.detail}")
            if bootstrap.bootstrap_attempted:
                print(f"Bootstrap strategy: {bootstrap.install_strategy}")
            raise SystemExit(1)

        if args.doctor:
            raise SystemExit(run_doctor(wm, as_json=args.json, output_file=args.doctor_file or ""))
        if args.doctor_file:
            print("--doctor-file is only valid with --doctor.")
            raise SystemExit(2)
        if args.json:
            print("--json is only valid with --doctor, --status, --preflight, or --trace-status.")
            raise SystemExit(2)
        engine = _resolve_kernel_engine(wm)
        runtime, memory, wm = build_runtime(wm, planner_backend=engine)
        runtime = _maybe_wrap_agent_runner(runtime, wm)
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.no_tui:
        _run_plain_repl(runtime, wm.name, str(wm.workspace_dir))
    else:
        _run_tui(runtime, memory, wm.name)


def _run_tui(runtime, memory, workspace_name: str) -> None:
    from ui.app import AIKernelApp
    app = AIKernelApp(runtime=runtime, memory=memory, workspace_name=workspace_name)
    app.run()


def _run_plain_repl(runtime, workspace_name: str, workspace_path: str = "") -> None:
    """Conversational terminal REPL with an explicit shell escape."""

    def approver(request) -> bool:
        print(f"\n⚠  APPROVAL REQUIRED")
        print(f"   Tool:    {request.tool_name}")
        print(f"   Action:  {request.description}")
        print(f"   Command: {request.command_or_path}")
        answer = input("   Approve? (yes/no): ").strip().lower()
        return answer in ("yes", "y")

    runtime._approve = approver

    workspace_dir = workspace_path or getattr(runtime, "workspace_dir", None)

    def print_help() -> None:
        print()
        print("Talk to AgentOS like a teammate:")
        print("  search AgentOS roadmap and summarize it")
        print("  draft a short reply based on my inbox")
        print("  what can this OS do right now?")
        print()
        print("Use Linux only when you need it:")
        print("  % ls -la")
        print("  % systemctl status agentos-ollama.service --no-pager")
        print("  shell journalctl -u agentos-operator-tty1.service --no-pager")
        print()
        print("Useful words: help, exit")
        print()

    def run_shell_escape(command: str) -> None:
        command = command.strip()
        if not command:
            print("Use `% <command>` or `shell <command>` to run Linux commands.")
            return
        cwd = str(workspace_dir) if workspace_dir else os.getcwd()
        completed = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            text=True,
            capture_output=True,
            timeout=120,
        )
        if completed.stdout:
            print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
        if completed.stderr:
            print(completed.stderr, end="" if completed.stderr.endswith("\n") else "\n", file=sys.stderr)
        if completed.returncode != 0:
            print(f"[shell exited with {completed.returncode}]")

    print(f"AgentOS v{APP_VERSION} — conversational runtime")
    print(f"Workspace: {workspace_name}")
    if getattr(runtime, "runner_mode", "") == "phase2-skeleton":
        print("Phase2 runner: agent_runner (skeleton)")
    print()
    print("This prompt is for talking to AgentOS.")
    print("Use `% <command>` only when you want a Linux shell command.")
    print("Type `help` for examples, or `exit` to leave.\n")

    while True:
        try:
            line = input("ai> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not line:
            continue
        if line.lower() in ("exit", "quit"):
            break
        if line.lower() in ("help", "?"):
            print_help()
            continue
        if line.startswith("%"):
            run_shell_escape(line[1:])
            continue
        if line.lower().startswith("shell "):
            run_shell_escape(line[6:])
            continue

        result = runtime.run(line)
        print(f"\nAgentOS: {result}\n")


if __name__ == "__main__":
    main()

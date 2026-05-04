"""
KernelRuntime — the core execution loop of AgentOS.

This is the heart of the system. LangGraph does NOT replace this loop.
In Phase 2, LangGraph handles individual LLM+tool cycles inside agent_runner.py,
but the outer loop always belongs here.

LLM = judgment (Planner produces a Plan)
Code = execution (Executor runs Steps deterministically)
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from kernel.broker import append_broker_events, build_approval_broker_decision, build_approval_broker_request
from kernel.planner.planner import Plan, Step
from kernel.runtime.executor import Executor
from kernel.runtime.trace import NoopRuntimeTraceWriter
from kernel.policies.approval_rules import PolicyEngine, ApprovalRequest
from kernel.memory.summarizer import NoopMemoryWindowSummarizer

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Execution state for a single intent run
# ──────────────────────────────────────────────────────────────

@dataclass
class ExecutionContext:
    user_input: str
    context: str = ""
    plan: Plan | None = None
    results: list[str] = field(default_factory=list)
    aborted_steps: list[int] = field(default_factory=list)
    blocked_steps: list[int] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────
# Approval callback type
# ──────────────────────────────────────────────────────────────

# Signature: (request: ApprovalRequest) -> bool
ApproverFn = Callable[[ApprovalRequest], bool]


# ──────────────────────────────────────────────────────────────
# Runtime
# ──────────────────────────────────────────────────────────────

class KernelRuntime:
    """
    Orchestrates a single intent → plan → execution cycle.

    Dependencies are injected; this class has no hard dependencies
    on LangGraph, specific LLM providers, or specific tools.
    """

    def __init__(
        self,
        planner,            # kernel.planner.planner.Planner
        executor: Executor,
        context_selector,   # kernel.context.selector.ContextSelector
        policy: PolicyEngine,
        approver_fn: ApproverFn,
        memory,             # kernel.memory.store.MemoryStore
        trace_writer=None,  # kernel.runtime.trace.RuntimeTraceWriter
        memory_summarizer=None,  # kernel.memory.summarizer.MemoryWindowSummarizer
        max_steps: int = 12,
        workspace_dir: str | Path | None = None,
        on_step_start: Callable[[int, Step], None] | None = None,
        on_step_done: Callable[[int, Step, str], None] | None = None,
    ):
        self._planner  = planner
        self._executor = executor
        self._selector = context_selector
        self._policy   = policy
        self._approve  = approver_fn
        self._memory   = memory
        self._trace    = trace_writer or NoopRuntimeTraceWriter()
        self._summarizer = memory_summarizer or NoopMemoryWindowSummarizer()
        self._max      = max_steps
        self._workspace_dir = Path(workspace_dir).resolve() if workspace_dir else None
        self._on_start = on_step_start   # for TUI monitor panel
        self._on_done  = on_step_done

    # ──────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────

    def run(self, user_input: str) -> str:
        """
        Execute a user intent synchronously.
        Returns a formatted response string.
        """
        ctx = ExecutionContext(user_input=user_input)
        if hasattr(self._policy, "begin_run"):
            self._policy.begin_run()
        self._trace.emit("run_start", {"user_input": user_input, "max_steps": self._max})

        # 1. Select context from memory
        ctx.context = self._selector.select(user_input, self._memory)
        if self._summarizer.is_enabled():
            ctx.context = self._summarizer.compact_message_window(
                user_input=user_input,
                context=ctx.context,
                memory=self._memory,
            )
        logger.debug("Context selected: %d chars", len(ctx.context))

        # 2. Generate plan (LLM)
        ctx.plan = self._planner.plan(user_input, ctx.context)
        logger.info("Plan: %d steps — %s", len(ctx.plan.steps), ctx.plan.summary)
        self._trace.emit(
            "plan_generated",
            {"summary": ctx.plan.summary, "steps": len(ctx.plan.steps)},
        )

        # If plan has no steps, return summary directly (direct LLM answer)
        if not ctx.plan.steps:
            self._trace.emit(
                "run_end",
                {"result_count": 0, "aborted": 0, "blocked": 0, "direct_answer": True},
            )
            return ctx.plan.summary

        # 3. Execute steps
        for i, step in enumerate(ctx.plan.steps):
            if i >= self._max:
                ctx.results.append(f"[stopped: max_steps={self._max} reached]")
                self._trace.emit("run_stopped", {"reason": "max_steps_reached", "step_index": i})
                break
            self._trace.emit(
                "step_started",
                {"step_index": i, "tool_name": step.tool_name, "description": step.description},
            )

            # Check if blocked outright
            if self._policy.is_blocked(step):
                if step.tool_name == "browser_run":
                    msg = f"[blocked] {step.description}: browser navigation refused by security policy"
                else:
                    msg = f"[blocked] {step.description}: command refused by security policy"
                ctx.results.append(msg)
                ctx.blocked_steps.append(i)
                self._trace.emit(
                    "step_blocked",
                    {"step_index": i, "tool_name": step.tool_name, "reason": msg},
                )
                logger.warning("Step %d blocked: %s", i, step.args)
                continue

            # Check if approval required
            if self._policy.requires_approval(step):
                request = self._policy.build_request(step, i)
                broker_request = build_approval_broker_request(step, request, step_index=i)
                if self._workspace_dir is not None:
                    append_broker_events(
                        self._workspace_dir,
                        request=broker_request,
                        request_kind="approval",
                    )
                self._trace.emit(
                    "approval_requested",
                    {
                        "step_index": i,
                        "tool_name": request.tool_name,
                        "risk_reason": request.risk_reason,
                        "command_or_path": request.command_or_path,
                        "broker": broker_request.to_dict(),
                    },
                )
                approved = self._approve(request)
                broker_decision = build_approval_broker_decision(
                    step,
                    request,
                    approved=bool(approved),
                    step_index=i,
                )
                if self._workspace_dir is not None:
                    append_broker_events(
                        self._workspace_dir,
                        decision=broker_decision,
                        request_kind="approval",
                    )
                self._trace.emit(
                    "approval_decision",
                    {
                        "step_index": i,
                        "tool_name": request.tool_name,
                        "approved": bool(approved),
                        "broker": broker_decision.to_dict(),
                    },
                )
                if not approved:
                    msg = f"[aborted] step {i+1}: {step.description}"
                    ctx.results.append(msg)
                    ctx.aborted_steps.append(i)
                    logger.info("Step %d aborted by user", i)
                    continue

            # Execute
            if self._on_start:
                self._on_start(i, step)

            result = self._executor.execute(step)
            ctx.results.append(result)
            self._trace.emit(
                "step_completed",
                {
                    "step_index": i,
                    "tool_name": step.tool_name,
                    "result_chars": len(result),
                    "result_is_error": result.startswith("[error]"),
                },
            )
            if hasattr(self._policy, "on_step_executed"):
                self._policy.on_step_executed(step, result)

            # Persist to memory
            self._memory.save_result(step, result)

            if self._on_done:
                self._on_done(i, step, result)

            logger.debug("Step %d done (%d chars)", i, len(result))

        self._trace.emit(
            "run_end",
            {
                "result_count": len(ctx.results),
                "aborted": len(ctx.aborted_steps),
                "blocked": len(ctx.blocked_steps),
                "direct_answer": False,
            },
        )
        return self._format(ctx)

    # ──────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────

    def _format(self, ctx: ExecutionContext) -> str:
        if not ctx.results:
            return ctx.plan.summary if ctx.plan else "(no output)"

        if len(ctx.results) == 1:
            # Single step: return result with plan summary as prefix if available
            result = ctx.results[0]
            if ctx.plan and ctx.plan.summary and not result.startswith("["):
                return result
            return result

        # Multiple steps: number them
        parts = []
        for i, r in enumerate(ctx.results):
            parts.append(f"[{i+1}] {r}")
        header = ctx.plan.summary + "\n\n" if ctx.plan and ctx.plan.summary else ""
        return header + "\n\n".join(parts)

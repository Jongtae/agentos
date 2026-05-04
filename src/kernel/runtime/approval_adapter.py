from __future__ import annotations

from dataclasses import dataclass

from kernel.policies.approval_rules import ApprovalRequest


@dataclass(frozen=True)
class ResumeOutcome:
    approved: bool
    reason: str


class ApprovalInterruptAdapter:
    """
    Phase 2 interrupt/resume adapter contract.

    - build_interrupt_payload(): runtime request -> interrupt payload
    - resolve_resume(): resume decision -> runtime outcome
    """

    def build_interrupt_payload(self, request: ApprovalRequest, run_id: str = "") -> dict:
        return {
            "kind": "approval_interrupt",
            "run_id": run_id,
            "step_index": request.step_index,
            "tool_name": request.tool_name,
            "description": request.description,
            "command_or_path": request.command_or_path,
            "risk_reason": request.risk_reason,
        }

    def resolve_resume(self, decision: str) -> ResumeOutcome:
        normalized = decision.strip().lower()
        if normalized in ("approve", "approved", "allow", "yes", "y", "true", "1"):
            return ResumeOutcome(approved=True, reason="approved")
        if normalized in ("deny", "denied", "reject", "no", "n", "false", "0"):
            return ResumeOutcome(approved=False, reason="denied")
        if normalized in ("timeout", "timed_out"):
            return ResumeOutcome(approved=False, reason="timeout")
        raise ValueError(f"Unknown resume decision: {decision}")

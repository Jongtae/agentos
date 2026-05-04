from __future__ import annotations

from dataclasses import dataclass

from kernel.broker.schema import (
    BrokerDecision,
    BrokerRequest,
    build_broker_decision,
    build_broker_request,
)
from kernel.event_fabric.correlation import build_correlation_context


@dataclass(frozen=True)
class BrokerMediationResult:
    state: str
    request: BrokerRequest
    decision: BrokerDecision
    approval_request: object | None = None

    def to_dict(self) -> dict:
        payload = {
            "state": self.state,
            "request": self.request.to_dict(),
            "decision": self.decision.to_dict(),
        }
        if self.approval_request is not None:
            payload["approval_request"] = {
                "step_index": int(getattr(self.approval_request, "step_index", 0)),
                "tool_name": str(getattr(self.approval_request, "tool_name", "")),
                "description": str(getattr(self.approval_request, "description", "")),
                "command_or_path": str(getattr(self.approval_request, "command_or_path", "")),
                "risk_reason": str(getattr(self.approval_request, "risk_reason", "")),
            }
        return payload


def mediate_managed_exec(step, policy, *, step_index: int = 0) -> BrokerMediationResult:
    """
    Route AgentOS-managed execution through a broker contract before execution.

    This stage only produces a stable request/decision envelope. Later issues
    will emit these decisions into the OS event fabric and route additional
    managed paths through the same mediation layer.
    """
    request_id = f"managed-exec:{step_index}:{step.tool_name}:{step.description}".strip(":")
    correlation = build_correlation_context(request_id=request_id)
    actor = {
        "component": "agentos-shell",
        "path": "managed_exec",
        "tool_name": step.tool_name,
    }
    object_payload = {
        "tool_name": step.tool_name,
        "description": step.description,
        "args": dict(step.args),
        "is_destructive": bool(step.is_destructive),
        "policy_target": "destructive_action_approval" if policy.requires_approval(step) else "",
    }
    metadata = {"step_index": int(step_index)}

    if policy.is_blocked(step):
        request = build_broker_request(
            kind="exec",
            action="managed_exec",
            actor=actor,
            object=object_payload,
            correlation=correlation,
            metadata=metadata,
        )
        decision = build_broker_decision(
            state="blocked",
            reason="blocked by policy before execution",
            actor=actor,
            object=object_payload,
            correlation=correlation,
            metadata=metadata,
        )
        return BrokerMediationResult(state="blocked", request=request, decision=decision)

    if policy.requires_approval(step):
        approval_request = policy.build_request(step, step_index)
        request = build_broker_request(
            kind="approval",
            action="managed_exec",
            actor=actor,
            object=object_payload,
            correlation=build_correlation_context(
                request_id=request_id,
                approval_id=f"approval:{request_id}",
            ),
            metadata=metadata,
        )
        decision = build_broker_decision(
            state="approval_required",
            reason=str(approval_request.risk_reason),
            actor=actor,
            object=object_payload,
            correlation=request.correlation,
            metadata=metadata,
        )
        return BrokerMediationResult(
            state="approval_required",
            request=request,
            decision=decision,
            approval_request=approval_request,
        )

    request = build_broker_request(
        kind="exec",
        action="managed_exec",
        actor=actor,
        object=object_payload,
        correlation=correlation,
        metadata=metadata,
    )
    decision = build_broker_decision(
        state="allowed",
        reason="allowed by policy for managed execution",
        actor=actor,
        object=object_payload,
        correlation=correlation,
        metadata=metadata,
    )
    return BrokerMediationResult(state="allowed", request=request, decision=decision)


def build_approval_broker_request(step, approval_request, *, step_index: int = 0) -> BrokerRequest:
    request_id = f"managed-exec:{step_index}:{step.tool_name}:{step.description}".strip(":")
    approval_id = f"approval:{request_id}"
    actor = {
        "component": "agentos-runtime",
        "path": "approval_gate",
        "tool_name": step.tool_name,
    }
    object_payload = {
        "tool_name": step.tool_name,
        "description": step.description,
        "args": dict(step.args),
        "command_or_path": str(getattr(approval_request, "command_or_path", "")),
        "risk_reason": str(getattr(approval_request, "risk_reason", "")),
        "policy_target": "destructive_action_approval",
    }
    return build_broker_request(
        kind="approval",
        action="approval_gate",
        actor=actor,
        object=object_payload,
        correlation=build_correlation_context(request_id=request_id, approval_id=approval_id),
        metadata={"step_index": int(step_index)},
    )


def build_approval_broker_decision(
    step,
    approval_request,
    *,
    approved: bool,
    step_index: int = 0,
) -> BrokerDecision:
    request = build_approval_broker_request(step, approval_request, step_index=step_index)
    return build_broker_decision(
        state="approved" if approved else "denied",
        reason="approval granted by approver" if approved else "approval denied by approver",
        actor=request.actor,
        object=request.object,
        correlation=request.correlation,
        metadata=request.metadata,
    )

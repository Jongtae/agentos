from __future__ import annotations

from pathlib import Path

from kernel.broker.schema import BrokerDecision, BrokerRequest
from kernel.broker.schema import build_broker_decision, build_broker_request
from kernel.event_fabric import append_events_jsonl, build_os_event_record, os_event_log_path


def broker_request_event(request: BrokerRequest) -> object:
    event_kind = "broker.approval_request" if request.kind == "approval" else "broker.exec_request"
    return build_os_event_record(
        source="broker",
        kind=event_kind,
        actor=request.actor,
        object=request.object,
        action=request.action or "request",
        decision={"state": "requested", "request_kind": request.kind},
        correlation=request.correlation,
        raw_ref={"component": "broker", "metadata": request.metadata},
    )


def broker_decision_event(decision: BrokerDecision, *, request_kind: str = "exec") -> object:
    event_kind = "broker.approval_decision" if request_kind == "approval" else "broker.exec_decision"
    return build_os_event_record(
        source="broker",
        kind=event_kind,
        actor=decision.actor,
        object=decision.object,
        action="decision",
        decision={"state": decision.state, "reason": decision.reason, "request_kind": request_kind},
        correlation=decision.correlation,
        raw_ref={"component": "broker", "metadata": decision.metadata},
    )


def append_broker_events(
    workspace_dir: str | Path,
    *,
    request: BrokerRequest | None = None,
    decision: BrokerDecision | None = None,
    request_kind: str = "exec",
) -> int:
    events = []
    if request is not None:
        events.append(broker_request_event(request))
    if decision is not None:
        events.append(broker_decision_event(decision, request_kind=request_kind))
    if not events:
        return 0
    workspace = Path(workspace_dir).resolve()
    return append_events_jsonl(os_event_log_path(workspace), events)


def append_broker_transition(
    workspace_dir: str | Path,
    *,
    kind: str,
    action: str,
    state: str,
    reason: str,
    actor: dict | None = None,
    object: dict | None = None,
    correlation: dict | None = None,
    metadata: dict | None = None,
) -> int:
    request = build_broker_request(
        kind=kind,
        action=action,
        actor=actor,
        object=object,
        correlation=correlation,
        metadata=metadata,
    )
    decision = build_broker_decision(
        state=state,
        reason=reason,
        actor=actor,
        object=object,
        correlation=correlation,
        metadata=metadata,
    )
    return append_broker_events(workspace_dir, request=request, decision=decision, request_kind=kind)

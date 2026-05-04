from __future__ import annotations

from dataclasses import asdict, dataclass

from kernel.event_fabric.correlation import normalize_correlation_context

BROKER_REQUEST_KINDS = (
    "exec",
    "approval",
    "session_entry",
    "firstrun",
    "override",
    "operator_control",
    "install_control",
)

BROKER_DECISION_STATES = (
    "allowed",
    "approval_required",
    "blocked",
    "approved",
    "denied",
    "override",
)


@dataclass(frozen=True)
class BrokerRequest:
    kind: str
    action: str
    actor: dict
    object: dict
    correlation: dict
    metadata: dict

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BrokerDecision:
    state: str
    reason: str
    actor: dict
    object: dict
    correlation: dict
    metadata: dict

    def to_dict(self) -> dict:
        return asdict(self)


def build_broker_request(
    *,
    kind: str,
    action: str,
    actor: dict | None = None,
    object: dict | None = None,
    correlation: dict | None = None,
    metadata: dict | None = None,
) -> BrokerRequest:
    normalized_kind = str(kind).strip()
    if normalized_kind not in BROKER_REQUEST_KINDS:
        raise ValueError(f"unsupported broker request kind: {normalized_kind}")
    return BrokerRequest(
        kind=normalized_kind,
        action=str(action).strip(),
        actor=actor or {},
        object=object or {},
        correlation=normalize_correlation_context(correlation),
        metadata=metadata or {},
    )


def build_broker_decision(
    *,
    state: str,
    reason: str,
    actor: dict | None = None,
    object: dict | None = None,
    correlation: dict | None = None,
    metadata: dict | None = None,
) -> BrokerDecision:
    normalized_state = str(state).strip()
    if normalized_state not in BROKER_DECISION_STATES:
        raise ValueError(f"unsupported broker decision state: {normalized_state}")
    return BrokerDecision(
        state=normalized_state,
        reason=str(reason).strip(),
        actor=actor or {},
        object=object or {},
        correlation=normalize_correlation_context(correlation),
        metadata=metadata or {},
    )


def broker_contract() -> dict:
    return {
        "request_kinds": list(BROKER_REQUEST_KINDS),
        "decision_states": list(BROKER_DECISION_STATES),
        "request_required_fields": ["kind", "action", "actor", "object", "correlation", "metadata"],
        "decision_required_fields": ["state", "reason", "actor", "object", "correlation", "metadata"],
        "override_semantics": {
            "allowed": "request can execute immediately",
            "approval_required": "request needs explicit approval before execution",
            "blocked": "request must not execute",
            "approved": "approval request granted",
            "denied": "approval request denied",
            "override": "operator emergency bypass applied",
        },
        "event_emission": {
            "exec_request": "broker.exec_request",
            "exec_decision": "broker.exec_decision",
            "approval_request": "broker.approval_request",
            "approval_decision": "broker.approval_decision",
        },
    }

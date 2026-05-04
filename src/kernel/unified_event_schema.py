from __future__ import annotations

from kernel.event_fabric.correlation import correlation_contract
from kernel.event_fabric.schema import OS_EVENT_ALLOWED_SOURCES, OS_EVENT_REQUIRED_FIELDS

UNIFIED_EVENT_SCHEMA_VERSION = "agentos-unified-event-schema.v1"


def unified_event_schema_contract() -> dict:
    correlation = correlation_contract()
    common_fields = [
        {"name": "timestamp_utc", "type": "string", "required": True, "description": "UTC timestamp for the emitted event"},
        {"name": "source", "type": "string", "required": True, "description": "Emitting layer such as journald, broker, runtime, or kernel"},
        {"name": "kind", "type": "string", "required": True, "description": "Stable event kind identifier"},
        {"name": "actor", "type": "object", "required": True, "description": "Who or what initiated the action"},
        {"name": "object", "type": "object", "required": True, "description": "Primary subject of the action"},
        {"name": "action", "type": "string", "required": True, "description": "Normalized operator-facing action verb"},
        {"name": "decision", "type": "object", "required": True, "description": "Observed or mediated decision outcome"},
        {"name": "correlation", "type": "object", "required": True, "description": "Stable linkage fields for replay, approval, and policy joins"},
        {"name": "raw_ref", "type": "object", "required": True, "description": "Collector/component-local provenance and raw references"},
    ]
    causal_chain = {
        "stable_fields": correlation["stable_keys"],
        "linkage_priority": correlation["linkage_priority"],
        "phase_fields": ["session_id", "boot_id", "request_id", "approval_id", "trace_id", "parent_event_id"],
        "rules": [
            "session_id and boot_id anchor boot/setup/session ownership",
            "request_id and approval_id connect broker approval and execution decisions",
            "trace_id links runtime traces with OS-level evidence when available",
            "parent_event_id is reserved for explicit causal ancestry across chained system actions",
        ],
    }
    provenance = {
        "source_contract": {
            "allowed_sources": list(OS_EVENT_ALLOWED_SOURCES),
            "source_meaning": {
                "runtime": "AgentOS runtime trace or intent-level emission",
                "broker": "Broker mediation and approval control plane",
                "journald": "systemd/logind/session lifecycle evidence",
                "dbus": "message-bus lifecycle and control evidence",
                "kernel": "policy or kernel-adjacent operator surface",
                "ebpf": "kernel-observed process/file/network evidence",
                "audit": "audit/AppArmor evidence",
                "manual": "operator-supplied or imported evidence",
            },
        },
        "field_semantics": {
            "actor": "The initiator, component, pid, uid, or system subject that performed the action",
            "object": "The resource, policy target, tool, session, service, or network endpoint being acted on",
            "decision": "Observed state, broker result, policy outcome, or advisory/enforced posture",
            "correlation": "Stable linkage keys used to join runtime, broker, and OS evidence into one chain",
            "raw_ref": "Collector-local provenance such as component, cursor, collector name, or raw reference id",
        },
        "normalization_rules": [
            "All events preserve the required top-level fields defined by the OS event schema",
            "Unknown correlation keys are allowed, but joins should begin from the stable key set",
            "Provenance should stay operator-readable and must not hide source identity behind opaque ids alone",
        ],
    }
    families = [
        {
            "family": "process",
            "description": "Process lifecycle and lineage evidence",
            "representative_kinds": ["process.exec", "process.exit"],
            "primary_sources": ["ebpf", "runtime"],
            "typical_object_keys": ["exe", "comm", "session_id"],
        },
        {
            "family": "file",
            "description": "File access candidates and workspace-boundary evidence",
            "representative_kinds": ["file.outside_workspace_candidate"],
            "primary_sources": ["ebpf", "kernel"],
            "typical_object_keys": ["path", "workspace_root", "policy_target"],
        },
        {
            "family": "network",
            "description": "Network connection candidates and allowlist evidence",
            "representative_kinds": ["network.connect_candidate"],
            "primary_sources": ["ebpf", "kernel"],
            "typical_object_keys": ["remote_host", "remote_port", "policy_target"],
        },
        {
            "family": "approval",
            "description": "Approval requests and decisions tied to risky actions",
            "representative_kinds": ["broker.approval_request", "broker.approval_decision"],
            "primary_sources": ["broker", "runtime"],
            "typical_object_keys": ["tool_name", "policy_target", "request_kind"],
        },
        {
            "family": "policy",
            "description": "Policy bridge, shadow, readiness, and enforce lifecycle evidence",
            "representative_kinds": ["broker.exec_request", "broker.exec_decision", "apparmor.audit"],
            "primary_sources": ["broker", "kernel", "audit"],
            "typical_object_keys": ["policy_target", "workspace_root", "status"],
        },
        {
            "family": "recovery",
            "description": "Bypass, override, remediation, and emergency recovery actions",
            "representative_kinds": ["broker.exec_decision", "session.logout"],
            "primary_sources": ["broker", "journald", "manual"],
            "typical_object_keys": ["status", "recovery_mode", "policy_target"],
        },
        {
            "family": "service",
            "description": "Service and unit-state lifecycle events",
            "representative_kinds": ["systemd.unit_state", "dbus.message"],
            "primary_sources": ["journald", "dbus"],
            "typical_object_keys": ["unit", "message_class", "session_id"],
        },
        {
            "family": "session",
            "description": "Boot, setup, session ownership, and managed-entry evidence",
            "representative_kinds": ["session.login", "session.logout", "systemd.unit_state"],
            "primary_sources": ["journald", "broker", "runtime"],
            "typical_object_keys": ["session_id", "boot_id", "next_managed_entry"],
        },
    ]
    return {
        "schema_version": UNIFIED_EVENT_SCHEMA_VERSION,
        "base_required_fields": list(OS_EVENT_REQUIRED_FIELDS),
        "common_fields": common_fields,
        "causal_chain": causal_chain,
        "provenance": provenance,
        "event_families": families,
        "operator_views": {
            "events": "recent normalized events",
            "policy_correlation": "userspace versus OS evidence comparison",
            "replay": "narrative reconstruction for boot/setup/ai/approval/recovery",
            "evidence": "operator triage bundle over runtime, broker, policy, and session signals",
        },
    }

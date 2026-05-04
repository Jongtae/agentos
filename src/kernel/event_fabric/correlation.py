from __future__ import annotations

CORRELATION_KEYS = (
    "session_id",
    "run_id",
    "request_id",
    "approval_id",
    "trace_id",
    "boot_id",
    "parent_event_id",
)


def build_correlation_context(**values: object) -> dict:
    context: dict[str, object] = {}
    for key in CORRELATION_KEYS:
        value = values.get(key)
        if value in (None, ""):
            continue
        context[key] = value
    for key, value in values.items():
        if key in CORRELATION_KEYS or value in (None, ""):
            continue
        context[key] = value
    return context


def normalize_correlation_context(context: dict | None = None) -> dict:
    if not context:
        return {}
    normalized: dict[str, object] = {}
    for key in CORRELATION_KEYS:
        value = context.get(key)
        if value in (None, ""):
            continue
        normalized[key] = value
    for key, value in context.items():
        if key in normalized or value in (None, ""):
            continue
        normalized[str(key)] = value
    return normalized


def correlation_contract() -> dict:
    return {
        "stable_keys": list(CORRELATION_KEYS),
        "required_keys": [],
        "linkage_priority": [
            "session_id",
            "request_id",
            "run_id",
            "approval_id",
            "trace_id",
            "boot_id",
        ],
        "session_join_keys": [
            "session_id",
            "boot_id",
        ],
        "notes": [
            "runtime and broker paths should emit the same stable correlation keys when available",
            "collectors may omit correlation keys when upstream evidence is unavailable",
            "unknown keys are allowed but stable keys should be preferred for joins",
            "boot/setup/session ownership views should prefer session_id and boot_id for timeline joins",
        ],
    }

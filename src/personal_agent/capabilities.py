"""Reviewed capability lifecycle; never installs or executes arbitrary code."""

import math
import time


CATALOGUE = (
    {"id": "builtin-mcp-read", "kind": "mcp", "version": "1", "tools": ["read_only"], "scopes": ["read"]},
    {"id": "google-drive-read", "kind": "mcp", "version": "1", "tools": ["search", "read_selected"], "scopes": ["read"]},
    {"id": "compatibility-a2a-peer", "kind": "a2a", "version": "1", "tools": ["delegate"], "scopes": ["delegate"]},
    {"id": "google-calendar-create", "kind": "mcp", "version": "1", "tools": ["draft_event"], "scopes": ["calendar.events"]},
    {"id": "isolated-runtime-placeholder", "kind": "runtime", "version": "1", "tools": [], "scopes": []},
)
STATES = {
    "available",
    "connected-disabled",
    "enabled",
    "paused",
    "auth-required",
    "error",
    "disconnected",
}
_ACTIVE_GRANT_STATES = {"enabled", "paused"}
_MISSING_CAPABILITY_STATE = object()
_INVALID_CAPABILITY_STATE = "저장된 capability 상태를 확인하세요."


class CapabilityRegistry:
    def __init__(self, store):
        self.store = store
        self._catalogue = {item["id"]: item for item in CATALOGUE}

    @staticmethod
    def _reject():
        raise ValueError(_INVALID_CAPABILITY_STATE)

    @classmethod
    def _timestamp(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            cls._reject()
        return float(value)

    @classmethod
    def _scopes(cls, value):
        if (
            not isinstance(value, list)
            or any(not isinstance(scope, str) for scope in value)
            or len(value) != len(set(value))
        ):
            cls._reject()
        return value

    @classmethod
    def _validate_event(cls, item, event):
        if not isinstance(event, dict):
            cls._reject()
        state = event.get("state")
        expected_fields = (
            {"state", "changed_at", "approved_scopes"}
            if state == "enabled"
            else {"state", "changed_at"}
        )
        if not isinstance(state, str) or state not in STATES or set(event) != expected_fields:
            cls._reject()
        cls._timestamp(event["changed_at"])
        if state == "enabled" and cls._scopes(event["approved_scopes"]) != sorted(item["scopes"]):
            cls._reject()

    @classmethod
    def _validate_row(cls, item, row):
        if not isinstance(row, dict) or set(row) != {"state", "changed_at", "grant", "audit"}:
            cls._reject()
        state = row["state"]
        if not isinstance(state, str) or state not in STATES:
            cls._reject()
        changed_at = cls._timestamp(row["changed_at"])
        grant = cls._scopes(row["grant"])
        declared_grant = sorted(item["scopes"])
        if state == "enabled":
            allowed_grants = [declared_grant]
        elif state == "paused":
            allowed_grants = [[], declared_grant]
        else:
            allowed_grants = [[]]
        if grant not in allowed_grants:
            cls._reject()
        audit = row["audit"]
        if not isinstance(audit, list) or not 1 <= len(audit) <= 50:
            cls._reject()
        for event in audit:
            cls._validate_event(item, event)
        if audit[-1]["state"] != state or cls._timestamp(audit[-1]["changed_at"]) != changed_at:
            cls._reject()
        return row

    def _saved(self):
        saved = self.store.config("capability_registry", _MISSING_CAPABILITY_STATE)
        if saved is _MISSING_CAPABILITY_STATE:
            return {}
        if not isinstance(saved, dict) or any(key not in self._catalogue for key in saved):
            self._reject()
        for capability_id, row in saved.items():
            self._validate_row(self._catalogue[capability_id], row)
        return saved

    def list(self):
        saved = self._saved()
        return [
            {
                **item,
                "tools": list(item["tools"]),
                "scopes": list(item["scopes"]),
                "state": saved.get(item["id"], {}).get("state", "available"),
                "grant": list(saved.get(item["id"], {}).get("grant", [])),
            }
            for item in CATALOGUE
        ]

    def transition(self, capability_id, target, approved_scopes=()):
        item = self._catalogue.get(capability_id)
        if not item or target not in STATES:
            raise ValueError("검토된 capability와 상태를 확인하세요.")
        if target == "enabled" and set(item["scopes"]) != set(approved_scopes):
            raise ValueError("선언된 scope의 명시 승인이 필요합니다.")
        saved = self._saved()
        prior = saved.get(capability_id, {})
        changed_at = time.time()
        event = {"state": target, "changed_at": changed_at}
        if target == "enabled":
            event["approved_scopes"] = sorted(approved_scopes)
        grant = sorted(item["scopes"]) if target == "enabled" else list(prior.get("grant", []))
        if target not in _ACTIVE_GRANT_STATES:
            grant = []
        candidate = {
            "state": target,
            "changed_at": changed_at,
            "grant": grant,
            "audit": [*prior.get("audit", []), event][-50:],
        }
        self._validate_row(item, candidate)
        saved[capability_id] = candidate
        self.store.put("capability_registry", saved)
        return next(entry for entry in self.list() if entry["id"] == capability_id)

    def require_enabled(self, capability_id, scope):
        """The sole lifecycle gate used before a reviewed capability is invoked."""
        item = next((entry for entry in self.list() if entry["id"] == capability_id), None)
        if not item or scope not in item["scopes"]:
            raise ValueError("검토된 capability와 scope를 확인하세요.")
        if item["state"] != "enabled" or scope not in item.get("grant", []):
            raise ValueError("이 capability는 현재 사용할 수 없습니다. 연결 상태와 승인을 확인하세요.")
        return item

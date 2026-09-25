"""Historical reviewed-capability lifecycle records; never installs or executes code.

Retired as a live control plane by PRESENCE-SETTINGS-01 #506.  No production
execution path consults this registry: Google connection and use state is owned
by ``ConnectorRegistry`` and the concrete connector/OAuth paths, local files by
folder Grants, and isolated execution by ``TaskCapabilityRegistry``.  Settings,
``/api/settings`` and the removed ``/api/capabilities`` route no longer read or
mutate it.  The class is kept so stored ``capability_registry`` rows and
``retired_capability_evidence`` stay strictly validated historical evidence; do
not wire it back in as an authority gate without a successor contract.
"""

import math
import threading
import time


CATALOGUE = (
    {"id": "builtin-mcp-read", "kind": "mcp", "version": "1", "tools": ["read_only"], "scopes": ["read"]},
    {"id": "google-drive-read", "kind": "mcp", "version": "1", "tools": ["search", "read_selected"], "scopes": ["read"]},
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
_RETIRED_CAPABILITIES = {
    "compatibility-a2a-peer": {
        "id": "compatibility-a2a-peer",
        "kind": "a2a",
        "version": "1",
        "tools": ["delegate"],
        "scopes": ["delegate"],
    },
}
_RETIRED_CAPABILITY_IDS = frozenset(_RETIRED_CAPABILITIES)
_RETIRED_EVIDENCE_KEY = "retired_capability_evidence"
_MISSING_CAPABILITY_STATE = object()
_INVALID_CAPABILITY_STATE = "저장된 capability 상태를 확인하세요."
_CAPABILITY_STATE_LOCK = threading.RLock()


class CapabilityRegistry:
    def __init__(self, store):
        self.store = store
        self._catalogue = {item["id"]: item for item in CATALOGUE}
        # QuickStore has no compare-and-swap config primitive.  All registry
        # instances therefore share this in-process lock so a one-time legacy
        # migration cannot overwrite a concurrent lifecycle transition.
        self._lock = _CAPABILITY_STATE_LOCK

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
    def _validated_row_parts(cls, item, row):
        if not isinstance(row, dict) or set(row) != {"state", "changed_at", "grant", "audit"}:
            cls._reject()
        state = row["state"]
        if not isinstance(state, str) or state not in STATES:
            cls._reject()
        changed_at = cls._timestamp(row["changed_at"])
        grant = cls._scopes(row["grant"])
        audit = row["audit"]
        if not isinstance(audit, list) or not 1 <= len(audit) <= 50:
            cls._reject()
        for event in audit:
            cls._validate_event(item, event)
        if audit[-1]["state"] != state or cls._timestamp(audit[-1]["changed_at"]) != changed_at:
            cls._reject()
        return state, grant, audit

    @classmethod
    def _validate_row(cls, item, row):
        state, grant, _ = cls._validated_row_parts(item, row)
        declared_grant = sorted(item["scopes"])
        if state == "enabled":
            allowed_grants = [declared_grant]
        elif state == "paused":
            allowed_grants = [[], declared_grant]
        else:
            allowed_grants = [[]]
        if grant not in allowed_grants:
            cls._reject()
        return row

    @classmethod
    def _migrate_legacy_inactive_grant(cls, item, row):
        """Normalize only inactive grants proved to come from the old lifecycle.

        Before this contract, leaving ``enabled`` retained its exact grant.  A
        structurally valid enabled audit event is the evidence that distinguishes
        that historical row from fabricated inactive authority.
        """
        state, grant, audit = cls._validated_row_parts(item, row)
        declared_grant = sorted(item["scopes"])
        if (
            state in _ACTIVE_GRANT_STATES
            or not grant
            or grant != declared_grant
            or not any(event["state"] == "enabled" for event in audit)
        ):
            return None
        migrated = {**row, "grant": []}
        cls._validate_row(item, migrated)
        return migrated

    def _saved(self):
        with self._lock:
            saved = self.store.config("capability_registry", _MISSING_CAPABILITY_STATE)
            if saved is _MISSING_CAPABILITY_STATE:
                return {}
            if not isinstance(saved, dict):
                self._reject()
            unknown = [key for key in saved if key not in self._catalogue and key not in _RETIRED_CAPABILITY_IDS]
            if unknown:
                self._reject()
            retired = self.store.config(_RETIRED_EVIDENCE_KEY, {})
            if not isinstance(retired, dict):
                self._reject()
            retired = dict(retired)
            migrated = {key: value for key, value in saved.items() if key not in _RETIRED_CAPABILITY_IDS}
            changed = len(migrated) != len(saved)
            for capability_id in _RETIRED_CAPABILITY_IDS & saved.keys():
                item = _RETIRED_CAPABILITIES[capability_id]
                row = saved[capability_id]
                legacy = self._migrate_legacy_inactive_grant(item, row)
                validated = legacy if legacy is not None else self._validate_row(item, row)
                if capability_id not in retired:
                    retired[capability_id] = {
                        "id": capability_id,
                        "last_state": validated["state"],
                        "changed_at": validated["changed_at"],
                        "audit": [dict(event) for event in validated["audit"]],
                    }
                    self.store.put(_RETIRED_EVIDENCE_KEY, retired)
            for capability_id, row in list(migrated.items()):
                item = self._catalogue[capability_id]
                legacy = self._migrate_legacy_inactive_grant(item, row)
                if legacy is not None and legacy != row:
                    migrated[capability_id] = legacy
                    changed = True
                else:
                    self._validate_row(item, row)
            if changed:
                self.store.put("capability_registry", migrated)
            return migrated

    def list(self):
        with self._lock:
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
        with self._lock:
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
        """Historical lifecycle check; not consulted by any current execution path."""
        with self._lock:
            item = next((entry for entry in self.list() if entry["id"] == capability_id), None)
            if not item or scope not in item["scopes"]:
                raise ValueError("검토된 capability와 scope를 확인하세요.")
            if item["state"] != "enabled" or scope not in item.get("grant", []):
                raise ValueError("이 capability는 현재 사용할 수 없습니다. 연결 상태와 승인을 확인하세요.")
            return item

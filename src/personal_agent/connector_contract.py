"""Owner-bound connector and pending-Work contracts for PA1.

This module deliberately contains no provider client, OAuth implementation, or
network transport.  It stores only redacted lifecycle metadata in the supplied
owner store.  Credentials and the original private Work payload never belong in
this contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import base64
import hashlib
import re
import secrets
import threading
import time
from typing import Callable, Iterable, Protocol


CONNECTOR_STATE_KEY = "connector_contract_state"
PENDING_WORK_KEY = "connector_pending_work"
_IDENTIFIER = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,95})\Z")
_WORK_REFERENCE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._:-]{0,159})\Z")
_PENDING_WORK_LOCK = threading.RLock()


class OwnerStore(Protocol):
    """The existing owner store surface used by the connector contracts."""

    def config(self, key: str, default=None): ...

    def put(self, key: str, value) -> None: ...


class ConnectorContractError(ValueError):
    """Fail-closed error whose text does not disclose private connector data."""

    def __init__(self, reason: str = "rejected"):
        super().__init__("connector contract rejected")
        self.reason = reason


class ConnectorState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    REAUTH_REQUIRED = "reauth_required"
    BLOCKED = "blocked"


class ConnectorResultKind(str, Enum):
    CONNECTION_REQUIRED = "connection_required"
    REAUTH_REQUIRED = "reauth_required"
    BLOCKED = "blocked"


class HealthState(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    UNAVAILABLE = "unavailable"


class RecoveryAction(str, Enum):
    CONNECT = "connect"
    REAUTHENTICATE = "reauthenticate"
    REVIEW_ACCESS = "review_access"


def _nonempty(value: object, field: str, *, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field} must be a non-empty bounded string")
    return value


def _scopes(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("scopes must be an iterable of scope strings")
    scopes = tuple(values)
    if any(
        not isinstance(scope, str)
        or not scope
        or scope != scope.strip()
        or len(scope) > 256
        or any(character.isspace() for character in scope)
        for scope in scopes
    ):
        raise ValueError("scopes must contain non-empty bounded strings")
    if len(set(scopes)) != len(scopes):
        raise ValueError("scopes must not contain duplicates")
    return tuple(sorted(scopes))


def _owner_key(owner_id: str) -> str:
    """Keep raw owner identifiers out of connector metadata."""
    return hashlib.sha256(_nonempty(owner_id, "owner_id").encode()).hexdigest()


@dataclass(frozen=True)
class ConnectorSpec:
    connector_id: str
    required_scopes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.connector_id, str) or not _IDENTIFIER.fullmatch(self.connector_id):
            raise ValueError("connector_id must be a stable lowercase identifier")
        object.__setattr__(self, "required_scopes", _scopes(self.required_scopes))


@dataclass(frozen=True)
class ConnectorHealth:
    state: HealthState
    checked_at: float | None
    recovery: RecoveryAction | None

    def __post_init__(self) -> None:
        if self.checked_at is not None and (
            isinstance(self.checked_at, bool) or not isinstance(self.checked_at, (int, float))
        ):
            raise ValueError("checked_at must be a timestamp or None")
        if self.state is HealthState.HEALTHY and self.recovery is not None:
            raise ValueError("healthy connector metadata cannot request recovery")


@dataclass(frozen=True)
class ConnectorStatus:
    connector_id: str
    state: ConnectorState
    required_scopes: tuple[str, ...]
    granted_scopes: tuple[str, ...]
    health: ConnectorHealth

    def as_dict(self) -> dict:
        return {
            "connector_id": self.connector_id,
            "state": self.state.value,
            "required_scopes": list(self.required_scopes),
            "granted_scopes": list(self.granted_scopes),
            "health": {
                "state": self.health.state.value,
                "checked_at": self.health.checked_at,
                "recovery": self.health.recovery.value if self.health.recovery else None,
            },
        }


@dataclass(frozen=True)
class ConnectorResult:
    """A redacted result safe for a conversation or management surface."""

    kind: ConnectorResultKind
    connector_id: str
    required_scopes: tuple[str, ...]
    recovery: RecoveryAction
    resume_token: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.connector_id, str) or not _IDENTIFIER.fullmatch(self.connector_id):
            raise ValueError("connector_id must be a stable lowercase identifier")
        object.__setattr__(self, "required_scopes", _scopes(self.required_scopes))
        if self.resume_token is not None and not PendingWorkRegistry.valid_token(self.resume_token):
            raise ValueError("resume_token must be an opaque 256-bit token")

    def as_dict(self) -> dict:
        value = {
            "result": self.kind.value,
            "connector_id": self.connector_id,
            "required_scopes": list(self.required_scopes),
            "recovery": self.recovery.value,
        }
        if self.resume_token is not None:
            value["resume_token"] = self.resume_token
        return value


@dataclass(frozen=True)
class PendingWorkReference:
    """Minimum data returned after an authorized one-time resume."""

    work_id: str
    connector_id: str
    required_scopes: tuple[str, ...]


@dataclass(frozen=True)
class ResumeHandle:
    token: str
    connector_id: str
    required_scopes: tuple[str, ...]
    expires_at: float


@dataclass(frozen=True)
class WorktreeDelegationRecord:
    """Redacted PA1 worktree ownership record; never an authority grant."""

    issue: int
    branch: str
    base_sha: str
    owned_files: tuple[str, ...]
    requested_profile: str
    tool_accepted_setting: str
    observed_execution_setting: str = "unknown"

    def __post_init__(self) -> None:
        if isinstance(self.issue, bool) or not isinstance(self.issue, int) or self.issue <= 0:
            raise ValueError("issue must be a positive integer")
        _nonempty(self.branch, "branch")
        if not isinstance(self.base_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", self.base_sha):
            raise ValueError("base_sha must be a full lowercase commit SHA")
        files = tuple(sorted(self.owned_files))
        if not files or len(files) != len(set(files)) or any(not isinstance(path, str) or not path for path in files):
            raise ValueError("owned_files must contain unique paths")
        object.__setattr__(self, "owned_files", files)
        if self.requested_profile not in {"economy", "standard", "critical"}:
            raise ValueError("requested_profile is not recognized")
        _nonempty(self.tool_accepted_setting, "tool_accepted_setting")
        _nonempty(self.observed_execution_setting, "observed_execution_setting")

    def as_dict(self) -> dict:
        return {
            "issue": self.issue,
            "branch": self.branch,
            "base_sha": self.base_sha,
            "owned_files": list(self.owned_files),
            "requested_profile": self.requested_profile,
            "tool_accepted_setting": self.tool_accepted_setting,
            "observed_execution_setting": self.observed_execution_setting,
        }


class ConnectorRegistry:
    """Deterministic definitions plus owner-bound state in the existing store."""

    def __init__(
        self,
        store: OwnerStore,
        connectors: Iterable[ConnectorSpec] = (),
        *,
        clock: Callable[[], float] = time.time,
    ):
        self.store = store
        self.clock = clock
        self._definitions: dict[str, ConnectorSpec] = {}
        self._lock = threading.RLock()
        for connector in connectors:
            self.register(connector)

    def register(self, connector: ConnectorSpec) -> ConnectorSpec:
        """Register a definition only; registration never creates a scope grant."""
        if not isinstance(connector, ConnectorSpec):
            raise TypeError("connector must be a ConnectorSpec")
        prior = self._definitions.get(connector.connector_id)
        if prior is not None and prior != connector:
            raise ConnectorContractError("conflicting_registration")
        self._definitions[connector.connector_id] = connector
        return connector

    def definitions(self) -> tuple[ConnectorSpec, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))

    def definition(self, connector_id: str) -> ConnectorSpec:
        connector = self._definitions.get(connector_id)
        if connector is None:
            raise ConnectorContractError("unknown_connector")
        return connector

    @staticmethod
    def _default_health(state: ConnectorState, checked_at: float | None) -> ConnectorHealth:
        if state is ConnectorState.CONNECTED:
            return ConnectorHealth(HealthState.HEALTHY, checked_at, None)
        if state is ConnectorState.REAUTH_REQUIRED:
            return ConnectorHealth(HealthState.UNAVAILABLE, checked_at, RecoveryAction.REAUTHENTICATE)
        if state is ConnectorState.BLOCKED:
            return ConnectorHealth(HealthState.UNAVAILABLE, checked_at, RecoveryAction.REVIEW_ACCESS)
        return ConnectorHealth(HealthState.UNKNOWN, checked_at, RecoveryAction.CONNECT)

    def _rows(self) -> dict:
        value = self.store.config(CONNECTOR_STATE_KEY, {})
        return value if isinstance(value, dict) else {}

    def status(self, owner_id: str, connector_id: str) -> ConnectorStatus:
        connector = self.definition(connector_id)
        owner_rows = self._rows().get(_owner_key(owner_id), {})
        if not isinstance(owner_rows, dict):
            raise ConnectorContractError("invalid_stored_state")
        row = owner_rows.get(connector_id, {})
        if not isinstance(row, dict):
            raise ConnectorContractError("invalid_stored_state")
        try:
            state = ConnectorState(row.get("state", ConnectorState.DISCONNECTED.value))
            granted = _scopes(row.get("granted_scopes", ()))
        except (TypeError, ValueError):
            raise ConnectorContractError("invalid_stored_state") from None
        if state is not ConnectorState.CONNECTED:
            granted = ()
        checked_at = row.get("checked_at")
        health = self._default_health(state, checked_at if isinstance(checked_at, (int, float)) else None)
        return ConnectorStatus(connector_id, state, connector.required_scopes, granted, health)

    def transition(
        self,
        owner_id: str,
        connector_id: str,
        state: ConnectorState,
        *,
        granted_scopes: Iterable[str] = (),
    ) -> ConnectorStatus:
        connector = self.definition(connector_id)
        if not isinstance(state, ConnectorState):
            raise ConnectorContractError("invalid_state")
        granted = _scopes(granted_scopes)
        if state is ConnectorState.CONNECTED:
            if granted != connector.required_scopes:
                raise ConnectorContractError("scope_mismatch")
        elif granted:
            raise ConnectorContractError("inactive_grant")
        with self._lock:
            rows = self._rows()
            owner = _owner_key(owner_id)
            owner_rows = rows.get(owner, {})
            if not isinstance(owner_rows, dict):
                raise ConnectorContractError("invalid_stored_state")
            owner_rows[connector_id] = {
                "state": state.value,
                "granted_scopes": list(granted) if state is ConnectorState.CONNECTED else [],
                "checked_at": self.clock(),
            }
            rows[owner] = owner_rows
            self.store.put(CONNECTOR_STATE_KEY, rows)
        return self.status(owner_id, connector_id)

    def require_connected(
        self,
        owner_id: str,
        connector_id: str,
        required_scopes: Iterable[str],
    ) -> ConnectorStatus:
        connector = self.definition(connector_id)
        requested = _scopes(required_scopes)
        if not requested or not set(requested).issubset(connector.required_scopes):
            raise ConnectorContractError("scope_mismatch")
        status = self.status(owner_id, connector_id)
        if status.state is not ConnectorState.CONNECTED:
            raise ConnectorContractError(status.state.value)
        if not set(requested).issubset(status.granted_scopes):
            raise ConnectorContractError("scope_mismatch")
        return status

    def required_result(self, owner_id: str, connector_id: str, *, resume_token: str | None = None) -> ConnectorResult:
        status = self.status(owner_id, connector_id)
        if status.state is ConnectorState.CONNECTED:
            raise ConnectorContractError("already_connected")
        kinds = {
            ConnectorState.DISCONNECTED: ConnectorResultKind.CONNECTION_REQUIRED,
            ConnectorState.REAUTH_REQUIRED: ConnectorResultKind.REAUTH_REQUIRED,
            ConnectorState.BLOCKED: ConnectorResultKind.BLOCKED,
        }
        return ConnectorResult(
            kinds[status.state],
            connector_id,
            status.required_scopes,
            status.health.recovery or RecoveryAction.REVIEW_ACCESS,
            resume_token,
        )


class PendingWorkRegistry:
    """Opaque, expiring, owner/connector/scope-bound exactly-once resumes."""

    def __init__(
        self,
        store: OwnerStore,
        connector_registry: ConnectorRegistry,
        *,
        clock: Callable[[], float] = time.time,
        token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
    ):
        self.store = store
        self.connector_registry = connector_registry
        self.clock = clock
        self.token_factory = token_factory
        # A process-wide lock preserves exactly-once semantics when the local
        # service constructs more than one registry over the same owner store.
        self._lock = _PENDING_WORK_LOCK

    @staticmethod
    def valid_token(token: object) -> bool:
        if not isinstance(token, str) or not token:
            return False
        try:
            padding = "=" * (-len(token) % 4)
            decoded = base64.b64decode(token + padding, altchars=b"-_", validate=True)
        except (TypeError, ValueError):
            return False
        return len(decoded) == 32

    @staticmethod
    def _token_key(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def _rows(self) -> dict:
        value = self.store.config(PENDING_WORK_KEY, {})
        return value if isinstance(value, dict) else {}

    def issue(
        self,
        owner_id: str,
        work_id: str,
        connector_id: str,
        required_scopes: Iterable[str],
        *,
        ttl_seconds: float = 15 * 60,
    ) -> ResumeHandle:
        connector = self.connector_registry.definition(connector_id)
        requested = _scopes(required_scopes)
        if not requested or not set(requested).issubset(connector.required_scopes):
            raise ConnectorContractError("scope_mismatch")
        if not isinstance(work_id, str) or not _WORK_REFERENCE.fullmatch(work_id):
            raise ValueError("work_id must be an opaque Work reference")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)) or not 0 < ttl_seconds <= 3600:
            raise ValueError("ttl_seconds must be between zero and one hour")
        owner = _owner_key(owner_id)
        with self._lock:
            rows = self._rows()
            for _ in range(8):
                token = self.token_factory()
                if self.valid_token(token) and self._token_key(token) not in rows:
                    break
            else:
                raise ConnectorContractError("token_generation_failed")
            expires_at = self.clock() + float(ttl_seconds)
            rows[self._token_key(token)] = {
                "owner": owner,
                "work_id": work_id,
                "connector_id": connector_id,
                "required_scopes": list(requested),
                "expires_at": expires_at,
                "used": False,
            }
            self.store.put(PENDING_WORK_KEY, rows)
        return ResumeHandle(token, connector_id, requested, expires_at)

    def consume(
        self,
        token: object,
        owner_id: str,
        connector_id: str,
        granted_scopes: Iterable[str],
    ) -> PendingWorkReference:
        """Consume before returning Work, including on substitution attempts."""
        if not self.valid_token(token):
            raise ConnectorContractError("invalid_resume")
        owner = _owner_key(owner_id)
        with self._lock:
            rows = self._rows()
            key = self._token_key(token)
            row = rows.get(key)
            if not isinstance(row, dict):
                raise ConnectorContractError("invalid_resume")
            if row.get("used"):
                raise ConnectorContractError("replayed_resume")
            row["used"] = True
            rows[key] = row
            self.store.put(PENDING_WORK_KEY, rows)
            expires_at = row.get("expires_at")
            if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)):
                raise ConnectorContractError("invalid_resume")
            if self.clock() >= expires_at:
                raise ConnectorContractError("expired_resume")
            if row.get("owner") != owner or row.get("connector_id") != connector_id:
                raise ConnectorContractError("invalid_resume")
            self.connector_registry.require_connected(owner_id, connector_id, granted_scopes)
            expected = _scopes(row.get("required_scopes", ()))
            actual = _scopes(granted_scopes)
            if actual != expected:
                raise ConnectorContractError("scope_mismatch")
            work_id = row.get("work_id")
            if not isinstance(work_id, str) or not work_id:
                raise ConnectorContractError("invalid_resume")
            return PendingWorkReference(work_id, connector_id, expected)

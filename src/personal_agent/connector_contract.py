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
import math
import re
import secrets
import threading
import time
from typing import Callable, Iterable, Protocol
import uuid


CONNECTOR_STATE_KEY = "connector_contract_state"
PENDING_WORK_KEY = "connector_pending_work"
_IDENTIFIER = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,95})\Z")
_CONNECTOR_STATE_LOCK = threading.RLock()
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


class ResumeState(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


_ALLOWED_HEALTH_BY_CONNECTOR_STATE = {
    ConnectorState.DISCONNECTED: frozenset({HealthState.UNKNOWN}),
    ConnectorState.CONNECTED: frozenset({HealthState.UNKNOWN, HealthState.HEALTHY, HealthState.UNAVAILABLE}),
    ConnectorState.REAUTH_REQUIRED: frozenset({HealthState.UNKNOWN}),
    ConnectorState.BLOCKED: frozenset({HealthState.UNKNOWN}),
}


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


def _work_reference(work_id: object) -> str:
    """Accept the canonical UUID form emitted by the authoritative Work store."""
    if not isinstance(work_id, str) or len(work_id) != 36:
        raise ValueError("work_id must be a canonical UUID4 Work reference")
    try:
        parsed = uuid.UUID(work_id)
    except (AttributeError, ValueError):
        raise ValueError("work_id must be a canonical UUID4 Work reference") from None
    if parsed.version != 4 or str(parsed) != work_id:
        raise ValueError("work_id must be a canonical UUID4 Work reference")
    return work_id


def _finite_timestamp(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{field} must be a finite numeric timestamp")
    return float(value)


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
        if not isinstance(self.state, HealthState):
            raise ValueError("health state must be typed")
        if self.recovery is not None and not isinstance(self.recovery, RecoveryAction):
            raise ValueError("health recovery must be typed")
        if self.checked_at is not None:
            _finite_timestamp(self.checked_at, "checked_at")
        if self.state is HealthState.UNKNOWN and (self.checked_at is not None or self.recovery is not None):
            raise ValueError("unknown health cannot claim an observation or recovery")
        if self.state is HealthState.HEALTHY and (self.checked_at is None or self.recovery is not None):
            raise ValueError("healthy status requires an observed timestamp and no recovery")
        if self.state is HealthState.UNAVAILABLE and (self.checked_at is None or self.recovery is None):
            raise ValueError("unavailable status requires an observed timestamp and recovery")


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
    """Minimum data returned to an authorized resumable handoff claimant."""

    work_id: str
    connector_id: str
    required_scopes: tuple[str, ...]


@dataclass(frozen=True)
class ResumeHandle:
    token: str
    connector_id: str
    required_scopes: tuple[str, ...]
    expires_at: float


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
        # QuickStore is single-process; share one process lock across registry
        # instances so read-modify-write lifecycle updates cannot resurrect a
        # stale grant. This does not claim multi-process CAS semantics.
        self._lock = _CONNECTOR_STATE_LOCK
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
    def _unknown_health() -> ConnectorHealth:
        return ConnectorHealth(HealthState.UNKNOWN, None, None)

    def _rows(self) -> dict:
        value = self.store.config(CONNECTOR_STATE_KEY, {})
        return value if isinstance(value, dict) else {}

    def status(self, owner_id: str, connector_id: str) -> ConnectorStatus:
        with self._lock:
            connector = self.definition(connector_id)
            owner_rows = self._rows().get(_owner_key(owner_id), {})
            if not isinstance(owner_rows, dict):
                raise ConnectorContractError("invalid_stored_state")
            row = owner_rows.get(connector_id, {})
            if not isinstance(row, dict):
                raise ConnectorContractError("invalid_stored_state")
            if row and set(row) != {"state", "granted_scopes", "changed_at", "health"}:
                raise ConnectorContractError("invalid_stored_state")
            try:
                state = ConnectorState(row.get("state", ConnectorState.DISCONNECTED.value))
                granted = _scopes(row.get("granted_scopes", ()))
                _finite_timestamp(row["changed_at"], "changed_at") if row else None
                health_row = row["health"] if row else None
                if health_row is None:
                    health = self._unknown_health()
                else:
                    if not isinstance(health_row, dict) or set(health_row) != {"state", "checked_at", "recovery"}:
                        raise ValueError("invalid health")
                    health_state = HealthState(health_row["state"])
                    health_checked_at = (
                        _finite_timestamp(health_row["checked_at"], "health.checked_at")
                        if health_row["checked_at"] is not None
                        else None
                    )
                    recovery = RecoveryAction(health_row["recovery"]) if health_row["recovery"] is not None else None
                    health = ConnectorHealth(health_state, health_checked_at, recovery)
            except (TypeError, ValueError):
                raise ConnectorContractError("invalid_stored_state") from None
            if state is ConnectorState.CONNECTED:
                if granted != connector.required_scopes:
                    raise ConnectorContractError("invalid_stored_state")
            elif granted:
                raise ConnectorContractError("invalid_stored_state")
            if health.state not in _ALLOWED_HEALTH_BY_CONNECTOR_STATE[state]:
                raise ConnectorContractError("invalid_stored_state")
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
        try:
            changed_at = _finite_timestamp(self.clock(), "changed_at")
        except ValueError:
            raise ConnectorContractError("invalid_clock") from None
        with self._lock:
            rows = self._rows()
            owner = _owner_key(owner_id)
            owner_rows = rows.get(owner, {})
            if not isinstance(owner_rows, dict):
                raise ConnectorContractError("invalid_stored_state")
            owner_rows[connector_id] = {
                "state": state.value,
                "granted_scopes": list(granted) if state is ConnectorState.CONNECTED else [],
                "changed_at": changed_at,
                "health": {"state": HealthState.UNKNOWN.value, "checked_at": None, "recovery": None},
            }
            rows[owner] = owner_rows
            self.store.put(CONNECTOR_STATE_KEY, rows)
        return self.status(owner_id, connector_id)

    def record_health(
        self,
        owner_id: str,
        connector_id: str,
        health_state: HealthState,
        *,
        recovery: RecoveryAction | None = None,
    ) -> ConnectorStatus:
        """Record an observed provider check without changing connection state."""
        if not isinstance(health_state, HealthState) or health_state not in {
            HealthState.HEALTHY,
            HealthState.UNAVAILABLE,
        }:
            raise ConnectorContractError("invalid_health")
        if health_state is HealthState.HEALTHY and recovery is not None:
            raise ConnectorContractError("invalid_health")
        if health_state is HealthState.UNAVAILABLE and not isinstance(recovery, RecoveryAction):
            raise ConnectorContractError("invalid_health")
        try:
            checked_at = _finite_timestamp(self.clock(), "health.checked_at")
        except ValueError:
            raise ConnectorContractError("invalid_clock") from None
        with self._lock:
            status = self.status(owner_id, connector_id)
            if status.state is not ConnectorState.CONNECTED:
                raise ConnectorContractError("not_connected")
            rows = self._rows()
            owner_rows = rows.get(_owner_key(owner_id))
            if not isinstance(owner_rows, dict) or not isinstance(owner_rows.get(connector_id), dict):
                raise ConnectorContractError("invalid_stored_state")
            owner_rows[connector_id]["health"] = {
                "state": health_state.value,
                "checked_at": checked_at,
                "recovery": recovery.value if recovery else None,
            }
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
        recovery = {
            ConnectorState.DISCONNECTED: RecoveryAction.CONNECT,
            ConnectorState.REAUTH_REQUIRED: RecoveryAction.REAUTHENTICATE,
            ConnectorState.BLOCKED: RecoveryAction.REVIEW_ACCESS,
        }
        return ConnectorResult(
            kinds[status.state],
            connector_id,
            status.required_scopes,
            recovery[status.state],
            resume_token,
        )


class PendingWorkRegistry:
    """Bounded, resumable claim/complete handoff for pending Work references.

    This contract does not schedule or execute Work.  A later integration layer
    must durably schedule with the same caller-supplied handoff ID before it
    calls ``complete``; no atomic exactly-once external execution is claimed.
    """

    _FIELDS = {
        "owner",
        "work_id",
        "connector_id",
        "required_scopes",
        "expires_at",
        "state",
        "claim_digest",
        "claimed_at",
        "completed_at",
        "terminal_at",
        "sequence",
    }
    _TERMINAL = {ResumeState.COMPLETED, ResumeState.SUPERSEDED, ResumeState.EXPIRED}

    def __init__(
        self,
        store: OwnerStore,
        connector_registry: ConnectorRegistry,
        *,
        clock: Callable[[], float] = time.time,
        token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
        max_records: int = 128,
        terminal_retention_seconds: float = 3600,
    ):
        if isinstance(max_records, bool) or not isinstance(max_records, int) or not 1 <= max_records <= 10_000:
            raise ValueError("max_records must be between one and 10,000")
        if (
            isinstance(terminal_retention_seconds, bool)
            or not isinstance(terminal_retention_seconds, (int, float))
            or not 0 <= terminal_retention_seconds <= 86_400
        ):
            raise ValueError("terminal_retention_seconds must be between zero and one day")
        self.store = store
        self.connector_registry = connector_registry
        self.clock = clock
        self.token_factory = token_factory
        self.max_records = max_records
        self.terminal_retention_seconds = float(terminal_retention_seconds)
        # A process-wide lock serializes local state transitions when the service
        # constructs multiple registries. Durable scheduling remains #393 work.
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

    @staticmethod
    def _claim_key(handoff_id: object) -> str:
        return hashlib.sha256(_work_reference(handoff_id).encode()).hexdigest()

    def _rows(self) -> dict:
        value = self.store.config(PENDING_WORK_KEY, {})
        return value if isinstance(value, dict) else {}

    def _validated_row(self, row: object) -> tuple[ResumeState, str, str, str, tuple[str, ...], float, int]:
        if not isinstance(row, dict) or set(row) != self._FIELDS:
            raise ConnectorContractError("invalid_resume")
        try:
            state = ResumeState(row["state"])
            owner = row["owner"]
            if not isinstance(owner, str) or not re.fullmatch(r"[0-9a-f]{64}", owner):
                raise ValueError("owner")
            work_id = _work_reference(row["work_id"])
            connector_id = row["connector_id"]
            if not isinstance(connector_id, str) or not _IDENTIFIER.fullmatch(connector_id):
                raise ValueError("connector")
            connector = self.connector_registry.definition(connector_id)
            scopes = _scopes(row["required_scopes"])
            if not scopes or not set(scopes).issubset(connector.required_scopes):
                raise ValueError("scopes")
            expires_at = _finite_timestamp(row["expires_at"], "expires_at")
            sequence = row["sequence"]
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
                raise ValueError("sequence")
            claim_digest = row["claim_digest"]
            if claim_digest is not None and (
                not isinstance(claim_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", claim_digest)
            ):
                raise ValueError("claim")
            timestamps = {}
            for field in ("claimed_at", "completed_at", "terminal_at"):
                timestamps[field] = (
                    _finite_timestamp(row[field], field) if row[field] is not None else None
                )
            if state is ResumeState.PENDING and any(
                row[field] is not None for field in ("claim_digest", "claimed_at", "completed_at", "terminal_at")
            ):
                raise ValueError("pending")
            if state is ResumeState.CLAIMED and (
                claim_digest is None
                or timestamps["claimed_at"] is None
                or timestamps["completed_at"] is not None
                or timestamps["terminal_at"] is not None
            ):
                raise ValueError("claimed")
            if state is ResumeState.COMPLETED and (
                claim_digest is None
                or timestamps["claimed_at"] is None
                or timestamps["completed_at"] is None
                or timestamps["terminal_at"] != timestamps["completed_at"]
            ):
                raise ValueError("completed")
            if state in {ResumeState.SUPERSEDED, ResumeState.EXPIRED} and (
                timestamps["terminal_at"] is None or timestamps["completed_at"] is not None
            ):
                raise ValueError("terminal")
            if (claim_digest is None) != (timestamps["claimed_at"] is None):
                raise ValueError("claim timestamp")
        except (ConnectorContractError, TypeError, ValueError):
            raise ConnectorContractError("invalid_resume") from None
        return state, owner, work_id, connector_id, scopes, expires_at, sequence

    def _prune(self, rows: dict, now: float, *, reserve: int = 0) -> None:
        sequences = []
        for row in rows.values():
            state, _owner, _work, _connector, _scopes_value, expires_at, sequence = self._validated_row(row)
            sequences.append(sequence)
            # Expiry closes only an unclaimed offer. Once Work has been returned
            # to a claimant, that claimant remains authoritative until complete;
            # silently expiring it could let a second handoff schedule the Work.
            if state is ResumeState.PENDING and now >= expires_at:
                row["state"] = ResumeState.EXPIRED.value
                row["completed_at"] = None
                row["terminal_at"] = now
        if len(sequences) != len(set(sequences)):
            raise ConnectorContractError("invalid_resume")
        removable = []
        for key, row in rows.items():
            state, _owner, _work, _connector, _scopes_value, _expires, sequence = self._validated_row(row)
            if state in self._TERMINAL:
                terminal_at = _finite_timestamp(row["terminal_at"], "terminal_at")
                if now - terminal_at >= self.terminal_retention_seconds:
                    removable.append((terminal_at, sequence, key))
        for _terminal_at, _sequence, key in sorted(removable):
            rows.pop(key, None)
        if len(rows) + reserve > self.max_records:
            terminal = sorted(
                (_finite_timestamp(row["terminal_at"], "terminal_at"), row["sequence"], key)
                for key, row in rows.items()
                if ResumeState(row["state"]) in self._TERMINAL
            )
            for _terminal_at, _sequence, key in terminal:
                if len(rows) + reserve <= self.max_records:
                    break
                rows.pop(key, None)
        if len(rows) + reserve > self.max_records:
            raise ConnectorContractError("pending_limit")

    @staticmethod
    def _terminal_reason(state: ResumeState) -> str:
        return {
            ResumeState.COMPLETED: "replayed_resume",
            ResumeState.SUPERSEDED: "superseded_resume",
            ResumeState.EXPIRED: "expired_resume",
        }[state]

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
        work_id = _work_reference(work_id)
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)) or not 0 < ttl_seconds <= 3600:
            raise ValueError("ttl_seconds must be between zero and one hour")
        owner = _owner_key(owner_id)
        with self._lock:
            rows = self._rows()
            try:
                now = _finite_timestamp(self.clock(), "current time")
                expires_at = _finite_timestamp(now + float(ttl_seconds), "expires_at")
            except ValueError:
                raise ConnectorContractError("invalid_clock") from None
            self._prune(rows, now)
            matches = []
            for row in rows.values():
                state, saved_owner, saved_work, saved_connector, saved_scopes, _expires, _sequence = self._validated_row(row)
                if (
                    saved_owner == owner
                    and saved_work == work_id
                    and saved_connector == connector_id
                    and saved_scopes == requested
                ):
                    matches.append((state, row))
            if any(state is ResumeState.CLAIMED for state, _row in matches):
                raise ConnectorContractError("work_already_claimed")
            if any(state is ResumeState.COMPLETED for state, _row in matches):
                # This bounded local tombstone prevents immediate duplicate
                # handoff. #393 remains authoritative after retention pruning.
                raise ConnectorContractError("work_already_completed")
            for state, row in matches:
                if state is ResumeState.PENDING:
                    row["state"] = ResumeState.SUPERSEDED.value
                    row["completed_at"] = None
                    row["terminal_at"] = now
            self._prune(rows, now, reserve=1)
            for _ in range(8):
                token = self.token_factory()
                if self.valid_token(token) and self._token_key(token) not in rows:
                    break
            else:
                raise ConnectorContractError("token_generation_failed")
            sequence = max((row["sequence"] for row in rows.values()), default=0) + 1
            rows[self._token_key(token)] = {
                "owner": owner,
                "work_id": work_id,
                "connector_id": connector_id,
                "required_scopes": list(requested),
                "expires_at": expires_at,
                "state": ResumeState.PENDING.value,
                "claim_digest": None,
                "claimed_at": None,
                "completed_at": None,
                "terminal_at": None,
                "sequence": sequence,
            }
            self.store.put(PENDING_WORK_KEY, rows)
        return ResumeHandle(token, connector_id, requested, expires_at)

    def claim(
        self,
        token: object,
        owner_id: str,
        connector_id: str,
        granted_scopes: Iterable[str],
        handoff_id: str,
    ) -> PendingWorkReference:
        """Claim a handoff; the same authorized claimant may recover a lost response."""
        if not self.valid_token(token):
            raise ConnectorContractError("invalid_resume")
        owner = _owner_key(owner_id)
        try:
            claim_digest = self._claim_key(handoff_id)
            actual = _scopes(granted_scopes)
            now = _finite_timestamp(self.clock(), "current time")
        except (TypeError, ValueError):
            raise ConnectorContractError("invalid_resume") from None
        with self._lock:
            rows = self._rows()
            self._prune(rows, now)
            key = self._token_key(token)
            row = rows.get(key)
            if row is None:
                raise ConnectorContractError("invalid_resume")
            self.store.put(PENDING_WORK_KEY, rows)
            state, saved_owner, work_id, saved_connector, expected, _expires, _sequence = self._validated_row(row)
            if state in self._TERMINAL:
                raise ConnectorContractError(self._terminal_reason(state))
            if state is ResumeState.CLAIMED and row["claim_digest"] != claim_digest:
                raise ConnectorContractError("resume_claimed")
            if saved_owner != owner or saved_connector != connector_id or actual != expected:
                row["state"] = ResumeState.SUPERSEDED.value
                row["completed_at"] = None
                row["terminal_at"] = now
                self.store.put(PENDING_WORK_KEY, rows)
                reason = "scope_mismatch" if actual != expected else "invalid_resume"
                raise ConnectorContractError(reason)
            try:
                self.connector_registry.require_connected(owner_id, connector_id, actual)
            except ConnectorContractError as exc:
                row["state"] = ResumeState.SUPERSEDED.value
                row["completed_at"] = None
                row["terminal_at"] = now
                self.store.put(PENDING_WORK_KEY, rows)
                raise exc
            if state is ResumeState.PENDING:
                row["state"] = ResumeState.CLAIMED.value
                row["claim_digest"] = claim_digest
                row["claimed_at"] = now
                self.store.put(PENDING_WORK_KEY, rows)
            return PendingWorkReference(work_id, connector_id, expected)

    def complete(
        self,
        token: object,
        owner_id: str,
        connector_id: str,
        handoff_id: str,
    ) -> PendingWorkReference:
        """Complete a claimed handoff after #393 durably schedules with its ID."""
        if not self.valid_token(token):
            raise ConnectorContractError("invalid_resume")
        owner = _owner_key(owner_id)
        try:
            claim_digest = self._claim_key(handoff_id)
            now = _finite_timestamp(self.clock(), "current time")
        except ValueError:
            raise ConnectorContractError("invalid_resume") from None
        with self._lock:
            rows = self._rows()
            self._prune(rows, now)
            key = self._token_key(token)
            row = rows.get(key)
            if row is None:
                raise ConnectorContractError("invalid_resume")
            self.store.put(PENDING_WORK_KEY, rows)
            state, saved_owner, work_id, saved_connector, expected, _expires, _sequence = self._validated_row(row)
            if state in self._TERMINAL:
                raise ConnectorContractError(self._terminal_reason(state))
            if state is ResumeState.PENDING:
                raise ConnectorContractError("unclaimed_resume")
            if (
                saved_owner != owner
                or saved_connector != connector_id
                or row["claim_digest"] != claim_digest
            ):
                raise ConnectorContractError("invalid_resume")
            row["state"] = ResumeState.COMPLETED.value
            row["completed_at"] = now
            row["terminal_at"] = now
            self.store.put(PENDING_WORK_KEY, rows)
            return PendingWorkReference(work_id, connector_id, expected)

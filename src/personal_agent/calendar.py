"""Owner-bound, bounded Calendar query and mutation policy.

Only an explicit primary-calendar query or one approved create/update/cancel
can reach the injected provider. Durable status is deliberately redacted;
exact event content is returned only by the owner-bound preview.
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import math
import re
import secrets
import threading
import time
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .connector_contract import ConnectorContractError, ConnectorRegistry, ConnectorSpec, ConnectorState
from .google_calendar import (
    CALENDAR_READ_SCOPE,
    CALENDAR_WRITE_SCOPE,
    GoogleCalendar,
    GoogleCalendarError,
)


CALENDAR_CONNECTOR_ID = "google-calendar"
CALENDAR_WRITE_CONNECTOR_ID = "google-calendar-write"
CALENDAR_STATE_KEY = "calendar_create"
CALENDAR_SPEC = ConnectorSpec(
    CALENDAR_CONNECTOR_ID,
    (CALENDAR_READ_SCOPE,),
)
CALENDAR_WRITE_SPEC = ConnectorSpec(
    CALENDAR_WRITE_CONNECTOR_ID,
    (CALENDAR_WRITE_SCOPE,),
)
_ACTIONS = frozenset({"create", "update", "cancel"})
_CONTENT_FIELDS = frozenset({"summary", "start", "end", "timezone", "location", "description"})
_MAX_WINDOW = timedelta(days=366)
_RFC3339_LOCAL = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?\Z"
)
_LOCK = threading.RLock()


class CalendarError(ValueError):
    """A redacted policy failure safe to pass through a conversation surface."""

    def __init__(self, reason: str = "rejected", *, effect: str = "none", recovery: str = "review-request"):
        super().__init__("Calendar request could not be completed.")
        self.reason = reason
        self.effect = effect
        self.recovery = recovery


def _owner_key(owner: object) -> str:
    if not isinstance(owner, str) or not owner or len(owner) > 256:
        raise CalendarError("invalid-owner")
    return hashlib.sha256(owner.encode()).hexdigest()


def _bounded_text(value: object, field: str, maximum: int, *, empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise CalendarError(f"invalid-{field}")
    return value


def _timestamp(value: object, field: str, *, require_offset: bool = False) -> datetime:
    text = _bounded_text(value, field, 64)
    if _RFC3339_LOCAL.fullmatch(text) is None:
        raise CalendarError(f"invalid-{field}")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise CalendarError(f"invalid-{field}") from None
    if require_offset and (parsed.tzinfo is None or parsed.utcoffset() is None):
        raise CalendarError(f"invalid-{field}")
    return parsed


def _timezone(value: object) -> str:
    name = _bounded_text(value, "timezone", 128)
    try:
        ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError):
        raise CalendarError("invalid-timezone") from None
    return name


def _event_id(value: object) -> str:
    return _bounded_text(value, "event-id", 1024)


def _etag(value: object) -> str:
    text = _bounded_text(value, "event-version", 1024)
    # One concrete RFC 9110 entity-tag only. Wildcards and comma-separated
    # lists would authorize mutation against a version the owner did not review.
    if re.fullmatch(r'"[\x21\x23-\x7e]*"', text) is None:
        raise CalendarError("invalid-event-version")
    return text


def _canonical(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _constant_text_equal(left: object, right: object) -> bool:
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _validate_event(payload: object, *, partial: bool = False) -> dict:
    if not isinstance(payload, dict) or not payload or not set(payload).issubset(_CONTENT_FIELDS):
        raise CalendarError("invalid-event")
    # Attendees, recurrence, conference data, and provider-specific fields are
    # excluded by the exact allowlist above.
    if not partial and not {"summary", "start", "end", "timezone"}.issubset(payload):
        raise CalendarError("invalid-event")
    temporal = {"start", "end", "timezone"} & set(payload)
    if temporal and temporal != {"start", "end", "timezone"}:
        raise CalendarError("invalid-event")
    result = {}
    for field, maximum in (("summary", 1000), ("location", 1000), ("description", 8192)):
        if field in payload:
            result[field] = _bounded_text(payload[field], field, maximum, empty=field != "summary")
    if temporal:
        start = _timestamp(payload["start"], "start")
        end = _timestamp(payload["end"], "end")
        try:
            invalid_window = start >= end
        except TypeError:
            invalid_window = True
        if invalid_window:
            raise CalendarError("invalid-window")
        result.update(
            start=payload["start"],
            end=payload["end"],
            timezone=_timezone(payload["timezone"]),
        )
    if not result:
        raise CalendarError("invalid-event")
    return result


class CalendarConnector:
    """Calendar authority, approval, idempotency, and recovery boundary."""

    def __init__(
        self,
        store,
        provider: GoogleCalendar,
        *,
        registry: ConnectorRegistry | None = None,
        authority=None,
        now=time.time,
        approval_ttl: float = 900,
        approval_factory=lambda: secrets.token_urlsafe(24),
    ):
        if registry is None and authority is None:
            raise ValueError("connector registry or explicit authority callback is required")
        if isinstance(approval_ttl, bool) or not isinstance(approval_ttl, (int, float)) or not 1 <= approval_ttl <= 3600:
            raise ValueError("approval_ttl must be between one second and one hour")
        self.store = store
        self.provider = provider
        self.registry = registry
        self.authority = authority
        self.now = now
        self.approval_ttl = float(approval_ttl)
        self.approval_factory = approval_factory
        if self.registry is not None:
            self.registry.register(CALENDAR_SPEC)
            self.registry.register(CALENDAR_WRITE_SPEC)

    def _rows(self) -> dict:
        rows = self.store.config(CALENDAR_STATE_KEY, {})
        if not isinstance(rows, dict):
            raise CalendarError("invalid-stored-state")
        return rows

    def _put(self, rows: dict) -> None:
        self.store.put(CALENDAR_STATE_KEY, rows)

    @staticmethod
    def _connector_for_scope(scope: str) -> str:
        if scope == CALENDAR_READ_SCOPE:
            return CALENDAR_CONNECTOR_ID
        if scope == CALENDAR_WRITE_SCOPE:
            return CALENDAR_WRITE_CONNECTOR_ID
        raise CalendarError("scope-denied", recovery="reconnect")

    def _authorize(self, owner: str, scope: str) -> tuple[tuple[str, str], ...] | None:
        _owner_key(owner)
        try:
            if self.registry is not None:
                connector_id = self._connector_for_scope(scope)
                self.registry.require_connected(owner, connector_id, (scope,))
                # Both records describe authority backed by this connector's
                # one injected Google credential. Capture each currently
                # connected revision so a provider 401 can revoke the shared
                # credential lifecycle without revoking a later reconnect.
                snapshot = []
                for candidate in (CALENDAR_CONNECTOR_ID, CALENDAR_WRITE_CONNECTOR_ID):
                    status = self.registry.status(owner, candidate)
                    if status.state is ConnectorState.CONNECTED:
                        snapshot.append((candidate, status.connection_revision))
                return tuple(snapshot)
            elif not self.authority(owner, scope):
                raise CalendarError("scope-denied", recovery="reconnect")
        except ConnectorContractError as error:
            reason = "scope-expired" if error.reason in {"reauth_required", "scope_mismatch"} else "scope-denied"
            raise CalendarError(reason, recovery="reconnect") from None
        return None

    def _mark_scope_expired(
        self,
        owner: str,
        authority_snapshot: tuple[tuple[str, str], ...] | None,
    ) -> None:
        if self.registry is None or authority_snapshot is None:
            return
        with self.registry._authority_guard():
            for connector_id, expected_revision in authority_snapshot:
                current = self.registry.status(owner, connector_id)
                if (
                    current.state is ConnectorState.CONNECTED
                    and current.connection_revision == expected_revision
                ):
                    self.registry.transition(owner, connector_id, ConnectorState.REAUTH_REQUIRED)

    @staticmethod
    def _provider_error(error: GoogleCalendarError) -> CalendarError:
        recovery = "inspect-calendar-before-retry" if error.effect == "unknown" else (
            "reconnect" if error.reason == "scope-expired" else "review-request"
        )
        return CalendarError(error.reason, effect=error.effect, recovery=recovery)

    def query(self, owner: str, start: str, end: str, timezone: str, *, max_results: int = 50) -> dict:
        # Google events.list requires RFC3339 bounds with an explicit offset.
        start_at = _timestamp(start, "start", require_offset=True)
        end_at = _timestamp(end, "end", require_offset=True)
        try:
            invalid_window = start_at >= end_at or end_at - start_at > _MAX_WINDOW
        except TypeError:
            invalid_window = True
        if invalid_window:
            raise CalendarError("invalid-window")
        timezone = _timezone(timezone)
        if isinstance(max_results, bool) or not isinstance(max_results, int) or not 1 <= max_results <= 100:
            raise CalendarError("invalid-limit")
        authority_guard = self.registry._authority_guard() if self.registry is not None else nullcontext()
        with authority_guard:
            authority_snapshot = self._authorize(owner, CALENDAR_READ_SCOPE)
            try:
                events = self.provider.query(start, end, timezone, max_results)
            except GoogleCalendarError as error:
                if error.reason == "scope-expired":
                    self._mark_scope_expired(owner, authority_snapshot)
                raise self._provider_error(error) from None
        return {
            "events": events,
            "window": {"start": start, "end": end, "timezone": timezone},
            "evidence": {
                "operation": "calendar-query",
                "calendar": "primary",
                "window_hash": _canonical({"start": start, "end": end, "timezone": timezone}),
                "result_count": len(events),
                "effect": "none",
            },
        }

    def draft_create(self, payload: dict, owner: str) -> dict:
        return self._draft("create", owner, _validate_event(payload))

    def draft_update(self, event_id: str, event_version: str, changes: dict, owner: str) -> dict:
        return self._draft("update", owner, _validate_event(changes, partial=True), _event_id(event_id), _etag(event_version))

    def draft_cancel(self, event_id: str, event_version: str, owner: str) -> dict:
        return self._draft("cancel", owner, {}, _event_id(event_id), _etag(event_version))

    def _draft(self, action: str, owner: str, payload: dict, event_id: str = "", event_version: str = "") -> dict:
        if action not in _ACTIONS:
            raise CalendarError("invalid-action")
        owner_key = _owner_key(owner)
        bound = {"action": action, "payload": payload, "event_id": event_id, "event_version": event_version}
        ident = str(uuid.uuid4())
        with _LOCK:
            rows = self._rows()
            rows[ident] = {
                "id": ident,
                "action": action,
                "payload": payload,
                "event_id": event_id,
                "event_version": event_version,
                "owner": owner_key,
                "hash": _canonical(bound),
                "state": "awaiting-approval",
                "effect": "none",
            }
            self._put(rows)
        return self.preview(ident, owner)

    def _owned(self, rows: dict, ident: object, owner: str) -> dict:
        if not isinstance(ident, str):
            raise CalendarError("draft-not-found")
        row = rows.get(ident)
        if not isinstance(row, dict):
            raise CalendarError("draft-not-found")
        owner_key = _owner_key(owner)
        stored_owner = row.get("owner")
        if "payload" not in row:
            portable_fields = {
                "id", "state", "hash", "error_class", "result", "action", "recovery", "portable_evidence"
            }
            portable_state = row.get("state")
            if (
                not set(row).issubset(portable_fields)
                or portable_state not in {
                    "awaiting-approval", "approved", "created", "completed", "failed",
                    "expired", "executing", "outcome-unknown",
                }
            ):
                raise CalendarError("invalid-stored-state")
            portable_action = row.get("action")
            if portable_action not in _ACTIONS:
                portable_action = "unknown"
            if row.get("recovery", "") not in {
                "", "inspect-calendar-before-retry", "reconnect", "request-new-approval",
                "request-new-draft", "reconnect-and-request-new-draft", "review-request",
                "review-request-and-request-new-draft",
            }:
                raise CalendarError("invalid-stored-state")
            quarantined_approval = portable_state in {"awaiting-approval", "approved"}
            portable_unknown_effect = (
                portable_state in {"executing", "outcome-unknown"}
                or (
                    portable_state == "failed"
                    and row.get("error_class") in {"transport-error", "malformed-response", "provider-timeout"}
                )
            )
            row.update(
                action=portable_action,
                payload={},
                event_id="",
                event_version="",
                owner=owner_key,
                state=(
                    "expired"
                    if quarantined_approval
                    else "outcome-unknown" if portable_unknown_effect else portable_state
                ),
                effect=(
                    "unknown"
                    if portable_unknown_effect
                    else "observed" if isinstance(row.get("result"), dict) else "none"
                ),
                portable_evidence=True,
            )
            if portable_unknown_effect:
                row["recovery"] = "inspect-calendar-before-retry"
            elif quarantined_approval:
                row.update(
                    error_class="restored-approval-quarantined",
                    recovery="request-new-draft",
                )
            elif portable_state == "expired" and row.get("recovery") == "request-new-approval":
                row["recovery"] = "request-new-draft"
            elif (
                portable_state == "failed"
                and row.get("error_class") in {"scope-denied", "scope-expired"}
                and row.get("recovery") in {None, "", "reconnect"}
            ):
                row["recovery"] = "reconnect-and-request-new-draft"
            elif portable_state == "failed" and row.get("recovery") == "review-request":
                row["recovery"] = "review-request-and-request-new-draft"
            rows[ident] = row
            self._put(rows)
            return row
        if "action" not in row:
            # The pre-PA1 CalendarCreate schema stored a raw owner (or None)
            # and did not include action/effect fields. Normalize one legacy
            # row atomically when its historical owner next accesses it.
            if stored_owner is not None and stored_owner != owner:
                raise CalendarError("draft-not-found")
            payload = row.get("payload")
            if not isinstance(payload, dict):
                raise CalendarError("invalid-stored-state")
            legacy_payload_valid = True
            try:
                _validate_event(payload)
            except CalendarError:
                legacy_payload_valid = False
            legacy_unknown_effect = (
                row.get("state") == "failed"
                and row.get("error_class") in {"transport-error", "malformed-response", "provider-timeout"}
            )
            legacy_state = row.get("state")
            legacy_hash = (
                hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
                if legacy_payload_valid
                else ""
            )
            legacy_approval_matches = (
                legacy_state != "approved"
                or (
                    legacy_payload_valid
                    and _constant_text_equal(row.get("hash"), legacy_hash)
                    and _constant_text_equal(row.get("approval_hash"), legacy_hash)
                )
            )
            bound = {"action": "create", "payload": payload, "event_id": "", "event_version": ""}
            digest = _canonical(bound) if legacy_payload_valid else ""
            row.update(
                action="create",
                event_id="",
                event_version="",
                owner=owner_key,
                hash=digest,
                state="outcome-unknown" if legacy_unknown_effect else row.get("state"),
                effect=("observed" if row.get("state") == "created" else
                        "unknown" if legacy_unknown_effect else "none"),
            )
            if legacy_unknown_effect:
                row["recovery"] = "inspect-calendar-before-retry"
            if not legacy_payload_valid and legacy_state in {"awaiting-approval", "approved"}:
                row.update(
                    state="expired",
                    error_class="legacy-payload-invalid",
                    recovery="request-new-draft",
                    effect="none",
                )
                row.pop("approval", None)
                row.pop("approval_hash", None)
            elif not legacy_approval_matches:
                row.update(
                    state="expired",
                    error_class="legacy-approval-mismatch",
                    recovery="request-new-draft",
                    effect="none",
                )
                row.pop("approval", None)
                row.pop("approval_hash", None)
            elif row.get("state") in {"approved", "created"}:
                row["approval_hash"] = digest
            rows[ident] = row
            self._put(rows)
        elif not _constant_text_equal(stored_owner, owner_key):
            raise CalendarError("draft-not-found")
        if row.get("state") == "expired" and row.get("recovery") == "request-new-approval":
            row["recovery"] = "request-new-draft"
            rows[ident] = row
            self._put(rows)
        elif (
            row.get("state") == "failed"
            and row.get("error_class") in {"scope-denied", "scope-expired"}
            and row.get("recovery") in {None, "", "reconnect"}
        ):
            row["recovery"] = "reconnect-and-request-new-draft"
            rows[ident] = row
            self._put(rows)
        elif row.get("state") == "failed" and row.get("recovery") == "review-request":
            row["recovery"] = "review-request-and-request-new-draft"
            rows[ident] = row
            self._put(rows)
        return row

    def preview(self, ident: str, owner: str) -> dict:
        with _LOCK:
            row = self._owned(self._rows(), ident, owner)
            return {
                "id": ident,
                "action": row["action"],
                "calendar": "primary",
                "event_id": row.get("event_id", ""),
                "event_version": row.get("event_version", ""),
                "payload": dict(row.get("payload", {})),
                "payload_hash": row["hash"],
                "state": row["state"],
            }

    def approve(self, ident: str, owner: str) -> dict:
        with _LOCK:
            rows = self._rows()
            row = self._owned(rows, ident, owner)
            if row.get("state") != "awaiting-approval":
                raise CalendarError("not-awaiting-approval")
            now = self._now()
            approval = self.approval_factory()
            if not isinstance(approval, str) or len(approval) < 16:
                raise CalendarError("invalid-approval")
            row.update(
                state="approved",
                approval=approval,
                approval_hash=row["hash"],
                expires=now + self.approval_ttl,
            )
            rows[ident] = row
            self._put(rows)
        return {"approval_id": approval, "payload_hash": row["hash"], "action": row["action"]}

    def status(self, ident: str, owner: str) -> dict:
        with _LOCK:
            rows = self._rows()
            row = self._owned(rows, ident, owner)
            if row.get("state") == "approved" and self._now() >= row.get("expires", 0):
                row.update(
                    state="expired",
                    error_class="approval-expired",
                    effect="none",
                    recovery="request-new-draft",
                )
                rows[ident] = row
                self._put(rows)
            state = "outcome-unknown" if row.get("state") == "executing" else row.get("state")
            effect = "unknown" if row.get("state") == "executing" else row.get("effect", "none")
            result = row.get("result", {})
            safe_result = {}
            if isinstance(result, dict):
                if isinstance(result.get("id"), str):
                    safe_result["id"] = result["id"]
                for field in ("updated", "cancelled"):
                    if result.get(field) is True:
                        safe_result[field] = True
            return {
                "id": ident,
                "action": row.get("action", "create"),
                "state": state,
                "payload_hash": row.get("hash", ""),
                "event_ref_hash": hashlib.sha256(str(row.get("event_id", "")).encode()).hexdigest() if row.get("event_id") else "",
                "result": safe_result,
                "error_class": row.get("error_class", ""),
                "effect": effect,
                "recovery": row.get("recovery", ""),
            }

    def _now(self) -> float:
        try:
            value = float(self.now())
        except (TypeError, ValueError):
            raise CalendarError("invalid-clock") from None
        if not math.isfinite(value):
            raise CalendarError("invalid-clock")
        return value

    def execute(self, ident: str, approval: str, owner: str) -> dict:
        with _LOCK:
            rows = self._rows()
            row = self._owned(rows, ident, owner)
            if row.get("state") == "completed" and _constant_text_equal(row.get("approval"), approval):
                return dict(row["result"])
            if row.get("state") in {"executing", "outcome-unknown"}:
                raise CalendarError("unknown-external-outcome", effect="unknown", recovery="inspect-calendar-before-retry")
            if row.get("state") != "approved" or not _constant_text_equal(row.get("approval"), approval):
                raise CalendarError("exact-approval-required")
            if self._now() >= row.get("expires", 0):
                row.update(
                    state="expired",
                    error_class="approval-expired",
                    effect="none",
                    recovery="request-new-draft",
                )
                rows[ident] = row
                self._put(rows)
                raise CalendarError("approval-expired", recovery="request-new-draft")
            bound = {
                "action": row.get("action"),
                "payload": row.get("payload"),
                "event_id": row.get("event_id", ""),
                "event_version": row.get("event_version", ""),
            }
            if _canonical(bound) != row.get("hash") or row.get("approval_hash") != row.get("hash"):
                row.update(
                    state="failed",
                    error_class="payload-changed",
                    effect="none",
                    recovery="request-new-draft",
                )
                rows[ident] = row
                self._put(rows)
                raise CalendarError("payload-changed", recovery="request-new-draft")
            authority_guard = self.registry._authority_guard() if self.registry is not None else nullcontext()
            with authority_guard:
                try:
                    authority_snapshot = self._authorize(owner, CALENDAR_WRITE_SCOPE)
                except CalendarError as error:
                    recovery = (
                        "reconnect-and-request-new-draft"
                        if error.recovery == "reconnect"
                        else "request-new-draft"
                    )
                    row.update(state="failed", error_class=error.reason, effect="none", recovery=recovery)
                    rows[ident] = row
                    self._put(rows)
                    raise CalendarError(error.reason, effect=error.effect, recovery=recovery) from None
                observed_at = self._now()
                if observed_at >= row.get("expires", 0):
                    row.update(state="expired", error_class="approval-expired", effect="none",
                               recovery="request-new-draft")
                    rows[ident] = row
                    self._put(rows)
                    raise CalendarError("approval-expired", recovery="request-new-draft")
                # Persist the dispatch commitment while the same connector
                # authority revision is guarded. A later revocation applies
                # to later work and cannot race into this pre-dispatch gap.
                row.update(state="executing", effect="unknown", approval_used_at=observed_at)
                rows[ident] = row
                self._put(rows)

        try:
            action = row["action"]
            if action == "create":
                key = hashlib.sha256((approval + row["hash"]).encode()).hexdigest()
                result = self.provider.create(row["payload"], key)
                safe_result = {"id": result["id"], "summary": row["payload"]["summary"]}
            elif action == "update":
                result = self.provider.update(row["event_id"], row["event_version"], row["payload"])
                safe_result = {"id": result["id"], "updated": True}
            else:
                result = self.provider.cancel(row["event_id"], row["event_version"])
                safe_result = {"id": result["id"], "cancelled": True}
        except GoogleCalendarError as provider_error:
            if provider_error.reason == "scope-expired":
                self._mark_scope_expired(owner, authority_snapshot)
            error = self._provider_error(provider_error)
            if error.recovery == "reconnect":
                error = CalendarError(
                    error.reason,
                    effect=error.effect,
                    recovery="reconnect-and-request-new-draft",
                )
            elif error.effect == "none":
                error = CalendarError(
                    error.reason,
                    effect="none",
                    recovery="review-request-and-request-new-draft",
                )
            with _LOCK:
                rows = self._rows()
                current = self._owned(rows, ident, owner)
                current.update(
                    state="outcome-unknown" if error.effect == "unknown" else "failed",
                    error_class=error.reason,
                    effect=error.effect,
                    recovery=error.recovery,
                )
                rows[ident] = current
                self._put(rows)
            raise error from None

        with _LOCK:
            rows = self._rows()
            current = self._owned(rows, ident, owner)
            if current.get("state") != "executing":
                raise CalendarError("invalid-stored-state", effect="unknown", recovery="inspect-calendar-before-retry")
            current.update(state="completed", result=safe_result, effect="observed", recovery="")
            rows[ident] = current
            self._put(rows)
        return dict(safe_result)

    def create(self, ident: str, approval: str, owner: str) -> dict:
        row = self._owned(self._rows(), ident, owner)
        if row.get("action") != "create":
            raise CalendarError("action-mismatch")
        return self.execute(ident, approval, owner)

    def update(self, ident: str, approval: str, owner: str) -> dict:
        row = self._owned(self._rows(), ident, owner)
        if row.get("action") != "update":
            raise CalendarError("action-mismatch")
        return self.execute(ident, approval, owner)

    def cancel(self, ident: str, approval: str, owner: str) -> dict:
        row = self._owned(self._rows(), ident, owner)
        if row.get("action") != "cancel":
            raise CalendarError("action-mismatch")
        return self.execute(ident, approval, owner)


class _LegacyCreateProvider:
    """Keep the established three-argument create transport/API compatible."""

    def __init__(self, transport):
        self.transport = transport

    def create(self, payload: dict, idempotency_key: str) -> dict:
        try:
            response = self.transport(
                "/calendars/primary/events",
                payload,
                {"Idempotency-Key": idempotency_key},
            )
        except (TimeoutError, OSError):
            raise GoogleCalendarError("provider-timeout", "unknown") from None
        except Exception:
            raise GoogleCalendarError("transport-error", "unknown") from None
        if not isinstance(response, dict) or not isinstance(response.get("id"), str) or not response["id"]:
            raise GoogleCalendarError("malformed-response", "unknown")
        return response


class CalendarCreate(CalendarConnector):
    """Compatibility facade for the original create-only orchestrator API."""

    def __init__(self, store, transport, now=time.time, scope_granted=lambda: True):
        super().__init__(
            store,
            _LegacyCreateProvider(transport),
            authority=lambda _owner, _scope: bool(scope_granted()),
            now=now,
        )

    def draft(self, value: dict, owner: str | None = None) -> dict:
        if owner is None:
            raise CalendarError("invalid-owner")
        return self.draft_create(value, owner)

    def create(self, ident: str, approval: str, owner: str) -> dict:
        row = self._owned(self._rows(), ident, owner)
        if row.get("state") == "created" and _constant_text_equal(row.get("approval"), approval):
            return dict(row["result"])
        result = super().create(ident, approval, owner)
        with _LOCK:
            rows = self._rows()
            row = self._owned(rows, ident, owner)
            row["state"] = "created"
            rows[ident] = row
            self._put(rows)
        return result

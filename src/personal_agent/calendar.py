"""Owner-bound, bounded Calendar query and mutation policy.

Only an explicit primary-calendar query or one approved create/update/cancel
can reach the injected provider. Durable status is deliberately redacted;
exact event content is returned only by the owner-bound preview.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import hmac
import json
import math
import secrets
import threading
import time
import uuid

from .connector_contract import ConnectorContractError, ConnectorRegistry, ConnectorSpec
from .google_calendar import (
    CALENDAR_READ_SCOPE,
    CALENDAR_WRITE_SCOPE,
    GoogleCalendar,
    GoogleCalendarError,
)


CALENDAR_CONNECTOR_ID = "google-calendar"
CALENDAR_STATE_KEY = "calendar_create"
CALENDAR_SPEC = ConnectorSpec(
    CALENDAR_CONNECTOR_ID,
    (CALENDAR_READ_SCOPE, CALENDAR_WRITE_SCOPE),
)
_ACTIONS = frozenset({"create", "update", "cancel"})
_CONTENT_FIELDS = frozenset({"summary", "start", "end", "timezone", "location", "description"})
_MAX_WINDOW = timedelta(days=366)
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


def _timestamp(value: object, field: str) -> datetime:
    text = _bounded_text(value, field, 64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise CalendarError(f"invalid-{field}") from None
    return parsed


def _event_id(value: object) -> str:
    return _bounded_text(value, "event-id", 1024)


def _etag(value: object) -> str:
    return _bounded_text(value, "event-version", 1024)


def _canonical(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


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
            timezone=_bounded_text(payload["timezone"], "timezone", 128),
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

    def _rows(self) -> dict:
        rows = self.store.config(CALENDAR_STATE_KEY, {})
        if not isinstance(rows, dict):
            raise CalendarError("invalid-stored-state")
        return rows

    def _put(self, rows: dict) -> None:
        self.store.put(CALENDAR_STATE_KEY, rows)

    def _authorize(self, owner: str, scope: str) -> None:
        _owner_key(owner)
        try:
            if self.registry is not None:
                self.registry.require_connected(owner, CALENDAR_CONNECTOR_ID, (scope,))
            elif not self.authority(owner, scope):
                raise CalendarError("scope-denied", recovery="reconnect")
        except ConnectorContractError as error:
            reason = "scope-expired" if error.reason in {"reauth_required", "scope_mismatch"} else "scope-denied"
            raise CalendarError(reason, recovery="reconnect") from None

    @staticmethod
    def _provider_error(error: GoogleCalendarError) -> CalendarError:
        recovery = "inspect-calendar-before-retry" if error.effect == "unknown" else (
            "reconnect" if error.reason == "scope-expired" else "review-request"
        )
        return CalendarError(error.reason, effect=error.effect, recovery=recovery)

    def query(self, owner: str, start: str, end: str, timezone: str, *, max_results: int = 50) -> dict:
        start_at = _timestamp(start, "start")
        end_at = _timestamp(end, "end")
        try:
            invalid_window = start_at >= end_at or end_at - start_at > _MAX_WINDOW
        except TypeError:
            invalid_window = True
        if invalid_window:
            raise CalendarError("invalid-window")
        timezone = _bounded_text(timezone, "timezone", 128)
        if isinstance(max_results, bool) or not isinstance(max_results, int) or not 1 <= max_results <= 100:
            raise CalendarError("invalid-limit")
        self._authorize(owner, CALENDAR_READ_SCOPE)
        try:
            events = self.provider.query(start, end, timezone, max_results)
        except GoogleCalendarError as error:
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
        if not isinstance(row, dict) or not hmac.compare_digest(str(row.get("owner", "")), _owner_key(owner)):
            raise CalendarError("draft-not-found")
        return row

    def preview(self, ident: str, owner: str) -> dict:
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
            if row.get("state") == "approved" and self._now() > row.get("expires", 0):
                row.update(state="expired", error_class="approval-expired", effect="none")
                rows[ident] = row
                self._put(rows)
            state = "outcome-unknown" if row.get("state") == "executing" else row.get("state")
            effect = "unknown" if row.get("state") == "executing" else row.get("effect", "none")
            return {
                "id": ident,
                "action": row.get("action", "create"),
                "state": state,
                "payload_hash": row.get("hash", ""),
                "event_ref_hash": hashlib.sha256(str(row.get("event_id", "")).encode()).hexdigest() if row.get("event_id") else "",
                "result": dict(row.get("result", {})),
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
            if row.get("state") == "completed" and hmac.compare_digest(str(row.get("approval", "")), str(approval)):
                return dict(row["result"])
            if row.get("state") in {"executing", "outcome-unknown"}:
                raise CalendarError("unknown-external-outcome", effect="unknown", recovery="inspect-calendar-before-retry")
            if row.get("state") != "approved" or not isinstance(approval, str) or not hmac.compare_digest(str(row.get("approval", "")), approval):
                raise CalendarError("exact-approval-required")
            if self._now() > row.get("expires", 0):
                row.update(state="expired", error_class="approval-expired", effect="none")
                rows[ident] = row
                self._put(rows)
                raise CalendarError("approval-expired", recovery="request-new-approval")
            bound = {
                "action": row.get("action"),
                "payload": row.get("payload"),
                "event_id": row.get("event_id", ""),
                "event_version": row.get("event_version", ""),
            }
            if _canonical(bound) != row.get("hash") or row.get("approval_hash") != row.get("hash"):
                row.update(state="failed", error_class="payload-changed", effect="none")
                rows[ident] = row
                self._put(rows)
                raise CalendarError("payload-changed")
            try:
                self._authorize(owner, CALENDAR_WRITE_SCOPE)
            except CalendarError as error:
                row.update(state="failed", error_class=error.reason, effect="none", recovery=error.recovery)
                rows[ident] = row
                self._put(rows)
                raise
            row.update(state="executing", effect="unknown", approval_used_at=self._now())
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
            error = self._provider_error(provider_error)
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
        if row.get("state") == "created" and hmac.compare_digest(str(row.get("approval", "")), str(approval)):
            return dict(row["result"])
        result = super().create(ident, approval, owner)
        with _LOCK:
            rows = self._rows()
            row = self._owned(rows, ident, owner)
            row["state"] = "created"
            rows[ident] = row
            self._put(rows)
        return result

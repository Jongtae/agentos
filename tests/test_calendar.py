import tempfile
import unittest

from personal_agent.calendar import (
    CALENDAR_CONNECTOR_ID,
    CALENDAR_SPEC,
    CalendarConnector,
    CalendarCreate,
    CalendarError,
)
from personal_agent.connector_contract import ConnectorRegistry, ConnectorState
from personal_agent.google_calendar import (
    CALENDAR_READ_SCOPE,
    CALENDAR_WRITE_SCOPE,
    GoogleCalendarError,
)
from personal_agent.quickstart_store import QuickStore


EVENT = {
    "summary": "review",
    "start": "2026-09-22T10:00:00+09:00",
    "end": "2026-09-22T11:00:00+09:00",
    "timezone": "Asia/Seoul",
    "description": "private agenda",
}


class Provider:
    def __init__(self):
        self.calls = []
        self.error = None

    def _result(self, name, *args):
        self.calls.append((name, *args))
        if self.error:
            raise self.error
        return {"id": args[0] if name != "create" else "new-event", "etag": '"v2"'}

    def query(self, *args):
        self.calls.append(("query", *args))
        if self.error:
            raise self.error
        return [{"id": "event-1", "etag": '"v1"', "summary": "review", "start": EVENT["start"], "end": EVENT["end"], "location": "", "status": "confirmed"}]

    def create(self, payload, key):
        return self._result("create", payload, key)

    def update(self, event_id, etag, payload):
        return self._result("update", event_id, etag, payload)

    def cancel(self, event_id, etag):
        result = self._result("cancel", event_id, etag)
        result["cancelled"] = True
        return result


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = QuickStore(self.temp.name)
        self.provider = Provider()
        self.registry = ConnectorRegistry(self.store, (CALENDAR_SPEC,))
        self.calendar = CalendarConnector(self.store, self.provider, registry=self.registry)
        self.registry.transition(
            "owner",
            CALENDAR_CONNECTOR_ID,
            ConnectorState.CONNECTED,
            granted_scopes=(CALENDAR_READ_SCOPE, CALENDAR_WRITE_SCOPE),
        )

    def tearDown(self):
        self.temp.cleanup()

    def approve(self, draft):
        return self.calendar.approve(draft["id"], "owner")["approval_id"]

    def test_query_requires_explicit_bounded_window_and_read_authority(self):
        result = self.calendar.query(
            "owner",
            "2026-09-21T00:00:00+09:00",
            "2026-09-28T00:00:00+09:00",
            "Asia/Seoul",
            max_results=25,
        )
        self.assertEqual(result["events"][0]["id"], "event-1")
        self.assertEqual(
            self.provider.calls,
            [("query", "2026-09-21T00:00:00+09:00", "2026-09-28T00:00:00+09:00", "Asia/Seoul", 25)],
        )
        self.assertNotIn("private agenda", str(result["evidence"]))
        with self.assertRaises(CalendarError):
            self.calendar.query("owner", "2026-01-01T00:00:00Z", "2028-01-01T00:00:00Z", "UTC")
        with self.assertRaises(CalendarError):
            self.calendar.query("owner", "2026-01-01T00:00:00", "2026-01-02T00:00:00", "UTC")

        disconnected = CalendarConnector(
            QuickStore(self.temp.name + "-other"),
            Provider(),
            registry=ConnectorRegistry(QuickStore(self.temp.name + "-other-registry"), (CALENDAR_SPEC,)),
        )
        with self.assertRaises(CalendarError) as denied:
            disconnected.query("owner", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "UTC")
        self.assertEqual(denied.exception.reason, "scope-denied")
        self.assertFalse(disconnected.provider.calls)

    def test_query_authority_guard_covers_provider_dispatch(self):
        observed = []
        original_query = self.provider.query

        def guarded_query(*args):
            observed.append(self.registry._lock._is_owned())
            return original_query(*args)

        self.provider.query = guarded_query
        self.calendar.query(
            "owner",
            "2026-09-21T00:00:00+09:00",
            "2026-09-28T00:00:00+09:00",
            "Asia/Seoul",
        )
        self.assertEqual(observed, [True])

    def test_create_exact_preview_one_time_approval_and_idempotency(self):
        draft = self.calendar.draft_create(EVENT, "owner")
        self.assertEqual(draft["action"], "create")
        self.assertEqual(draft["payload"], EVENT)
        self.assertFalse(self.provider.calls)
        with self.assertRaises(CalendarError):
            self.calendar.create(draft["id"], "not-approved", "owner")
        with self.assertRaises(CalendarError) as non_ascii:
            self.calendar.create(draft["id"], "승인", "owner")
        self.assertEqual(non_ascii.exception.reason, "exact-approval-required")
        self.assertFalse(self.provider.calls)

        approval = self.approve(draft)
        created = self.calendar.create(draft["id"], approval, "owner")
        self.assertEqual(created, {"id": "new-event", "summary": "review"})
        self.assertEqual(self.calendar.create(draft["id"], approval, "owner"), created)
        self.assertEqual(len(self.provider.calls), 1)

    def test_update_and_cancel_bind_exact_event_version_action_and_owner(self):
        update = self.calendar.draft_update("event/1", '"v1"', {"summary": "new title"}, "owner")
        cancel = self.calendar.draft_cancel("event-2", '"v7"', "owner")
        self.assertFalse(self.provider.calls)
        with self.assertRaises(CalendarError):
            self.calendar.preview(update["id"], "other")
        with self.assertRaises(CalendarError):
            self.calendar.cancel(update["id"], self.approve(update), "owner")
        self.assertFalse(self.provider.calls)

        # A new update draft is used because an approval is action-bound and
        # cannot be repurposed after the rejected action mismatch.
        update = self.calendar.draft_update("event/1", '"v1"', {"summary": "new title"}, "owner")
        updated = self.calendar.update(update["id"], self.approve(update), "owner")
        cancelled = self.calendar.cancel(cancel["id"], self.approve(cancel), "owner")
        self.assertEqual(updated, {"id": "event/1", "updated": True})
        self.assertEqual(cancelled, {"id": "event-2", "cancelled": True})
        self.assertEqual(self.provider.calls[0], ("update", "event/1", '"v1"', {"summary": "new title"}))
        self.assertEqual(self.provider.calls[1], ("cancel", "event-2", '"v7"'))

    def test_changed_payload_event_identity_and_foreign_owner_fail_before_call(self):
        draft = self.calendar.draft_update("event-1", '"v1"', {"summary": "new"}, "owner")
        approval = self.approve(draft)
        rows = self.calendar._rows()
        rows[draft["id"]]["event_id"] = "event-2"
        self.calendar._put(rows)
        with self.assertRaises(CalendarError) as changed:
            self.calendar.update(draft["id"], approval, "owner")
        self.assertEqual(changed.exception.reason, "payload-changed")
        self.assertFalse(self.provider.calls)

        foreign = self.calendar.draft_cancel("event-3", '"v1"', "owner")
        with self.assertRaises(CalendarError):
            self.calendar.approve(foreign["id"], "other")
        self.assertFalse(self.provider.calls)

    def test_attendees_recurrence_and_partial_time_changes_are_not_authorized(self):
        for payload in (
            {**EVENT, "attendees": [{"email": "person@example.test"}]},
            {**EVENT, "recurrence": ["RRULE:FREQ=DAILY"]},
            {**EVENT, "timezone": "Not/A-Timezone"},
            {"start": EVENT["start"]},
        ):
            with self.assertRaises(CalendarError):
                if "summary" in payload:
                    self.calendar.draft_create(payload, "owner")
                else:
                    self.calendar.draft_update("event", '"v1"', payload, "owner")
        self.assertFalse(self.provider.calls)

        with self.assertRaises(CalendarError):
            self.calendar.draft_create(
                {**EVENT, "start": "2026-09-22", "end": "2026-09-23"},
                "owner",
            )
        local = self.calendar.draft_create(
            {
                **EVENT,
                "start": "2026-09-22T10:00:00",
                "end": "2026-09-22T11:00:00",
            },
            "owner",
        )
        self.assertEqual(local["payload"]["start"], "2026-09-22T10:00:00")

    def test_expired_approval_scope_expiry_and_unknown_effect_are_truthful(self):
        clock = [0.0]
        calendar = CalendarConnector(
            self.store,
            self.provider,
            authority=lambda _owner, _scope: True,
            now=lambda: clock[0],
        )
        draft = calendar.draft_create(EVENT, "owner")
        approval = calendar.approve(draft["id"], "owner")["approval_id"]
        status_draft = calendar.draft_create(EVENT, "owner")
        calendar.approve(status_draft["id"], "owner")
        clock[0] = 900
        self.assertEqual(calendar.status(status_draft["id"], "owner")["state"], "expired")
        with self.assertRaises(CalendarError) as expired:
            calendar.create(draft["id"], approval, "owner")
        self.assertEqual(expired.exception.reason, "approval-expired")
        self.assertFalse(self.provider.calls)

        self.provider.error = GoogleCalendarError("scope-expired")
        stale_scope = self.calendar.draft_cancel("event", '"v1"', "owner")
        with self.assertRaises(CalendarError) as scope:
            self.calendar.cancel(stale_scope["id"], self.approve(stale_scope), "owner")
        self.assertEqual((scope.exception.reason, scope.exception.effect), ("scope-expired", "none"))
        self.assertEqual(self.calendar.status(stale_scope["id"], "owner")["state"], "failed")
        self.assertEqual(
            self.registry.status("owner", CALENDAR_CONNECTOR_ID).state,
            ConnectorState.REAUTH_REQUIRED,
        )

        self.registry.transition(
            "owner",
            CALENDAR_CONNECTOR_ID,
            ConnectorState.CONNECTED,
            granted_scopes=(CALENDAR_READ_SCOPE, CALENDAR_WRITE_SCOPE),
        )
        with self.assertRaises(CalendarError):
            self.calendar.query(
                "owner",
                "2026-09-21T00:00:00+09:00",
                "2026-09-28T00:00:00+09:00",
                "Asia/Seoul",
            )
        self.assertEqual(
            self.registry.status("owner", CALENDAR_CONNECTOR_ID).state,
            ConnectorState.REAUTH_REQUIRED,
        )
        self.registry.transition(
            "owner",
            CALENDAR_CONNECTOR_ID,
            ConnectorState.CONNECTED,
            granted_scopes=(CALENDAR_READ_SCOPE, CALENDAR_WRITE_SCOPE),
        )
        self.provider.error = GoogleCalendarError("provider-timeout", "unknown")
        uncertain = self.calendar.draft_create(EVENT, "owner")
        uncertain_approval = self.approve(uncertain)
        with self.assertRaises(CalendarError) as timeout:
            self.calendar.create(uncertain["id"], uncertain_approval, "owner")
        status = self.calendar.status(uncertain["id"], "owner")
        self.assertEqual((timeout.exception.reason, status["state"], status["effect"]), ("provider-timeout", "outcome-unknown", "unknown"))
        with self.assertRaises(CalendarError):
            self.calendar.create(uncertain["id"], uncertain_approval, "owner")
        self.assertEqual(len([call for call in self.provider.calls if call[0] == "create"]), 1)

    def test_event_version_rejects_header_controls_before_approval(self):
        for version in ('"v1"\r\nX-Injected: yes', '"v1"\x00'):
            with self.subTest(version=version):
                with self.assertRaises(CalendarError) as rejected:
                    self.calendar.draft_cancel("event", version, "owner")
                self.assertEqual(rejected.exception.reason, "invalid-event-version")
        self.assertFalse(self.provider.calls)

    def test_status_and_stored_owner_are_redacted(self):
        draft = self.calendar.draft_create(EVENT, "owner-secret-id")
        status = self.calendar.status(draft["id"], "owner-secret-id")
        self.assertNotIn("private agenda", str(status))
        self.assertNotIn("owner-secret-id", str(self.calendar._rows()))
        self.assertNotIn("event_id", status)

        self.registry.transition(
            "owner-secret-id",
            CALENDAR_CONNECTOR_ID,
            ConnectorState.CONNECTED,
            granted_scopes=(CALENDAR_READ_SCOPE, CALENDAR_WRITE_SCOPE),
        )
        approval = self.calendar.approve(draft["id"], "owner-secret-id")["approval_id"]
        self.calendar.create(draft["id"], approval, "owner-secret-id")
        completed = self.calendar.status(draft["id"], "owner-secret-id")
        self.assertEqual(completed["result"], {"id": "new-event"})
        self.assertNotIn(EVENT["summary"], str(completed))
        self.assertNotIn(EVENT["description"], str(completed))

    def test_legacy_rows_migrate_raw_or_unbound_owner_without_losing_retry(self):
        for legacy_owner in ("owner", None):
            with self.subTest(legacy_owner=legacy_owner):
                ident = "legacy-" + (legacy_owner or "unbound")
                legacy_hash = "legacy-content-hash"
                self.store.put(
                    "calendar_create",
                    {
                        ident: {
                            "id": ident,
                            "payload": dict(EVENT),
                            "hash": legacy_hash,
                            "owner": legacy_owner,
                            "state": "created",
                            "approval": "legacy-approval",
                            "approval_hash": legacy_hash,
                            "expires": 9999999999,
                            "result": {"id": "legacy-event", "summary": EVENT["summary"]},
                        }
                    },
                )
                legacy = CalendarCreate(self.store, lambda *_: self.fail("legacy retry dispatched"))
                self.assertEqual(
                    legacy.create(ident, "legacy-approval", "owner"),
                    {"id": "legacy-event", "summary": EVENT["summary"]},
                )
                migrated = legacy._rows()[ident]
                self.assertNotEqual(migrated["owner"], "owner")
                self.assertEqual(migrated["action"], "create")
                self.assertEqual(legacy.status(ident, "owner")["result"], {"id": "legacy-event"})

        calls = []
        self.store.put(
            "calendar_create",
            {
                "legacy-approved": {
                    "id": "legacy-approved",
                    "payload": dict(EVENT),
                    "hash": "legacy-content-hash",
                    "owner": "owner",
                    "state": "approved",
                    "approval": "legacy-approval",
                    "approval_hash": "legacy-content-hash",
                    "expires": 9999999999,
                }
            },
        )
        legacy = CalendarCreate(
            self.store,
            lambda *_: calls.append("create") or {"id": "migrated-event"},
        )
        self.assertEqual(
            legacy.create("legacy-approved", "legacy-approval", "owner")["id"],
            "migrated-event",
        )
        self.assertEqual(calls, ["create"])

        self.store.put(
            "calendar_create",
            {
                "legacy-unicode": {
                    "id": "legacy-unicode",
                    "payload": dict(EVENT),
                    "hash": "legacy-content-hash",
                    "owner": "소유자",
                    "state": "awaiting-approval",
                }
            },
        )
        unicode_legacy = CalendarCreate(self.store, lambda *_: {"id": "unused"})
        preview = unicode_legacy.preview("legacy-unicode", "소유자")
        self.assertEqual(preview["action"], "create")
        self.assertNotEqual(unicode_legacy._rows()["legacy-unicode"]["owner"], "소유자")

    def test_invalid_legacy_approved_payload_is_quarantined_before_provider_dispatch(self):
        for invalid_payload in (
            {**EVENT, "start": "a", "end": "b"},
            {**EVENT, "start": "2026-10-01", "end": "2026-10-02"},
        ):
            with self.subTest(payload=invalid_payload):
                self.store.put(
                    "calendar_create",
                    {
                        "legacy-invalid": {
                            "id": "legacy-invalid",
                            "payload": invalid_payload,
                            "hash": "legacy-content-hash",
                            "owner": "owner",
                            "state": "approved",
                            "approval": "legacy-approval",
                            "approval_hash": "legacy-content-hash",
                            "expires": 9999999999,
                        }
                    },
                )
                calls = []
                legacy = CalendarCreate(
                    self.store,
                    lambda *_: calls.append("create") or {"id": "must-not-dispatch"},
                )
                with self.assertRaises(CalendarError) as rejected:
                    legacy.create("legacy-invalid", "legacy-approval", "owner")
                self.assertEqual(rejected.exception.reason, "exact-approval-required")
                migrated = legacy._rows()["legacy-invalid"]
                self.assertEqual(migrated["state"], "expired")
                self.assertEqual(migrated["error_class"], "legacy-payload-invalid")
                self.assertEqual(migrated["recovery"], "request-new-draft")
                self.assertNotIn("approval", migrated)
                self.assertNotIn("approval_hash", migrated)
                self.assertEqual(calls, [])

    def test_portable_terminal_calendar_evidence_remains_readable(self):
        self.store.put(
            "calendar_create",
            {
                "portable": {
                    "id": "portable",
                    "state": "created",
                    "hash": "redacted-hash",
                    "result": {"id": "event-1"},
                }
            },
        )
        restored = CalendarCreate(self.store, lambda *_: self.fail("portable evidence dispatched"))
        status = restored.status("portable", "restored-owner")
        self.assertEqual(status["state"], "created")
        self.assertEqual(status["action"], "unknown")
        self.assertEqual(status["result"], {"id": "event-1"})
        self.assertNotIn("restored-owner", str(restored._rows()))

        self.store.put(
            "calendar_create",
            {
                "in-flight": {
                    "id": "in-flight",
                    "state": "executing",
                    "hash": "redacted-hash",
                }
            },
        )
        uncertain = restored.status("in-flight", "restored-owner")
        self.assertEqual(uncertain["state"], "outcome-unknown")
        self.assertEqual(uncertain["effect"], "unknown")
        self.assertEqual(uncertain["recovery"], "inspect-calendar-before-retry")

        for pending_state in ("awaiting-approval", "approved"):
            with self.subTest(pending_state=pending_state):
                ident = "pending-" + pending_state
                self.store.put(
                    "calendar_create",
                    {
                        ident: {
                            "id": ident,
                            "state": pending_state,
                            "hash": "redacted-hash",
                        }
                    },
                )
                quarantined = restored.status(ident, "restored-owner")
                self.assertEqual(quarantined["state"], "expired")
                self.assertEqual(quarantined["action"], "unknown")
                self.assertEqual(quarantined["error_class"], "restored-approval-quarantined")
                self.assertEqual(quarantined["recovery"], "request-new-approval")

    def test_write_authority_check_and_executing_commit_share_registry_guard(self):
        draft = self.calendar.draft_create(EVENT, "owner")
        approval = self.approve(draft)
        observations = []
        original_authorize = self.calendar._authorize

        def observed_authorize(owner, scope):
            observations.append(self.registry._lock._is_owned())
            return original_authorize(owner, scope)

        self.calendar._authorize = observed_authorize
        self.calendar.create(draft["id"], approval, "owner")
        self.assertEqual(observations, [True])

    def test_legacy_create_surface_remains_idempotent(self):
        calls = []
        legacy = CalendarCreate(
            self.store,
            lambda url, body, headers: calls.append((url, body, headers)) or {"id": "legacy-event"},
        )
        draft = legacy.draft(EVENT, "owner")
        approval = legacy.approve(draft["id"], "owner")
        self.assertEqual(legacy.create(draft["id"], approval["approval_id"], "owner")["id"], "legacy-event")
        legacy.create(draft["id"], approval["approval_id"], "owner")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()

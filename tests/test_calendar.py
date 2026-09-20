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

    def test_create_exact_preview_one_time_approval_and_idempotency(self):
        draft = self.calendar.draft_create(EVENT, "owner")
        self.assertEqual(draft["action"], "create")
        self.assertEqual(draft["payload"], EVENT)
        self.assertFalse(self.provider.calls)
        with self.assertRaises(CalendarError):
            self.calendar.create(draft["id"], "not-approved", "owner")
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
        clock[0] = 901
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

    def test_status_and_stored_owner_are_redacted(self):
        draft = self.calendar.draft_create(EVENT, "owner-secret-id")
        status = self.calendar.status(draft["id"], "owner-secret-id")
        self.assertNotIn("private agenda", str(status))
        self.assertNotIn("owner-secret-id", str(self.calendar._rows()))
        self.assertNotIn("event_id", status)

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

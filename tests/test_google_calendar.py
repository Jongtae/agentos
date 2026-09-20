import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

from personal_agent.calendar import CalendarConnector, CalendarError
from personal_agent.google_calendar import (
    CALENDAR_API,
    GoogleCalendar,
    GoogleCalendarError,
    GoogleCalendarHTTPError,
)
from personal_agent.quickstart_store import QuickStore


class GoogleCalendarTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def transport(method, url, body, headers):
            self.calls.append((method, url, body, headers))
            if method == "GET":
                return {
                    "items": [
                        {
                            "id": "event-1",
                            "etag": '"v1"',
                            "summary": "review",
                            "start": {"dateTime": "2026-09-22T10:00:00+09:00"},
                            "end": {"dateTime": "2026-09-22T11:00:00+09:00"},
                            "description": "not copied into query result",
                        }
                    ]
                }
            if method in {"POST", "PATCH"}:
                return {"id": body.get("id", "event/1"), "etag": '"v2"'}
            return None

        self.calendar = GoogleCalendar(transport, "access-secret")

    def test_exact_get_is_primary_only_and_has_explicit_window(self):
        result = self.calendar.query(
            "2026-09-21T00:00:00+09:00",
            "2026-09-28T00:00:00+09:00",
            "Asia/Seoul",
            20,
        )
        method, url, body, headers = self.calls[0]
        query = parse_qs(urlparse(url).query)
        self.assertEqual((method, urlparse(url).path, body), ("GET", "/calendar/v3/calendars/primary/events", None))
        self.assertEqual(query["timeMin"], ["2026-09-21T00:00:00+09:00"])
        self.assertEqual(query["timeMax"], ["2026-09-28T00:00:00+09:00"])
        self.assertEqual(query["singleEvents"], ["true"])
        self.assertEqual(query["orderBy"], ["startTime"])
        self.assertEqual(headers["Authorization"], "Bearer access-secret")
        self.assertNotIn("access-secret", url)
        self.assertNotIn("description", result[0])

    def test_exact_post_uses_stable_event_id_and_suppresses_invites(self):
        payload = {
            "summary": "review",
            "start": "2026-09-22T10:00:00+09:00",
            "end": "2026-09-22T11:00:00+09:00",
            "timezone": "Asia/Seoul",
            "description": "private agenda",
        }
        first = self.calendar.create(payload, "approved-key")
        _, _, first_body, _ = self.calls[-1]
        second = self.calendar.create(payload, "approved-key")
        method, url, body, headers = self.calls[-1]
        self.assertEqual(method, "POST")
        self.assertEqual(url, f"{CALENDAR_API}/calendars/primary/events?sendUpdates=none")
        self.assertEqual(first_body["id"], body["id"])
        self.assertEqual(first, second)
        self.assertEqual(body["start"], {"dateTime": payload["start"], "timeZone": "Asia/Seoul"})
        self.assertNotIn("attendees", body)
        self.assertNotIn("recurrence", body)
        self.assertEqual(headers["Idempotency-Key"], "approved-key")

    def test_create_rejects_response_for_different_event_identity(self):
        calendar = GoogleCalendar(lambda _method, _url, _body, _headers: {"id": "different-event"})
        payload = {
            "summary": "review",
            "start": "2026-01-01T10:00:00Z",
            "end": "2026-01-01T11:00:00Z",
            "timezone": "UTC",
        }
        with self.assertRaises(GoogleCalendarError) as mismatch:
            calendar.create(payload, "approved-key")
        self.assertEqual((mismatch.exception.reason, mismatch.exception.effect), ("malformed-response", "unknown"))

    def test_policy_makes_no_exact_post_before_owner_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            connector = CalendarConnector(
                QuickStore(folder),
                self.calendar,
                authority=lambda _owner, _scope: True,
            )
            draft = connector.draft_create(
                {
                    "summary": "review",
                    "start": "2026-09-22T10:00:00+09:00",
                    "end": "2026-09-22T11:00:00+09:00",
                    "timezone": "Asia/Seoul",
                },
                "owner",
            )
            with self.assertRaises(CalendarError):
                connector.create(draft["id"], "unapproved", "owner")
            self.assertFalse(self.calls)
            approval = connector.approve(draft["id"], "owner")["approval_id"]
            connector.create(draft["id"], approval, "owner")
            self.assertEqual(self.calls[0][0], "POST")

    def test_exact_patch_and_delete_bind_version_and_never_send_updates(self):
        updated = self.calendar.update("event/1", '"v1"', {"summary": "new title"})
        method, url, body, headers = self.calls[-1]
        self.assertEqual(method, "PATCH")
        self.assertEqual(url, f"{CALENDAR_API}/calendars/primary/events/event%2F1?sendUpdates=none")
        self.assertEqual(body, {"summary": "new title"})
        self.assertEqual(headers["If-Match"], '"v1"')
        self.assertEqual(updated["id"], "event/1")

        cancelled = self.calendar.cancel("event/2", '"v2"')
        method, url, body, headers = self.calls[-1]
        self.assertEqual(method, "DELETE")
        self.assertEqual(url, f"{CALENDAR_API}/calendars/primary/events/event%2F2?sendUpdates=none")
        self.assertIsNone(body)
        self.assertEqual(headers["If-Match"], '"v2"')
        self.assertEqual(cancelled, {"id": "event/2", "cancelled": True})

    def test_read_timeout_malformed_and_scope_expiry_have_no_claimed_effect(self):
        cases = (
            (lambda *_: (_ for _ in ()).throw(TimeoutError()), "provider-timeout"),
            (lambda *_: {}, "malformed-response"),
            (lambda *_: (_ for _ in ()).throw(GoogleCalendarHTTPError(401)), "scope-expired"),
            (lambda *_: (_ for _ in ()).throw(GoogleCalendarHTTPError(500)), "provider-error"),
            (lambda *_: (_ for _ in ()).throw(GoogleCalendarHTTPError(503)), "provider-error"),
        )
        for transport, reason in cases:
            with self.subTest(reason=reason):
                calendar = GoogleCalendar(transport)
                with self.assertRaises(GoogleCalendarError) as error:
                    calendar.query("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "UTC", 10)
                self.assertEqual((error.exception.reason, error.exception.effect), (reason, "none"))

    def test_write_timeout_server_failure_and_malformed_are_unknown(self):
        transports = (
            (lambda *_: (_ for _ in ()).throw(TimeoutError()), "provider-timeout"),
            (lambda *_: (_ for _ in ()).throw(GoogleCalendarHTTPError(503)), "provider-error"),
            (lambda *_: (_ for _ in ()).throw(ValueError("private parser detail")), "provider-error"),
            (lambda *_: {}, "malformed-response"),
        )
        payload = {
            "summary": "review",
            "start": "2026-01-01T10:00:00Z",
            "end": "2026-01-01T11:00:00Z",
            "timezone": "UTC",
        }
        for transport, reason in transports:
            with self.subTest(reason=reason):
                with self.assertRaises(GoogleCalendarError) as error:
                    GoogleCalendar(transport).create(payload, "key")
                self.assertEqual((error.exception.reason, error.exception.effect), (reason, "unknown"))

    def test_stale_provider_version_fails_without_unknown_effect(self):
        calendar = GoogleCalendar(lambda *_: (_ for _ in ()).throw(GoogleCalendarHTTPError(412)))
        with self.assertRaises(GoogleCalendarError) as error:
            calendar.update("event", '"stale"', {"summary": "changed"})
        self.assertEqual((error.exception.reason, error.exception.effect), ("stale-event", "none"))

    def test_forbidden_response_does_not_claim_scope_expiry(self):
        calendar = GoogleCalendar(lambda *_: (_ for _ in ()).throw(GoogleCalendarHTTPError(403)))
        with self.assertRaises(GoogleCalendarError) as error:
            calendar.query("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "UTC", 10)
        self.assertEqual((error.exception.reason, error.exception.effect), ("provider-rejected", "none"))


if __name__ == "__main__":
    unittest.main()

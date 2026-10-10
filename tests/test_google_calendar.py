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

    def test_exact_get_reads_the_primary_with_an_explicit_window(self):
        result = self.calendar.query(
            "2026-09-21T00:00:00+09:00",
            "2026-09-28T00:00:00+09:00",
            "Asia/Seoul",
            20,
        )
        # #1225: the calendar list comes first; the fixture shows no other calendar.
        self.assertEqual(urlparse(self.calls[0][1]).path, "/calendar/v3/users/me/calendarList")
        method, url, body, headers = self.calls[1]
        query = parse_qs(urlparse(url).query)
        self.assertEqual((method, urlparse(url).path, body), ("GET", "/calendar/v3/calendars/primary/events", None))
        self.assertEqual(query["timeMin"], ["2026-09-21T00:00:00+09:00"])
        self.assertEqual(query["timeMax"], ["2026-09-28T00:00:00+09:00"])
        self.assertEqual(query["singleEvents"], ["true"])
        self.assertEqual(query["orderBy"], ["startTime"])
        self.assertEqual(headers["Authorization"], "Bearer access-secret")
        self.assertNotIn("access-secret", url)
        # #1273 (after #826): the owner's AI reads what the event says and who is invited, so a
        # follow-up about it needs no web sign-in; the description is bounded (MAX_DESCRIPTION_CHARS).
        self.assertEqual(result[0]["description"], "not copied into query result")

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

    def test_query_reads_attendees_organizer_and_description(self):
        """#1273: the follow-up "who is the lunch with" is answerable from the read itself."""
        seen = []
        response = {"items": [{
            "id": "lunch", "summary": "점심", "etag": '"e"',
            "start": {"dateTime": "2026-10-12T12:30:00+09:00"}, "end": {"dateTime": "2026-10-12T13:30:00+09:00"},
            "description": "x" * 4100,
            "organizer": {"email": "me@example.com", "self": True},
            "attendees": [
                {"email": "me@example.com", "self": True, "organizer": True, "responseStatus": "accepted"},
                {"email": "kim@example.com", "displayName": "김", "responseStatus": "needsAction", "optional": True},
                "not-a-person", {"responseStatus": "declined"},
            ],
        }]}

        def transport(method, url, body, headers):
            seen.append(url)
            return response if "/events?" in url else {"items": []}
        [event] = GoogleCalendar(transport).query("2026-10-12T00:00:00+09:00", "2026-10-13T00:00:00+09:00", "Asia/Seoul", 10)
        self.assertEqual(event["attendees"], [
            {"email": "me@example.com", "response": "accepted", "organizer": True, "self": True},
            {"email": "kim@example.com", "name": "김", "response": "needsAction", "optional": True}])
        self.assertEqual(event["organizer"], {"email": "me@example.com", "self": True})
        self.assertEqual(len(event["description"]), 4000)
        self.assertTrue(event["description_truncated"])
        query = next(url for url in seen if "/events?" in url)
        self.assertIn("attendees", query)
        self.assertIn("maxAttendees=50", query)

    def test_an_event_without_people_or_notes_reads_as_before(self):
        response = {"items": [{"id": "e1", "summary": "Office", "start": {"date": "2026-10-12"}, "end": {"date": "2026-10-13"}}]}
        [event] = GoogleCalendar(lambda method, url, *_: response if "/events?" in url else {"items": []}).query(
            "2026-10-12T00:00:00+09:00", "2026-10-13T00:00:00+09:00", "Asia/Seoul", 10)
        for key in ("attendees", "organizer", "description", "description_truncated"):
            self.assertNotIn(key, event)

    def test_query_rejects_over_limit_and_unbounded_provider_fields(self):
        event={
            "id":"event-1","summary":"review",
            "start":{"dateTime":"2026-01-01T00:00:00Z"},
            "end":{"dateTime":"2026-01-01T01:00:00Z"},
        }
        cases=(
            {"items":[event,event]},
            {"items":[{**event,"summary":"x"*1001}]},
            {"items":[{**event,"id":"x"*1025}]},
            {"items":[{**event,"status":7}]},
        )
        for response in cases:
            with self.subTest(response_size=len(response["items"])):
                calendar=GoogleCalendar(lambda *_args,response=response:response)
                with self.assertRaises(GoogleCalendarError) as malformed:
                    calendar.query("2026-01-01T00:00:00Z","2026-01-02T00:00:00Z","UTC",1)
                self.assertEqual(malformed.exception.reason,"malformed-response")

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

    def test_conflict_on_mutation_is_unknown_effect_not_a_plain_rejection(self):
        # #447: Google documents 409 as "The requested identifier already
        # exists" (events.insert with an existing ID) or "Conflict". create()
        # derives the event ID from the approved idempotency key, so a create
        # 409 means the event plausibly exists already.
        payload = {
            "summary": "review",
            "start": "2026-01-01T10:00:00Z",
            "end": "2026-01-01T11:00:00Z",
            "timezone": "UTC",
        }
        calendar = GoogleCalendar(lambda *_: (_ for _ in ()).throw(GoogleCalendarHTTPError(409)))
        cases = (
            (lambda: calendar.create(payload, "key"), "event-already-exists"),
            (lambda: calendar.update("event", '"v1"', {"summary": "changed"}), "provider-conflict"),
            (lambda: calendar.cancel("event", '"v1"'), "provider-conflict"),
        )
        for call, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaises(GoogleCalendarError) as error:
                    call()
                self.assertEqual((error.exception.reason, error.exception.effect), (reason, "unknown"))
                self.assertNotEqual(error.exception.reason, "provider-rejected")
        with self.assertRaises(GoogleCalendarError) as read:
            calendar.query("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "UTC", 10)
        self.assertEqual((read.exception.reason, read.exception.effect), ("provider-rejected", "none"))

    def test_conflict_receipt_through_connector_never_claims_no_external_effect(self):
        calendar = GoogleCalendar(lambda *_: (_ for _ in ()).throw(GoogleCalendarHTTPError(409)))
        payload = {
            "summary": "review",
            "start": "2026-09-22T10:00:00+09:00",
            "end": "2026-09-22T11:00:00+09:00",
            "timezone": "Asia/Seoul",
        }
        with tempfile.TemporaryDirectory() as folder:
            connector = CalendarConnector(
                QuickStore(folder), calendar, authority=lambda _owner, _scope: True
            )
            drafts = (
                (connector.draft_create(payload, "owner"), connector.create, "event-already-exists"),
                (connector.draft_update("event-1", '"v1"', {"summary": "new"}, "owner"),
                 connector.update, "provider-conflict"),
                (connector.draft_cancel("event-2", '"v1"', "owner"), connector.cancel, "provider-conflict"),
            )
            for draft, run, reason in drafts:
                with self.subTest(action=draft["action"]):
                    approval = connector.approve(draft["id"], "owner")["approval_id"]
                    with self.assertRaises(CalendarError) as raised:
                        run(draft["id"], approval, "owner")
                    self.assertEqual(
                        (raised.exception.reason, raised.exception.effect, raised.exception.recovery),
                        (reason, "unknown", "inspect-calendar-before-retry"),
                    )
                    receipt = connector.status(draft["id"], "owner")
                    self.assertEqual(
                        (receipt["state"], receipt["error_class"], receipt["effect"], receipt["recovery"]),
                        ("outcome-unknown", reason, "unknown", "inspect-calendar-before-retry"),
                    )
                    self.assertNotEqual(receipt["effect"], "none")
                    # The replay barrier holds: no second provider attempt.
                    with self.assertRaises(CalendarError) as replay:
                        run(draft["id"], approval, "owner")
                    self.assertEqual(replay.exception.reason, "unknown-external-outcome")

    def test_existing_non_conflict_mutation_classifications_are_unchanged(self):
        cases = (
            (401, "scope-expired", "none"),
            (403, "provider-rejected", "none"),
            (412, "stale-event", "none"),
            (400, "provider-rejected", "none"),
            (500, "provider-error", "unknown"),
            (503, "provider-error", "unknown"),
        )
        for status, reason, effect in cases:
            with self.subTest(status=status):
                calendar = GoogleCalendar(
                    lambda *_, status=status: (_ for _ in ()).throw(GoogleCalendarHTTPError(status))
                )
                with self.assertRaises(GoogleCalendarError) as error:
                    calendar.update("event", '"v1"', {"summary": "changed"})
                self.assertEqual((error.exception.reason, error.exception.effect), (reason, effect))


if __name__ == "__main__":
    unittest.main()


class ShownCalendarsTests(unittest.TestCase):
    """#1225: every calendar the owner shows in Google Calendar is read; writes stay on primary."""

    WINDOW = ("2026-10-11T00:00:00+09:00", "2026-10-12T00:00:00+09:00", "Asia/Seoul", 20)

    def provider(self, listing, events, failing=()):
        calls = []

        def transport(method, url, body, headers):
            path = urlparse(url).path
            calls.append(path)
            if path.endswith("/users/me/calendarList"):
                if isinstance(listing, Exception):
                    raise listing
                return listing
            calendar_id = path.split("/calendars/", 1)[1].split("/events", 1)[0]
            from urllib.parse import unquote
            calendar_id = unquote(calendar_id)
            if calendar_id in failing:
                raise GoogleCalendarHTTPError(404)
            return {"items": events.get(calendar_id, [])}
        return GoogleCalendar(transport, "token"), calls

    @staticmethod
    def event(ident, start):
        return {"id": ident, "etag": f'"{ident}"', "summary": ident,
                "start": {"dateTime": start}, "end": {"dateTime": start}, "status": "confirmed"}

    def test_shown_calendars_are_read_tagged_and_merged_in_time_order(self):
        listing = {"items": [
            {"id": "me@example.com", "summary": "jongtae lee", "primary": True, "selected": True},
            {"id": "family#cal", "summary": "Family", "selected": True},
            {"id": "birthdays", "summary": "Birthdays", "selected": False},
            {"id": "ko.south_korea#holiday", "summary": "Holidays", "summaryOverride": "공휴일", "selected": True},
        ]}
        events = {"primary": [self.event("mine", "2026-10-11T10:00:00+09:00")],
                  "family#cal": [self.event("dinner", "2026-10-11T09:00:00+09:00")],
                  "birthdays": [self.event("never", "2026-10-11T08:00:00+09:00")],
                  "ko.south_korea#holiday": [self.event("holiday", "2026-10-11T00:00:00+09:00")]}
        provider, calls = self.provider(listing, events)
        result = provider.query(*self.WINDOW)
        self.assertEqual([row["id"] for row in result], ["holiday", "dinner", "mine"])
        self.assertEqual([row["calendar"] for row in result], ["공휴일", "Family", "jongtae lee"])
        self.assertEqual([row["etag"] for row in result], ["", "", '"mine"'], "only primary events can be changed")
        self.assertNotIn("/calendar/v3/calendars/birthdays/events", calls)

    def test_a_failing_shown_calendar_is_skipped_and_named(self):
        listing = {"items": [{"id": "me", "primary": True, "selected": True, "summary": "me"},
                             {"id": "gone", "summary": "Gone", "selected": True}]}
        provider, _calls = self.provider(listing, {"primary": [self.event("mine", "2026-10-11T10:00:00+09:00")]},
                                         failing=("gone",))
        self.assertEqual([row["id"] for row in provider.query(*self.WINDOW)], ["mine"])
        self.assertEqual(provider.skipped_calendars, ["Gone"])

    def test_an_unreadable_list_falls_back_to_the_primary_calendar(self):
        provider, calls = self.provider(GoogleCalendarHTTPError(403), {"primary": [self.event("mine", "2026-10-11T10:00:00+09:00")]})
        self.assertEqual([row["id"] for row in provider.query(*self.WINDOW)], ["mine"])
        self.assertEqual(calls[-1], "/calendar/v3/calendars/primary/events")

    def test_an_expired_grant_is_not_hidden_by_the_fallback(self):
        provider, _calls = self.provider(GoogleCalendarHTTPError(401), {})
        with self.assertRaises(GoogleCalendarError) as caught:
            provider.query(*self.WINDOW)
        self.assertEqual(caught.exception.reason, "scope-expired")


class ShownCalendarsReviewTests(unittest.TestCase):
    WINDOW = ShownCalendarsTests.WINDOW
    provider = ShownCalendarsTests.provider
    event = staticmethod(ShownCalendarsTests.event)

    def test_events_are_merged_by_instant_not_by_string(self):
        listing = {"items": [{"id": "me", "primary": True, "selected": True, "summary": "me"},
                             {"id": "abroad", "summary": "Abroad", "selected": True}]}
        events = {"primary": [self.event("later", "2026-10-11T01:15:00-05:00")],
                  "abroad": [self.event("earlier", "2026-10-11T01:30:00-04:00")]}
        provider, _calls = self.provider(listing, events)
        self.assertEqual([row["id"] for row in provider.query(*self.WINDOW)], ["earlier", "later"])

    def test_the_calendars_read_include_ones_without_events(self):
        listing = {"items": [{"id": "me", "primary": True, "selected": True, "summary": "me"},
                             {"id": "quiet", "summary": "Quiet", "selected": True}]}
        provider, _calls = self.provider(listing, {})
        self.assertEqual(provider.query(*self.WINDOW), [])
        self.assertEqual(provider.read_calendars, ["me", "Quiet"])
        self.assertFalse(provider.calendar_list_failed)

    def test_a_failed_discovery_is_marked(self):
        provider, _calls = self.provider(GoogleCalendarHTTPError(500), {})
        provider.query(*self.WINDOW)
        self.assertTrue(provider.calendar_list_failed)

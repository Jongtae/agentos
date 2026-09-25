"""Owner-authority tests for the Google Calendar OAuth credential path.

Every provider and HTTP interaction is injected; nothing here touches the
network. The suite is written so each assertion has exactly one guard in
``personal_agent.calendar_oauth`` that can produce it (see the mutation record
in the PA1-J4 report), rather than passing because an earlier predicate
already excluded the case.
"""

import base64
import hashlib
import json
import pathlib
import tempfile
import traceback
import unittest
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

from personal_agent import calendar_oauth as calendar_oauth_module
from personal_agent.calendar import (
    CALENDAR_CONNECTOR_ID,
    CALENDAR_WRITE_CONNECTOR_ID,
)
from personal_agent.calendar_oauth import (
    AUTHORIZATION_ENDPOINT,
    PENDING_SECRET_KEY,
    READ_GRANT,
    TOKEN_SECRET_KEY,
    WRITE_GRANT,
    CalendarOAuth,
    CalendarOAuthError,
    CalendarReauthenticationRequired,
    EncryptedCalendarSecretStore,
    calendar_transport,
)
from personal_agent.connector_contract import (
    ConnectorContractError,
    ConnectorRegistry,
    ConnectorState,
)
from personal_agent.gmail import EncryptedGmailSecretStore
from personal_agent.google_calendar import (
    CALENDAR_API,
    CALENDAR_READ_SCOPE,
    CALENDAR_WRITE_SCOPE,
    GoogleCalendar,
    GoogleCalendarError,
    GoogleCalendarHTTPError,
)
from personal_agent.quickstart_store import QuickStore


EVENTS_URL = (
    CALENDAR_API
    + "/calendars/primary/events?timeMin=2026-09-22T09:00:00%2B09:00"
    + "&timeMax=2026-09-22T18:00:00%2B09:00&maxResults=5"
)


class CalendarOAuthTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.key = Fernet.generate_key()
        self.raw_store = QuickStore(self.temp.name)
        self.store = EncryptedCalendarSecretStore(self.raw_store, self.key)
        self.clock = [1_000.0]
        self.registry = ConnectorRegistry(self.store, (), clock=lambda: self.clock[0])
        self.oauth = CalendarOAuth(
            self.store,
            "calendar-client",
            "https://connect.example.test/calendar/callback",
            registry=self.registry,
            now=lambda: self.clock[0],
        )

    # -- helpers ---------------------------------------------------------

    def begin(self, owner="owner-a", *, write=False):
        offer = self.oauth.begin_oauth(owner, write=write)
        query = parse_qs(urlparse(offer["authorization_url"]).query)
        return offer, query["state"][0], query

    def connect(
        self,
        owner="owner-a",
        *,
        write=False,
        access_token="access-1",
        refresh_token="refresh-1",
        expires_in=3_600,
        scope=None,
    ):
        _offer, state, _query = self.begin(owner, write=write)
        seen = []

        def exchange(request):
            seen.append(request)
            response = {
                "access_token": access_token,
                "expires_in": expires_in,
                "scope": CALENDAR_WRITE_SCOPE if write else CALENDAR_READ_SCOPE,
            }
            if scope is not None:
                response["scope"] = scope
            if refresh_token is not None:
                response["refresh_token"] = refresh_token
            return response

        status = self.oauth.complete_oauth(owner, {"state": state, "code": "auth-code"}, exchange)
        return status, seen

    def connector_state(self, connector_id, owner="owner-a"):
        return self.registry.status(owner, connector_id).state

    def pending_slot(self, grant, owner="owner-a"):
        connector_id = CALENDAR_WRITE_CONNECTOR_ID if grant == WRITE_GRANT else CALENDAR_CONNECTOR_ID
        owner_hash = hashlib.sha256(owner.encode()).hexdigest()
        return f"{PENDING_SECRET_KEY}:{connector_id}:{owner_hash}"

    def token_slot(self, grant, owner="owner-a"):
        connector_id = CALENDAR_WRITE_CONNECTOR_ID if grant == WRITE_GRANT else CALENDAR_CONNECTOR_ID
        owner_hash = hashlib.sha256(owner.encode()).hexdigest()
        return f"{TOKEN_SECRET_KEY}:{connector_id}:{owner_hash}"

    def recording_opener(self, responses):
        calls = []

        def opener(method, url, body, headers):
            calls.append({"method": method, "url": url, "body": body, "headers": headers})
            outcome = responses.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        return opener, calls


class GrantSeparationTests(CalendarOAuthTestCase):
    def test_read_grant_does_not_produce_a_write_capable_connection(self):
        self.connect()
        self.assertEqual(self.connector_state(CALENDAR_CONNECTOR_ID), ConnectorState.CONNECTED)
        read_status = self.oauth.status("owner-a")
        self.assertEqual(read_status["granted_scopes"], [CALENDAR_READ_SCOPE])
        self.assertNotIn(CALENDAR_WRITE_SCOPE, read_status["granted_scopes"])

        write_status = self.oauth.status("owner-a", write=True)
        self.assertEqual(write_status["state"], ConnectorState.DISCONNECTED.value)
        self.assertEqual(write_status["granted_scopes"], [])
        with self.assertRaises(ConnectorContractError):
            self.registry.require_connected(
                "owner-a", CALENDAR_WRITE_CONNECTOR_ID, (CALENDAR_WRITE_SCOPE,)
            )
        # No write credential exists to be spent, either.
        self.assertEqual(self.store.secret(self.token_slot(WRITE_GRANT)), "")
        self.assertTrue(self.store.secret(self.token_slot(READ_GRANT))["access_token"])

    def test_write_grant_does_not_produce_a_read_capable_connection(self):
        self.connect(write=True, access_token="write-access")
        self.assertEqual(self.connector_state(CALENDAR_WRITE_CONNECTOR_ID), ConnectorState.CONNECTED)
        self.assertEqual(
            self.oauth.status("owner-a", write=True)["granted_scopes"], [CALENDAR_WRITE_SCOPE]
        )
        self.assertEqual(
            self.oauth.status("owner-a")["state"], ConnectorState.DISCONNECTED.value
        )
        with self.assertRaises(ConnectorContractError):
            self.registry.require_connected(
                "owner-a", CALENDAR_CONNECTOR_ID, (CALENDAR_READ_SCOPE,)
            )
        self.assertEqual(self.store.secret(self.token_slot(READ_GRANT)), "")

    def test_read_authorization_returning_the_write_scope_is_refused(self):
        with self.assertRaises(CalendarOAuthError) as caught:
            self.connect(scope=f"{CALENDAR_READ_SCOPE} {CALENDAR_WRITE_SCOPE}")
        self.assertEqual(caught.exception.reason, "token_exchange_failed")
        self.assertEqual(
            self.connector_state(CALENDAR_CONNECTOR_ID), ConnectorState.DISCONNECTED
        )
        self.assertEqual(
            self.connector_state(CALENDAR_WRITE_CONNECTOR_ID), ConnectorState.DISCONNECTED
        )
        self.assertEqual(self.store.secret(self.token_slot(READ_GRANT)), "")

    def test_revoking_the_read_grant_leaves_the_write_grant_connected(self):
        self.connect()
        self.connect(write=True, access_token="write-access")
        self.oauth.mark_reauthentication_required("owner-a")
        self.assertEqual(
            self.connector_state(CALENDAR_CONNECTOR_ID), ConnectorState.REAUTH_REQUIRED
        )
        self.assertEqual(
            self.connector_state(CALENDAR_WRITE_CONNECTOR_ID), ConnectorState.CONNECTED
        )
        self.assertEqual(
            self.store.secret(self.token_slot(WRITE_GRANT))["access_token"], "write-access"
        )


    def test_refresh_cannot_revive_or_widen_a_revoked_grant(self):
        self.connect(access_token="access-1", refresh_token="refresh-1")
        self.oauth.mark_reauthentication_required("owner-a")
        with self.assertRaises(CalendarReauthenticationRequired):
            self.oauth.refresh(
                "owner-a",
                lambda request: {
                    "access_token": "access-2",
                    "expires_in": 3_600,
                    "scope": CALENDAR_READ_SCOPE,
                },
            )

        self.connect(access_token="access-3", refresh_token="refresh-3")
        with self.assertRaises(CalendarOAuthError) as caught:
            self.oauth.refresh(
                "owner-a",
                lambda request: {
                    "access_token": "access-4",
                    "expires_in": 3_600,
                    "scope": f"{CALENDAR_READ_SCOPE} {CALENDAR_WRITE_SCOPE}",
                },
            )
        self.assertEqual(caught.exception.reason, "token_exchange_failed")
        self.assertEqual(
            self.store.secret(self.token_slot(READ_GRANT))["access_token"], "access-3"
        )
        self.assertEqual(
            self.store.secret(self.token_slot(READ_GRANT))["scope"], [CALENDAR_READ_SCOPE]
        )


class SignedStateTests(CalendarOAuthTestCase):
    def test_state_is_single_use(self):
        _offer, state, _query = self.begin()
        calls = []

        def exchange(request):
            calls.append(request)
            return {
                "access_token": "access-1",
                "expires_in": 3_600,
                "scope": CALENDAR_READ_SCOPE,
            }

        self.oauth.complete_oauth("owner-a", {"state": state, "code": "auth-code"}, exchange)
        with self.assertRaises(CalendarOAuthError) as caught:
            self.oauth.complete_oauth("owner-a", {"state": state, "code": "auth-code"}, exchange)
        self.assertEqual(caught.exception.reason, "missing_or_replayed_state")
        self.assertEqual(len(calls), 1, "a replayed callback reached the token endpoint")

    def test_failed_callback_still_consumes_the_state(self):
        _offer, state, _query = self.begin()
        with self.assertRaises(CalendarOAuthError):
            self.oauth.complete_oauth(
                "owner-a", {"state": state, "error": "access_denied"}, lambda request: {}
            )
        with self.assertRaises(CalendarOAuthError) as caught:
            self.oauth.complete_oauth(
                "owner-a", {"state": state, "code": "auth-code"}, lambda request: {}
            )
        self.assertEqual(caught.exception.reason, "missing_or_replayed_state")

    def test_tampered_state_signature_is_rejected(self):
        _offer, state, _query = self.begin()
        grant, nonce, signature = state.split(".")
        flipped = signature[:-1] + ("0" if signature[-1] != "0" else "1")
        reached = []
        with self.assertRaises(CalendarOAuthError) as caught:
            self.oauth.complete_oauth(
                "owner-a",
                {"state": f"{grant}.{nonce}.{flipped}", "code": "auth-code"},
                lambda request: reached.append(request) or {},
            )
        self.assertEqual(caught.exception.reason, "state_mismatch")
        self.assertEqual(reached, [])
        self.assertEqual(
            self.connector_state(CALENDAR_CONNECTOR_ID), ConnectorState.DISCONNECTED
        )

    def test_tampered_state_nonce_is_rejected(self):
        _offer, state, _query = self.begin()
        grant, nonce, signature = state.split(".")
        forged = ("A" if nonce[0] != "A" else "B") + nonce[1:]
        with self.assertRaises(CalendarOAuthError) as caught:
            self.oauth.complete_oauth(
                "owner-a", {"state": f"{grant}.{forged}.{signature}", "code": "auth-code"}, dict
            )
        self.assertEqual(caught.exception.reason, "state_mismatch")

    def test_state_from_another_owner_is_rejected(self):
        _offer_a, state_a, _q = self.begin("owner-a")
        self.begin("owner-b")
        reached = []
        with self.assertRaises(CalendarOAuthError) as caught:
            self.oauth.complete_oauth(
                "owner-b",
                {"state": state_a, "code": "auth-code"},
                lambda request: reached.append(request) or {},
            )
        self.assertEqual(caught.exception.reason, "state_mismatch")
        self.assertEqual(reached, [])
        self.assertEqual(
            self.connector_state(CALENDAR_CONNECTOR_ID, owner="owner-b"),
            ConnectorState.DISCONNECTED,
        )
        # Owner A's authorization is untouched by owner B's failed callback.
        self.oauth.complete_oauth(
            "owner-a",
            {"state": state_a, "code": "auth-code"},
            lambda request: {
                "access_token": "access-a",
                "expires_in": 3_600,
                "scope": CALENDAR_READ_SCOPE,
            },
        )
        self.assertEqual(
            self.connector_state(CALENDAR_CONNECTOR_ID, owner="owner-a"), ConnectorState.CONNECTED
        )

    def test_state_issued_for_the_other_grant_cannot_complete_this_one(self):
        _read_offer, read_state, _q1 = self.begin(write=False)
        _write_offer, write_state, _q2 = self.begin(write=True)
        self.assertTrue(read_state.startswith(READ_GRANT + "."))
        self.assertTrue(write_state.startswith(WRITE_GRANT + "."))
        _label, nonce, signature = read_state.split(".")
        relabelled = f"{WRITE_GRANT}.{nonce}.{signature}"
        reached = []
        with self.assertRaises(CalendarOAuthError) as caught:
            self.oauth.complete_oauth(
                "owner-a",
                {"state": relabelled, "code": "auth-code"},
                lambda request: reached.append(request) or {},
            )
        self.assertEqual(caught.exception.reason, "state_mismatch")
        self.assertEqual(reached, [])
        self.assertEqual(
            self.connector_state(CALENDAR_WRITE_CONNECTOR_ID), ConnectorState.DISCONNECTED
        )
        self.assertEqual(
            self.connector_state(CALENDAR_CONNECTOR_ID), ConnectorState.DISCONNECTED
        )

    def test_one_callback_route_resolves_each_grant_from_its_state_label(self):
        """The signed label is how a single callback tells the grants apart."""
        _read_offer, read_state, _q1 = self.begin(write=False)
        _write_offer, write_state, _q2 = self.begin(write=True)

        def exchange_for(scope):
            return lambda request: {
                "access_token": "access-" + scope[-5:],
                "expires_in": 3_600,
                "scope": scope,
            }

        # Deliberately complete the write authorization first: the route has no
        # out-of-band hint, only the state it was handed.
        self.oauth.complete_oauth(
            "owner-a", {"state": write_state, "code": "code-w"}, exchange_for(CALENDAR_WRITE_SCOPE)
        )
        self.assertEqual(
            self.connector_state(CALENDAR_WRITE_CONNECTOR_ID), ConnectorState.CONNECTED
        )
        self.assertEqual(
            self.connector_state(CALENDAR_CONNECTOR_ID), ConnectorState.DISCONNECTED
        )
        self.oauth.complete_oauth(
            "owner-a", {"state": read_state, "code": "code-r"}, exchange_for(CALENDAR_READ_SCOPE)
        )
        self.assertEqual(self.connector_state(CALENDAR_CONNECTOR_ID), ConnectorState.CONNECTED)
        self.assertEqual(
            self.store.secret(self.token_slot(READ_GRANT))["scope"], [CALENDAR_READ_SCOPE]
        )
        self.assertEqual(
            self.store.secret(self.token_slot(WRITE_GRANT))["scope"], [CALENDAR_WRITE_SCOPE]
        )

    def test_expired_state_is_refused_and_consumed(self):
        _offer, state, _query = self.begin()
        self.clock[0] += 601
        with self.assertRaises(CalendarOAuthError) as caught:
            self.oauth.complete_oauth("owner-a", {"state": state, "code": "auth-code"}, dict)
        self.assertEqual(caught.exception.reason, "state_expired")
        self.clock[0] -= 601
        with self.assertRaises(CalendarOAuthError) as caught:
            self.oauth.complete_oauth("owner-a", {"state": state, "code": "auth-code"}, dict)
        self.assertEqual(caught.exception.reason, "missing_or_replayed_state")


class AuthorizationRequestTests(CalendarOAuthTestCase):
    def test_pkce_challenge_is_the_s256_digest_of_the_sent_verifier(self):
        _offer, state, query = self.begin()
        challenge = query["code_challenge"][0]
        self.assertEqual(query["code_challenge_method"], ["S256"])
        seen = []
        self.oauth.complete_oauth(
            "owner-a",
            {"state": state, "code": "auth-code"},
            lambda request: seen.append(request)
            or {"access_token": "a", "expires_in": 60, "scope": CALENDAR_READ_SCOPE},
        )
        verifier = seen[0]["code_verifier"]
        self.assertRegex(verifier, r"\A[A-Za-z0-9._~-]{43,128}\Z")
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        self.assertEqual(challenge, expected.decode().rstrip("="))
        self.assertNotEqual(challenge, verifier)

    def test_authorization_request_is_offline_and_never_widens_the_grant(self):
        _read_offer, _read_state, read_query = self.begin()
        self.assertTrue(
            _read_offer["authorization_url"].startswith(AUTHORIZATION_ENDPOINT + "?")
        )
        self.assertEqual(read_query["access_type"], ["offline"])
        self.assertEqual(read_query["include_granted_scopes"], ["false"])
        self.assertEqual(read_query["scope"], [CALENDAR_READ_SCOPE])
        self.assertEqual(read_query["redirect_uri"], ["https://connect.example.test/calendar/callback"])
        _write_offer, _write_state, write_query = self.begin(write=True)
        self.assertEqual(write_query["scope"], [CALENDAR_WRITE_SCOPE])
        self.assertEqual(_write_offer["grant"], WRITE_GRANT)
        self.assertEqual(_read_offer["connector_id"], CALENDAR_CONNECTOR_ID)
        self.assertEqual(_write_offer["connector_id"], CALENDAR_WRITE_CONNECTOR_ID)

    def test_begin_refuses_an_already_connected_grant(self):
        self.connect()
        consumed = self.store.secret(self.pending_slot(READ_GRANT))
        self.assertEqual(consumed, {"status": "used"})
        with self.assertRaises(CalendarOAuthError) as caught:
            self.oauth.begin_oauth("owner-a")
        self.assertEqual(caught.exception.reason, "already_connected")
        # The refusal happens before any new pending authorization is written,
        # so a live connection cannot be displaced by an unwanted redirect.
        self.assertEqual(self.store.secret(self.pending_slot(READ_GRANT)), {"status": "used"})


class TransportTests(CalendarOAuthTestCase):
    def test_access_token_is_resolved_inside_each_call(self):
        self.connect(access_token="access-1", refresh_token="refresh-1")
        opener, calls = self.recording_opener([{"items": []}, {"items": []}])
        transport = calendar_transport(
            self.store, self.registry, "owner-a", opener=opener, now=lambda: self.clock[0]
        )
        transport("GET", EVENTS_URL, None, {})
        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer access-1")

        self.oauth.refresh(
            "owner-a",
            lambda request: {
                "access_token": "access-2",
                "expires_in": 3_600,
                "scope": CALENDAR_READ_SCOPE,
            },
        )
        # Same transport object, built before the refresh.
        transport("GET", EVENTS_URL, None, {})
        self.assertEqual(calls[1]["headers"]["Authorization"], "Bearer access-2")
        self.assertEqual(len(calls), 2)

    def test_expired_access_token_is_not_presented_and_forces_reauth(self):
        self.connect(access_token="access-1", expires_in=60)
        opener, calls = self.recording_opener([{"items": []}])
        transport = calendar_transport(
            self.store, self.registry, "owner-a", opener=opener, now=lambda: self.clock[0]
        )
        self.clock[0] += 61
        with self.assertRaises(CalendarReauthenticationRequired):
            transport("GET", EVENTS_URL, None, {})
        self.assertEqual(calls, [])
        self.assertEqual(
            self.connector_state(CALENDAR_CONNECTOR_ID), ConnectorState.REAUTH_REQUIRED
        )

    def test_transport_refuses_every_mutation_method_before_resolving_a_token(self):
        self.connect()
        opener, calls = self.recording_opener([{"id": "evt"}, {"id": "evt"}, {}])
        transport = calendar_transport(
            self.store, self.registry, "owner-a", opener=opener, now=lambda: self.clock[0]
        )
        for method, body in (("POST", {"summary": "x"}), ("PATCH", {"summary": "x"}), ("DELETE", None)):
            with self.assertRaises(CalendarOAuthError) as caught:
                transport(method, CALENDAR_API + "/calendars/primary/events", body, {})
            self.assertEqual(caught.exception.reason, "mutation_not_permitted")
        self.assertEqual(calls, [], "a mutation reached the injected opener")

    def test_transport_refuses_a_destination_outside_the_calendar_api(self):
        self.connect()
        opener, calls = self.recording_opener([{"items": []}])
        transport = calendar_transport(
            self.store, self.registry, "owner-a", opener=opener, now=lambda: self.clock[0]
        )
        for url in (
            "https://calendar.evil.test/calendar/v3/calendars/primary/events",
            "http://www.googleapis.com/calendar/v3/calendars/primary/events",
            CALENDAR_API.replace("https://", "https://user:pw@") + "/calendars/primary/events",
        ):
            with self.assertRaises(CalendarOAuthError) as caught:
                transport("GET", url, None, {})
            self.assertEqual(caught.exception.reason, "unsupported_destination")
        self.assertEqual(calls, [], "a bearer token was sent to a foreign destination")

    def test_a_write_grant_alone_does_not_satisfy_the_read_transport(self):
        self.connect(write=True, access_token="write-access")
        opener, calls = self.recording_opener([{"items": []}])
        transport = calendar_transport(
            self.store, self.registry, "owner-a", opener=opener, now=lambda: self.clock[0]
        )
        with self.assertRaises(CalendarOAuthError) as caught:
            transport("GET", EVENTS_URL, None, {})
        self.assertEqual(caught.exception.reason, "connection_required")
        self.assertEqual(calls, [])
        self.assertEqual(
            self.connector_state(CALENDAR_WRITE_CONNECTOR_ID), ConnectorState.CONNECTED
        )

    def test_provider_401_marks_the_connection_as_needing_reauthentication(self):
        self.connect(access_token="access-1")
        opener, calls = self.recording_opener([GoogleCalendarHTTPError(401)])
        transport = calendar_transport(
            self.store, self.registry, "owner-a", opener=opener, now=lambda: self.clock[0]
        )
        with self.assertRaises(GoogleCalendarHTTPError):
            transport("GET", EVENTS_URL, None, {})
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            self.connector_state(CALENDAR_CONNECTOR_ID), ConnectorState.REAUTH_REQUIRED
        )
        self.assertEqual(self.store.secret(self.token_slot(READ_GRANT)), {})
        with self.assertRaises(CalendarReauthenticationRequired):
            transport("GET", EVENTS_URL, None, {})
        self.assertEqual(len(calls), 1, "a revoked connection still reached the provider")

    def test_google_calendar_query_runs_on_this_transport_and_maps_401(self):
        self.connect(access_token="access-1")
        payload = {
            "items": [
                {
                    "id": "evt-1",
                    "etag": "etag-1",
                    "summary": "Review",
                    "start": {"dateTime": "2026-09-22T09:00:00+09:00"},
                    "end": {"dateTime": "2026-09-22T10:00:00+09:00"},
                    "status": "confirmed",
                }
            ]
        }
        opener, calls = self.recording_opener([payload, GoogleCalendarHTTPError(401)])
        provider = GoogleCalendar(
            calendar_transport(
                self.store, self.registry, "owner-a", opener=opener, now=lambda: self.clock[0]
            ),
            access_token=None,
        )
        events = provider.query(
            "2026-09-22T09:00:00+09:00", "2026-09-22T18:00:00+09:00", "Asia/Seoul", 5
        )
        self.assertEqual([event["id"] for event in events], ["evt-1"])
        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer access-1")
        with self.assertRaises(GoogleCalendarError) as caught:
            provider.query(
                "2026-09-22T09:00:00+09:00", "2026-09-22T18:00:00+09:00", "Asia/Seoul", 5
            )
        self.assertEqual(caught.exception.reason, "scope-expired")
        self.assertEqual(
            self.connector_state(CALENDAR_CONNECTOR_ID), ConnectorState.REAUTH_REQUIRED
        )

    def test_a_rotated_connection_invalidates_an_in_flight_response(self):
        self.connect(access_token="access-1")
        registry = self.registry

        def opener(method, url, body, headers):
            # The owner reconnects while this request is in flight.
            registry.transition(
                "owner-a",
                CALENDAR_CONNECTOR_ID,
                ConnectorState.CONNECTED,
                granted_scopes=(CALENDAR_READ_SCOPE,),
            )
            return {"items": []}

        transport = calendar_transport(
            self.store, self.registry, "owner-a", opener=opener, now=lambda: self.clock[0]
        )
        with self.assertRaises(CalendarOAuthError) as caught:
            transport("GET", EVENTS_URL, None, {})
        self.assertEqual(caught.exception.reason, "superseded_connection")


class SecretBoundaryTests(CalendarOAuthTestCase):
    def test_calendar_secrets_are_not_reachable_through_a_gmail_key(self):
        gmail_store = EncryptedGmailSecretStore(self.raw_store, self.key)
        self.store.secret("oauth_tokens", {"access_token": "calendar-token"})
        gmail_store.secret("oauth_tokens", {"access_token": "gmail-token"})

        self.assertEqual(
            self.store.secret("oauth_tokens"), {"access_token": "calendar-token"}
        )
        self.assertEqual(gmail_store.secret("oauth_tokens"), {"access_token": "gmail-token"})
        # A key that spells the other namespace stays inside this one.
        self.assertEqual(self.store.secret("encrypted:gmail:oauth_tokens"), "")
        self.assertEqual(gmail_store.secret("encrypted:calendar:oauth_tokens"), "")

        raw = json.loads(pathlib.Path(self.raw_store.secret_path).read_text())
        self.assertIn("encrypted:calendar:oauth_tokens", raw)
        self.assertIn("encrypted:gmail:oauth_tokens", raw)
        self.assertNotEqual(
            raw["encrypted:calendar:oauth_tokens"], raw["encrypted:gmail:oauth_tokens"]
        )

    def test_a_real_calendar_token_is_invisible_to_the_gmail_store(self):
        self.connect(access_token="calendar-access-secret")
        gmail_store = EncryptedGmailSecretStore(self.raw_store, self.key)
        owner_hash = hashlib.sha256(b"owner-a").hexdigest()
        for key in (
            f"{TOKEN_SECRET_KEY}:{CALENDAR_CONNECTOR_ID}:{owner_hash}",
            f"{PENDING_SECRET_KEY}:{CALENDAR_CONNECTOR_ID}:{owner_hash}",
        ):
            self.assertEqual(gmail_store.secret(key), "")

    def test_unreadable_ciphertext_revokes_authority_instead_of_reporting_it(self):
        self.connect()
        other = EncryptedCalendarSecretStore(self.raw_store, Fernet.generate_key())
        transport = calendar_transport(
            other, self.registry, "owner-a", opener=lambda *a: {}, now=lambda: self.clock[0]
        )
        with self.assertRaises(CalendarReauthenticationRequired):
            transport("GET", EVENTS_URL, None, {})
        self.assertEqual(
            self.connector_state(CALENDAR_CONNECTOR_ID), ConnectorState.REAUTH_REQUIRED
        )


class ClientSecretBoundaryTests(CalendarOAuthTestCase):
    SECRET = "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t"

    def stored_bytes(self):
        blobs = []
        for path in (self.raw_store.secret_path, self.raw_store.path):
            candidate = pathlib.Path(path)
            if candidate.exists():
                blobs.append(candidate.read_bytes())
        return b"".join(blobs)

    def test_a_failing_token_exchange_never_echoes_the_client_secret(self):
        _offer, state, _query = self.begin()

        def exchange(request):
            # The client secret belongs to the owner-local exchange, not here.
            self.assertNotIn(self.SECRET, json.dumps(request))
            raise RuntimeError(f"token endpoint refused client_secret={self.SECRET}")

        with self.assertRaises(CalendarOAuthError) as caught:
            self.oauth.complete_oauth("owner-a", {"state": state, "code": "auth-code"}, exchange)
        error = caught.exception
        rendered = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        for text in (str(error), repr(error), error.reason, rendered):
            self.assertNotIn(self.SECRET, text)
        self.assertIsNone(error.__cause__)
        self.assertNotIn(self.SECRET.encode(), self.stored_bytes())

    def test_a_token_response_carrying_the_client_secret_does_not_persist_it(self):
        _offer, state, _query = self.begin()
        status = self.oauth.complete_oauth(
            "owner-a",
            {"state": state, "code": "auth-code"},
            lambda request: {
                "access_token": "access-1",
                "refresh_token": "refresh-1",
                "expires_in": 3_600,
                "scope": CALENDAR_READ_SCOPE,
                "client_secret": self.SECRET,
                "id_token": self.SECRET,
            },
        )
        self.assertNotIn(self.SECRET, json.dumps(status))
        self.assertNotIn(self.SECRET, json.dumps(self.oauth.status("owner-a", write=True)))
        tokens = self.store.secret(self.token_slot(READ_GRANT))
        self.assertEqual(
            sorted(tokens),
            ["access_token", "expires_at", "grant", "owner", "refresh_token", "scope"],
        )
        self.assertNotIn(self.SECRET, json.dumps(tokens))
        self.assertNotIn(self.SECRET.encode(), self.stored_bytes())

    def test_status_and_offer_expose_no_credential_material(self):
        offer, state, _query = self.begin()
        self.assertNotIn("verifier", json.dumps(offer))
        self.assertNotIn(state.split(".")[2], json.dumps(self.oauth.status("owner-a")))
        self.connect(access_token="access-secret-value")
        self.assertNotIn("access-secret-value", json.dumps(self.oauth.status("owner-a")))


class InertnessTests(CalendarOAuthTestCase):
    def test_wiring_a_route_registers_definitions_but_grants_nothing(self):
        """Importing this module is inert; constructing the route defines only.

        The first assertion is structural (registration is per-registry, so an
        import cannot reach a registry instance). The rest is behavioural: the
        route must register both definitions - otherwise Work would be refused
        with ``unknown_connector`` - while leaving every owner row absent.
        """
        registry = ConnectorRegistry(self.store, (), clock=lambda: self.clock[0])
        with self.assertRaises(ConnectorContractError):
            registry.status("owner-a", CALENDAR_CONNECTOR_ID)

        CalendarOAuth(
            self.store,
            "calendar-client",
            "https://connect.example.test/calendar/callback",
            registry=registry,
            now=lambda: self.clock[0],
        )
        for connector_id in (CALENDAR_CONNECTOR_ID, CALENDAR_WRITE_CONNECTOR_ID):
            status = registry.status("owner-a", connector_id)
            self.assertEqual(status.state, ConnectorState.DISCONNECTED)
            self.assertEqual(status.granted_scopes, ())
            self.assertIsNone(status.connection_revision)
        self.assertIsNone(self.raw_store.config("connector_contract_state", None))

    def test_the_module_never_constructs_the_calendar_policy_connector(self):
        source = pathlib.Path(calendar_oauth_module.__file__).read_text()
        self.assertNotIn("CalendarConnector(", source)
        self.assertIsNone(getattr(calendar_oauth_module, "CalendarConnector", None))



class CredentialCurrentTests(CalendarOAuthTestCase):
    """#506 / PR #584: per-grant read-only expiry check with no transition."""

    def test_each_grant_is_checked_locally_and_independently(self):
        self.connect(expires_in=60)
        self.connect(write=True, expires_in=3_600)
        self.assertTrue(self.oauth.credential_current("owner-a"))
        self.clock[0] += 61
        before = self.raw_store.config("connector_contract_state")
        self.assertFalse(self.oauth.credential_current("owner-a"))
        self.assertTrue(self.oauth.credential_current("owner-a", write=True))
        self.assertEqual(self.connector_state(CALENDAR_CONNECTOR_ID).value, "connected", "the check records nothing")
        self.assertEqual(self.raw_store.config("connector_contract_state"), before)

if __name__ == "__main__":
    unittest.main()

import base64
import hashlib
import pathlib
import re
import tempfile
import threading
import unittest
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

from personal_agent import gmail as gmail_module
from personal_agent.connector_contract import ConnectorRegistry, ConnectorState
from personal_agent.gmail import (
    GMAIL_CONNECTOR,
    GMAIL_CONNECTOR_ID,
    GMAIL_READONLY_SCOPE,
    MESSAGES_ENDPOINT,
    EncryptedGmailSecretStore,
    GmailConnector,
    GmailError,
    GmailReauthenticationRequired,
    _assert_renderable_charset,
    _parsed_mime_header,
)
from personal_agent.quickstart_store import QuickStore


class GmailConnectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.key = Fernet.generate_key()
        self.raw_store = QuickStore(self.temp.name)
        self.store = EncryptedGmailSecretStore(self.raw_store, self.key)
        self.clock = [1000.0]
        self.calls = []
        self.responses = []

        def transport(method, endpoint, params, headers):
            self.calls.append((method, endpoint, params, headers))
            if not self.responses:
                raise AssertionError("unexpected Gmail transport call")
            return self.responses.pop(0)

        self.registry = ConnectorRegistry(self.store, (GMAIL_CONNECTOR,), clock=lambda: self.clock[0])
        self.gmail = GmailConnector(
            self.store,
            "gmail-client",
            "https://connect.example.test/gmail/callback",
            registry=self.registry,
            transport=transport,
            now=lambda: self.clock[0],
        )

    def tearDown(self):
        # Every provider call recorded anywhere in this suite must be a read.
        # This is an observed-call assertion, unlike checking that invented
        # method names are absent, which passes for any object.
        self.assertEqual(
            sorted({call[0] for call in self.calls}) or ["GET"],
            ["GET"],
            "a non-GET Gmail provider call was recorded",
        )
        self.temp.cleanup()

    def begin(self, owner="owner-a"):
        offer = self.gmail.begin_oauth(owner)
        state = parse_qs(urlparse(offer["authorization_url"]).query)["state"][0]
        return offer, state

    def connect(self, owner="owner-a", access_token="access-secret", refresh_token="refresh-secret"):
        _offer, state = self.begin(owner)
        seen = []

        def exchange(request):
            seen.append(request)
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": 60,
                "scope": GMAIL_READONLY_SCOPE,
            }

        result = self.gmail.complete_oauth(owner, {"state": state, "code": "oauth-code"}, exchange)
        return result, seen[0]

    def read(self, message_id="m_1", owner="owner-a"):
        return self.gmail.read_message(
            owner,
            message_id,
            expected_connection_revision=self.gmail.status(owner)["connection_revision"],
        )

    @staticmethod
    def secret_key(prefix, owner="owner-a"):
        return f"{prefix}:{hashlib.sha256(owner.encode()).hexdigest()}"

    @staticmethod
    def metadata(message_id="m_1", thread_id="t_1"):
        return {
            "id": message_id,
            "threadId": thread_id,
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Booking receipt"},
                    {"name": "From", "value": "Vendor <vendor@example.test>"},
                    {"name": "Date", "value": "Mon, 1 Sep 2026 10:00:00 +0000"},
                ]
            },
        }

    def test_disconnected_offer_is_owner_bound_redacted_and_minimum_scope_pkce(self):
        self.assertEqual(
            self.gmail.connection_required("owner-a"),
            {
                "result": "connection_required",
                "connector_id": GMAIL_CONNECTOR_ID,
                "required_scopes": [GMAIL_READONLY_SCOPE],
                "recovery": "connect",
            },
        )
        offer, _state = self.begin()
        query = parse_qs(urlparse(offer["authorization_url"]).query)
        self.assertEqual(query["scope"], [GMAIL_READONLY_SCOPE])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["include_granted_scopes"], ["false"])
        self.assertNotIn("code_verifier", query)
        self.assertNotIn("owner-a", str(offer))
        self.assertNotIn("token", str(self.gmail.portable_status("owner-a")).lower())
        self.assertEqual(self.gmail.status("owner-b")["state"], "disconnected")

    def test_callback_uses_exact_pkce_exchange_and_separate_gmail_authority(self):
        result, request = self.connect()
        self.assertEqual(result["state"], "connected")
        self.assertEqual(
            set(request),
            {"code", "code_verifier", "redirect_uri", "client_id", "grant_type"},
        )
        self.assertEqual(request["grant_type"], "authorization_code")
        self.assertNotEqual(request["code_verifier"], "oauth-code")
        self.assertEqual(result["granted_scopes"], [GMAIL_READONLY_SCOPE])
        self.assertNotIn("drive", str(result).lower())
        self.assertNotIn("calendar", str(result).lower())

    def test_oauth_state_tamper_wrong_owner_expiry_and_replay_fail_closed(self):
        _offer, state = self.begin()
        with self.assertRaisesRegex(GmailError, "rejected") as wrong_owner:
            self.gmail.complete_oauth("owner-b", {"state": state, "code": "code"}, lambda _: {})
        self.assertEqual(wrong_owner.exception.reason, "missing_or_replayed_state")
        with self.assertRaises(GmailError) as tampered:
            self.gmail.complete_oauth("owner-a", {"state": state + "x", "code": "code"}, lambda _: {})
        self.assertEqual(tampered.exception.reason, "state_mismatch")
        with self.assertRaises(GmailError) as non_ascii:
            self.gmail.complete_oauth("owner-a", {"state": "상태", "code": "code"}, lambda _: {})
        self.assertEqual(non_ascii.exception.reason, "state_mismatch")

        self.clock[0] += 601
        with self.assertRaises(GmailError) as expired:
            self.gmail.complete_oauth("owner-a", {"state": state, "code": "code"}, lambda _: {})
        self.assertEqual(expired.exception.reason, "state_expired")
        with self.assertRaises(GmailError) as replay:
            self.gmail.complete_oauth("owner-a", {"state": state, "code": "code"}, lambda _: {})
        self.assertEqual(replay.exception.reason, "missing_or_replayed_state")
        self.assertEqual(self.gmail.status("owner-a")["state"], "disconnected")

    def test_successful_callback_is_single_use_and_rejects_wider_or_wrong_scope(self):
        _result, request = self.connect()
        pending = self.store.secret(self.secret_key("gmail_oauth_pending"))
        self.assertEqual(pending, {"status": "used"})
        with self.assertRaises(GmailError):
            self.gmail.complete_oauth("owner-a", {"state": "replay", "code": "again"}, lambda _: {})
        self.assertNotIn("access-secret", str(self.gmail.status("owner-a")))
        self.assertNotIn("refresh-secret", str(self.gmail.portable_status("owner-a")))
        self.assertNotIn(request["code_verifier"], str(self.gmail.status("owner-a")))

        other_temp = tempfile.TemporaryDirectory()
        self.addCleanup(other_temp.cleanup)
        other_raw = QuickStore(other_temp.name)
        other_store = EncryptedGmailSecretStore(other_raw, Fernet.generate_key())
        other = GmailConnector(
            other_store,
            "client",
            "https://connect.example.test/callback",
            now=lambda: self.clock[0],
        )
        _offer, state = (
            lambda value: (value, parse_qs(urlparse(value["authorization_url"]).query)["state"][0])
        )(other.begin_oauth("owner-a"))
        with self.assertRaises(GmailError):
            other.complete_oauth(
                "owner-a",
                {"state": state, "code": "code"},
                lambda _: {
                    "access_token": "secret",
                    "expires_in": 60,
                    "scope": GMAIL_READONLY_SCOPE + " https://www.googleapis.com/auth/gmail.modify",
                },
            )
        self.assertEqual(other.status("owner-a")["state"], "disconnected")

    def test_callback_cannot_restore_authority_changed_after_oauth_started(self):
        for changed_state in (ConnectorState.BLOCKED, ConnectorState.DISCONNECTED):
            with self.subTest(changed_state=changed_state):
                self.registry.transition("owner-a", GMAIL_CONNECTOR_ID, ConnectorState.DISCONNECTED)
                _offer, state = self.begin()
                self.registry.transition("owner-a", GMAIL_CONNECTOR_ID, changed_state)
                exchanges = []
                with self.assertRaises(GmailError) as rejected:
                    self.gmail.complete_oauth(
                        "owner-a",
                        {"state": state, "code": "oauth-code"},
                        lambda request: exchanges.append(request) or {
                            "access_token": "must-not-survive",
                            "refresh_token": "must-not-survive",
                            "expires_in": 60,
                            "scope": GMAIL_READONLY_SCOPE,
                        },
                    )
                self.assertEqual(rejected.exception.reason, "connector_authority_changed")
                self.assertEqual(exchanges, [])
                self.assertEqual(self.gmail.status("owner-a")["state"], changed_state.value)
                self.assertFalse(self.store.secret(self.secret_key("gmail_oauth_tokens")))

    def test_late_reauthentication_signal_preserves_owner_block(self):
        self.connect()
        prior = self.gmail.status("owner-a")["connection_revision"]
        self.registry.transition("owner-a", GMAIL_CONNECTOR_ID, ConnectorState.BLOCKED)
        result = self.gmail.mark_reauthentication_required(
            "owner-a",
            expected_revision=prior,
        )
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(self.gmail.status("owner-a")["state"], "blocked")

    def test_plaintext_store_and_implicit_insecure_callback_are_rejected(self):
        with self.assertRaises(ValueError):
            GmailConnector(self.raw_store, "client", "https://connect.example.test/callback")
        with self.assertRaises(ValueError):
            GmailConnector(self.store, "client", "http://localhost:8787/callback")
        local = GmailConnector(
            self.store,
            "client",
            "http://127.0.0.1:8787/callback",
            allow_localhost=True,
        )
        self.assertEqual(local.status("owner-a")["connector_id"], GMAIL_CONNECTOR_ID)

    def test_search_is_bounded_metadata_only_with_exact_get_endpoints_and_parameters(self):
        self.connect()
        self.responses.extend(
            [
                {"messages": [{"id": "m_1", "threadId": "ignored"}]},
                self.metadata(),
            ]
        )
        results = self.gmail.search("owner-a", "newer_than:30d booking", max_results=3)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].subject, "Booking receipt")
        self.assertEqual(results[0].source["message_id"], "m_1")
        self.assertEqual(
            results[0].source["connection_revision"],
            self.gmail.status("owner-a")["connection_revision"],
        )
        self.assertEqual(
            [(call[0], call[1], call[2]) for call in self.calls],
            [
                (
                    "GET",
                    MESSAGES_ENDPOINT,
                    {"q": "newer_than:30d booking", "maxResults": 3, "includeSpamTrash": False},
                ),
                (
                    "GET",
                    MESSAGES_ENDPOINT + "/m_1",
                    {"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
                ),
            ],
        )
        self.assertTrue(all(call[0] == "GET" for call in self.calls))
        self.assertTrue(all(set(call[2]).isdisjoint({"addLabelIds", "removeLabelIds", "raw"}) for call in self.calls))

    def test_search_decodes_bounded_rfc2047_metadata_headers(self):
        self.connect()
        encoded = self.metadata()
        encoded["payload"]["headers"][0]["value"] = "=?UTF-8?B?7JWI64WV?="
        encoded["payload"]["headers"][1]["value"] = "=?UTF-8?B?7JWI64WV?= <vendor@example.test>"
        self.responses.extend([{"messages": [{"id": "m_1"}]}, encoded])
        result = self.gmail.search("owner-a", "booking")[0]
        self.assertEqual(result.subject, "안녕")
        self.assertEqual(result.sender, "안녕 <vendor@example.test>")

    def test_search_bounds_malformed_rfc2047_parser_errors(self):
        self.connect()
        malformed = self.metadata()
        malformed["payload"]["headers"][0]["value"] = "=?utf-8?b?a?="
        self.responses.extend([{"messages": [{"id": "m_1"}]}, malformed])
        with self.assertRaises(GmailError) as rejected:
            self.gmail.search("owner-a", "receipt")
        self.assertEqual(rejected.exception.reason, "invalid_provider_response")

    def test_search_rejects_metadata_header_list_overflow(self):
        self.connect()
        overflow = self.metadata()
        overflow["payload"]["headers"] = [
            {"name": "X-Unrelated", "value": str(index)} for index in range(100)
        ] + [{"name": "Subject", "value": "Must not be silently omitted"}]
        self.responses.extend([{"messages": [{"id": "m_1"}]}, overflow])
        with self.assertRaises(GmailError) as rejected:
            self.gmail.search("owner-a", "receipt")
        self.assertEqual(rejected.exception.reason, "invalid_provider_response")

    def test_search_rejects_duplicate_singleton_metadata_headers(self):
        self.connect()
        for name in ("Subject", "From", "Date"):
            with self.subTest(name=name):
                duplicate=self.metadata()
                duplicate["payload"]["headers"].append({"name":name.swapcase(),"value":"ambiguous"})
                self.responses.extend([{"messages":[{"id":"m_1"}]},duplicate])
                with self.assertRaises(GmailError) as rejected:
                    self.gmail.search("owner-a","receipt")
                self.assertEqual(rejected.exception.reason,"invalid_provider_response")

    def test_search_limits_and_provider_over_return_are_bounded(self):
        self.connect()
        for invalid in (0, 21, True):
            with self.assertRaises(GmailError):
                self.gmail.search("owner-a", "receipt", max_results=invalid)
        with self.assertRaises(GmailError):
            self.gmail.search("owner-a", "x" * 513)
        self.responses.extend(
            [
                {"messages": [{"id": "m_1"}, {"id": "m_2"}]},
                self.metadata("m_1", "t_1"),
            ]
        )
        results = self.gmail.search("owner-a", "receipt", max_results=1)
        self.assertEqual([item.message_id for item in results], ["m_1"])

    def test_search_rechecks_authority_before_each_metadata_request(self):
        self.connect()
        calls = []

        def revoke_after_list(method, endpoint, params, headers):
            calls.append((method, endpoint, params, headers))
            self.registry.transition("owner-a", GMAIL_CONNECTOR_ID, ConnectorState.DISCONNECTED)
            return {"messages": [{"id": "m_1"}]}

        self.gmail.transport = revoke_after_list
        with self.assertRaises(GmailError) as revoked:
            self.gmail.search("owner-a", "receipt")
        self.assertEqual(revoked.exception.reason, "superseded_connection")
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.gmail.status("owner-a")["state"], "disconnected")

    def test_search_discards_metadata_when_authority_changes_during_parsing(self):
        self.connect()
        self.responses.extend([{"messages": [{"id": "m_1"}]}, self.metadata()])
        original = self.gmail._search_result

        def revoke_during_parse(message_id, metadata, connection_revision):
            result = original(message_id, metadata, connection_revision)
            self.registry.transition("owner-a", GMAIL_CONNECTOR_ID, ConnectorState.BLOCKED)
            return result

        self.gmail._search_result = revoke_during_parse
        with self.assertRaises(GmailError) as revoked:
            self.gmail.search("owner-a", "receipt")
        self.assertEqual(revoked.exception.reason, "superseded_connection")
        self.assertEqual(self.gmail.status("owner-a")["state"], "blocked")

    def test_inflight_success_is_discarded_after_authority_revocation(self):
        self.connect()

        def revoke_during_read(_method, _endpoint, _params, _headers):
            self.registry.transition("owner-a", GMAIL_CONNECTOR_ID, ConnectorState.BLOCKED)
            return {
                "id": "m_1",
                "threadId": "t_1",
                "payload": {
                    "mimeType": "text/plain",
                    "body": {"data": base64.urlsafe_b64encode(b"must not escape").decode()},
                },
            }

        self.gmail.transport = revoke_during_read
        with self.assertRaises(GmailError) as revoked:
            self.read()
        self.assertEqual(revoked.exception.reason, "superseded_connection")
        self.assertEqual(self.gmail.status("owner-a")["state"], "blocked")

    def test_body_is_discarded_when_authority_changes_during_final_parsing(self):
        self.connect()
        self.responses.append(
            {
                "id": "m_1",
                "threadId": "t_1",
                "payload": {"mimeType": "text/plain", "body": {"data": "cHJpdmF0ZQ=="}},
            }
        )
        original_body = self.gmail._body

        def revoke_during_parse(payload, attachment_loader=None):
            parsed = original_body(payload, attachment_loader)
            self.registry.transition("owner-a", GMAIL_CONNECTOR_ID, ConnectorState.BLOCKED)
            return parsed

        self.gmail._body = revoke_during_parse
        with self.assertRaises(GmailError) as revoked:
            self.read()
        self.assertEqual(revoked.exception.reason, "superseded_connection")
        self.assertEqual(self.gmail.status("owner-a")["state"], "blocked")

    def test_expiry_during_provider_call_discards_response_and_stops_followups(self):
        self.connect()
        calls = []

        def expire_during_list(method, endpoint, params, headers):
            calls.append((method, endpoint, params, headers))
            self.clock[0] += 61
            return {"messages": [{"id": "m_1"}]}

        self.gmail.transport = expire_during_list
        with self.assertRaises(GmailReauthenticationRequired):
            self.gmail.search("owner-a", "receipt")
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.gmail.status("owner-a")["state"], "reauth_required")

    def test_explicit_body_read_is_source_attributable_ephemeral_and_get_only(self):
        self.connect()
        encoded = base64.urlsafe_b64encode(b"private mail body").rstrip(b"=").decode()
        self.responses.append(
            {
                "id": "m_1",
                "threadId": "t_1",
                "payload": {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {"mimeType": "text/html", "body": {"data": base64.urlsafe_b64encode(b"<p>html</p>").decode()}},
                        {"mimeType": "text/plain", "body": {"data": encoded}},
                    ],
                },
            }
        )
        message = self.read()
        self.assertEqual(message.body, "private mail body")
        self.assertEqual(message.mime_type, "text/plain")
        self.assertEqual(message.source["message_id"], "m_1")
        self.assertEqual(
            message.source["connection_revision"],
            self.gmail.status("owner-a")["connection_revision"],
        )
        self.assertEqual(message.as_evidence(), {"source": message.source, "body_included": False})
        self.assertNotIn("private mail body", repr(message))
        self.assertNotIn("private mail body", str(self.gmail.portable_status("owner-a")))
        self.assertEqual(self.calls[-1][0:3], ("GET", MESSAGES_ENDPOINT + "/m_1", {"format": "full"}))
        self.assertNotIn("private mail body", str(self.raw_store.config("connector_contract_state")))

    def test_source_identity_changes_when_owner_reconnects(self):
        self.connect(access_token="first-access", refresh_token="first-refresh")
        first_revision = self.gmail.status("owner-a")["connection_revision"]
        self.responses.extend([{"messages": [{"id": "m_1"}]}, self.metadata()])
        first = self.gmail.search("owner-a", "receipt")[0]

        self.registry.transition("owner-a", GMAIL_CONNECTOR_ID, ConnectorState.DISCONNECTED)
        self.connect(access_token="second-access", refresh_token="second-refresh")
        second_revision = self.gmail.status("owner-a")["connection_revision"]
        self.responses.extend([{"messages": [{"id": "m_1"}]}, self.metadata()])
        second = self.gmail.search("owner-a", "receipt")[0]

        self.assertNotEqual(first_revision, second_revision)
        self.assertEqual(first.source["connection_revision"], first_revision)
        self.assertEqual(second.source["connection_revision"], second_revision)

    def test_explicit_read_rejects_stale_search_source_before_transport(self):
        self.connect(access_token="first-access", refresh_token="first-refresh")
        stale_revision = self.gmail.status("owner-a")["connection_revision"]
        self.registry.transition("owner-a", GMAIL_CONNECTOR_ID, ConnectorState.DISCONNECTED)
        self.connect(access_token="second-access", refresh_token="second-refresh")
        calls_before = len(self.calls)

        with self.assertRaises(GmailError) as stale:
            self.gmail.read_message(
                "owner-a",
                "m_1",
                expected_connection_revision=stale_revision,
            )

        self.assertEqual(stale.exception.reason, "superseded_connection")
        self.assertEqual(len(self.calls), calls_before)

    def test_body_traversal_is_bounded_by_all_visited_nodes(self):
        self.connect()
        shared = {"mimeType": "multipart/mixed", "parts": []}
        shared["parts"] = [shared] * 100
        self.responses.append(
            {
                "id": "m_1",
                "threadId": "t_1",
                "payload": {"mimeType": "multipart/mixed", "parts": [shared] * 100},
            }
        )

        with self.assertRaises(GmailError) as bounded:
            self.read()
        self.assertEqual(bounded.exception.reason, "message_too_complex")

    def test_oversized_mime_tree_never_returns_a_partial_body(self):
        self.connect()
        self.responses.append(
            {
                "id": "m_1",
                "threadId": "t_1",
                "payload": {
                    "mimeType": "multipart/mixed",
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {"data": base64.urlsafe_b64encode(b"partial").decode()},
                        }
                    ] + [{"mimeType": "application/octet-stream", "body": {}} for _ in range(100)],
                },
            }
        )
        with self.assertRaises(GmailError) as bounded:
            self.read()
        self.assertEqual(bounded.exception.reason, "message_too_complex")

    def test_body_ignores_text_attachments_and_honors_declared_charset(self):
        self.connect()
        html = "<p>café</p>".encode("iso-8859-1")
        attachment = base64.urlsafe_b64encode(b"attachment text").decode()
        self.responses.append(
            {
                "id": "m_1",
                "threadId": "t_1",
                "payload": {
                    "mimeType": "multipart/mixed",
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "filename": "notes.txt",
                            "headers": [
                                {"name": "Content-Disposition", "value": "attachment; filename=notes.txt"}
                            ],
                            "body": {"data": attachment},
                        },
                        {
                            "mimeType": "text/html",
                            "headers": [
                                {"name": "Content-Type", "value": "text/html; charset=iso-8859-1"}
                            ],
                            "body": {"data": base64.urlsafe_b64encode(html).decode()},
                        },
                    ],
                },
            }
        )
        message = self.read()
        self.assertEqual(message.body, "<p>café</p>")
        self.assertEqual(message.mime_type, "text/html")

    def test_oversized_header_list_cannot_hide_attachment_disposition(self):
        self.connect()
        self.responses.append(
            {
                "id": "m_1",
                "threadId": "t_1",
                "payload": {
                    "mimeType": "multipart/mixed",
                    "parts": [
                        {
                            "mimeType": "text/html",
                            "body": {"data": base64.urlsafe_b64encode(b"<p>main</p>").decode()},
                        },
                        {
                            "mimeType": "text/plain",
                            "headers": [
                                {"name": "X-Unrelated", "value": str(index)} for index in range(100)
                            ] + [{"name": "Content-Disposition", "value": "attachment"}],
                            "body": {"data": base64.urlsafe_b64encode(b"ATTACHMENT").decode()},
                        },
                    ],
                },
            }
        )
        with self.assertRaises(GmailError) as bounded:
            self.read()
        self.assertEqual(bounded.exception.reason, "message_too_complex")

    def test_oversized_disposition_value_cannot_hide_attachment(self):
        self.connect()
        self.responses.append(
            {
                "id": "m_1",
                "threadId": "t_1",
                "payload": {
                    "mimeType": "text/plain",
                    "headers": [
                        {
                            "name": "Content-Disposition",
                            "value": (" " * 1024) + "attachment; filename=hidden.txt",
                        }
                    ],
                    "body": {"data": base64.urlsafe_b64encode(b"ATTACHMENT").decode()},
                },
            }
        )
        with self.assertRaises(GmailError) as bounded:
            self.read()
        self.assertEqual(bounded.exception.reason, "message_too_complex")

    def test_oversized_content_type_value_cannot_hide_charset(self):
        self.connect()
        self.responses.append(
            {
                "id": "m_1",
                "threadId": "t_1",
                "payload": {
                    "mimeType": "text/plain",
                    "headers": [
                        {
                            "name": "Content-Type",
                            "value": "text/plain; x=" + ("a" * 1024) + "; charset=iso-8859-1",
                        }
                    ],
                    "body": {
                        "data": base64.urlsafe_b64encode("café".encode("iso-8859-1")).decode()
                    },
                },
            }
        )
        with self.assertRaises(GmailError) as bounded:
            self.read()
        self.assertEqual(bounded.exception.reason, "message_too_complex")

    def test_top_level_rfc822_payload_exposes_its_selected_message_body(self):
        self.connect()
        self.responses.append(
            {
                "id": "m_1",
                "threadId": "t_1",
                "payload": {
                    "mimeType": "message/rfc822",
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {"data": base64.urlsafe_b64encode(b"top-level body").decode()},
                        }
                    ],
                },
            }
        )
        message = self.read()
        self.assertEqual(message.body, "top-level body")
        self.assertEqual(message.mime_type, "text/plain")

    def test_body_does_not_traverse_nested_attachment_subtrees(self):
        self.connect()
        self.responses.append(
            {
                "id": "m_1",
                "threadId": "t_1",
                "payload": {
                    "mimeType": "multipart/mixed",
                    "parts": [
                        {
                            "mimeType": "text/html",
                            "body": {"data": base64.urlsafe_b64encode(b"<p>main body</p>").decode()},
                        },
                        {
                            "mimeType": "message/rfc822",
                            "filename": "attached.eml",
                            "headers": [
                                {"name": "Content-Disposition", "value": "attachment; filename=attached.eml"}
                            ],
                            "parts": [
                                {
                                    "mimeType": "text/plain",
                                    "body": {"data": base64.urlsafe_b64encode(b"nested attachment").decode()},
                                }
                            ],
                        },
                    ],
                },
            }
        )
        message = self.read()
        self.assertEqual(message.body, "<p>main body</p>")
        self.assertEqual(message.mime_type, "text/html")

    def test_body_excludes_undispositioned_attached_message_subtree(self):
        self.connect()
        self.responses.append(
            {
                "id": "m_1",
                "threadId": "t_1",
                "payload": {
                    "mimeType": "multipart/mixed",
                    "parts": [
                        {"mimeType": "text/plain", "body": {"data": base64.urlsafe_b64encode(b"main body").decode()}},
                        {
                            "mimeType": "message/rfc822",
                            "parts": [
                                {"mimeType": "text/plain", "body": {"data": base64.urlsafe_b64encode(b"attached body").decode()}},
                            ],
                        },
                    ],
                },
            }
        )
        message = self.read()
        self.assertEqual(message.body, "main body")
        self.assertNotIn("attached", message.body)

    def test_non_text_registered_codec_is_refused_as_an_unsupported_charset(self):
        """A registered codec that is not a mail charset is refused by name.

        These previously surfaced as ``invalid_provider_response`` only
        because the narrow utf-7 denylist let them through and the decode
        happened to fail afterwards. ``undefined`` in particular is a real
        registered codec. The allowlist now classifies them for what they
        are, and the rejection no longer depends on a downstream accident.
        """
        self.connect()
        for charset in ("base64_codec", "undefined", "rot13", "quopri_codec"):
            with self.subTest(charset=charset):
                self.responses.clear()
                self.responses.append(
                    {
                        "id": "m_1",
                        "threadId": "t_1",
                        "payload": {
                            "mimeType": "text/plain",
                            "headers": [
                                {"name": "Content-Type", "value": f"text/plain; charset={charset}"}
                            ],
                            "body": {"data": base64.urlsafe_b64encode(b"body").decode()},
                        },
                    }
                )
                with self.assertRaises(GmailError) as refused:
                    self.read()
                self.assertEqual(refused.exception.reason, "unsupported_charset")

    def test_charset_lookup_and_decode_failures_are_bounded_provider_errors(self):
        self.connect()
        # Both names fail ``codecs.lookup`` outright, which is a malformed
        # provider response rather than a deliberate charset refusal.
        for charset in ("x-no-such-charset", "utf-8\x00"):
            with self.subTest(charset=charset):
                self.responses.clear()
                self.responses.append(
                    {
                        "id": "m_1",
                        "threadId": "t_1",
                        "payload": {
                            "mimeType": "text/plain",
                            "headers": [
                                {"name": "Content-Type", "value": f'text/plain; charset="{charset}"'}
                            ],
                            "body": {"data": base64.urlsafe_b64encode(b"body").decode()},
                        },
                    }
                )
                with self.assertRaises(GmailError) as malformed:
                    self.read()
                self.assertEqual(malformed.exception.reason, "invalid_provider_response")

    def test_present_content_type_must_match_mime_and_have_one_charset(self):
        self.connect()
        for content_type in (
            "application/octet-stream; charset=utf-8",
            'text/plain; charset=""',
            "text/plain; charset=   ",
            'text/plain; charset="utf-8',
            "text/plain; charset=utf-8; charset=iso-8859-1",
            "text/plain; charset=utf-8; CHARSET=iso-8859-1",
            # A CFWS comment must not hide a duplicate parameter name. Python's
            # header parser drops the comment and selects the case variant, so a
            # raw scanner that stops at "(" would leave the charset ambiguous.
            "text/plain; charset=us-ascii; (x) CHARSET=utf-8",
            "text/plain; charset=us-ascii; (nested (comment)) CHARSET=utf-8",
            "text/plain; (c) charset=us-ascii; CHARSET=utf-8",
            # An unterminated comment or quoted string is malformed.
            "text/plain; charset=utf-8; (unterminated",
        ):
            with self.subTest(content_type=content_type):
                self.responses.clear()
                self.responses.append({
                    "id": "m_1",
                    "threadId": "t_1",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [{"name": "Content-Type", "value": content_type}],
                        "body": {"data": base64.urlsafe_b64encode(b"private body").decode()},
                    },
                })
                with self.assertRaises(GmailError) as malformed:
                    self.read()
                self.assertEqual(malformed.exception.reason, "invalid_provider_response")

    def test_present_content_type_can_omit_optional_charset(self):
        self.connect()
        for content_type in (
            "text/plain",
            "text/plain; format=flowed",
            # A comment is legal CFWS and must not turn a single parameter into
            # a duplicate or otherwise reject an ordinary part.
            "text/plain; (only one) charset=us-ascii",
            # A parenthesis inside a quoted parameter value is data, not CFWS.
            'text/plain; format="paren(in)quotes"',
            # HTAB is legal folding whitespace and must not fail the message.
            "text/plain;\tcharset=us-ascii",
            "text/plain;\tformat=flowed",
            # A leading comment must not make the raw main type disagree with
            # the parsed content type.
            "(sent by relay) text/plain; charset=us-ascii",
        ):
            with self.subTest(content_type=content_type):
                self.responses.append({
                    "id": "m_1",
                    "threadId": "t_1",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [{"name": "Content-Type", "value": content_type}],
                        "body": {"data": base64.urlsafe_b64encode(b"plain body").decode()},
                    },
                })
                self.assertEqual(self.read().body, "plain body")

        self.responses.append({
            "id": "m_1",
            "threadId": "t_1",
            "payload": {
                "mimeType": "text/plain",
                "headers": [{"name": "Content-Type", "value": "text/plain"}],
                "body": {"data": base64.urlsafe_b64encode("café".encode()).decode()},
            },
        })
        with self.assertRaises(GmailError) as non_ascii_default:
            self.read()
        self.assertEqual(non_ascii_default.exception.reason, "invalid_provider_response")

    def test_malformed_header_container_is_rejected(self):
        self.connect()
        self.responses.append({
            "id": "m_1",
            "threadId": "t_1",
            "payload": {
                "mimeType": "text/plain",
                "headers": {"name": "Content-Disposition", "value": "attachment"},
                "body": {"data": base64.urlsafe_b64encode(b"must not be body").decode()},
            },
        })
        with self.assertRaises(GmailError) as malformed:
            self.read()
        self.assertEqual(malformed.exception.reason, "invalid_provider_response")

    def test_present_valid_charset_requires_strict_body_decoding(self):
        self.connect()
        self.responses.append({
            "id": "m_1",
            "threadId": "t_1",
            "payload": {
                "mimeType": "text/plain",
                "headers": [{"name": "Content-Type", "value": "text/plain; charset=utf-8"}],
                "body": {"data": base64.urlsafe_b64encode(b"private \xff body").decode()},
            },
        })
        with self.assertRaises(GmailError) as malformed:
            self.read()
        self.assertEqual(malformed.exception.reason, "invalid_provider_response")

    def test_mixed_body_combines_serial_parts_but_alternative_chooses_plain(self):
        self.connect()
        encode = lambda value: base64.urlsafe_b64encode(value.encode()).decode()
        self.responses.append(
            {
                "id": "m_1",
                "threadId": "t_1",
                "payload": {
                    "mimeType": "multipart/mixed",
                    "parts": [
                        {"mimeType": "text/plain", "body": {"data": encode("intro")}},
                        {
                            "mimeType": "multipart/alternative",
                            "parts": [
                                {"mimeType": "text/html", "body": {"data": encode("<p>main</p>")}},
                                {"mimeType": "text/plain", "body": {"data": encode("main")}},
                            ],
                        },
                        {"mimeType": "text/plain", "body": {"data": encode("footer")}},
                    ],
                },
            }
        )
        message = self.read()
        self.assertEqual(message.body, "intro\n\nmain\n\nfooter")
        self.assertEqual(message.mime_type, "text/plain")

    def test_related_body_selects_only_root_and_excludes_inline_text_resources(self):
        self.connect()
        encode = lambda value: base64.urlsafe_b64encode(value.encode()).decode()
        for content_type,parts,expected,mime_type in (
            (
                "multipart/related",
                [
                    {"mimeType":"text/html","body":{"data":encode("<p>root</p>")}},
                    {"mimeType":"text/plain","body":{"data":encode("inline resource")}},
                ],
                "<p>root</p>",
                "text/html",
            ),
            (
                'multipart/related; start="<root-part>"',
                [
                    {"mimeType":"text/plain","headers":[{"name":"Content-ID","value":"<resource>"}],"body":{"data":encode("resource")}},
                    {"mimeType":"text/html","headers":[{"name":"Content-ID","value":"<root-part>"}],"body":{"data":encode("<p>selected root</p>")}},
                ],
                "<p>selected root</p>",
                "text/html",
            ),
        ):
            with self.subTest(content_type=content_type):
                self.responses.append({
                    "id":"m_1","threadId":"t_1","payload":{
                        "mimeType":"multipart/related",
                        "headers":[{"name":"Content-Type","value":content_type}],
                        "parts":parts,
                    },
                })
                message=self.read()
                self.assertEqual(message.body,expected)
                self.assertEqual(message.mime_type,mime_type)

    def test_related_body_rejects_explicit_empty_root_selector(self):
        self.connect()
        encoded=base64.urlsafe_b64encode(b"inline-first").decode()
        for content_type in (
            'multipart/related; start=""','multipart/related; start=<>',
            'multipart/related; start="<root"','multipart/related; start="root>"',
            'multipart/related; start="root"','multipart/related; start="<<root>>"',
            'multipart/related; start="<root>"; START="<other>"',
        ):
            with self.subTest(content_type=content_type):
                self.responses.append({
                    "id":"m_1","threadId":"t_1","payload":{
                        "mimeType":"multipart/related",
                        "headers":[{"name":"Content-Type","value":content_type}],
                        "parts":[{"mimeType":"text/plain","body":{"data":encoded}}],
                    },
                })
                with self.assertRaises(GmailError) as malformed:
                    self.read()
                self.assertEqual(malformed.exception.reason,"invalid_provider_response")

    def test_body_rejects_duplicate_structure_security_headers(self):
        self.connect()
        encoded=base64.urlsafe_b64encode(b"must not be body").decode()
        payloads=(
            {
                "mimeType":"text/plain",
                "headers":[
                    {"name":"Content-Disposition","value":"inline"},
                    {"name":"Content-Disposition","value":"attachment"},
                ],
                "body":{"data":encoded},
            },
            {
                "mimeType":"multipart/related",
                "headers":[
                    {"name":"Content-Type","value":"multipart/related"},
                    {"name":"Content-Type","value":"multipart/related; start=\"<root>\""},
                ],
                "parts":[{"mimeType":"text/plain","body":{"data":encoded}}],
            },
        )
        for payload in payloads:
            with self.subTest(mime_type=payload["mimeType"]):
                self.responses.append({"id":"m_1","threadId":"t_1","payload":payload})
                with self.assertRaises(GmailError) as duplicate:
                    self.read()
                self.assertEqual(duplicate.exception.reason,"invalid_provider_response")

    def test_related_body_rejects_ambiguous_content_ids(self):
        self.connect()
        encoded=base64.urlsafe_b64encode(b"ambiguous root").decode()
        for parts in (
            [
                {"mimeType":"text/plain","headers":[
                    {"name":"Content-ID","value":"<root>"},
                    {"name":"Content-ID","value":"<other>"},
                ],"body":{"data":encoded}},
            ],
            [
                {"mimeType":"text/plain","headers":[{"name":"Content-ID","value":"<root>"}],"body":{"data":encoded}},
                {"mimeType":"text/html","headers":[{"name":"Content-ID","value":"<root>"}],"body":{"data":encoded}},
            ],
        ):
            with self.subTest(parts=len(parts)):
                self.responses.append({
                    "id":"m_1","threadId":"t_1","payload":{
                        "mimeType":"multipart/related",
                        "headers":[{"name":"Content-Type","value":'multipart/related; start="<root>"'}],
                        "parts":parts,
                    },
                })
                with self.assertRaises(GmailError) as ambiguous:
                    self.read()
                self.assertEqual(ambiguous.exception.reason,"invalid_provider_response")

    def test_body_attachment_id_is_fetched_with_same_bounded_authority(self):
        self.connect()
        encoded = base64.urlsafe_b64encode(b"separate body").decode()
        self.responses.extend(
            [
                {
                    "id": "m_1",
                    "threadId": "t_1",
                    "payload": {
                        "mimeType": "text/plain",
                        "body": {"attachmentId": "attachment_1"},
                    },
                },
                {"data": encoded, "size": len(b"separate body")},
            ]
        )
        message = self.read()
        self.assertEqual(message.body, "separate body")
        self.assertEqual(
            self.calls[-1][1],
            MESSAGES_ENDPOINT + "/m_1/attachments/attachment_1",
        )

    def test_expiry_and_provider_revocation_clear_tokens_and_require_reauth(self):
        self.connect()
        self.clock[0] += 61
        with self.assertRaises(GmailReauthenticationRequired):
            self.gmail.search("owner-a", "receipt")
        self.assertEqual(self.gmail.status("owner-a")["state"], "reauth_required")
        self.assertEqual(self.store.secret(self.secret_key("gmail_oauth_tokens")), {})
        self.assertEqual(self.gmail.connection_required("owner-a")["recovery"], "reauthenticate")

        _result, _request = self.connect()
        self.responses.append({"status_code": 401, "error": "invalid credentials"})
        with self.assertRaises(GmailReauthenticationRequired):
            self.gmail.search("owner-a", "receipt")
        self.assertEqual(self.gmail.status("owner-a")["state"], "reauth_required")
        self.assertEqual(self.store.secret(self.secret_key("gmail_oauth_tokens")), {})

    def test_redirect_and_malformed_provider_statuses_fail_closed(self):
        self.connect()
        self.responses.append({"status_code": 302, "messages": []})
        with self.assertRaises(GmailError) as redirected:
            self.gmail.search("owner-a", "receipt")
        self.assertEqual(redirected.exception.reason, "provider_rejected")

        for status in ("200", True, None):
            self.responses.append({"status_code": status, "messages": []})
            with self.assertRaises(GmailError) as malformed:
                self.gmail.search("owner-a", "receipt")
            self.assertEqual(malformed.exception.reason, "invalid_provider_response")

    def test_unknown_content_disposition_is_not_admitted_as_message_body(self):
        self.connect()
        encoded = base64.urlsafe_b64encode(b"must not be body").decode()
        self.responses.append({
            "id": "m_1",
            "threadId": "t_1",
            "payload": {
                "mimeType": "text/plain",
                "headers": [{"name": "Content-Disposition", "value": "x-vendor-attachment"}],
                "body": {"data": encoded},
            },
        })
        # The part is correctly withheld, but the only text in the message was
        # dropped, so an empty body is an unknown outcome rather than a
        # successful source-attributed read.
        with self.assertRaises(GmailError) as dropped:
            self.read()
        self.assertEqual(dropped.exception.reason, "body_not_attributable")
        self.assertNotIn("must not be body", str(dropped.exception))

    def test_empty_content_disposition_is_not_treated_as_an_absent_header(self):
        """A blank disposition is malformed, not an unrecognised disposition.

        RFC 2183 section 2 requires a ``disposition-type`` token, so an empty
        or whitespace-only value is a header that does not parse rather than a
        well-formed header naming a role this parser does not know. The stdlib
        parse records ``HeaderMissingRequiredValue``/``InvalidHeaderDefect``
        for both spellings, and the defect rule refuses the read.

        This previously reported ``body_not_attributable``, which asserts the
        stronger and here untrue claim that the message parsed cleanly but no
        part could be attributed as its body. Both reasons withhold the body;
        ``invalid_provider_response`` names the actual cause. The
        unrecognised-but-well-formed case keeps the old reason and is covered
        by ``test_unknown_content_disposition_is_not_admitted_as_message_body``.
        """
        self.connect()
        encoded = base64.urlsafe_b64encode(b"must not be body").decode()
        for disposition in ("", "   "):
            with self.subTest(disposition=repr(disposition)):
                self.responses.append({
                    "id": "m_1",
                    "threadId": "t_1",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [{"name": "Content-Disposition", "value": disposition}],
                        "body": {"data": encoded},
                    },
                })
                with self.assertRaises(GmailError) as dropped:
                    self.read()
                self.assertEqual(dropped.exception.reason, "invalid_provider_response")
                self.assertNotIn("must not be body", str(dropped.exception))

    def test_cfws_comment_in_content_disposition_keeps_an_inline_body(self):
        """A legal comment must not silently reclassify inline text.

        A naive ``split(";")`` turned ``inline (rendered)`` into an attachment,
        dropped the part, and returned a *successful* empty body.
        """
        self.connect()
        for disposition in (
            "inline (rendered by client)",
            "(added by relay) inline",
            "inline (nested (comment))",
            "inline\t",
        ):
            with self.subTest(disposition=disposition):
                self.responses.clear()
                self.responses.append({
                    "id": "m_1",
                    "threadId": "t_1",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [{"name": "Content-Disposition", "value": disposition}],
                        "body": {"data": base64.urlsafe_b64encode(b"inline body").decode()},
                    },
                })
                self.assertEqual(self.read().body, "inline body")

    def test_bodyless_message_is_distinguished_from_a_dropped_candidate(self):
        self.connect()
        # A message whose only part is a real non-text attachment genuinely has
        # no text body. That is a truthful empty read.
        self.responses.append({
            "id": "m_1",
            "threadId": "t_1",
            "payload": {
                "mimeType": "multipart/mixed",
                "parts": [
                    {
                        "mimeType": "application/pdf",
                        "filename": "receipt.pdf",
                        "body": {"attachmentId": "attachment_1"},
                    },
                ],
            },
        })
        message = self.read()
        self.assertEqual(message.body, "")
        self.assertEqual(message.mime_type, "multipart/mixed")
        # The same shape whose only text part was removed by a *heuristic* is
        # an unknown outcome and must not be reported identically. The
        # previous version of this test used ``Content-Disposition:
        # attachment``, which is the sender declaring the part's role outright
        # - nothing was guessed and nothing was dropped - so it asserted the
        # opposite of what its own comment claimed. The legacy ``name``
        # parameter with no Content-Disposition is a real guess, so it is the
        # shape that belongs here.
        self.responses.append({
            "id": "m_1",
            "threadId": "t_1",
            "payload": {
                "mimeType": "multipart/mixed",
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "headers": [
                            {"name": "Content-Type", "value": 'text/plain; name="notes.txt"'}
                        ],
                        "body": {"data": base64.urlsafe_b64encode(b"withheld").decode()},
                    },
                ],
            },
        })
        with self.assertRaises(GmailError) as dropped:
            self.read()
        self.assertEqual(dropped.exception.reason, "body_not_attributable")

    def test_related_root_that_renders_nothing_is_not_a_silent_empty_body(self):
        self.connect()
        # Without a start parameter the first part is the root. It renders
        # nothing here while a sibling has text, so the empty result is a
        # parser outcome, not an attributable root body.
        self.responses.append({
            "id": "m_1",
            "threadId": "t_1",
            "payload": {
                "mimeType": "multipart/related",
                "parts": [
                    {
                        "mimeType": "image/png",
                        "filename": "logo.png",
                        "body": {"attachmentId": "attachment_1"},
                    },
                    {
                        "mimeType": "text/plain",
                        "body": {"data": base64.urlsafe_b64encode(b"sibling text").decode()},
                    },
                ],
            },
        })
        with self.assertRaises(GmailError) as ambiguous:
            self.read()
        self.assertEqual(ambiguous.exception.reason, "body_not_attributable")

    def test_content_type_name_parameter_marks_a_text_part_as_an_attachment(self):
        self.connect()
        self.responses.append({
            "id": "m_1",
            "threadId": "t_1",
            "payload": {
                "mimeType": "multipart/mixed",
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "headers": [
                            {"name": "Content-Type", "value": 'text/plain; name="transcript.txt"'}
                        ],
                        "body": {"data": base64.urlsafe_b64encode(b"ATTACHED TEXT").decode()},
                    },
                    {
                        "mimeType": "text/plain",
                        "body": {"data": base64.urlsafe_b64encode(b"real body").decode()},
                    },
                ],
            },
        })
        message = self.read()
        self.assertEqual(message.body, "real body")
        self.assertNotIn("ATTACHED TEXT", message.body)

    def test_explicit_inline_disposition_outranks_the_legacy_name_parameter(self):
        """RFC 2183 section 2.1 makes Content-Disposition authoritative.

        ``name`` is the pre-RFC-2183 fallback and is evidence only when the
        authoritative header is silent. Letting it override an explicit
        ``inline`` made ordinary Outlook/Exchange and mailing-list mail
        unreadable: the single text part was withheld, nothing was left to
        attribute, and the whole read raised.
        """
        self.connect()
        for disposition in ("inline", "inline (rendered)", 'inline; filename="message.txt"'):
            with self.subTest(disposition=disposition):
                self.responses.clear()
                self.responses.append({
                    "id": "m_1",
                    "threadId": "t_1",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [
                            {
                                "name": "Content-Type",
                                "value": 'text/plain; charset=utf-8; name="message.txt"',
                            },
                            {"name": "Content-Disposition", "value": disposition},
                        ],
                        "body": {"data": base64.urlsafe_b64encode(b"readable body").decode()},
                    },
                })
                # Note the third case: a filename *parameter* under an inline
                # disposition is still inline. Gmail's separate top-level
                # ``filename`` field is what marks a declared attachment.
                self.assertEqual(self.read().body, "readable body")

        # The fallback still applies where the authoritative header is silent
        # or says the opposite, so closing this hole does not reopen the one
        # the ``name`` heuristic was added for.
        for headers in (
            [{"name": "Content-Type", "value": 'text/plain; name="transcript.txt"'}],
            [
                {"name": "Content-Type", "value": 'text/plain; name="transcript.txt"'},
                {"name": "Content-Disposition", "value": "attachment"},
            ],
        ):
            with self.subTest(headers=len(headers)):
                self.responses.clear()
                self.responses.append({
                    "id": "m_1",
                    "threadId": "t_1",
                    "payload": {
                        "mimeType": "multipart/mixed",
                        "parts": [
                            {
                                "mimeType": "text/plain",
                                "headers": headers,
                                "body": {"data": base64.urlsafe_b64encode(b"ATTACHED TEXT").decode()},
                            },
                            {
                                "mimeType": "text/plain",
                                "body": {"data": base64.urlsafe_b64encode(b"real body").decode()},
                            },
                        ],
                    },
                })
                message = self.read()
                self.assertEqual(message.body, "real body")
                self.assertNotIn("ATTACHED TEXT", message.body)

    def test_sender_declared_text_attachment_is_a_truthful_empty_body(self):
        """A declared attachment is classified, not dropped.

        Counting it as a dropped candidate made the outcome depend on the
        attachment's MIME type rather than on whether anything was ambiguous:
        an empty message with one attached ``.txt``/``.log``/``.html`` raised
        while the identical shape with a ``.pdf`` returned ``""``. Because
        ``read_message`` raises, that also cost the owner the rest of the
        message, which is strictly worse than the truthful empty body.
        """
        self.connect()
        declarations = (
            # Gmail's own filename field, with no part headers at all.
            ({"filename": "notes.txt"}, "gmail-filename"),
            # The sender saying so outright in the authoritative header.
            (
                {
                    "headers": [
                        {"name": "Content-Disposition", "value": "attachment; filename=notes.txt"}
                    ]
                },
                "declared-attachment",
            ),
        )
        for extra, label in declarations:
            for mime_type in ("text/plain", "text/html", "application/pdf"):
                with self.subTest(declaration=label, mime_type=mime_type):
                    part = {
                        "mimeType": mime_type,
                        "body": {"data": base64.urlsafe_b64encode(b"withheld attachment").decode()},
                    }
                    part.update(extra)
                    self.responses.clear()
                    self.responses.append({
                        "id": "m_1",
                        "threadId": "t_1",
                        "payload": {"mimeType": "multipart/mixed", "parts": [part]},
                    })
                    message = self.read()
                    # The outcome must not depend on the attachment's type.
                    self.assertEqual(message.body, "")
                    self.assertEqual(message.mime_type, "multipart/mixed")
                    self.assertNotIn("withheld attachment", message.body)

    def test_forwarded_alternative_thread_is_bounded_after_selection(self):
        """The candidate bound must count what a reader would actually see.

        ``multipart/alternative`` discards one of each plain/html pair after
        admission, so counting at admission tripped the cap at half the parts
        that survive. An eleven-message quoted thread flattened into
        ``multipart/mixed`` admitted 22 and kept 11, and was rejected.
        """
        self.connect()

        def thread(count):
            return {
                "id": "m_1",
                "threadId": "t_1",
                "payload": {
                    "mimeType": "multipart/mixed",
                    "parts": [
                        {
                            "mimeType": "multipart/alternative",
                            "parts": [
                                {
                                    "mimeType": "text/plain",
                                    "body": {
                                        "data": base64.urlsafe_b64encode(
                                            f"reply {index}".encode()
                                        ).decode()
                                    },
                                },
                                {
                                    "mimeType": "text/html",
                                    "body": {
                                        "data": base64.urlsafe_b64encode(
                                            f"<p>reply {index}</p>".encode()
                                        ).decode()
                                    },
                                },
                            ],
                        }
                        for index in range(count)
                    ],
                },
            }

        self.responses.append(thread(11))
        message = self.read()
        self.assertEqual(
            message.body, "\n\n".join(f"reply {index}" for index in range(11))
        )
        self.assertNotIn("<p>", message.body)

        # The bound still bites once the surviving parts exceed it, and it
        # still refuses rather than silently truncating a partial body.
        self.responses.clear()
        self.responses.append(thread(40))
        with self.assertRaises(GmailError) as bounded:
            self.read()
        self.assertEqual(bounded.exception.reason, "message_too_complex")

    def test_header_encoded_words_use_the_same_charset_gate_as_the_body(self):
        """Subject/From are owner-rendered text and need the body's gate.

        The charset rule was applied to the body decode only, leaving RFC 2047
        encoded-words one function away able to smuggle the same ASCII-looking
        markup into exactly the fields the owner reads.
        """
        self.connect()
        markup = "<script>alert(1)</script>"

        def encoded_word(charset, text, codec=None):
            raw = text.encode(codec or charset)
            return "=?%s?B?%s?=" % (charset, base64.b64encode(raw).decode())

        for header in ("Subject", "From"):
            for charset in ("utf-7", "UTF-7", "unicode_escape", "idna"):
                with self.subTest(header=header, charset=charset):
                    if charset == "unicode_escape":
                        word = "=?unicode_escape?B?%s?=" % base64.b64encode(
                            b"\\u003cscript\\u003ealert(1)\\u003c/script\\u003e"
                        ).decode()
                    elif charset == "idna":
                        word = "=?idna?B?%s?=" % base64.b64encode(b"example.test.").decode()
                    else:
                        word = encoded_word(charset, markup, codec="utf-7")
                    metadata = self.metadata()
                    metadata["payload"]["headers"] = [
                        {"name": name, "value": word if name == header else "plain"}
                        for name in ("Subject", "From", "Date")
                    ]
                    self.responses.clear()
                    self.responses.append({"messages": [{"id": "m_1"}]})
                    self.responses.append(metadata)
                    with self.assertRaises(GmailError) as refused:
                        self.gmail.search("owner-a", "receipt")
                    self.assertEqual(refused.exception.reason, "unsupported_charset")
                    self.assertNotIn("script", str(refused.exception))

        # A legitimate encoded-word in an allowed charset still decodes, so
        # the gate does not break ordinary non-ASCII mail metadata.
        metadata = self.metadata()
        metadata["payload"]["headers"] = [
            {"name": "Subject", "value": encoded_word("utf-8", "Rezervasyon başarılı")},
            {"name": "From", "value": encoded_word("iso-8859-1", "Café <cafe@example.test>")},
            {"name": "Date", "value": "Mon, 1 Sep 2026 10:00:00 +0000"},
        ]
        self.responses.clear()
        self.responses.append({"messages": [{"id": "m_1"}]})
        self.responses.append(metadata)
        result = self.gmail.search("owner-a", "receipt")[0]
        self.assertEqual(result.subject, "Rezervasyon başarılı")
        self.assertEqual(result.sender, "Café <cafe@example.test>")

    def test_ebcdic_codepages_cannot_synthesise_markup_through_the_allowlist(self):
        """An allowlist is only a control if every entry respects its own threat.

        cp1026/cp1140/cp875 map byte 0x4C to "<", so admitting them would let
        source bytes containing no 0x3C decode into markup - exactly the
        property the gate exists to deny. They were transcribed from Python's
        standard-encodings table rather than curated; no mail declares EBCDIC.
        """
        import codecs

        for charset in ("cp1026", "cp1140", "cp875"):
            with self.subTest(charset=charset):
                self.assertEqual(codecs.decode(b"\x4c", charset), "<")
                with self.assertRaises(GmailError) as caught:
                    _assert_renderable_charset(charset)
                self.assertIn("unsupported_charset", str(caught.exception.reason))

    def test_allowlist_covers_mail_charsets_omitted_by_transcription(self):
        """cp950 and the remaining mac-* pages are real mail charsets.

        big5 was allowed while cp950, its Microsoft superset, was not, and
        eight of ten mac-* pages were listed. Both gaps are the same
        transcription accident as the EBCDIC entries, in the opposite
        direction: refusing mail a reader should be able to open.
        """
        for charset in ("cp950", "mac-arabic", "mac-farsi"):
            with self.subTest(charset=charset):
                _assert_renderable_charset(charset)

    def test_charset_gate_is_an_allowlist_rather_than_a_utf7_denylist(self):
        """Any codec that can synthesise ASCII markup must be refused.

        utf-7 was only the reported example. ``unicode_escape`` turns
        ``\\u003c`` into ``<`` for the same reason, and ``idna``/``punycode``
        are transforms rather than mail charsets. A one-entry denylist left a
        new hole open behind each fix, so the rule is an allowlist.
        """
        self.connect()
        for charset, raw in (
            ("unicode_escape", b"\\u003cscript\\u003ealert(1)\\u003c/script\\u003e"),
            ("raw_unicode_escape", b"\\u003cscript\\u003ealert(1)\\u003c/script\\u003e"),
            ("idna", b"example.test."),
            ("punycode", b"example-"),
            ("hex_codec", b"3c7363726970743e"),
        ):
            with self.subTest(charset=charset):
                self.responses.clear()
                self.responses.append({
                    "id": "m_1",
                    "threadId": "t_1",
                    "payload": {
                        "mimeType": "text/html",
                        "headers": [
                            {"name": "Content-Type", "value": f"text/html; charset={charset}"}
                        ],
                        "body": {"data": base64.urlsafe_b64encode(raw).decode()},
                    },
                })
                with self.assertRaises(GmailError) as refused:
                    self.read()
                self.assertEqual(refused.exception.reason, "unsupported_charset")
                self.assertNotIn("script", str(refused.exception))

    def test_allowlist_still_decodes_the_charsets_real_mail_uses(self):
        """The allowlist must not reject legitimate real-world mail charsets."""
        self.connect()
        samples = (
            ("us-ascii", "ascii", "plain receipt"),
            ("utf-8", "utf-8", "Rezervasyon başarılı"),
            ("UTF-8", "utf-8", "café"),
            ("utf-16", "utf-16", "café"),
            ("utf-16le", "utf-16-le", "café"),
            ("iso-8859-1", "iso-8859-1", "café"),
            ("latin-1", "iso-8859-1", "café"),
            ("iso-8859-2", "iso-8859-2", "přehled"),
            ("iso-8859-7", "iso-8859-7", "καλημέρα"),
            ("iso-8859-9", "iso-8859-9", "günaydın"),
            ("iso-8859-15", "iso-8859-15", "20€"),
            ("windows-1250", "cp1250", "přehled"),
            ("windows-1251", "cp1251", "привет"),
            ("windows-1252", "cp1252", "café"),
            ("windows-1254", "cp1254", "günaydın"),
            ("windows-1256", "cp1256", "مرحبا"),
            ("koi8-r", "koi8-r", "привет"),
            ("koi8-u", "koi8-u", "привіт"),
            ("Shift_JIS", "shift_jis", "こんにちは"),
            ("sjis", "shift_jis", "こんにちは"),
            ("cp932", "cp932", "こんにちは"),
            ("euc-jp", "euc_jp", "こんにちは"),
            ("ISO-2022-JP", "iso2022_jp", "こんにちは"),
            ("euc-kr", "euc_kr", "안녕하세요"),
            ("ks_c_5601-1987", "euc_kr", "안녕하세요"),
            ("gb2312", "gb2312", "你好"),
            ("gbk", "gbk", "你好"),
            ("gb18030", "gb18030", "你好"),
            ("big5", "big5", "你好"),
        )
        for declared, codec, text in samples:
            with self.subTest(charset=declared):
                self.responses.clear()
                self.responses.append({
                    "id": "m_1",
                    "threadId": "t_1",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [
                            {"name": "Content-Type", "value": f"text/plain; charset={declared}"}
                        ],
                        "body": {
                            "data": base64.urlsafe_b64encode(text.encode(codec)).decode()
                        },
                    },
                })
                self.assertEqual(self.read().body, text)

    def test_utf7_charset_is_refused_for_body_decoding(self):
        self.connect()
        for charset in ("utf-7", "UTF-7", "utf7", "unicode-1-1-utf-7"):
            with self.subTest(charset=charset):
                self.responses.clear()
                self.responses.append({
                    "id": "m_1",
                    "threadId": "t_1",
                    "payload": {
                        "mimeType": "text/html",
                        "headers": [
                            {"name": "Content-Type", "value": f"text/html; charset={charset}"}
                        ],
                        "body": {"data": base64.urlsafe_b64encode(b"+ADw-script+AD4-").decode()},
                    },
                })
                with self.assertRaises(GmailError) as refused:
                    self.read()
                self.assertEqual(refused.exception.reason, "unsupported_charset")

    def test_absent_content_type_uses_the_same_strict_charset_default(self):
        """A missing Content-Type must not decode more permissively.

        The two paths previously defaulted to utf-8 and us-ascii, so an
        undeclared part decoded bytes that an identically declared part
        rejected, which made the strict-charset guarantee unenforceable.
        """
        self.connect()
        non_ascii = base64.urlsafe_b64encode("café".encode()).decode()
        for headers in ([], [{"name": "Content-Type", "value": "text/plain"}]):
            with self.subTest(content_type_present=bool(headers)):
                self.responses.clear()
                self.responses.append({
                    "id": "m_1",
                    "threadId": "t_1",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": headers,
                        "body": {"data": non_ascii},
                    },
                })
                with self.assertRaises(GmailError) as strict:
                    self.read()
                self.assertEqual(strict.exception.reason, "invalid_provider_response")
        for headers in ([], [{"name": "Content-Type", "value": "text/plain"}]):
            with self.subTest(ascii_content_type_present=bool(headers)):
                self.responses.clear()
                self.responses.append({
                    "id": "m_1",
                    "threadId": "t_1",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": headers,
                        "body": {"data": base64.urlsafe_b64encode(b"plain ascii").decode()},
                    },
                })
                self.assertEqual(self.read().body, "plain ascii")

    def test_admitted_body_candidate_count_is_bounded(self):
        self.connect()
        encoded = base64.urlsafe_b64encode(b"x").decode()
        self.responses.append({
            "id": "m_1",
            "threadId": "t_1",
            "payload": {
                "mimeType": "multipart/mixed",
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": encoded}} for _ in range(40)
                ],
            },
        })
        with self.assertRaises(GmailError) as bounded:
            self.read()
        self.assertEqual(bounded.exception.reason, "message_too_complex")

    def test_stdlib_header_defects_are_a_general_fail_closed_signal(self):
        """Any defect the stdlib header parse records refuses the read.

        This replaces an enumeration of the malformations this module happened
        to think of - a hand-written CFWS/comment scanner, a quoted-string
        aware parameter splitter, an explicit HTAB/control-character sweep and
        a bespoke duplicate-name check - with the parser's own defect list. A
        malformation nobody enumerated is now refused for the same reason as
        one that was.

        The legal constructs this must NOT reject (HTAB folding, nested
        comments, parentheses inside quoted values, a single leading comment)
        are asserted by ``test_present_content_type_can_omit_optional_charset``
        and ``test_cfws_comment_in_content_disposition_keeps_an_inline_body``.
        """
        self.connect()
        encoded = base64.urlsafe_b64encode(b"private body").decode()
        cases = (
            # Duplicate conflicting parameter, as the sender spelled it.
            ("Content-Type", "text/plain; charset=utf-8; charset=iso-8859-1"),
            # The same duplicate spelled in two cases, optionally hidden behind
            # a comment. RFC 2045 parameter names are case-insensitive, so
            # these are one parameter given twice.
            ("Content-Type", "text/plain; charset=utf-8; CHARSET=iso-8859-1"),
            ("Content-Type", "text/plain; charset=us-ascii; (x) CHARSET=utf-8"),
            # Unterminated comment and unterminated quoted string.
            ("Content-Type", "text/plain; charset=utf-8; (unterminated"),
            ("Content-Type", "text/plain; charset=(unterminated utf-8"),
            ("Content-Type", 'text/plain; charset="utf-8'),
            # Embedded control characters. HTAB is legal and excluded here.
            ("Content-Type", "text/plain; charset=utf-8\r"),
            ("Content-Type", "text/plain; charset=utf-8\n"),
            ("Content-Type", "text/plain; charset=utf-8\x00"),
            ("Content-Type", "text/plain; charset=utf-8\x01"),
            ("Content-Type", "text/plain; charset=utf-8\x7f"),
            # No media type at all.
            ("Content-Type", ""),
            ("Content-Type", "   "),
            ("Content-Type", "notatype"),
            # A doubled interior semicolon IS a defect, unlike a trailing
            # one: CPython records InvalidHeaderDefect for the empty
            # segment between two parameters but not for one at the end.
            ("Content-Type", "text/plain;; charset=utf-8"),
            # The same rule applies to the disposition header, which decides
            # whether the part may become the body at all.
            ("Content-Disposition", "inline\r"),
            ("Content-Disposition", "inline\n"),
            ("Content-Disposition", "inline\x00"),
            ("Content-Disposition", 'attachment; filename="unterminated'),
            ("Content-Disposition", "inline; filename=a; FILENAME=b"),
        )
        for header_name, value in cases:
            with self.subTest(header=header_name, value=repr(value)):
                self.responses.clear()
                self.responses.append({
                    "id": "m_1",
                    "threadId": "t_1",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [{"name": header_name, "value": value}],
                        "body": {"data": encoded},
                    },
                })
                with self.assertRaises(GmailError) as malformed:
                    self.read()
                self.assertEqual(malformed.exception.reason, "invalid_provider_response")
                self.assertNotIn("private body", str(malformed.exception))

    def test_mixed_rfc2231_forms_are_judged_on_the_resolved_value(self):
        """Where these are refused moved, but they are still refused.

        Mixing an RFC 2231 extended parameter with a sectioned continuation
        (``charset*=utf-8''x; charset*1=y``) was refused at the header gate by
        the hand-written scanner. The stdlib parser reads it without recording
        a defect, so the header now parses and the value it resolves to -
        the sections concatenated - reaches the charset allowlist instead.

        The outcome is unchanged: every form below still fails closed. Pinned
        because the refusal point moved, which is the kind of change that
        looks like a widening in a diff and needs to be stated rather than
        discovered.
        """
        self.connect()
        encoded = base64.urlsafe_b64encode(b"private body").decode()
        for header_name, value in (
            ("Content-Type", "text/plain; charset*=utf-8''x; charset*1=y"),
            ("Content-Type", "text/plain; charset*1=y; charset*=utf-8''x"),
            ("Content-Type", "text/plain; charset*=us-ascii''utf-7; charset*1=z"),
            ("Content-Type", "text/plain; charset*=us-ascii''utf-8; charset*1=z"),
            ("Content-Disposition", "inline; filename*=utf-8''a.txt; filename*1=b"),
        ):
            with self.subTest(header=header_name, value=value):
                self.responses.clear()
                self.responses.append({
                    "id": "m_1",
                    "threadId": "t_1",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [{"name": header_name, "value": value}],
                        "body": {"data": encoded},
                    },
                })
                if header_name == "Content-Type":
                    with self.assertRaises(GmailError) as refused:
                        self.read()
                    self.assertIn(
                        refused.exception.reason,
                        {"unsupported_charset", "invalid_provider_response"},
                    )
                    self.assertNotIn("private body", str(refused.exception))
                else:
                    # A disposition parameter is not decoded, so this one is
                    # simply read as an inline body rather than refused.
                    self.assertEqual(self.read().body, "private body")

    def test_no_defect_and_no_duplicate_is_never_refused(self):
        """The invariant the duplicate check must not violate.

        Two hand-enumerated tables guard this function: one listing
        malformations that must be refused, one listing legal shapes that must
        be accepted. Both are lists, and the function's failure mode is
        precisely "the case nobody listed" - the previous cycle's table missed
        a trailing semicolon, and the commit that fixed it introduced a crash
        on an RFC 2231 form that was also not listed.

        So state the rule instead of extending the list: if the stdlib parse
        records no defect and no parameter name repeats once case and comments
        are folded, the header is legal as far as this module can tell and
        must not be refused. Generated inputs, not chosen ones - a future
        member of the class fails here without anyone having thought of it.
        """
        import itertools
        import re
        from email.headerregistry import HeaderRegistry

        registry = HeaderRegistry()
        comment = re.compile(r"\([^()]*\)")

        def folded_names(value):
            """Parameter names as a sender wrote them, comments stripped."""
            names = []
            for segment in value.split(";")[1:]:
                bare = comment.sub("", segment).split("=", 1)[0].strip().casefold()
                # An RFC 2231 continuation or extended form is one parameter.
                bare = re.sub(r"\*\d*\*?$", "", bare)
                if bare:
                    names.append(bare)
            return names

        fragments = (
            "charset=utf-8", "charset=us-ascii", 'name="a.txt"', "name=a.txt",
            "format=flowed", "boundary=B", 'start="<root>"',
            "charset*0=utf-", "charset*1=8", "charset*=us-ascii''utf-8",
            "name*0=a", "name*1=.txt", "(c)", "", " ", "\t",
        )
        refused = []
        for count in (1, 2, 3):
            for combination in itertools.product(fragments, repeat=count):
                value = "text/plain; " + "; ".join(combination)
                names = folded_names(value)
                if len(names) != len(set(names)):
                    continue  # a genuine duplicate; refusal is correct
                try:
                    parsed = registry("Content-Type", value)
                except Exception:
                    continue  # stdlib itself cannot read it; refusal is correct
                if parsed.defects:
                    continue  # the defect gate owns this; refusal is correct
                try:
                    _parsed_mime_header("Content-Type", value)
                except GmailError:
                    refused.append(value)
                except Exception as unexpected:
                    self.fail(
                        "non-GmailError escaped the connector for "
                        f"{value!r}: {type(unexpected).__name__}"
                    )
        self.assertEqual(refused, [], f"{len(refused)} legal headers refused")

    def test_empty_parameter_segments_do_not_refuse_ordinary_mail(self):
        """A trailing semicolon must not make a message unreadable.

        The duplicate-name check compares how many parameters were written
        against how many survived folding. ``get_params`` emits a nameless
        ``('', '')`` entry for an empty segment, so counting those refused a
        header that CPython records no defect for - an ordinary trailing
        semicolon, which any sender can append.

        The harm was not a rejected header. The refusal happens inside
        ``_body``, so ``read_message`` returns nothing and the owner loses
        subject, sender and date as well. A previous review cycle fixed
        exactly that harm class; the count heuristic reopened it, and the
        defect table added alongside it did not contain a single trailing
        semicolon - another enumeration.
        """
        self.connect()
        encoded = base64.urlsafe_b64encode(b"readable body").decode()
        for header_name, value in (
            ("Content-Type", "text/plain;"),
            ("Content-Type", "text/plain ;"),
            ("Content-Type", "text/plain;\t"),
            ("Content-Type", "text/plain; charset=utf-8;"),
            ("Content-Type", "text/plain; charset=utf-8; "),
            ("Content-Disposition", "inline;"),
            ("Content-Disposition", "inline ;"),
            ("Content-Disposition", 'inline; filename="a.txt";'),
        ):
            with self.subTest(header=header_name, value=repr(value)):
                self.responses.clear()
                self.responses.append({
                    "id": "m_1",
                    "threadId": "t_1",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [{"name": header_name, "value": value}],
                        "body": {"data": encoded},
                    },
                })
                self.assertEqual(self.read().body, "readable body")

        # The same shape on an explicitly declared attachment must still give
        # the truthful empty body rather than an error.
        self.responses.clear()
        self.responses.append({
            "id": "m_1",
            "threadId": "t_1",
            "payload": {
                "mimeType": "multipart/mixed",
                "parts": [{
                    "mimeType": "application/pdf",
                    "filename": "invoice.pdf",
                    "headers": [{
                        "name": "Content-Disposition",
                        "value": 'attachment; filename="invoice.pdf";',
                    }],
                    "body": {"attachmentId": "a1"},
                }],
            },
        })
        self.assertEqual(self.read().body, "")

    def test_media_type_grammar_is_delegated_but_still_agreement_bound(self):
        """Record what removing the hand-written media-type regex widened.

        The regex rejected any type outside its own character class. The
        parsed type is now compared for equality against Gmail's ``mimeType``
        instead, which constrains agreement rather than grammar, so
        spec-conformant CFWS around the solidus and token characters the old
        class omitted are accepted where they previously were not.

        This is a deliberate widening and is pinned here so it cannot drift
        further unnoticed. It crosses no boundary: the charset allowlist is
        unchanged, and only ``text/plain`` and ``text/html`` are ever decoded
        as a body, so a type outside that pair still yields a truthful empty
        body rather than rendered content.
        """
        self.connect()
        encoded = base64.urlsafe_b64encode(b"cfws body").decode()
        # CFWS around the solidus is legal and now yields the body.
        for value in ("text /plain", "text/ plain", "text / plain"):
            with self.subTest(accepted=value):
                self.responses.clear()
                self.responses.append({
                    "id": "m_1",
                    "threadId": "t_1",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [{"name": "Content-Type", "value": value}],
                        "body": {"data": encoded},
                    },
                })
                self.assertEqual(self.read().body, "cfws body")

        # A type the old regex rejected is accepted by the grammar but is not
        # text/plain or text/html, so it is never decoded as a body.
        for value in ("text/plain%", "text/plain*", "text/plain|"):
            with self.subTest(not_decoded=value):
                self.responses.clear()
                self.responses.append({
                    "id": "m_1",
                    "threadId": "t_1",
                    "payload": {
                        "mimeType": value,
                        "headers": [{"name": "Content-Type", "value": value}],
                        "body": {"data": encoded},
                    },
                })
                self.assertEqual(self.read().body, "")

        # Disagreement between the parsed type and Gmail's own mimeType is
        # still refused - that is the check the regex was replaced by.
        self.responses.clear()
        self.responses.append({
            "id": "m_1",
            "threadId": "t_1",
            "payload": {
                "mimeType": "text/plain",
                "headers": [{"name": "Content-Type", "value": "text/html"}],
                "body": {"data": encoded},
            },
        })
        with self.assertRaises(GmailError) as mismatch:
            self.read()
        self.assertEqual(mismatch.exception.reason, "invalid_provider_response")

    def test_rfc2231_extended_parameter_cannot_smuggle_a_blocked_charset(self):
        """An RFC 2231 charset reaches the allowlist like any other.

        ``charset*=us-ascii\'\'utf-7`` parses cleanly - no defect - and the
        stdlib resolves it to ``utf-7``. The defect rule therefore cannot be
        the thing that stops it; the curated allowlist has to, and it must see
        the resolved value rather than the literal parameter text.
        """
        self.connect()
        for encoding, refused_charset in (
            ("us-ascii''utf-7", "utf-7"),
            ("us-ascii''unicode_escape", "unicode_escape"),
        ):
            with self.subTest(charset=refused_charset):
                markup = "<script>alert(1)</script>"
                raw = (
                    markup.encode("utf-7")
                    if refused_charset == "utf-7"
                    else b"\\u003cscript\\u003e"
                )
                self.responses.clear()
                self.responses.append({
                    "id": "m_1",
                    "threadId": "t_1",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [
                            {"name": "Content-Type", "value": "text/plain; charset*=" + encoding}
                        ],
                        "body": {"data": base64.urlsafe_b64encode(raw).decode()},
                    },
                })
                with self.assertRaises(GmailError) as refused:
                    self.read()
                self.assertEqual(refused.exception.reason, "unsupported_charset")
                self.assertNotIn("script", str(refused.exception))

        # A sectioned continuation naming an allowed charset still decodes, so
        # the gate reads the reassembled value and does not simply distrust
        # every RFC 2231 parameter.
        self.responses.clear()
        self.responses.append({
            "id": "m_1",
            "threadId": "t_1",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "Content-Type", "value": "text/plain; charset*0=utf-; charset*1=8"}
                ],
                "body": {"data": base64.urlsafe_b64encode("café".encode()).decode()},
            },
        })
        self.assertEqual(self.read().body, "café")

    def test_search_result_exposes_symmetric_redacted_evidence(self):
        self.connect()
        self.responses.append({"messages": [{"id": "m_1"}]})
        self.responses.append(self.metadata())
        result = self.gmail.search("owner-a", "receipt")[0]
        evidence = result.as_evidence()
        self.assertEqual(evidence["metadata_included"], False)
        self.assertEqual(evidence["source"], result.source)
        for private in ("Booking receipt", "vendor@example.test", "Mon, 1 Sep 2026"):
            self.assertNotIn(private, str(evidence))
        self.assertIn("Booking receipt", str(result.as_dict()))

    def test_adapter_surface_raises_only_gmail_errors(self):
        for owner in ("", "   ", None, 0, "x" * 201):
            with self.subTest(owner=repr(owner)):
                for call in (
                    self.gmail.status,
                    self.gmail.portable_status,
                    self.gmail.connection_required,
                ):
                    with self.assertRaises(GmailError) as invalid:
                        call(owner)
                    self.assertEqual(invalid.exception.reason, "invalid_owner")
        self.connect()
        # required_result raises the shared contract error once connected. The
        # adapter must translate it so downstream wiring catches one type.
        with self.assertRaises(GmailError) as connected:
            self.gmail.connection_required("owner-a")
        self.assertEqual(connected.exception.reason, "already_connected")

    def test_lifecycle_transition_and_revocation_do_not_deadlock(self):
        """Pin the repository-wide ``dispatch -> authority`` lock order.

        ``mark_reauthentication_required`` previously took the process-wide
        authority lock and then called ``transition``, which takes the dispatch
        lock first. A concurrent registry transition holding dispatch and
        waiting on authority wedged every connector in the process. The joins
        below use a timeout so a returning inversion fails instead of hanging.
        """
        self.connect()
        start = threading.Barrier(3, timeout=30)
        errors = []

        def revoke():
            try:
                start.wait()
                for _ in range(50):
                    self.gmail.mark_reauthentication_required("owner-a")
            except Exception as exc:  # pragma: no cover - failure detail only
                errors.append(exc)

        def cycle():
            try:
                start.wait()
                for _ in range(50):
                    self.registry.transition(
                        "owner-a",
                        GMAIL_CONNECTOR_ID,
                        ConnectorState.CONNECTED,
                        granted_scopes=(GMAIL_READONLY_SCOPE,),
                    )
                    self.registry.transition(
                        "owner-a", GMAIL_CONNECTOR_ID, ConnectorState.DISCONNECTED
                    )
            except Exception as exc:  # pragma: no cover - failure detail only
                errors.append(exc)

        # daemon=True so a returning inversion reports a normal test failure
        # instead of wedging interpreter shutdown on unjoinable threads.
        threads = [
            threading.Thread(target=revoke, daemon=True),
            threading.Thread(target=cycle, daemon=True),
        ]
        for thread in threads:
            thread.start()
        start.wait()
        for thread in threads:
            thread.join(timeout=20)
        self.assertEqual(
            [thread.name for thread in threads if thread.is_alive()],
            [],
            "Gmail lifecycle locking deadlocked",
        )
        self.assertEqual(errors, [])
        self.assertIn(
            self.gmail.status("owner-a")["state"],
            {"connected", "disconnected", "reauth_required"},
        )

    def test_owner_namespaced_oauth_state_and_tokens_do_not_overwrite_or_cross_revoke(self):
        _offer_a,state_a=self.begin("owner-a")
        _offer_b,state_b=self.begin("owner-b")
        for owner,state,token in (("owner-a",state_a,"token-a"),("owner-b",state_b,"token-b")):
            self.gmail.complete_oauth(
                owner,
                {"state":state,"code":"oauth-code"},
                lambda _request, token=token: {
                    "access_token":token,
                    "refresh_token":"refresh-"+token,
                    "expires_in":60,
                    "scope":GMAIL_READONLY_SCOPE,
                },
            )
        self.assertEqual(
            self.store.secret(self.secret_key("gmail_oauth_tokens","owner-a"))["access_token"],
            "token-a",
        )
        self.assertEqual(
            self.store.secret(self.secret_key("gmail_oauth_tokens","owner-b"))["access_token"],
            "token-b",
        )

        self.responses.extend(({"messages":[]},{"messages":[]}))
        self.assertEqual(self.gmail.search("owner-a","receipt"),())
        self.assertEqual(self.gmail.search("owner-b","receipt"),())
        self.assertEqual(self.calls[-2][3]["Authorization"],"Bearer token-a")
        self.assertEqual(self.calls[-1][3]["Authorization"],"Bearer token-b")

        self.responses.append({"status_code":401})
        with self.assertRaises(GmailReauthenticationRequired):
            self.gmail.search("owner-a","receipt")
        self.assertEqual(self.gmail.status("owner-a")["state"],"reauth_required")
        self.assertEqual(self.gmail.status("owner-b")["state"],"connected")
        self.assertEqual(self.store.secret(self.secret_key("gmail_oauth_tokens","owner-a")),{})
        self.assertEqual(
            self.store.secret(self.secret_key("gmail_oauth_tokens","owner-b"))["access_token"],
            "token-b",
        )
        self.responses.append({"messages":[]})
        self.assertEqual(self.gmail.search("owner-b","receipt"),())

    def test_late_401_from_superseded_connection_does_not_revoke_new_token(self):
        self.connect(access_token="token-a", refresh_token="refresh-a")

        def reconnect_then_reject(_method, _endpoint, _params, _headers):
            self.registry.transition("owner-a", GMAIL_CONNECTOR_ID, ConnectorState.DISCONNECTED)
            _offer, state = self.begin()
            self.gmail.complete_oauth(
                "owner-a",
                {"state": state, "code": "new-code"},
                lambda _: {
                    "access_token": "token-b",
                    "refresh_token": "refresh-b",
                    "expires_in": 60,
                    "scope": GMAIL_READONLY_SCOPE,
                },
            )
            return {"status_code": 401}

        self.gmail.transport = reconnect_then_reject
        with self.assertRaises(GmailError) as stale:
            self.gmail.search("owner-a", "receipt")
        self.assertEqual(stale.exception.reason, "superseded_connection")
        self.assertEqual(self.gmail.status("owner-a")["state"], "connected")
        self.assertEqual(self.store.secret(self.secret_key("gmail_oauth_tokens"))["access_token"], "token-b")

    def test_restart_restores_redacted_metadata_and_encrypted_credentials_only(self):
        self.connect()
        stored = self.raw_store.secret("encrypted:gmail:" + self.secret_key("gmail_oauth_tokens"))
        self.assertIsInstance(stored, str)
        self.assertNotIn("access-secret", stored)
        restarted_raw = QuickStore(self.temp.name)
        restarted_store = EncryptedGmailSecretStore(restarted_raw, self.key)
        restarted_registry = ConnectorRegistry(restarted_store, (GMAIL_CONNECTOR,), clock=lambda: self.clock[0])
        restarted_calls = []

        def restarted_transport(method, endpoint, params, headers):
            restarted_calls.append((method, endpoint, params, headers))
            return {"messages": []}

        restarted = GmailConnector(
            restarted_store,
            "gmail-client",
            "https://connect.example.test/gmail/callback",
            registry=restarted_registry,
            transport=restarted_transport,
            now=lambda: self.clock[0],
        )
        self.assertEqual(restarted.status("owner-a")["state"], "connected")
        self.assertEqual(restarted.search("owner-a", "receipt"), ())
        self.assertEqual(restarted_calls[0][0], "GET")
        self.assertEqual(restarted_store.secret(self.secret_key("gmail_oauth_tokens"))["access_token"], "access-secret")
        self.assertNotIn("access-secret", str(restarted.portable_status("owner-a")))

    def test_wrong_owner_cannot_use_restarted_token_and_no_mutation_surface_exists(self):
        self.connect()
        with self.assertRaises(GmailError) as error:
            self.gmail.search("owner-b", "receipt")
        self.assertEqual(error.exception.reason, "connection_required")
        self.assertEqual(self.calls, [])

    def test_module_has_no_mutating_http_verb(self):
        """Assert the read-only surface from the module, not from absent names.

        ``assertFalse(hasattr(obj, "send"))`` for invented method names passes
        for any object and proves nothing. The connector dispatches through a
        single caller-supplied transport, so the check that matters is that no
        mutating verb literal exists in the module at all.
        """
        source = pathlib.Path(gmail_module.__file__).read_text()
        for verb in ("POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRASH"):
            self.assertIsNone(
                re.search(rf"""['"]{verb}['"]""", source),
                f"module contains a {verb} request literal",
            )
        self.assertEqual(re.findall(r"""self\.transport\(\s*['"](\w+)['"]""", source), ["GET"])

    def test_corrupt_encrypted_secret_fails_closed_without_disclosure(self):
        self.connect()
        self.raw_store.secret("encrypted:gmail:" + self.secret_key("gmail_oauth_tokens"), "not-a-valid-token")
        with self.assertRaises(GmailError) as error:
            self.gmail.search("owner-a", "receipt")
        self.assertIsInstance(error.exception, GmailReauthenticationRequired)
        self.assertEqual(error.exception.reason, "reauth_required")
        self.assertEqual(str(error.exception), "Gmail request rejected")
        self.assertEqual(self.gmail.status("owner-a")["state"], "reauth_required")
        self.assertEqual(self.store.secret(self.secret_key("gmail_oauth_tokens")), {})

    def test_inflight_token_corruption_revokes_matching_connected_revision(self):
        self.connect()

        def corrupt_after_dispatch(_method, _endpoint, _params, _headers):
            self.raw_store.secret("encrypted:gmail:" + self.secret_key("gmail_oauth_tokens"), "not-a-valid-token")
            return {"messages": []}

        self.gmail.transport = corrupt_after_dispatch
        with self.assertRaises(GmailReauthenticationRequired):
            self.gmail.search("owner-a", "receipt")
        self.assertEqual(self.gmail.status("owner-a")["state"], "reauth_required")
        self.assertEqual(self.store.secret(self.secret_key("gmail_oauth_tokens")), {})


if __name__ == "__main__":
    unittest.main()

import base64
import hashlib
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

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

    def test_non_text_registered_codec_is_rejected_as_provider_data(self):
        self.connect()
        self.responses.append(
            {
                "id": "m_1",
                "threadId": "t_1",
                "payload": {
                    "mimeType": "text/plain",
                    "headers": [
                        {"name": "Content-Type", "value": "text/plain; charset=base64_codec"}
                    ],
                    "body": {"data": base64.urlsafe_b64encode(b"body").decode()},
                },
            }
        )
        with self.assertRaises(GmailError) as malformed:
            self.read()
        self.assertEqual(malformed.exception.reason, "invalid_provider_response")

    def test_charset_lookup_and_decode_failures_are_bounded_provider_errors(self):
        self.connect()
        for charset in ("undefined", "utf-8\x00"):
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

        for status in ("200", True):
            self.responses.append({"status_code": status, "messages": []})
            with self.assertRaises(GmailError) as malformed:
                self.gmail.search("owner-a", "receipt")
            self.assertEqual(malformed.exception.reason, "invalid_provider_response")

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
        for forbidden in (
            "send",
            "reply",
            "forward",
            "delete",
            "archive",
            "create_draft",
            "modify_labels",
            "watch",
        ):
            self.assertFalse(hasattr(self.gmail, forbidden), forbidden)

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

import base64
import hashlib
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

from personal_agent.google_drive import DRIVE_READONLY, DriveAuthorizationError, GoogleDrive, GoogleDriveConnection
from personal_agent.quickstart_store import QuickStore


class DriveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = QuickStore(self.temp.name)
        self.calls = []
        def transport(url, body, headers):
            self.calls.append((url, body, headers))
            if url.endswith("/token"):
                return {"access_token": "access-secret", "refresh_token": "refresh-secret", "scope": DRIVE_READONLY}
            return {"files": [{"id": "a", "name": "plan", "mimeType": "text/plain"}]}
        self.transport = transport
        self.connection = GoogleDriveConnection(self.store, transport, "public-client-id", "http://127.0.0.1:9999/callback")

    def tearDown(self):
        self.temp.cleanup()

    def test_read_only_search_and_escaped_file_id(self):
        drive = GoogleDrive(self.transport, "secret")
        self.assertEqual(drive.search("plan"), [{"id": "a", "name": "plan", "mime_type": "text/plain", "modified_time": ""}])
        drive.read("a/b")
        self.assertIn("a%2Fb", self.calls[-1][0])
        self.assertNotIn("secret", self.calls[0][0])

    def test_connect_uses_pkce_and_keeps_verifier_out_of_url(self):
        result = self.connection.connect()
        query = parse_qs(urlparse(result["authorization_url"]).query)
        self.assertEqual(query["scope"], [DRIVE_READONLY])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertNotIn("code_verifier", query)
        self.assertEqual(self.store.secret("google_drive_oauth_pending")["state"], result["state"])

    def test_state_mismatch_and_denial_do_not_call_token_endpoint(self):
        pending = self.connection.connect()
        with self.assertRaises(DriveAuthorizationError): self.connection.complete({"code": "code", "state": "wrong"})
        self.assertFalse(self.calls)
        with self.assertRaises(DriveAuthorizationError): self.connection.complete({"error": "access_denied", "state": pending["state"]})
        self.assertFalse(self.calls)
        self.assertEqual(self.connection.status()["state"], "disconnected")

    def test_tokens_are_private_status_is_redacted_and_disconnect_removes_them(self):
        pending = self.connection.connect()
        self.assertEqual(self.connection.complete({"code": "code", "state": pending["state"]}), {"state": "connected", "audit": ["connected"]})
        self.assertIn("access-secret", str(self.store.secret("google_drive_tokens")))
        self.assertNotIn("access-secret", str(self.connection.status()))
        self.assertEqual(self.connection.health(), {"ok": True, "state": "connected"})
        self.assertEqual(self.connection.disconnect(), {"state": "disconnected", "audit": ["connected", "disconnected"]})
        self.assertEqual(self.store.secret("google_drive_tokens"), "")

    def test_missing_scope_and_transport_error_fail_closed(self):
        pending = self.connection.connect()
        self.connection.transport = lambda *args: {"access_token": "secret", "scope": "https://www.googleapis.com/auth/drive.metadata.readonly"}
        with self.assertRaises(DriveAuthorizationError): self.connection.complete({"code": "code", "state": pending["state"]})
        self.assertEqual(self.connection.status()["state"], "disconnected")
        self.assertEqual(GoogleDrive(lambda *args: (_ for _ in ()).throw(RuntimeError("offline")), "secret").health(), {"ok": False, "error": "RuntimeError"})

    def test_pkce_challenge_is_a_real_s256_transform_and_scope_is_not_widened(self):
        """SEC-DRIVE-SCOPE-01 / #432 items 4 and 5.

        ``_pkce_pair`` now uses oauthlib, like gmail.py and drive_web_oauth.py.
        Asserting the advertised method alone is not enough: oauthlib's
        ``create_code_challenge`` silently returns the verifier unchanged -- a
        plain challenge -- when the method argument is omitted, so a URL can
        advertise S256 while carrying no transform. The hand-rolled sha256 this
        replaced could not fail that way, so adoption introduced the mode.
        """
        pending = self.connection.connect()
        query = parse_qs(urlparse(pending["authorization_url"]).query)
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertNotIn("code_verifier", query)
        verifier = self.store.secret("google_drive_oauth_pending")["verifier"]
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(query["code_challenge"], [expected])
        self.assertNotEqual(query["code_challenge"], [verifier])
        # Do not let Google fold scopes granted elsewhere into this grant; the
        # exact-set check would then hard-fail a connection that used to work.
        self.assertEqual(query["include_granted_scopes"], ["false"])
        self.assertEqual(query["scope"], [DRIVE_READONLY])

    def test_scope_is_exact_at_exchange(self):
        """SEC-DRIVE-SCOPE-01 / #432.

        The previous check was ``DRIVE_READONLY not in str(tokens.get("scope",
        DRIVE_READONLY))``.  Its default made the check vacuous when the server
        omitted ``scope``, and the substring test accepted drive.readonly plus
        anything else.  Both now fail closed.
        """
        refused = [
            {},                                                   # key absent entirely
            {"scope": ""},                                        # present but empty
            {"scope": None},                                      # present but null
            {"scope": DRIVE_READONLY + " https://www.googleapis.com/auth/drive"},   # over-granted
            {"scope": "https://www.googleapis.com/auth/drive " + DRIVE_READONLY},   # over-granted, other order
            {"scope": DRIVE_READONLY + "x"},                      # near-miss suffix
            {"scope": "https://www.googleapis.com/auth/drive.metadata.readonly"},   # wrong scope
            {"scope": DRIVE_READONLY.upper()},                    # OAuth scopes are case-sensitive
            {"scope": DRIVE_READONLY + "/"},                      # trailing slash
        ]
        for extra in refused:
            with self.subTest(scope=extra.get("scope", "<absent>")):
                # Fresh store per case: the subtests share self.connection, so
                # a case that wrongly connects would otherwise contaminate the
                # ones after it and be scored as extra detections.
                self.store = QuickStore(tempfile.mkdtemp(dir=self.temp.name))
                self.connection = GoogleDriveConnection(self.store, self.transport, "public-client-id", "http://127.0.0.1:9999/callback")
                pending = self.connection.connect()
                self.connection.transport = lambda *args, _e=extra: {"access_token": "secret", **_e}
                with self.assertRaises(DriveAuthorizationError):
                    self.connection.complete({"code": "code", "state": pending["state"]})
                self.assertEqual(self.connection.status()["state"], "disconnected")
                self.assertEqual(self.store.secret("google_drive_tokens"), "")

    def test_exact_scope_is_accepted_and_stored_canonically(self):
        """The positive control: the refusals above are the scope gate, not a broken fixture."""
        pending = self.connection.connect()
        self.connection.transport = lambda *args: {"access_token": "secret", "scope": "  %s  " % DRIVE_READONLY}
        self.connection.complete({"code": "code", "state": pending["state"]})
        self.assertEqual(self.connection.status()["state"], "connected")
        # Stored as this code's own validated value, not the response's text,
        # so the use-time check compares against something we decided.
        self.assertEqual(self.store.secret("google_drive_tokens")["scope"], DRIVE_READONLY)

    def test_a_stored_credential_with_the_wrong_scope_is_refused_on_use(self):
        """Tightening only the exchange would leave an already-stored credential usable.

        A token accepted by the earlier vacuous check keeps working forever
        unless the scope is re-checked where it is used, which is what Gmail
        does in ``_authorization_context``.
        """
        pending = self.connection.connect()
        self.connection.complete({"code": "code", "state": pending["state"]})
        self.assertIsNotNone(self.connection.adapter())
        for bad in ("", DRIVE_READONLY + " https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/drive"):
            with self.subTest(scope=bad):
                tokens = self.store.secret("google_drive_tokens")
                tokens["scope"] = bad
                self.store.secret("google_drive_tokens", tokens)
                with self.assertRaises(DriveAuthorizationError):
                    self.connection.adapter()
                self.assertEqual(self.connection.health(), {"ok": False, "state": "reauth-required"})
                # The audit distinguishes why: a scope refusal is not an expiry.
                self.assertEqual(self.connection.status()["audit"][-1], "scope-rejected")

    def test_a_stored_credential_missing_scope_entirely_is_refused_on_use(self):
        pending = self.connection.connect()
        self.connection.complete({"code": "code", "state": pending["state"]})
        tokens = self.store.secret("google_drive_tokens")
        tokens.pop("scope")
        self.store.secret("google_drive_tokens", tokens)
        with self.assertRaises(DriveAuthorizationError):
            self.connection.adapter()
        self.assertEqual(self.connection.health(), {"ok": False, "state": "reauth-required"})

    def test_expired_token_requires_reauth_and_reconnect_restores_health(self):
        pending = self.connection.connect(); self.connection.complete({"code": "code", "state": pending["state"]})
        tokens = self.store.secret("google_drive_tokens"); tokens["expires_at"] = 0; self.store.secret("google_drive_tokens", tokens)
        with self.assertRaises(DriveAuthorizationError): self.connection.adapter()
        self.assertEqual(self.connection.health(), {"ok": False, "state": "reauth-required"})
        pending = self.connection.connect(); self.connection.complete({"code": "code", "state": pending["state"]})
        self.assertEqual(self.connection.health(), {"ok": True, "state": "connected"})

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
        ]
        for extra in refused:
            with self.subTest(scope=extra.get("scope", "<absent>")):
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

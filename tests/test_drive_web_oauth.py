import tempfile
import threading
import unittest
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

from personal_agent.drive_web_oauth import DRIVE_FILE, EncryptedDriveSecretStore, DriveScopeError, DriveWebOAuthError, DriveWebOAuthHandoff
from personal_agent.quickstart_store import QuickStore
from personal_agent.quickstart_service import AgentService
from personal_agent.providers import ProviderError


class DriveWebOAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = QuickStore(self.temp.name)
        self.encrypted_store = EncryptedDriveSecretStore(self.store, Fernet.generate_key())
        self.clock = [1000]
        self.flow = DriveWebOAuthHandoff(self.encrypted_store, "web-client", "https://connect.example.test/oauth/callback", "https://connect.example.test", now=lambda: self.clock[0])

    def tearDown(self):
        self.temp.cleanup()

    def begin(self):
        offer = self.flow.begin(42)
        return offer, parse_qs(urlparse(offer["button"]["url"]).query)["state"][0]

    def connect(self):
        _offer, state = self.begin()
        return self.flow.complete({"state": state, "code": "short-code"}, 42, lambda request: {"access_token": "access-secret", "refresh_token": "refresh-secret", "scope": DRIVE_FILE, "expires_in": 60})

    def test_telegram_offer_is_https_and_oauth_uses_pkce_and_drive_file_only(self):
        offer, state = self.begin()
        self.assertEqual(offer["button"]["text"], "Google Drive 연결하기")
        self.assertTrue(offer["button"]["url"].startswith("https://"))
        self.assertNotIn("verifier", offer["button"]["url"])
        self.assertEqual(len(state.split(".")), 2)
        query = parse_qs(urlparse(self.flow.authorization_url(state, 42)).query)
        self.assertEqual(query["scope"], [DRIVE_FILE])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertNotIn("code_verifier", query)

    def test_local_only_mode_requires_explicit_opt_in_and_uses_loopback(self):
        with self.assertRaises(ValueError):
            DriveWebOAuthHandoff(self.encrypted_store, "web-client", "http://localhost:8787/oauth/callback", "http://localhost:8787")
        local = DriveWebOAuthHandoff(self.encrypted_store, "web-client", "http://localhost:8787/oauth/callback", "http://localhost:8787", allow_localhost=True)
        self.assertTrue(local.begin(42)["button"]["url"].startswith("http://localhost:8787/"))
        with self.assertRaises(ValueError):
            DriveWebOAuthHandoff(self.encrypted_store, "web-client", "https://example.test/callback", "https://example.test", local_only=True)

    def test_callback_is_owner_bound_single_use_and_redacts_tokens_from_status(self):
        self.assertEqual(self.connect()["state"], "connected")
        self.assertNotIn("secret", str(self.flow.status()))
        self.assertNotIn("access-secret", str(self.store.secret("encrypted:drive_web_oauth_tokens")))
        self.assertIn("access-secret", str(self.encrypted_store.secret("drive_web_oauth_tokens")))
        with self.assertRaises(DriveWebOAuthError):
            self.flow.complete({"state": "replay", "code": "again"}, 42, lambda _: {})

    def test_wrong_owner_denial_expiry_and_failed_callback_recover_without_tokens(self):
        _offer, state = self.begin()
        with self.assertRaises(DriveWebOAuthError): self.flow.authorization_url(state, 99)
        with self.assertRaises(DriveWebOAuthError): self.flow.complete({"state": state, "error": "access_denied"}, 42, lambda _: {})
        self.assertEqual(self.flow.status()["state"], "denied")
        _offer, state = self.begin(); self.clock[0] += 601
        with self.assertRaises(DriveWebOAuthError): self.flow.authorization_url(state, 42)
        self.assertEqual(self.flow.status()["state"], "expired")
        self.assertEqual(self.encrypted_store.secret("drive_web_oauth_tokens"), "")

    def test_plaintext_store_is_rejected_and_telegram_sends_https_connection_button(self):
        with self.assertRaises(ValueError):
            DriveWebOAuthHandoff(self.store, "web-client", "https://connect.example.test/oauth/callback", "https://connect.example.test")
        calls = []
        def transport(url, body, headers=None, timeout=60):
            calls.append((url, body)); return {"ok": True, "result": {"message_id": 1}}
        self.store.secret("telegram_token", "test-token")
        self.store.put("telegram", {"enabled": True, "generation": "g", "user_id": 42, "cursor": 0})
        service = AgentService(self.store, telegram_transport=transport, drive_web_oauth=self.flow)
        service.ingest_update({"update_id": 1, "message": {"from": {"id": 42}, "chat": {"id": 42, "type": "private"}, "text": "내 구글 드라이브에서 자료를 찾아줘"}}, "g")
        sent = next(body for _url, body in calls if "reply_markup" in body and "Google Drive 연결하기" in str(body["reply_markup"]))
        self.assertEqual(sent["text"], "Google Drive 연결이 필요합니다. 선택한 파일만 읽을 수 있으며 전체 Drive 검색은 하지 않습니다.")
        self.assertTrue(sent["reply_markup"]["inline_keyboard"][0][0]["url"].startswith("https://"))

    def test_callback_publishes_redacted_connected_and_denied_recovery_messages(self):
        calls = []
        def transport(url, body, headers=None, timeout=60):
            calls.append((url, body)); return {"ok": True, "result": {"message_id": 1}}
        self.store.secret("telegram_token", "test-token")
        service = AgentService(self.store, telegram_transport=transport, drive_web_oauth=self.flow)
        offer, state = self.begin()
        service.complete_drive_web_oauth({"state": state, "code": "code"}, 42, lambda _request: {"access_token": "access-secret", "scope": DRIVE_FILE})
        self.assertIn("연결되었습니다", calls[-1][1]["text"])
        _offer, state = self.begin()
        with self.assertRaises(DriveWebOAuthError):
            service.complete_drive_web_oauth({"state": state, "error": "access_denied"}, 42, lambda _request: {})
        self.assertIn("허용되지 않았습니다", calls[-1][1]["text"])
        self.assertNotIn("access-secret", str(calls))

    def test_failed_exchange_is_consumed_and_publishes_recovery(self):
        calls=[]
        self.store.secret("telegram_token", "test-token")
        service=AgentService(self.store, telegram_transport=lambda url, body, headers=None, timeout=60: calls.append(body) or {"ok": True, "result": {}} , drive_web_oauth=self.flow)
        _offer, state=self.begin()
        with self.assertRaises(DriveWebOAuthError):
            service.complete_drive_web_oauth({"state": state, "code": "code"}, 42, lambda _request: (_ for _ in ()).throw(RuntimeError("offline")))
        self.assertEqual(self.flow.status()["state"], "callback-failed")
        self.assertIn("완료하지 못했습니다", calls[-1]["text"])

    def test_telegram_notification_failure_does_not_fail_completed_oauth(self):
        self.store.secret("telegram_token", "test-token")
        service=AgentService(self.store, telegram_transport=lambda *_args, **_kwargs: (_ for _ in ()).throw(ProviderError("offline")), drive_web_oauth=self.flow)
        _offer, state=self.begin()
        result=service.complete_drive_web_oauth({"state": state, "code": "code"}, 42,
                                                lambda _request: {"access_token": "token", "scope": DRIVE_FILE})
        self.assertEqual(result["state"], "connected")

    def test_drive_request_waits_for_picker_then_resumes_exact_job(self):
        calls=[]
        def transport(url, body, headers=None, timeout=60):
            calls.append(body); return {"ok": True, "result": {"message_id": 1}}
        self.store.secret("telegram_token", "test-token")
        self.store.put("telegram", {"enabled": True, "generation": "g", "user_id": 42, "cursor": 0})
        service=AgentService(self.store, telegram_transport=transport, drive_web_oauth=self.flow)
        service.ingest_update({"update_id": 1, "message": {"from": {"id": 42}, "chat": {"id": 42, "type": "private"}, "text": "구글 드라이브 연결해 보자"}}, "g")
        job=self.store.jobs()[0]
        self.assertEqual(job["status"], "awaiting_drive")
        state=parse_qs(urlparse(next(body for body in calls if "reply_markup" in body)["reply_markup"]["inline_keyboard"][0][0]["url"]).query)["state"][0]
        service.complete_drive_web_oauth({"state": state, "code": "code"}, 42, lambda _request: {"access_token": "token", "scope": DRIVE_FILE})
        service.select_drive_files(42, [{"id": "picked"}])
        self.assertEqual(self.store.job(job["id"])["status"], "queued")

    def test_only_picker_selected_files_can_be_read_and_full_drive_search_is_blocked(self):
        self.connect()
        with self.assertRaises(DriveScopeError): self.flow.search("plan")
        with self.assertRaises(DriveScopeError): self.flow.assert_selected(42, "unselected")
        selected = self.flow.select_files(42, [{"id": "picked", "name": "meeting plan"}])
        self.assertEqual(selected["files"], [{"id": "picked", "name": "meeting plan", "mime_type": ""}])
        self.assertTrue(self.flow.assert_selected(42, "picked"))
        calls = []
        content = self.flow.read_selected(42, "picked", lambda url, body, headers: calls.append((url, body, headers)) or "local file body")
        self.assertEqual(content, "local file body")
        self.assertIn("/picked?alt=media", calls[0][0])
        self.assertNotIn("local file body", str(self.flow.status()))

    def test_picker_grant_is_owner_bound_short_lived_and_single_use(self):
        self.connect()
        grant=self.flow.create_picker_grant(42)
        self.assertTrue(self.flow.picker_grant_active(grant))
        owner, result=self.flow.select_files_for_grant(grant,[{"id":"picked","name":"plan"}])
        self.assertEqual(owner,42)
        self.assertEqual(result["state"],"files-selected")
        self.assertFalse(self.flow.picker_grant_active(grant))
        with self.assertRaises(DriveWebOAuthError):
            self.flow.select_files_for_grant(grant,[{"id":"other"}])

    def test_picker_grant_is_single_use_across_handoff_instances(self):
        self.connect(); grant=self.flow.create_picker_grant(42)
        other=DriveWebOAuthHandoff(self.encrypted_store, "web-client", "https://connect.example.test/oauth/callback", "https://connect.example.test", now=lambda: self.clock[0])
        start=threading.Barrier(2); outcomes=[]
        def consume(flow, name):
            start.wait()
            try: flow.select_files_for_grant(grant,[{"id":name}]); outcomes.append('ok')
            except DriveWebOAuthError: outcomes.append('rejected')
        first=threading.Thread(target=consume,args=(self.flow,'first'));second=threading.Thread(target=consume,args=(other,'second'))
        first.start();second.start();first.join();second.join()
        self.assertEqual(sorted(outcomes),['ok','rejected'])

    def test_google_native_file_is_exported_and_selection_keeps_connection_active(self):
        self.connect()
        self.flow.select_files(42, [{"id": "doc", "mimeType": "application/vnd.google-apps.document"}])
        calls=[]
        self.flow.read_selected(42, "doc", lambda url, body, headers: calls.append(url) or "body")
        self.assertIn("/doc/export?mimeType=text%2Fplain", calls[0])
        self.assertEqual(self.flow.status()["state"], "connected")

    def test_expired_access_token_requires_reauthentication(self):
        self.connect(); self.clock[0] += 61
        with self.assertRaisesRegex(DriveWebOAuthError, "expired"):
            self.flow.select_files(42, [{"id": "picked"}])
        self.assertEqual(self.flow.status()["state"], "reauth-required")

    def test_reauthentication_clears_selected_files_and_token(self):
        self.connect(); self.flow.select_files(42,[{"id":"picked"}])
        self.flow.mark_reauthentication_required()
        with self.assertRaises(DriveWebOAuthError):
            self.flow.read_selected(42,"picked",lambda *_: "must not run")

    def test_callback_without_the_requested_scope_is_rejected_and_stores_no_token(self):
        """A grant that omits drive.file must fail closed, leaving no usable credential."""
        _offer, state = self.begin()
        with self.assertRaises(DriveScopeError):
            self.flow.complete(
                {"state": state, "code": "short-code"}, 42,
                lambda _: {"access_token": "access-secret", "scope": "https://www.googleapis.com/auth/userinfo.email", "expires_in": 60},
            )
        self.assertEqual(self.flow.status()["state"], "scope-rejected")
        self.assertEqual(self.encrypted_store.secret("drive_web_oauth_tokens"), "")
        self.assertNotIn("access-secret", str(self.store.secret("encrypted:drive_web_oauth_tokens")))
        # The pending state is consumed, so the same callback cannot be replayed.
        with self.assertRaises(DriveWebOAuthError):
            self.flow.complete({"state": state, "code": "short-code"}, 42, lambda _: {"access_token": "a", "scope": DRIVE_FILE, "expires_in": 60})

    def test_callback_granting_more_than_drive_file_is_rejected_and_stores_no_token(self):
        """An over-granted response must fail closed, not silently store wider authority.

        Google may return additional scopes (for example when the owner's
        account already granted them and ``include_granted_scopes`` is not
        disabled).  A subset test would accept that token and this connector
        would then hold authority the owner never approved for it.
        """
        _offer, state = self.begin()
        over_granted = DRIVE_FILE + " https://www.googleapis.com/auth/gmail.readonly"
        with self.assertRaises(DriveScopeError):
            self.flow.complete(
                {"state": state, "code": "short-code"}, 42,
                lambda _: {"access_token": "access-secret", "scope": over_granted, "expires_in": 60},
            )
        self.assertEqual(self.flow.status()["state"], "scope-rejected")
        self.assertEqual(self.encrypted_store.secret("drive_web_oauth_tokens"), "")
        self.assertNotIn("access-secret", str(self.store.secret("encrypted:drive_web_oauth_tokens")))

    def test_callback_granting_exactly_drive_file_is_accepted(self):
        """The tightened check must not reject the only scope this connector requests."""
        _offer, state = self.begin()
        self.flow.complete(
            {"state": state, "code": "short-code"}, 42,
            lambda _: {"access_token": "access-secret", "scope": DRIVE_FILE, "expires_in": 60},
        )
        self.assertEqual(self.flow.status()["state"], "connected")

    def test_corrupted_encrypted_secret_fails_closed_without_disclosing_plaintext(self):
        """Unreadable ciphertext must raise the redacted error, never a partial credential."""
        self.connect()
        self.store.secret("encrypted:drive_web_oauth_tokens", "not-a-valid-fernet-token")
        with self.assertRaises(DriveWebOAuthError) as caught:
            self.encrypted_store.secret("drive_web_oauth_tokens")
        self.assertNotIn("access-secret", str(caught.exception))
        with self.assertRaises(DriveWebOAuthError):
            self.flow.read_selected(42, "picked", lambda *_: "must not run")
        # A wrong local key is equally unreadable: the key is not recoverable from storage.
        rekeyed = EncryptedDriveSecretStore(self.store, Fernet.generate_key())
        self.store.secret("encrypted:drive_web_oauth_tokens", "gAAAAA" + "B" * 40)
        with self.assertRaises(DriveWebOAuthError):
            rekeyed.secret("drive_web_oauth_tokens")


if __name__ == "__main__":
    unittest.main()

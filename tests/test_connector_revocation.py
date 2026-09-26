"""CONNECTOR-REVOKE-01 #588: owner disconnect and Google-side token revocation.

Every Google call here goes to an injected fake transport; no live Google
request is made. The fake records the exact RFC 7009 request so the tests can
assert what would have left the machine.
"""
import json
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet

from personal_agent import connector_revocation as revocation
from personal_agent.calendar import CALENDAR_CONNECTOR_ID, CALENDAR_READ_SCOPE, CALENDAR_WRITE_CONNECTOR_ID, CALENDAR_WRITE_SCOPE
from personal_agent.calendar_oauth import CalendarOAuth, EncryptedCalendarSecretStore
from personal_agent.connector_contract import ConnectorState
from personal_agent.conversation_handoff import ConversationHandoffError
from personal_agent.drive_web_oauth import DRIVE_FILE, DriveWebOAuthError, DriveWebOAuthHandoff, EncryptedDriveSecretStore
from personal_agent.gmail import GMAIL_CONNECTOR_ID, GmailError

from test_conversation_connector_handoff import GMAIL_SCOPES, OWNER, HandoffTestCase

SESSION = 'owner-session-token'


class FakeGoogle:
    """Stands in for oauth2.googleapis.com/revoke; records every request."""

    def __init__(self, *answers):
        self.answers = list(answers) or [(200, b'')]
        self.requests = []

    def __call__(self, url, body, headers):
        self.requests.append({'url': url, 'body': parse_qs(body.decode()), 'headers': headers})
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


INVALID_TOKEN = (400, json.dumps({'error': 'invalid_token'}).encode())


class RevocationTestCase(HandoffTestCase):
    def setUp(self):
        super().setUp()
        self.google = FakeGoogle()
        self.service.google_revoke_transport = lambda *a: self.google(*a)
        self.service.google_revocation_clock = lambda: self.clock[0]
        self.calendar_store = EncryptedCalendarSecretStore(self.store, Fernet.generate_key())
        self.calendar = CalendarOAuth(self.calendar_store, 'calendar-client',
                                      'https://connect.example.test/calendar/callback',
                                      registry=self.registry, now=lambda: self.clock[0])
        self.service.calendar_oauth = self.calendar
        self.drive = DriveWebOAuthHandoff(EncryptedDriveSecretStore(self.store, Fernet.generate_key()),
                                          'drive-client', 'https://connect.example.test/oauth/callback',
                                          'https://connect.example.test', now=lambda: self.clock[0])
        self.service.drive_web_oauth = self.drive

    def connect_calendar(self, write=False, access='cal-access', refresh='cal-refresh'):
        offer = self.calendar.begin_oauth(OWNER, write=write)
        state = parse_qs(urlsplit(offer['authorization_url']).query)['state'][0]
        return self.calendar.complete_oauth(OWNER, {'state': state, 'code': 'c'}, lambda request: {
            'access_token': access, 'refresh_token': refresh, 'expires_in': 3600,
            'scope': CALENDAR_WRITE_SCOPE if write else CALENDAR_READ_SCOPE})

    def connect_drive(self):
        offer = self.drive.begin(42)
        state = parse_qs(urlsplit(offer['button']['url']).query)['state'][0]
        self.drive.complete({'state': state, 'code': 'c'}, 42, lambda request: {
            'access_token': 'drive-access', 'refresh_token': 'drive-refresh', 'scope': DRIVE_FILE,
            'expires_in': 3600})
        self.drive.select_files(42, [{'id': 'f1', 'name': 'a.txt', 'mime_type': 'text/plain'}])

    def disconnect(self, connector_id=GMAIL_CONNECTOR_ID, session=SESSION):
        preview = self.service.google_disconnect_preview({'connector_id': connector_id}, session)
        return self.service.google_disconnect(
            {'connector_id': connector_id, 'confirmation': preview['confirmation']}, session)

    def gmail_state(self):
        return self.registry.status(OWNER, GMAIL_CONNECTOR_ID).state

    def plain_state(self):
        """Everything AgentOS stores outside the encrypted secret namespaces."""
        with self.store.db() as db:
            rows = [tuple(row) for row in db.execute('SELECT * FROM config')]
        return json.dumps(rows, default=str)


class ProviderRequestTests(RevocationTestCase):
    def test_request_is_rfc7009_to_google_with_the_refresh_token_preferred(self):
        outcome = revocation.revoke_google_token({'access_token': 'a', 'refresh_token': 'r'}, self.google)
        self.assertEqual(outcome, revocation.REVOKED)
        request = self.google.requests[0]
        self.assertEqual(request['url'], 'https://oauth2.googleapis.com/revoke')
        self.assertEqual(request['body'], {'token': ['r'], 'token_type_hint': ['refresh_token']})
        self.assertEqual(request['headers']['Content-Type'], 'application/x-www-form-urlencoded')

    def test_outcomes_are_classified_only_from_what_was_observed(self):
        cases = [((200, b''), revocation.REVOKED), (INVALID_TOKEN, revocation.ALREADY_INVALID),
                 ((400, b'{"error":"invalid_request"}'), revocation.FAILED),
                 ((503, b''), revocation.FAILED), (OSError('offline'), revocation.UNCONFIRMED)]
        for answer, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(revocation.revoke_google_token({'access_token': 'a'}, FakeGoogle(answer)), expected)
        self.assertEqual(revocation.revoke_google_token(None, self.google), revocation.NOT_ATTEMPTED)
        self.assertEqual(self.google.requests, [])

    def test_production_transport_refuses_every_other_destination(self):
        transport = revocation.google_revoke_transport(opener=lambda *a, **k: self.fail('sent'))
        for url in ('https://evil.test/revoke', 'http://oauth2.googleapis.com/revoke',
                    'https://user@oauth2.googleapis.com/revoke'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                transport(url, b'token=x', {})


class GmailDisconnectTests(RevocationTestCase):
    def test_useful_before_then_denied_after_with_google_revocation_observed(self):
        self.connect_gmail()
        self.assertTrue(self.gmail.search(OWNER, 'budget'))
        receipt = self.disconnect()
        self.assertEqual(receipt['provider_revocation'], 'revoked')
        self.assertEqual(receipt['local_access'], 'stopped')
        self.assertEqual(receipt['local_credentials'], 'deleted')
        self.assertEqual(receipt['retained_data'], 'preserved')
        self.assertFalse(receipt['retry_available'])
        self.assertIn('Google에서도 권한 취소를 확인', receipt['message'])
        self.assertEqual(self.google.requests[0]['body']['token'], ['fixture-refresh'])
        self.assertIs(self.gmail_state(), ConnectorState.DISCONNECTED)
        with self.assertRaises(GmailError) as caught:
            self.gmail.search(OWNER, 'budget')
        self.assertEqual(caught.exception.reason, 'connection_required')
        self.assertFalse(self.gmail.credential_current(OWNER))

    def test_an_in_flight_request_is_refused_by_the_revision_check(self):
        self.connect_gmail()
        _headers, revision, access = self.gmail._authorization_context(OWNER)
        self.disconnect()
        with self.assertRaises(GmailError) as caught:
            self.gmail._assert_current_request(OWNER, revision, access)
        self.assertEqual(caught.exception.reason, 'superseded_connection')

    def test_a_stale_authorization_callback_cannot_reconnect(self):
        self.gmail.begin_oauth(OWNER)
        pending = self.encrypted.secret('gmail_oauth_pending:' + __import__('hashlib').sha256(OWNER.encode()).hexdigest())
        self.disconnect()
        with self.assertRaises(GmailError):
            self.gmail.complete_oauth(OWNER, {'state': pending['state'], 'code': 'c'},
                                      lambda request: {'access_token': 'x', 'expires_in': 60,
                                                       'scope': GMAIL_SCOPES[0]})
        self.assertIs(self.gmail_state(), ConnectorState.DISCONNECTED)

    def test_no_token_reaches_plain_state_receipts_or_audit(self):
        self.connect_gmail()
        self.google.answers = [OSError('fixture-refresh leaked in an error')]
        receipt = self.disconnect()
        for text in (json.dumps(receipt, ensure_ascii=False), self.plain_state(),
                     json.dumps(self.service.google_revocations())):
            self.assertNotIn('fixture-refresh', text)
            self.assertNotIn('fixture-access', text)

    def test_blocked_stays_blocked(self):
        self.registry.transition(OWNER, GMAIL_CONNECTOR_ID, ConnectorState.BLOCKED)
        receipt = self.disconnect()
        self.assertEqual(receipt['provider_revocation'], 'not_attempted')
        self.assertIs(self.gmail_state(), ConnectorState.BLOCKED)


class UnreachableGoogleTests(RevocationTestCase):
    def test_local_removal_happens_and_retry_later_confirms(self):
        self.connect_gmail()
        self.google.answers = [OSError('network down')]
        receipt = self.disconnect()
        self.assertEqual(receipt['provider_revocation'], 'unconfirmed')
        self.assertEqual(receipt['provider_request'], 'unknown')
        self.assertTrue(receipt['retry_available'])
        self.assertIn('확인되지 않았습니다', receipt['message'])
        self.assertNotIn('Google에서도 권한 취소를 확인', receipt['message'])
        self.assertIs(self.gmail_state(), ConnectorState.DISCONNECTED)
        with self.assertRaises(GmailError):
            self.gmail.search(OWNER, 'budget')
        pending = self.service.google_revocations()['pending_provider_revocations']
        self.assertEqual([row['connector_id'] for row in pending], [GMAIL_CONNECTOR_ID])
        self.google.answers = [(200, b'')]
        retried = self.service.retry_google_revocation({'connector_id': GMAIL_CONNECTOR_ID})
        self.assertEqual(retried['provider_revocation'], 'revoked')
        self.assertEqual(self.google.requests[-1]['body']['token'], ['fixture-refresh'])
        self.assertEqual(self.service.google_revocations()['pending_provider_revocations'], [])
        with self.assertRaisesRegex(ValueError, '다시 취소를 요청할 항목이 없습니다'):
            self.service.retry_google_revocation({'connector_id': GMAIL_CONNECTOR_ID})

    def test_provider_rejection_is_failed_not_revoked(self):
        self.connect_gmail()
        self.google.answers = [(503, b'')]
        receipt = self.disconnect()
        self.assertEqual(receipt['provider_revocation'], 'failed')
        self.assertEqual(receipt['provider_request'], 'observed')
        self.assertTrue(receipt['retry_available'])

    def test_already_invalid_token_is_confirmed_and_not_retried(self):
        self.connect_gmail()
        self.google.answers = [INVALID_TOKEN]
        receipt = self.disconnect()
        self.assertEqual(receipt['provider_revocation'], 'already_invalid')
        self.assertFalse(receipt['retry_available'])

    def test_retry_is_refused_after_a_reconnect(self):
        self.connect_gmail()
        self.google.answers = [OSError('down')]
        self.disconnect()
        self.connect_gmail()
        sent = len(self.google.requests)
        with self.assertRaisesRegex(ValueError, '새 연결까지 끊길 수'):
            self.service.retry_google_revocation({'connector_id': GMAIL_CONNECTOR_ID})
        self.assertEqual(len(self.google.requests), sent)
        self.assertIs(self.gmail_state(), ConnectorState.CONNECTED)


class ConfirmationTests(RevocationTestCase):
    def preview(self, session=SESSION):
        return self.service.google_disconnect_preview({'connector_id': GMAIL_CONNECTOR_ID}, session)

    def confirm(self, token, session=SESSION):
        return self.service.google_disconnect({'connector_id': GMAIL_CONNECTOR_ID, 'confirmation': token}, session)

    def test_preview_names_every_effect_and_changes_nothing(self):
        self.connect_gmail()
        preview = self.preview()
        self.assertEqual(preview['effects']['provider_destination'], 'oauth2.googleapis.com')
        self.assertEqual(preview['effects']['retained_data'], 'preserve')
        self.assertEqual(preview['effects']['remote_data_deletion'], 'none')
        self.assertIs(self.gmail_state(), ConnectorState.CONNECTED)
        self.assertEqual(self.google.requests, [])

    def test_replay_foreign_session_expired_and_changed_are_refused(self):
        self.connect_gmail()
        token = self.preview()['confirmation']
        with self.assertRaisesRegex(ValueError, '다른 로그인 세션'):
            self.confirm(token, session='someone-else')
        self.confirm(token)
        with self.assertRaisesRegex(ValueError, '이미 사용한 확인'):
            self.confirm(token)
        self.connect_gmail()
        expired = self.preview()['confirmation']
        self.clock[0] += revocation.CONFIRMATION_TTL_SECONDS + 1
        with self.assertRaisesRegex(ValueError, '확인 시간이 지났습니다'):
            self.confirm(expired)
        changed = self.preview()['confirmation']
        self.gmail.mark_reauthentication_required(OWNER)
        with self.assertRaisesRegex(ValueError, '연결 상태가 바뀌었습니다'):
            self.confirm(changed)
        with self.assertRaisesRegex(ValueError, '올바르지 않습니다'):
            self.confirm('forged')
        with self.assertRaisesRegex(ValueError, '찾지 못했습니다'):
            self.service.google_disconnect_preview({'connector_id': 'google-unknown'}, SESSION)


class CalendarIndependenceTests(RevocationTestCase):
    def test_read_and_write_grants_disconnect_independently(self):
        self.connect_calendar(write=False, access='read-access', refresh='read-refresh')
        self.connect_calendar(write=True, access='write-access', refresh='write-refresh')
        receipt = self.disconnect(CALENDAR_CONNECTOR_ID)
        self.assertEqual(receipt['provider_revocation'], 'revoked')
        self.assertEqual(self.google.requests[0]['body']['token'], ['read-refresh'])
        self.assertIs(self.registry.status(OWNER, CALENDAR_CONNECTOR_ID).state, ConnectorState.DISCONNECTED)
        self.assertIs(self.registry.status(OWNER, CALENDAR_WRITE_CONNECTOR_ID).state, ConnectorState.CONNECTED)
        self.assertFalse(self.calendar.credential_current(OWNER))
        self.assertTrue(self.calendar.credential_current(OWNER, write=True))


class ParkedWorkAndArtifactTests(RevocationTestCase):
    def test_parked_work_is_ended_and_cannot_resume_after_reconnect(self):
        job_id = self.park()
        self.disconnect()
        job = self.store.job(job_id)
        self.assertEqual(job['status'], 'failed')
        self.assertIn('연결을 해제해서', job['error'])
        self.assertIsNone(self.handoff.record(GMAIL_CONNECTOR_ID))
        self.connect_gmail()
        with self.assertRaises(ConversationHandoffError) as caught:
            self.service.resume_connector_work(GMAIL_CONNECTOR_ID, OWNER, GMAIL_SCOPES)
        self.assertEqual(caught.exception.reason, 'no_pending_work')
        self.assertEqual(self.drain(), 0)
        self.assertEqual(self.searches(), 0)

    def test_finished_results_are_preserved(self):
        self.connect_gmail()
        job_id = self.enqueue('메일에서 예산 관련 내용 찾아줘')
        self.drain()
        before = self.store.job(job_id)
        self.assertEqual(before['status'], 'succeeded')
        self.disconnect()
        after = self.store.job(job_id)
        self.assertEqual((after['status'], after['response']), (before['status'], before['response']))


class DriveDisconnectTests(RevocationTestCase):
    def test_drive_credential_and_file_grant_are_removed_and_waiting_work_ends(self):
        self.connect_drive()
        self.assertTrue(self.drive.assert_selected(42, 'f1'))
        job_id = self.enqueue('드라이브 파일 요약해줘')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='awaiting_drive' WHERE id=?", (job_id,))
        self.drive._record('drive-job-pending', pending_job_id=job_id)
        receipt = self.disconnect('google-drive-read')
        self.assertEqual(receipt['provider_revocation'], 'revoked')
        self.assertEqual(self.google.requests[0]['body']['token'], ['drive-refresh'])
        self.assertEqual(receipt['state'], 'disconnected')
        with self.assertRaises(DriveWebOAuthError):
            self.drive.read_selected(42, 'f1', lambda *a: self.fail('Drive was called'))
        self.assertEqual(self.store.job(job_id)['status'], 'failed')
        self.assertIsNone(self.drive.consume_pending_job(42))


if __name__ == '__main__':
    import unittest
    unittest.main()

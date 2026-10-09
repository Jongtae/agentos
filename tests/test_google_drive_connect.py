"""DRIVE-CONNECT-01 (#1172): one-button Google Drive connection and full-Drive read.

Every provider and HTTP interaction is injected; nothing here reaches Google
or the macOS Keychain.
"""

import json
import pathlib
import tempfile
import unittest
from personal_agent.calendar import CALENDAR_SPEC
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

from personal_agent.agent_runtime import Capabilities
from personal_agent.calendar_oauth import (
    DRIVE_GRANT,
    DRIVE_SECRET_NAMESPACE,
    CalendarOAuth,
    CalendarOAuthError,
    CalendarReauthenticationRequired,
    EncryptedCalendarSecretStore,
    drive_transport,
)
from personal_agent.connector_contract import ConnectorRegistry, ConnectorState
from personal_agent.google_drive_read import (
    DRIVE_API,
    DRIVE_CONNECTOR_ID,
    DRIVE_READONLY_SCOPE,
    DriveHTTPError,
    DriveReadError,
    GoogleDriveReader,
)
from personal_agent.quickstart import configured_service, google_publisher_client
from personal_agent.quickstart_service import DRIVE_CALLBACK_PATH, DRIVE_CONNECT_PATH
from personal_agent.quickstart_store import QuickStore

OWNER = 'local-owner'
FILE_ID = 'abcdefghij0123456789'


class Recorder:
    """A transport that answers by URL prefix and records every URL it saw."""

    def __init__(self, answers):
        self.answers = answers
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        for prefix, body in self.answers:
            if url.startswith(prefix):
                return body
        raise AssertionError(f'unexpected Drive URL {url}')


class DriveReaderTest(unittest.TestCase):
    def test_search_escapes_the_query_literal_and_returns_rows(self):
        body = json.dumps({'files': [{'id': FILE_ID, 'name': '계약서', 'mimeType': 'application/pdf',
                                      'modifiedTime': '2026-10-01T00:00:00Z', 'webViewLink': 'https://x'}]}).encode()
        transport = Recorder([(DRIVE_API + '/files?', body)])
        result = GoogleDriveReader(transport).search("it's\\here")
        query = parse_qs(urlparse(transport.urls[0]).query)
        self.assertIn("name contains 'it\\'s\\\\here'", query['q'][0])
        self.assertIn('trashed = false', query['q'][0])
        self.assertNotIn('orderBy', query)
        self.assertEqual(result['files'][0]['file_id'], FILE_ID)
        self.assertEqual(result['files'][0]['name'], '계약서')

    def test_empty_search_lists_recent_files(self):
        transport = Recorder([(DRIVE_API + '/files?', b'{"files": []}')])
        GoogleDriveReader(transport).search('')
        query = parse_qs(urlparse(transport.urls[0]).query)
        self.assertEqual(query['orderBy'], ['modifiedTime desc'])
        self.assertNotIn('fullText', query['q'][0])

    def test_google_doc_is_exported_as_text(self):
        meta = json.dumps({'id': FILE_ID, 'name': '회의록', 'mimeType': 'application/vnd.google-apps.document'}).encode()
        transport = Recorder([(f'{DRIVE_API}/files/{FILE_ID}/export?', '﻿첫 줄\n둘째 줄'.encode()),
                              (f'{DRIVE_API}/files/{FILE_ID}?', meta)])
        result = GoogleDriveReader(transport).read(FILE_ID)
        self.assertIn('mimeType=text%2Fplain', transport.urls[1])
        self.assertIn('둘째 줄', result['content'])
        self.assertEqual(result['name'], '회의록')
        self.assertEqual(result['sources'], ['Google Drive: 회의록'])

    def test_ordinary_file_is_downloaded_and_extracted_locally(self):
        meta = json.dumps({'id': FILE_ID, 'name': 'notes.md', 'mimeType': 'text/markdown', 'size': '12'}).encode()
        transport = Recorder([(f'{DRIVE_API}/files/{FILE_ID}?alt=media', b'# Title\nbody'),
                              (f'{DRIVE_API}/files/{FILE_ID}?', meta)])
        result = GoogleDriveReader(transport).read(FILE_ID)
        self.assertEqual(result['kind'], 'markdown')
        self.assertIn('body', result['content'])

    def test_unsupported_type_and_oversize_are_refused_before_download(self):
        for meta in ({'id': FILE_ID, 'name': 'a.zip', 'mimeType': 'application/zip'},
                     {'id': FILE_ID, 'name': 'a.pdf', 'mimeType': 'application/pdf', 'size': str(20_000_000)}):
            transport = Recorder([(f'{DRIVE_API}/files/{FILE_ID}?', json.dumps(meta).encode())])
            with self.assertRaises(DriveReadError):
                GoogleDriveReader(transport).read(FILE_ID)
            self.assertEqual(len(transport.urls), 1)

    def test_malformed_file_id_never_reaches_the_transport(self):
        transport = Recorder([])
        for bad in ('short', '../files', FILE_ID + '/export', 7):
            with self.assertRaises(DriveReadError):
                GoogleDriveReader(transport).read(bad)
        self.assertEqual(transport.urls, [])


class DriveOAuthCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.raw = QuickStore(temp.name)
        self.key_calls = []
        key = Fernet.generate_key()

        def provider():
            self.key_calls.append(1)
            return key

        self.store = EncryptedCalendarSecretStore(self.raw, provider, namespace=DRIVE_SECRET_NAMESPACE)
        self.clock = [1_000.0]
        self.registry = ConnectorRegistry(self.store, (), clock=lambda: self.clock[0])
        self.oauth = CalendarOAuth(self.store, 'publisher.apps.googleusercontent.com',
                                   'http://127.0.0.1:8787' + DRIVE_CALLBACK_PATH, registry=self.registry,
                                   now=lambda: self.clock[0], allow_localhost=True, grants=(DRIVE_GRANT,))
        self.exchanges = []

    def exchange(self, payload):
        self.exchanges.append(payload)
        if payload['grant_type'] == 'refresh_token':
            return {'access_token': 'renewed', 'expires_in': 3600, 'scope': DRIVE_READONLY_SCOPE}
        return {'access_token': 'first', 'expires_in': 3600, 'refresh_token': 'refresh-1', 'scope': DRIVE_READONLY_SCOPE}

    def connect(self):
        offer = self.oauth.begin_oauth(OWNER)
        state = parse_qs(urlparse(offer['authorization_url']).query)['state'][0]
        return self.oauth.complete_oauth(OWNER, {'state': state, 'code': 'code-1'}, self.exchange)


class DriveOAuthTest(DriveOAuthCase):
    def test_wiring_and_empty_reads_do_not_touch_the_key_store(self):
        self.assertEqual(self.oauth.status(OWNER)['state'], 'disconnected')
        self.assertFalse(self.oauth.credential_current(OWNER))
        self.assertEqual(self.key_calls, [])
        self.oauth.begin_oauth(OWNER)
        self.assertEqual(len(self.key_calls), 1)

    def test_authorization_url_asks_for_exactly_drive_readonly_offline(self):
        url = self.oauth.begin_oauth(OWNER)['authorization_url']
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query['scope'], [DRIVE_READONLY_SCOPE])
        self.assertEqual(query['access_type'], ['offline'])
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertEqual(query['redirect_uri'], ['http://127.0.0.1:8787' + DRIVE_CALLBACK_PATH])
        self.assertTrue(query['state'][0].startswith('drive.'))

    def test_completion_commits_the_exact_scope(self):
        status = self.connect()
        self.assertEqual(status['state'], 'connected')
        self.assertEqual(status['connector_id'], DRIVE_CONNECTOR_ID)
        self.assertEqual(tuple(status['granted_scopes']), (DRIVE_READONLY_SCOPE,))

    def test_a_scope_superset_is_refused(self):
        offer = self.oauth.begin_oauth(OWNER)
        state = parse_qs(urlparse(offer['authorization_url']).query)['state'][0]
        wider = lambda payload: {'access_token': 'x', 'expires_in': 3600,
                                 'scope': DRIVE_READONLY_SCOPE + ' https://www.googleapis.com/auth/drive'}
        with self.assertRaises(CalendarOAuthError):
            self.oauth.complete_oauth(OWNER, {'state': state, 'code': 'c'}, wider)
        self.assertEqual(self.oauth.status(OWNER)['state'], 'disconnected')

    def test_calendar_grants_are_not_served_by_the_drive_instance(self):
        for kwargs in ({'write': True}, {'grant': 'read'}):
            with self.assertRaises(CalendarOAuthError):
                self.oauth.begin_oauth(OWNER, **kwargs)
        # A Calendar-labelled state cannot address a pending slot here.
        with self.assertRaises(CalendarOAuthError):
            self.oauth.complete_oauth(OWNER, {'state': 'read.' + 'a' * 43 + '.' + '0' * 64, 'code': 'c'}, self.exchange)

    def test_a_replayed_callback_is_refused(self):
        offer = self.oauth.begin_oauth(OWNER)
        state = parse_qs(urlparse(offer['authorization_url']).query)['state'][0]
        self.oauth.complete_oauth(OWNER, {'state': state, 'code': 'c'}, self.exchange)
        with self.assertRaises(CalendarOAuthError):
            self.oauth.complete_oauth(OWNER, {'state': state, 'code': 'c'}, self.exchange)


class DriveTransportTest(DriveOAuthCase):
    def setUp(self):
        super().setUp()
        self.requests = []
        self.reply = b'{"files": []}'

        def opener(url, headers):
            self.requests.append((url, headers.get('Authorization')))
            if isinstance(self.reply, Exception):
                raise self.reply
            return self.reply

        self.transport = drive_transport(self.oauth, OWNER, self.exchange, opener=opener)

    def test_not_connected_is_refused_without_a_request(self):
        with self.assertRaises(CalendarOAuthError) as caught:
            self.transport(DRIVE_API + '/files?q=x')
        self.assertEqual(caught.exception.reason, 'connection_required')
        self.assertEqual(self.requests, [])

    def test_off_allowlist_destinations_are_refused_before_any_token(self):
        self.connect()
        for url in ('https://evil.test/drive/v3/files', 'http://www.googleapis.com/drive/v3/files',
                    'https://user@www.googleapis.com/drive/v3/files', 'https://www.googleapis.com/gmail/v1/x'):
            with self.assertRaises(CalendarOAuthError):
                self.transport(url)
        self.assertEqual(self.requests, [])

    def test_an_expired_token_is_renewed_without_the_owner(self):
        self.connect()
        self.clock[0] += 7200
        self.transport(DRIVE_API + '/files?q=x')
        self.assertEqual(self.exchanges[-1]['grant_type'], 'refresh_token')
        self.assertEqual(self.exchanges[-1]['refresh_token'], 'refresh-1')
        self.assertEqual(self.requests, [(DRIVE_API + '/files?q=x', 'Bearer renewed')])
        self.assertEqual(self.oauth.status(OWNER)['state'], 'connected')

    def test_a_failed_renewal_requires_reauthentication(self):
        self.connect()
        self.clock[0] += 7200

        def broken(payload):
            raise OSError('network down')

        transport = drive_transport(self.oauth, OWNER, broken, opener=lambda url, headers: b'{}')
        with self.assertRaises(CalendarReauthenticationRequired):
            transport(DRIVE_API + '/files?q=x')
        self.assertEqual(self.registry.status(OWNER, DRIVE_CONNECTOR_ID).state, ConnectorState.REAUTH_REQUIRED)

    def test_401_moves_the_connection_to_reauth_required(self):
        self.connect()
        self.reply = DriveHTTPError(401)
        with self.assertRaises(DriveHTTPError):
            self.transport(DRIVE_API + '/files?q=x')
        self.assertEqual(self.registry.status(OWNER, DRIVE_CONNECTOR_ID).state, ConnectorState.REAUTH_REQUIRED)

    def test_the_transport_requires_the_drive_grant(self):
        calendar_oauth = CalendarOAuth(self.store, 'c.apps.googleusercontent.com', 'https://x.test/cb',
                                       registry=ConnectorRegistry(self.store, ()))
        with self.assertRaises(ValueError):
            drive_transport(calendar_oauth, OWNER, self.exchange)


class PublisherClientTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = pathlib.Path(temp.name)

    def write(self, value):
        path = self.root / 'client.json'
        path.write_text(json.dumps(value))
        return str(path)

    def test_desktop_client_download_is_accepted(self):
        path = self.write({'installed': {'client_id': 'n.apps.googleusercontent.com', 'client_secret': 'GOCSPX-x'}})
        self.assertEqual(google_publisher_client({'AGENTOS_GOOGLE_CLIENT_FILE': path}),
                         ('n.apps.googleusercontent.com', 'GOCSPX-x'))

    def test_absent_configuration_offers_nothing(self):
        self.assertIsNone(google_publisher_client({}))

    def test_web_client_and_malformed_files_are_refused(self):
        for value in ({'web': {'client_id': 'n.apps.googleusercontent.com', 'client_secret': 's'}},
                      {'installed': {'client_id': 'not-google', 'client_secret': 's'}},
                      {'installed': {'client_id': 'n.apps.googleusercontent.com'}}):
            with self.assertRaises(ValueError):
                google_publisher_client({'AGENTOS_GOOGLE_CLIENT_FILE': self.write(value)})

    def test_configured_service_offers_the_drive_connection_only_with_a_client(self):
        store = QuickStore(str(self.root / 'data'))
        self.assertIsNone(configured_service(store, {}).drive_oauth)
        path = self.write({'installed': {'client_id': 'n.apps.googleusercontent.com', 'client_secret': 's'}})
        service = configured_service(store, {'AGENTOS_GOOGLE_CLIENT_FILE': path, 'AGENTOS_GOOGLE_LOCAL_PORT': '9911',
                                             'AGENTOS_GOOGLE_OAUTH_KEY': Fernet.generate_key().decode()})
        self.assertIsNotNone(service.drive_oauth)
        self.assertEqual(service.connector_connect_url(DRIVE_CONNECTOR_ID),
                         f'http://127.0.0.1:9911{DRIVE_CONNECT_PATH}')
        self.assertIn(DRIVE_CONNECTOR_ID, {row['id'] for row in service.settings_connection_rows()})
        self.assertIn(DRIVE_CONNECTOR_ID, service.PARKABLE_READ_CONNECTORS)


class CapabilityTest(unittest.TestCase):
    def capabilities(self, drive):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = QuickStore(temp.name)
        return Capabilities(store, None, {}, None, 'job-1', {}, drive=drive)

    def test_a_read_without_a_drive_offer_is_setup_required(self):
        result = self.capabilities(None).execute('drive_read', {'file_id': FILE_ID})
        self.assertTrue(result['needs_setup'])
        self.assertEqual(result['requires'], DRIVE_CONNECTOR_ID)

    def test_an_unconnected_drive_read_is_setup_required(self):
        class Unconnected:
            def search(self, query):
                raise CalendarOAuthError('connection_required')

        result = self.capabilities(Unconnected()).execute('drive_search', {'query': 'x'})
        self.assertTrue(result['needs_setup'])
        self.assertEqual(result['requires'], DRIVE_CONNECTOR_ID)

    def test_a_read_is_labelled_as_owner_drive_provenance(self):
        class Reader:
            def read(self, file_id):
                return {'file_id': file_id, 'name': 'a', 'content': 'text', 'sources': ['Google Drive: a']}

        caps = self.capabilities(Reader())
        caps.execute('drive_read', {'file_id': FILE_ID})
        self.assertIn('owner-drive', caps.private_provenance)


if __name__ == '__main__':
    unittest.main()


class OwnClientConnectorsTest(unittest.TestCase):
    """One own client offers Gmail and Calendar too (#1172)."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = pathlib.Path(temp.name)
        path = self.root / 'client.json'
        path.write_text(json.dumps({'installed': {'client_id': 'n.apps.googleusercontent.com', 'client_secret': 's'}}))
        self.env = {'AGENTOS_GOOGLE_CLIENT_FILE': str(path), 'AGENTOS_GOOGLE_LOCAL_PORT': '9911',
                    'AGENTOS_GOOGLE_OAUTH_KEY': Fernet.generate_key().decode()}

    def test_gmail_and_calendar_are_offered_on_the_loopback_listener(self):
        from personal_agent.calendar import CALENDAR_CONNECTOR_ID, CALENDAR_WRITE_CONNECTOR_ID
        from personal_agent.gmail import GMAIL_CONNECTOR_ID
        service = configured_service(QuickStore(str(self.root / 'data')), self.env)
        self.assertEqual(service.connector_connect_url(GMAIL_CONNECTOR_ID), 'http://127.0.0.1:9911/google-gmail')
        self.assertEqual(service.connector_connect_url(CALENDAR_CONNECTOR_ID),
                         'http://127.0.0.1:9911/google-calendar?grant=read')
        self.assertEqual(service.connector_connect_url(CALENDAR_WRITE_CONNECTOR_ID),
                         'http://127.0.0.1:9911/google-calendar?grant=write')
        self.assertEqual(service.gmail.redirect_uri, 'http://127.0.0.1:9911/oauth/gmail/callback')
        self.assertTrue(callable(service.gmail.token_exchange))
        self.assertTrue(callable(service.calendar_token_exchange))
        rows = {row['id'] for row in service.settings_connection_rows()}
        self.assertTrue({GMAIL_CONNECTOR_ID, CALENDAR_CONNECTOR_ID, DRIVE_CONNECTOR_ID} <= rows)

    def test_owner_connector_configuration_takes_precedence(self):
        from personal_agent.quickstart import local_gmail_secret_values
        secret = self.root / 'gmail.json'
        secret.write_text(json.dumps({'client_id': 'owner-gmail', 'client_secret': 'x',
                                      'encryption_key': Fernet.generate_key().decode()}))
        secret.chmod(0o600)
        env = {**self.env, 'AGENTOS_GMAIL_LOCAL_ONLY': '1', 'AGENTOS_GMAIL_SECRET_FILE': str(secret)}
        service = configured_service(QuickStore(str(self.root / 'data')), env)
        self.assertEqual(service.gmail.client_id, 'owner-gmail')
        self.assertTrue(callable(service.gmail.token_exchange))

    def test_the_shared_keychain_key_is_created_once(self):
        from unittest import mock
        from personal_agent import quickstart

        class FakeKeychain:
            created = 0

            def __init__(self, *_args):
                self.value = None

            def get(self):
                return self.value

            def create(self):
                FakeKeychain.created += 1
                self.value = Fernet.generate_key()
                return self.value

        with mock.patch.object(quickstart, 'KeychainKey', FakeKeychain):
            provider = quickstart.google_oauth_key(QuickStore(str(self.root / 'data')))
            self.assertEqual(provider(), provider())
        self.assertEqual(FakeKeychain.created, 1)


class GmailRenewalTest(unittest.TestCase):
    def setUp(self):
        from personal_agent.connector_contract import ConnectorRegistry as Registry
        from personal_agent.gmail import GMAIL_CONNECTOR, EncryptedGmailSecretStore, GmailConnector
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = EncryptedGmailSecretStore(QuickStore(temp.name), Fernet.generate_key())
        self.clock = [1_000.0]
        self.calls = []
        self.exchanges = []

        def transport(method, endpoint, params, headers):
            self.calls.append(headers['Authorization'])
            return {'messages': []}

        self.registry = Registry(store, (GMAIL_CONNECTOR,), clock=lambda: self.clock[0])
        self.gmail = GmailConnector(store, 'n.apps.googleusercontent.com', 'http://127.0.0.1:8787/oauth/gmail/callback',
                                    registry=self.registry, transport=transport, now=lambda: self.clock[0],
                                    allow_localhost=True, token_exchange=self.exchange)
        offer = self.gmail.begin_oauth(OWNER)
        state = parse_qs(urlparse(offer['authorization_url']).query)['state'][0]
        self.gmail.complete_oauth(OWNER, {'state': state, 'code': 'c'}, self.exchange)

    def exchange(self, payload):
        from personal_agent.gmail import GMAIL_READONLY_SCOPE
        self.exchanges.append(payload)
        if payload['grant_type'] == 'refresh_token':
            return {'access_token': 'renewed', 'expires_in': 3600}
        return {'access_token': 'first', 'expires_in': 3600, 'refresh_token': 'refresh-1', 'scope': GMAIL_READONLY_SCOPE}

    def test_an_expired_token_is_renewed_before_the_request(self):
        self.clock[0] += 7200
        self.assertTrue(self.gmail.credential_renewable(OWNER))
        self.gmail.search(OWNER, 'from:me')
        self.assertEqual(self.calls, ['Bearer renewed'])
        self.assertEqual(self.exchanges[-1]['refresh_token'], 'refresh-1')
        self.assertEqual(self.gmail.status(OWNER)['state'], 'connected')

    def test_a_widened_renewal_is_refused_and_requires_reauthentication(self):
        from personal_agent.gmail import GmailReauthenticationRequired
        self.gmail.token_exchange = lambda payload: {'access_token': 'x', 'expires_in': 3600,
                                                     'scope': 'https://www.googleapis.com/auth/gmail.modify'}
        self.clock[0] += 7200
        with self.assertRaises(GmailReauthenticationRequired):
            self.gmail.search(OWNER, 'from:me')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.gmail.status(OWNER)['state'], 'reauth_required')


class CalendarRenewalTest(unittest.TestCase):
    def test_the_calendar_transport_renews_an_expired_grant(self):
        from personal_agent.calendar_oauth import calendar_transport
        from personal_agent.google_calendar import CALENDAR_API, CALENDAR_READ_SCOPE
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = EncryptedCalendarSecretStore(QuickStore(temp.name), Fernet.generate_key())
        clock = [1_000.0]
        registry = ConnectorRegistry(store, (), clock=lambda: clock[0])
        oauth = CalendarOAuth(store, 'n.apps.googleusercontent.com', 'http://127.0.0.1:8787/oauth/calendar/callback',
                              registry=registry, now=lambda: clock[0], allow_localhost=True)

        def exchange(payload):
            if payload['grant_type'] == 'refresh_token':
                return {'access_token': 'renewed', 'expires_in': 3600, 'scope': " ".join(CALENDAR_SPEC.required_scopes)}
            return {'access_token': 'first', 'expires_in': 3600, 'refresh_token': 'r', 'scope': " ".join(CALENDAR_SPEC.required_scopes)}

        offer = oauth.begin_oauth(OWNER)
        state = parse_qs(urlparse(offer['authorization_url']).query)['state'][0]
        oauth.complete_oauth(OWNER, {'state': state, 'code': 'c'}, exchange)
        clock[0] += 7200
        seen = []
        transport = calendar_transport(store, registry, OWNER, now=lambda: clock[0], oauth=oauth, exchange=exchange,
                                       opener=lambda method, url, body, headers: seen.append(headers['Authorization']) or {})
        transport('GET', CALENDAR_API + '/calendars/primary/events', None, {})
        self.assertEqual(seen, ['Bearer renewed'])

    def test_renewal_needs_both_the_oauth_instance_and_its_exchange(self):
        from personal_agent.calendar_oauth import calendar_transport
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = EncryptedCalendarSecretStore(QuickStore(temp.name), Fernet.generate_key())
        with self.assertRaises(ValueError):
            calendar_transport(store, ConnectorRegistry(store, ()), OWNER, exchange=lambda payload: {})


class OwnClientFromSettingsTest(unittest.TestCase):
    """The owner adds their own Desktop client in Settings; no client ships with AgentOS (#1172)."""

    CLIENT = json.dumps({'installed': {'client_id': '123-abcdefgh.apps.googleusercontent.com',
                                       'client_secret': 'GOCSPX-owner-secret'}})

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = pathlib.Path(temp.name)
        self.store = QuickStore(str(self.root / 'data'))
        self.env = {'AGENTOS_GOOGLE_LOCAL_PORT': '9911', 'AGENTOS_GOOGLE_OAUTH_KEY': Fernet.generate_key().decode()}

    def test_nothing_is_offered_until_the_owner_adds_a_client(self):
        service = configured_service(self.store, self.env)
        self.assertIsNone(service.drive_oauth)
        self.assertIsNone(service.gmail)
        status = service.google_client_status()
        self.assertEqual((status['configured'], status['available']), (False, True))

    def test_a_saved_client_offers_all_three_services_at_once_without_a_restart(self):
        from personal_agent.gmail import GMAIL_CONNECTOR_ID
        service = configured_service(self.store, self.env)
        status = service.save_google_client({'client_json': self.CLIENT})
        self.assertEqual((status['configured'], status['source'], status['client_hint']), (True, 'settings', '…cdefgh'))
        self.assertNotIn('GOCSPX', json.dumps(status))
        self.assertNotIn('GOCSPX', json.dumps(service.settings()))
        self.assertEqual(service.connector_connect_url(DRIVE_CONNECTOR_ID), f'http://127.0.0.1:9911{DRIVE_CONNECT_PATH}')
        self.assertEqual(service.connector_connect_url(GMAIL_CONNECTOR_ID), 'http://127.0.0.1:9911/google-gmail')
        self.assertIsNotNone(service.connector_handoff)
        rows = {row['connector_id']: row for row in service.google_connection_rows()}
        self.assertEqual(rows[DRIVE_CONNECTOR_ID]['source'], 'own-client')
        self.assertEqual(rows[GMAIL_CONNECTOR_ID]['source'], 'own-client')

    def test_a_saved_client_is_installed_again_after_a_restart(self):
        configured_service(self.store, self.env).save_google_client({'client_json': self.CLIENT})
        restarted = configured_service(self.store, self.env)
        self.assertEqual(restarted.google_client_status()['source'], 'settings')
        self.assertIsNotNone(restarted.drive_oauth)

    def test_replacing_a_client_in_use_waits_for_a_restart(self):
        service = configured_service(self.store, self.env)
        service.save_google_client({'client_json': self.CLIENT})
        first = service.drive_oauth
        other = json.dumps({'installed': {'client_id': '999-zzzzzz.apps.googleusercontent.com', 'client_secret': 's2'}})
        service.save_google_client({'client_json': other})
        self.assertIs(service.drive_oauth, first)
        self.assertEqual(configured_service(self.store, self.env).google_client_id, '999-zzzzzz.apps.googleusercontent.com')

    def test_web_clients_and_junk_are_refused_and_nothing_is_saved(self):
        service = configured_service(self.store, self.env)
        for value in ('', 'not json', json.dumps({'web': {'client_id': 'a.apps.googleusercontent.com', 'client_secret': 's'}})):
            with self.assertRaises(ValueError):
                service.save_google_client({'client_json': value})
        self.assertEqual(self.store.secret('google_oauth_client'), '')
        self.assertIsNone(service.drive_oauth)

    def test_an_environment_client_cannot_be_overwritten_from_settings(self):
        path = self.root / 'client.json'
        path.write_text(self.CLIENT)
        service = configured_service(self.store, {**self.env, 'AGENTOS_GOOGLE_CLIENT_FILE': str(path)})
        self.assertEqual(service.google_client_status()['source'], 'environment')
        with self.assertRaises(ValueError):
            service.save_google_client({'client_json': self.CLIENT})

    def test_an_unreadable_stored_client_offers_nothing_instead_of_failing_startup(self):
        self.store.secret('google_oauth_client', {'installed': {'client_id': 'broken'}})
        service = configured_service(self.store, self.env)
        self.assertIsNone(service.drive_oauth)


class CalendarRenewalLockOrderTest(unittest.TestCase):
    """#1172 review P1: renewal inside a Calendar query must not deadlock against disconnect."""

    def test_query_renewal_and_disconnect_both_finish(self):
        import threading
        import time
        from personal_agent.calendar import CalendarConnector
        from personal_agent.calendar_oauth import calendar_transport
        from personal_agent.google_calendar import CALENDAR_READ_SCOPE, GoogleCalendar
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        raw = QuickStore(temp.name)
        store = EncryptedCalendarSecretStore(raw, Fernet.generate_key())
        clock = [1_000.0]
        registry = ConnectorRegistry(store, (), clock=lambda: clock[0])
        oauth = CalendarOAuth(store, 'n.apps.googleusercontent.com', 'http://127.0.0.1:8787/oauth/calendar/callback',
                              registry=registry, now=lambda: clock[0], allow_localhost=True)

        def exchange(payload):
            if payload['grant_type'] == 'refresh_token':
                return {'access_token': 'renewed', 'expires_in': 3600, 'scope': " ".join(CALENDAR_SPEC.required_scopes)}
            return {'access_token': 'first', 'expires_in': 3600, 'refresh_token': 'r', 'scope': " ".join(CALENDAR_SPEC.required_scopes)}

        offer = oauth.begin_oauth(OWNER)
        oauth.complete_oauth(OWNER, {'state': parse_qs(urlparse(offer['authorization_url']).query)['state'][0],
                                     'code': 'c'}, exchange)
        clock[0] += 7200
        transport = calendar_transport(store, registry, OWNER, now=lambda: clock[0], oauth=oauth, exchange=exchange,
                                       opener=lambda method, url, body, headers: {'items': []})
        calendar = CalendarConnector(raw, GoogleCalendar(transport), registry=registry)
        inside = threading.Event()
        original = oauth.credential_current

        def slow(*args, **kwargs):
            result = original(*args, **kwargs)
            if threading.current_thread().name == 'query':
                inside.set()
                time.sleep(0.3)
            return result

        oauth.credential_current = slow

        def query():
            try:
                calendar.query(OWNER, '2026-10-09T00:00:00+00:00', '2026-10-10T00:00:00+00:00', 'UTC')
            except Exception:
                pass

        def disconnect():
            inside.wait(5)
            oauth.disconnect(OWNER, lambda credential: None)

        threads = [threading.Thread(target=query, name='query', daemon=True),
                   threading.Thread(target=disconnect, name='disconnect', daemon=True)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        self.assertEqual([thread.is_alive() for thread in threads], [False, False])
        self.assertEqual(oauth.status(OWNER)['state'], 'disconnected')


class CodexReviewFollowupsTest(unittest.TestCase):
    def test_a_google_sheet_is_exported_as_xlsx_so_every_sheet_is_read(self):
        meta = json.dumps({'id': FILE_ID, 'name': '예산', 'mimeType': 'application/vnd.google-apps.spreadsheet'}).encode()
        from io import BytesIO
        from openpyxl import Workbook
        book = Workbook()
        book.active.title = 'first'
        book.active.append(['a', 1])
        second = book.create_sheet('second')
        second.append(['only-in-second', 2])
        buffer = BytesIO()
        book.save(buffer)
        transport = Recorder([(f'{DRIVE_API}/files/{FILE_ID}/export?', buffer.getvalue()),
                              (f'{DRIVE_API}/files/{FILE_ID}?', meta)])
        result = GoogleDriveReader(transport).read(FILE_ID)
        self.assertIn('spreadsheetml.sheet', transport.urls[1])
        self.assertIn('only-in-second', result['content'])

    def test_truncation_is_reported_from_the_rendered_content(self):
        meta = json.dumps({'id': FILE_ID, 'name': 'lines', 'mimeType': 'application/vnd.google-apps.document'}).encode()
        body = '\n'.join('x' for _ in range(6_000)).encode()
        transport = Recorder([(f'{DRIVE_API}/files/{FILE_ID}/export?', body), (f'{DRIVE_API}/files/{FILE_ID}?', meta)])
        result = GoogleDriveReader(transport).read(FILE_ID)
        self.assertEqual(len(result['content']), 24_000)
        self.assertTrue(result['truncated'])

    def test_replacing_a_connected_client_is_refused_until_disconnected(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = QuickStore(str(pathlib.Path(temp.name) / 'data'))
        env = {'AGENTOS_GOOGLE_LOCAL_PORT': '9911', 'AGENTOS_GOOGLE_OAUTH_KEY': Fernet.generate_key().decode()}
        service = configured_service(store, env)
        service.save_google_client({'client_json': OwnClientFromSettingsTest.CLIENT})
        owner = service.connector_callback_owner(DRIVE_CONNECTOR_ID)
        service.drive_oauth.registry.transition(owner, DRIVE_CONNECTOR_ID, ConnectorState.CONNECTED,
                                                granted_scopes=(DRIVE_READONLY_SCOPE,))
        other = json.dumps({'installed': {'client_id': '999-zzzzzz.apps.googleusercontent.com', 'client_secret': 's2'}})
        with self.assertRaises(ValueError):
            service.save_google_client({'client_json': other})
        self.assertIn('123-abcdefgh', json.dumps(store.secret('google_oauth_client')))
        # The same client again is not a replacement.
        service.save_google_client({'client_json': OwnClientFromSettingsTest.CLIENT})


class OwnClientGuideTest(unittest.TestCase):
    """#1204: a conversation can tell the owner how to add their own Google client."""

    def test_settings_read_points_to_the_setup_and_never_reports_a_connection(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = QuickStore(str(pathlib.Path(temp.name) / 'data'))
        env = {'AGENTOS_GOOGLE_LOCAL_PORT': '9911', 'AGENTOS_GOOGLE_OAUTH_KEY': Fernet.generate_key().decode()}
        service = configured_service(store, env)
        response = service.conversation_settings_request({'operation': 'read', 'category': 'connections'})['response']
        self.assertIn('자체 Google client · 설정 안 됨', response)
        self.assertIn('설정 > 외부 연결 > 자체 Google client', response)
        self.assertNotIn('console.cloud.google.com', response)
        service.save_google_client({'client_json': OwnClientFromSettingsTest.CLIENT})
        response = service.conversation_settings_request({'operation': 'read', 'category': 'connections'})['response']
        self.assertIn('자체 Google client · 설정됨', response)
        self.assertNotIn('자체 Google client · 연결됨', response)

    def test_an_install_that_cannot_take_a_client_offers_no_guide(self):
        from personal_agent.quickstart_service import AgentService
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        rows = AgentService(QuickStore(temp.name)).settings_connection_rows()
        self.assertNotIn('google-own-client', {row['id'] for row in rows})


class ConnectionNoticeTest(unittest.TestCase):
    """#1207: a completed connection is told to the conversation; the chat can hand out the start link."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = QuickStore(str(pathlib.Path(temp.name) / 'data'))
        env = {'AGENTOS_GOOGLE_LOCAL_PORT': '9911', 'AGENTOS_GOOGLE_OAUTH_KEY': Fernet.generate_key().decode()}
        self.service = configured_service(self.store, env)
        self.service.save_google_client({'client_json': OwnClientFromSettingsTest.CLIENT})
        self.sent = []

        class Telegram:
            def send_message(inner, chat_id, text):
                self.sent.append((chat_id, text))

        self.service.telegram = Telegram()

    def complete_drive(self):
        offer = self.service.begin_drive_connection()
        state = parse_qs(urlparse(offer['authorization_url']).query)['state'][0]
        self.service.drive_read_token_exchange = lambda payload: {
            'access_token': 'a', 'expires_in': 3600, 'refresh_token': 'r', 'scope': DRIVE_READONLY_SCOPE}
        return self.service.complete_drive_connection({'state': state, 'code': 'c'})

    def assistant_rows(self):
        with self.store.db() as db:
            return [dict(row) for row in db.execute("SELECT content, channel FROM messages WHERE role='assistant'")]

    def test_a_completed_connection_is_told_to_the_web_conversation(self):
        self.complete_drive()
        rows = self.assistant_rows()
        self.assertEqual(len(rows), 1)
        self.assertIn('Google Drive 연결이 완료되었습니다', rows[0]['content'])
        self.assertEqual(rows[0]['channel'], 'web')
        self.assertEqual(self.sent, [])

    def test_a_paired_owner_also_gets_it_on_telegram(self):
        self.store.put('telegram', {'enabled': True, 'user_id': 4242, 'generation': 'g1'})
        self.complete_drive()
        self.assertEqual(self.assistant_rows()[0]['channel'], 'telegram:g1')
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0][0], 4242)
        self.assertIn('Google Drive', self.sent[0][1])

    def test_a_failed_connection_tells_nothing(self):
        offer = self.service.begin_drive_connection()
        state = parse_qs(urlparse(offer['authorization_url']).query)['state'][0]
        self.service.drive_read_token_exchange = lambda payload: {'access_token': 'a', 'expires_in': 3600,
                                                                  'scope': 'https://www.googleapis.com/auth/drive'}
        with self.assertRaises(ValueError):
            self.service.complete_drive_connection({'state': state, 'code': 'c'})
        self.assertEqual(self.assistant_rows(), [])

    def test_the_settings_read_hands_out_the_start_link(self):
        response = self.service.conversation_settings_request({'operation': 'read', 'category': 'connections'})['response']
        self.assertIn(f'http://127.0.0.1:9911{DRIVE_CONNECT_PATH}', response)
        self.assertIn('http://127.0.0.1:9911/google-gmail', response)


class ParkedConnectionNoticeTest(ConnectionNoticeTest):
    def test_a_parked_request_is_told_it_continues(self):
        class Handoff:
            def record(self, connector_id):
                return {'owner': 'x'}
        self.service.connector_handoff = Handoff()
        self.service.resume_connector_work = lambda connector_id, owner, granted: None
        self.complete_drive()
        rows = self.assistant_rows()
        self.assertEqual(len(rows), 1)
        self.assertIn('기다리던 요청을 이어서 처리합니다', rows[0]['content'])


class SettingsWebNoticeTest(unittest.TestCase):
    """#1211: a Settings-web change is told to the conversation; the chat links to the input surface."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = QuickStore(str(pathlib.Path(temp.name) / 'data'))
        env = {'AGENTOS_GOOGLE_LOCAL_PORT': '9911', 'AGENTOS_GOOGLE_OAUTH_KEY': Fernet.generate_key().decode()}
        self.service = configured_service(self.store, env)
        self.service.local_server_port = 9911

    def assistant_rows(self):
        with self.store.db() as db:
            return [row['content'] for row in db.execute("SELECT content FROM messages WHERE role='assistant'")]

    def test_a_change_is_described_from_the_redacted_read_model(self):
        before = self.service.settings_snapshot()
        self.service.save_google_client({'client_json': OwnClientFromSettingsTest.CLIENT})
        text = self.service.notify_settings_web_change('자체 Google client', before)
        self.assertIn('설정 화면에서 자체 Google client을(를) 바꿨습니다.', text)
        self.assertIn('자체 Google client: 설정 안 됨 → 설정됨', text)
        self.assertIn('Google Drive: 연결 안 됨', text)
        self.assertNotIn('GOCSPX', text)
        self.assertEqual(self.assistant_rows(), [text])

    def test_a_change_the_read_model_does_not_show_states_the_action_only(self):
        before = self.service.settings_snapshot()
        text = self.service.notify_settings_web_change('웹 검색 키', before, verb='저장했습니다')
        self.assertEqual(text, '설정 화면에서 웹 검색 키을(를) 저장했습니다.')

    def test_nothing_changed_means_no_notice(self):
        before = self.service.settings_snapshot()
        self.assertIsNone(self.service.notify_settings_web_change('현재 맥락', before))
        self.assertEqual(self.assistant_rows(), [])

    def test_the_conversation_links_to_the_own_client_input(self):
        response = self.service.conversation_settings_request({'operation': 'read', 'category': 'connections'})['response']
        self.assertIn('http://127.0.0.1:9911/#settings/external', response)


class SettingsWebRouteNoticeTest(unittest.TestCase):
    """The HTTP boundary sends the notice only for a declared route that succeeded (#1211)."""

    def test_only_successful_declared_routes_notify(self):
        from personal_agent import quickstart
        self.assertIn('/api/google/client', quickstart.SETTINGS_WEB_CHANGES)
        for excluded in ('/api/chat', '/api/settings/request', '/api/claim', '/api/model/test'):
            self.assertNotIn(excluded, quickstart.SETTINGS_WEB_CHANGES)


class SettingsWebNoticeOverHttpTest(unittest.TestCase):
    def test_a_successful_settings_post_notifies_and_a_refused_one_does_not(self):
        import threading
        from http.cookiejar import CookieJar
        from http.server import ThreadingHTTPServer
        from urllib.error import HTTPError
        from urllib.request import HTTPCookieProcessor, Request, build_opener
        from personal_agent.quickstart import make_handler
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = QuickStore(str(pathlib.Path(temp.name) / 'data'))
        service = configured_service(store, {'AGENTOS_GOOGLE_LOCAL_PORT': '9911',
                                             'AGENTOS_GOOGLE_OAUTH_KEY': Fernet.generate_key().decode()})
        store.claim(store.bootstrap.read_text(), 'long-password-test')
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        client = build_opener(HTTPCookieProcessor(CookieJar()))
        url = 'http://127.0.0.1:' + str(server.server_port)

        def request(path, body):
            req = Request(url + path, data=json.dumps(body).encode(),
                          headers={'Content-Type': 'application/json', 'Origin': url})
            with client.open(req, timeout=5) as response:
                return json.load(response)

        def notices():
            with store.db() as db:
                return [row['content'] for row in db.execute("SELECT content FROM messages WHERE role='assistant'")]

        try:
            request('/api/login', {'password': 'long-password-test'})
            with self.assertRaises(HTTPError):
                request('/api/google/client', {'client_json': 'not json'})
            self.assertEqual(notices(), [])
            request('/api/google/client', {'client_json': OwnClientFromSettingsTest.CLIENT})
            # Recorded before the success is exposed: no wait needed.
            self.assertEqual(len(notices()), 1)
            self.assertIn('설정 화면에서 자체 Google client을(를) 저장했습니다.', notices()[0])
            # Re-submitting the current value of a setting the read model shows says nothing.
            current = service.current_state.status()
            request('/api/current-context', {'enabled': bool(current.get('enabled'))})
            self.assertEqual(len(notices()), 1)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

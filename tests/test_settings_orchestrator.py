"""Settings read model and the retired CapabilityRegistry control plane (#506).

The legacy registry-backed pause/disconnect/resume changed only a config row
while the real connector credential and execution path stayed usable.  These
tests are the opposing regression: the action no longer exists on any
channel, a draft left over from the old control plane can never apply, and the
owner-visible connection state is derived from the authoritative boundaries.
"""
import copy
import json
import tempfile
import threading
import unittest
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor

from personal_agent.capabilities import CapabilityRegistry
from personal_agent.connector_contract import ConnectorRegistry
from personal_agent.gmail import GMAIL_CONNECTOR
from personal_agent.portable_state import export_owner_state, restore_owner_state
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.settings_orchestrator import RETIRED_CONTROL_MESSAGE, SettingsError, SettingsOrchestrator
from personal_agent.quickstart import make_handler


class FakeDrive:
    def __init__(self, state):
        self.state = state

    def status(self):
        return {"state": self.state, "audit": []}


def legacy_draft(owner='owner', channel='http'):
    change = {'target': 'google-drive-read', 'action': 'pause', 'before': 'enabled', 'after': 'paused',
              'effect': 'google-drive-read 상태를 paused로 변경', 'recovery': '검토된 연결 다시 시작 초안'}
    return {'id': 'legacy-draft', 'owner': owner, 'channel': channel, **change, 'digest': 'legacy-digest',
            'created_at': 900, 'expires_at': 1600, 'state': 'awaiting-confirmation'}


class SettingsOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.store = QuickStore(self.temp.name); self.clock = [1000]
        self.rows = [{'id': 'telegram', 'service': 'Telegram', 'state': 'connected'},
                     {'id': 'google-gmail-read', 'service': 'Google Gmail', 'state': 'reauth_required', 'connectable': True},
                     {'id': 'google-drive-read', 'service': 'Google Drive', 'state': 'disconnected', 'connectable': False,
                      'connect_hint': 'Telegram에서 Google Drive 파일을 요청하면 연결 링크를 보냅니다.'},
                     {'id': 'mystery', 'service': 'Mystery', 'state': 'strange'}]
        self.settings = SettingsOrchestrator(self.store, now=lambda: self.clock[0], connections=lambda: self.rows)
        # A historical enabled registry row must neither be read nor changed.
        CapabilityRegistry(self.store).transition('google-drive-read', 'enabled', ('read',))
        self.history = copy.deepcopy(self.store.config('capability_registry'))

    def tearDown(self): self.temp.cleanup()

    def test_read_reports_owner_states_from_the_supplied_authority_only(self):
        self.store.put('private-provider-token', {'token': 'never-expose', 'path': '/private/path'})
        read = self.settings.read('owner')
        self.assertEqual(read['state'], 'read')
        self.assertNotIn('never-expose', json.dumps(read)); self.assertNotIn('/private/path', json.dumps(read))
        self.assertNotIn('capabilities', read)
        labels = {row['id']: row['state_label'] for row in read['connections']}
        self.assertEqual(labels, {'telegram': '연결됨', 'google-gmail-read': '다시 인증 필요',
                                  'google-drive-read': '연결 안 됨', 'mystery': '확인 필요'})
        self.assertIn('Google Gmail · 다시 인증 필요', read['response'])
        self.assertNotIn('google-gmail-read', read['response'], 'chat summary uses owner names, not IDs')
        drive = next(row for row in read['connections'] if row['id'] == 'google-drive-read')
        self.assertIn('Telegram', drive['next_action'])
        self.assertEqual(self.store.config('capability_registry'), self.history)
        with self.assertRaises(SettingsError): self.settings.read('owner', 'runtime')

    def test_lifecycle_requests_are_refused_without_any_authority_change(self):
        for text in ('Drive pause', '드라이브 연결 해제해줘', 'pause the calendar connection', 'mcp resume'):
            with self.subTest(text=text):
                result = self.settings.handle_text('owner', 'http', text)
                self.assertEqual(result['state'], 'unsupported')
                self.assertEqual(result['response'], RETIRED_CONTROL_MESSAGE)
        self.assertEqual(self.store.config('settings_change_drafts', {}), {})
        self.assertEqual(self.store.config('capability_registry'), self.history)

    def test_a_legacy_draft_never_applies_and_fails_terminally(self):
        self.store.put('settings_change_drafts', {'legacy-draft': legacy_draft()})
        with self.assertRaises(SettingsError): self.settings.confirm('other', 'http', 'legacy-draft', 'legacy-digest')
        with self.assertRaisesRegex(SettingsError, '대화에서 제공하지 않습니다'):
            self.settings.confirm('owner', 'http', 'legacy-draft', 'legacy-digest')
        self.assertEqual(self.store.config('settings_change_drafts')['legacy-draft']['state'], 'failed')
        audit = self.store.config('settings_audit')
        self.assertEqual((audit[-1]['terminal'], audit[-1]['error_class']), ('failed', 'retired-control'))
        with self.assertRaises(SettingsError): self.settings.handle_text('owner', 'http', 'Confirm legacy-draft')
        self.assertEqual(self.store.config('capability_registry'), self.history)

    def test_a_legacy_draft_can_still_be_cancelled(self):
        self.store.put('settings_change_drafts', {'legacy-draft': legacy_draft()})
        self.assertFalse(self.settings.cancel('owner', 'http', 'legacy-draft')['idempotent'])
        self.assertTrue(self.settings.cancel('owner', 'http', 'legacy-draft')['idempotent'])

    def test_recovery_answers_from_connection_state(self):
        result = self.settings.handle_text('owner', 'http', 'Gmail 어떻게 복구해?')
        self.assertEqual((result['state'], result['target']), ('recovery', 'google-gmail-read'))
        self.assertIn('다시 연결', result['action'])
        self.assertEqual(self.settings.handle_text('owner', 'http', '어떻게 복구해?')['state'], 'read')
        with self.assertRaises(SettingsError): self.settings.recovery('owner', 'builtin-mcp-read')


class ServiceSettingsProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.store = QuickStore(self.temp.name)

    def tearDown(self): self.temp.cleanup()

    def test_settings_rows_come_from_connector_registry_drive_handoff_and_telegram(self):
        service = AgentService(self.store, connector_registry=ConnectorRegistry(self.store, (GMAIL_CONNECTOR,)),
                               drive_web_oauth=FakeDrive('reauth-required'))
        google = service.settings()['connectors']
        self.assertEqual([(row['connector_id'], row['state']) for row in google],
                         [('google-gmail-read', 'disconnected'), ('google-drive-read', 'reauth_required')])
        self.assertNotIn('conversation_settings', service.settings())
        drive = google[-1]
        self.assertEqual((drive['connect_path'], drive['detail_state']), ('', 'reauth-required'))
        rows = {row['id']: row['state'] for row in service.settings_connection_rows()}
        self.assertEqual(rows, {'telegram': 'disconnected', 'google-gmail-read': 'disconnected',
                                'google-drive-read': 'reauth_required'})
        self.store.put('telegram', {'enabled': True})
        self.assertEqual(service.settings_connection_rows()[0]['state'], 'pending')
        for raw, state in (('connected', 'connected'), ('expired', 'disconnected'), ('denied', 'disconnected')):
            service.drive_web_oauth = FakeDrive(raw)
            self.assertEqual(service.drive_connection_row()['state'], state)

    def test_install_without_connectors_reports_only_telegram(self):
        service = AgentService(self.store)
        self.assertEqual(service.settings()['connectors'], [])
        self.assertEqual([row['id'] for row in service.conversation_settings_request({'operation': 'read'})['connections']],
                         ['telegram'])

    def test_queued_telegram_settings_commands_refuse_the_retired_control(self):
        CapabilityRegistry(self.store).transition('google-drive-read', 'enabled', ('read',))
        history = copy.deepcopy(self.store.config('capability_registry'))
        service = AgentService(self.store)
        job = self.store.enqueue('/settings Drive pause', 'settings-telegram-draft', channel='telegram', chat_id=42)
        self.assertTrue(service.run_one())
        self.assertEqual(self.store.job(job)['response'], RETIRED_CONTROL_MESSAGE)
        self.assertEqual(self.store.config('settings_change_drafts', {}), {})
        self.assertEqual(self.store.config('capability_registry'), history)

    def test_http_routes_offer_no_capability_control_plane(self):
        self.store.claim(self.store.bootstrap.read_text(), 'long-password-test')
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(AgentService(self.store)))
        thread = threading.Thread(target=server.serve_forever); thread.start()
        client = build_opener(HTTPCookieProcessor(CookieJar())); base = 'http://127.0.0.1:' + str(server.server_port)
        def request(path, body=None):
            req = Request(base + path, data=None if body is None else json.dumps(body).encode(),
                          headers={'Content-Type': 'application/json'})
            with client.open(req, timeout=3) as response: return json.load(response)
        try:
            request('/api/login', {'password': 'long-password-test'})
            self.assertEqual(request('/api/settings/request', {'operation': 'draft', 'intent': 'Drive pause'})['state'], 'unsupported')
            self.assertEqual(request('/api/settings')['connections'][0]['id'], 'telegram')
            with self.assertRaises(HTTPError) as caught: request('/api/capabilities')
            self.assertEqual(caught.exception.code, 404)
        finally:
            server.shutdown(); thread.join(); server.server_close()

    def test_export_drops_pending_confirmation_and_keeps_only_redacted_audit(self):
        self.store.put('settings_change_drafts', {'legacy-draft': legacy_draft()})
        SettingsOrchestrator(self.store, now=lambda: 1000).cancel('owner', 'http', 'legacy-draft')
        archive = export_owner_state(self.temp.name, self.temp.name + '/owner.tar.gz')
        target = self.temp.name + '/restored'; restored = QuickStore(restore_owner_state(archive, target))
        self.assertIsNone(restored.config('settings_change_drafts'))
        self.assertNotIn('legacy-digest', json.dumps(restored.config('settings_audit', [])))
        self.assertNotIn('owner', json.dumps(restored.config('settings_audit', [])))


if __name__ == '__main__':
    unittest.main()

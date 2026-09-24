import json
import tempfile
import threading
import unittest
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
from urllib.request import Request, build_opener, HTTPCookieProcessor

from personal_agent.capabilities import CapabilityRegistry
from personal_agent.portable_state import export_owner_state, restore_owner_state
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.settings_orchestrator import SettingsError, SettingsOrchestrator
from personal_agent.quickstart import make_handler


class SettingsOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.store=QuickStore(self.temp.name); self.clock=[1000]
        self.settings=SettingsOrchestrator(self.store, now=lambda:self.clock[0])
        self.registry=CapabilityRegistry(self.store)
        self.registry.transition('google-drive-read','enabled',('read',))

    def tearDown(self): self.temp.cleanup()

    def test_read_is_redacted_and_draft_requires_exact_owner_channel_confirmation(self):
        self.store.put('private-provider-token',{'token':'never-expose','path':'/private/path'})
        read=self.settings.read('owner')
        self.assertEqual(read['state'],'read'); self.assertNotIn('never-expose',json.dumps(read)); self.assertNotIn('/private/path',json.dumps(read))
        draft=self.settings.draft('owner','http','Drive pause')
        preview=draft['preview']; self.assertEqual(preview['before'],'enabled'); self.assertNotIn('owner',json.dumps(preview))
        with self.assertRaises(SettingsError): self.settings.confirm('other','http',preview['id'],preview['digest'])
        with self.assertRaises(SettingsError): self.settings.confirm('owner','telegram',preview['id'],preview['digest'])
        applied=self.settings.confirm('owner','http',preview['id'],preview['digest'])
        self.assertEqual(applied['result']['state'],'paused')
        self.assertTrue(self.settings.confirm('owner','http',preview['id'],preview['digest'])['idempotent'])
        self.assertEqual(self.registry.list()[1]['state'],'paused')

    def test_ambiguous_expired_stale_cancel_and_resume_fail_closed(self):
        with self.assertRaises(SettingsError): self.settings.draft('owner','http','yes')
        draft=self.settings.draft('owner','http','Drive pause')['preview']
        self.clock[0]+=601
        with self.assertRaisesRegex(SettingsError,'만료'): self.settings.confirm('owner','http',draft['id'],draft['digest'])
        self.assertEqual(self.registry.list()[1]['state'],'enabled')
        second=self.settings.draft('owner','http','Drive pause')['preview']
        self.registry.transition('google-drive-read','paused')
        with self.assertRaisesRegex(SettingsError,'바뀌'): self.settings.confirm('owner','http',second['id'],second['digest'])
        third=self.settings.draft('owner','http','Drive resume')['preview']
        self.assertFalse(self.settings.cancel('owner','http',third['id'])['idempotent'])
        self.assertTrue(self.settings.cancel('owner','http',third['id'])['idempotent'])
        with self.assertRaises(SettingsError): self.settings.confirm('owner','http',third['id'],third['digest'])

    def test_retired_a2a_confirmation_fails_terminally_instead_of_500(self):
        change={'target':'compatibility-a2a-peer','action':'pause','before':'enabled','after':'paused',
                'effect':'compatibility-a2a-peer 상태를 paused로 변경','recovery':'현재 상태 확인'}
        row={'id':'legacy-a2a-draft','owner':'owner','channel':'http',**change,
             'digest':self.settings._digest(change),'created_at':900,'expires_at':1600,
             'state':'awaiting-confirmation'}
        self.store.put('settings_change_drafts',{row['id']:row})
        with self.assertRaisesRegex(SettingsError,'더 이상 제공되지'):
            self.settings.confirm('owner','http',row['id'],row['digest'])
        stored=self.store.config('settings_change_drafts')[row['id']]
        self.assertEqual(stored['state'],'failed')
        audit=self.store.config('settings_audit')
        self.assertEqual(audit[-1]['terminal'],'failed')
        self.assertEqual(audit[-1]['error_class'],'retired-target')

    def test_text_and_service_channels_share_semantics_but_not_drafts(self):
        service=AgentService(self.store)
        http=service.conversation_settings_request({'operation':'text','text':'Drive pause'},'same-owner','http')
        draft=http['preview']
        with self.assertRaises(SettingsError): service.conversation_settings_request({'operation':'confirm','draft_id':draft['id'],'digest':draft['digest']},'same-owner','telegram')
        applied=service.conversation_settings_request({'operation':'confirm','draft_id':draft['id'],'digest':draft['digest']},'same-owner','http')
        self.assertEqual(applied['state'],'applied')
        self.assertEqual(service.conversation_settings_request({'operation':'read'},'same-owner','telegram')['capabilities'][1]['state'],'paused')

    def test_queued_telegram_settings_commands_use_the_same_controller(self):
        service=AgentService(self.store)
        job=self.store.enqueue('/settings Drive pause','settings-telegram-draft',channel='telegram',chat_id=42)
        self.assertTrue(service.run_one())
        self.assertIn('Confirm ',self.store.job(job)['response'])
        draft=next(iter(self.store.config('settings_change_drafts').values()))
        confirm=self.store.enqueue('/settings Confirm '+draft['id'],'settings-telegram-confirm',channel='telegram',chat_id=42)
        self.assertTrue(service.run_one())
        self.assertIn('paused',self.store.job(confirm)['response'])

    def test_authenticated_http_settings_route_uses_preview_and_confirm_contract(self):
        self.store.claim(self.store.bootstrap.read_text(),'long-password-test')
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(AgentService(self.store)))
        thread=threading.Thread(target=server.serve_forever); thread.start()
        client=build_opener(HTTPCookieProcessor(CookieJar())); base='http://127.0.0.1:'+str(server.server_port)
        def request(path, body):
            req=Request(base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
            with client.open(req,timeout=3) as response:return json.load(response)
        try:
            request('/api/login',{'password':'long-password-test'})
            draft=request('/api/settings/request',{'operation':'draft','intent':'Drive pause'})['preview']
            result=request('/api/settings/request',{'operation':'confirm','draft_id':draft['id'],'digest':draft['digest']})
            self.assertEqual(result['result']['state'],'paused')
        finally:
            server.shutdown(); thread.join(); server.server_close()

    def test_export_drops_pending_confirmation_and_keeps_only_redacted_audit(self):
        preview=self.settings.draft('owner','http','Drive pause')['preview']
        archive=export_owner_state(self.temp.name,self.temp.name+'/owner.tar.gz')
        target=self.temp.name+'/restored'; restored=QuickStore(restore_owner_state(archive,target))
        self.assertIsNone(restored.config('settings_change_drafts'))
        self.assertNotIn(preview['digest'],json.dumps(restored.config('settings_audit',[])))
        self.assertNotIn('owner',json.dumps(restored.config('settings_audit',[])))

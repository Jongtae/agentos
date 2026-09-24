import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler
from urllib.error import HTTPError
from urllib.parse import urlsplit, parse_qs
from personal_agent.quickstart_store import QuickStore
from personal_agent.quickstart_service import AgentService, TELEGRAM_RESULT_PREVIEW_CHARS
from personal_agent.quickstart import make_handler, configured_service, local_drive_secret_values
from personal_agent.drive_web_oauth import DriveWebOAuthHandoff, EncryptedDriveSecretStore
from personal_agent.connector_contract import CONNECTOR_STATE_KEY, PENDING_WORK_KEY, ConnectorState
from personal_agent.conversation_handoff import CONVERSATION_RESUME_KEY
from personal_agent.gmail import GMAIL_CONNECTOR_ID, GMAIL_READONLY_SCOPE, GmailError
from cryptography.fernet import Fernet
from personal_agent.providers import ModelAdapter, ProviderError
from personal_agent.file_workspace import FileWorkspace


class QuickstartTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=QuickStore(self.temp.name)
        self.calls=[]
        def transport(url,body,headers=None,timeout=60):
            self.calls.append((url,body,headers))
            probing=any((tool.get('function',{}).get('name') or tool.get('name'))=='agentos_connection_probe' for tool in body.get('tools',[]))
            if url.endswith('/api/chat'):
                if probing:return {'message':{'content':'','tool_calls':[{'function':{'name':'agentos_connection_probe','arguments':{}}}]}}
                return {'message':{'content':'Ollama response'}}
            if url.endswith('/chat/completions'):
                if probing:return {'model':'verified/model:free','choices':[{'message':{'tool_calls':[{'id':'probe','function':{'name':'agentos_connection_probe','arguments':'{}'}}]}}]}
                return {'choices':[{'message':{'content':'Compatible response'}}]}
            if url.endswith('/v1/messages'):
                if probing:return {'content':[{'type':'tool_use','id':'probe','name':'agentos_connection_probe','input':{}}]}
                return {'content':[{'type':'text','text':'Anthropic response'}]}
            if url.endswith('/getMe'):return {'ok':True,'result':{'username':'test_bot'}}
            if url.endswith('/getWebhookInfo'):return {'ok':True,'result':{'url':''}}
            if url.endswith('/getUpdates'):return {'ok':True,'result':[]}
            if url.endswith('/sendMessage'):return {'ok':True,'result':{'message_id':len([c for c in self.calls if c[0].endswith('/sendMessage')])}}
            if url.endswith('/editMessageText'):return {'ok':True,'result':True}
            if url.endswith('/answerCallbackQuery'):return {'ok':True,'result':True}
            raise AssertionError(url)
        self.transport=transport
        self.service=AgentService(self.store,ModelAdapter(transport),transport)

    def tearDown(self):self.temp.cleanup()

    def model(self,provider='ollama',endpoint='http://127.0.0.1:11434',key=''):
        self.service.save_model({'provider':provider,'endpoint':endpoint,'model':'test-model','api_key':key})

    def make_due(self, job_id):
        with self.store.db() as db:
            db.execute("UPDATE jobs SET created=? WHERE id=?", (time.time()-4, job_id))

    def test_claim_session_restart_and_redaction(self):
        self.store.claim(self.store.bootstrap.read_text(),'a-long-test-password')
        self.assertFalse(self.store.bootstrap.exists())
        token=self.store.login('a-long-test-password')
        self.assertTrue(QuickStore(self.temp.name).session(token))
        self.assertIsNone(self.store.login('wrong'))
        self.model(key='private-api-key')
        self.assertNotIn('private-api-key',json.dumps(self.service.settings()))
        self.store.logout(token)
        self.assertFalse(self.store.session(token))

    def test_onboarding_http_api_requires_login_and_redacts_secrets(self):
        self.store.claim(self.store.bootstrap.read_text(),'long-password-test')
        self.model(key='private-api-key')
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.service))
        thread=threading.Thread(target=server.serve_forever);thread.start()
        client=build_opener(HTTPCookieProcessor(CookieJar()));url='http://127.0.0.1:'+str(server.server_port)
        def request(path,body=None):
            req=Request(url+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'} if body is not None else {})
            with client.open(req,timeout=3) as response:return json.load(response)
        try:
            with self.assertRaises(HTTPError) as error:request('/api/onboarding')
            self.assertEqual(error.exception.code,401)
            request('/api/login',{'password':'long-password-test'})
            guide=request('/api/onboarding')
            self.assertNotIn('private-api-key',json.dumps(guide))
            self.assertIn('recovery',guide)
        finally:
            server.shutdown();thread.join();server.server_close()

    def test_personal_assistant_http_surface_uses_policy_owned_fallback(self):
        self.store.claim(self.store.bootstrap.read_text(),'long-password-test')
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.service))
        thread=threading.Thread(target=server.serve_forever);thread.start()
        client=build_opener(HTTPCookieProcessor(CookieJar()));url='http://127.0.0.1:'+str(server.server_port)
        def request(path,body):
            req=Request(url+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
            with client.open(req,timeout=3) as response:return json.load(response)
        try:
            with self.assertRaises(HTTPError) as error:request('/api/assistant/request',{'message':'개인 공간을 보여줘'})
            self.assertEqual(error.exception.code,401)
            request('/api/login',{'password':'long-password-test'})
            result=request('/api/assistant/request',{'message':'알 수 없는 요청'})
            self.assertEqual(result['state'],'fallback')
            self.assertNotIn('알 수 없는 요청',json.dumps(self.store.config('personal_assistant_evidence')))
        finally:
            server.shutdown();thread.join();server.server_close()

    def test_authenticated_local_companion_knowledge_route_uses_owner_local_policy(self):
        self.store.claim(self.store.bootstrap.read_text(),'long-password-test')
        with self.store.db() as db:
            db.execute('INSERT INTO notes VALUES (?,?,?)',('knowledge-note','Aurora local plan',1))
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.service))
        thread=threading.Thread(target=server.serve_forever);thread.start()
        client=build_opener(HTTPCookieProcessor(CookieJar()));url='http://127.0.0.1:'+str(server.server_port)
        def request(path,body=None):
            req=Request(url+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'} if body is not None else {})
            with client.open(req,timeout=3) as response:return json.load(response)
        try:
            with self.assertRaises(HTTPError): request('/api/personal-knowledge',{'query':'aurora'})
            request('/api/login',{'password':'long-password-test'})
            result=request('/api/personal-knowledge',{'query':'aurora'})
            self.assertEqual(result['state'],'completed')
            self.assertTrue(result['results'][0]['reference'].startswith('pk_'))
            self.assertNotIn('owner',json.dumps(self.store.config('personal_knowledge_audit')))
        finally:
            server.shutdown();thread.join();server.server_close()

    def test_home_is_minimal_and_never_includes_connection_secrets(self):
        self.store.claim(self.store.bootstrap.read_text(),'long-password-test')
        self.model(key='private-api-key')
        self.assertTrue(self.service.test_model()['ok'])
        home=self.service.home()
        self.assertEqual(home['state'],'ready')
        self.assertTrue(home['model_connected'])
        self.assertNotIn('private-api-key',json.dumps(home))
        self.store.enqueue('hello','home-active')
        home=self.service.home()
        self.assertEqual(home['state'],'working')
        self.assertEqual(home['active_jobs'],1)

    def test_local_drive_configuration_is_explicit_and_never_exposes_secret(self):
        disabled=configured_service(self.store, {'AGENTOS_DRIVE_LOCAL_ONLY':'1','AGENTOS_DRIVE_CLIENT_ID':'client','AGENTOS_DRIVE_ENCRYPTION_KEY':Fernet.generate_key().decode()})
        self.assertIsNone(disabled.drive_web_oauth)
        configured=configured_service(self.store, {
            'AGENTOS_DRIVE_LOCAL_ONLY':'1', 'AGENTOS_DRIVE_CLIENT_ID':'client',
            'AGENTOS_DRIVE_ENCRYPTION_KEY':Fernet.generate_key().decode(), 'AGENTOS_DRIVE_LOCAL_PORT':'9123',
            'AGENTOS_DRIVE_CLIENT_SECRET':'never-return-this', 'AGENTOS_DRIVE_PICKER_API_KEY':'restricted-key',
        })
        self.assertEqual(configured.drive_web_oauth.redirect_uri,'http://localhost:9123/oauth/google/callback')
        self.assertTrue(configured.drive_web_oauth.begin(42)['button']['url'].startswith('https://agentos.localhost:9124/'))
        self.assertNotIn('never-return-this',json.dumps(configured.settings()))

    def test_local_drive_requires_a_complete_picker_configuration(self):
        env={'AGENTOS_DRIVE_LOCAL_ONLY':'1','AGENTOS_DRIVE_CLIENT_ID':'client',
             'AGENTOS_DRIVE_ENCRYPTION_KEY':Fernet.generate_key().decode(),
             'AGENTOS_DRIVE_CLIENT_SECRET':'secret'}
        self.assertIsNone(configured_service(self.store,env).drive_web_oauth)
        with tempfile.TemporaryDirectory() as external:
            path=Path(external)/'drive.json'
            path.write_text(json.dumps({'client_id':'client'}));path.chmod(0o600)
            with self.assertRaisesRegex(ValueError,'every required'):
                configured_service(self.store,{**env,'AGENTOS_DRIVE_SECRET_FILE':str(path)})

    def test_owner_only_drive_secret_file_configures_without_environment_secrets(self):
        with tempfile.TemporaryDirectory() as external:
            path=os.path.join(external,'drive-secrets.json')
            values={'client_id':'client','client_secret':'secret-not-exposed','picker_api_key':'restricted-key',
                    'encryption_key':Fernet.generate_key().decode()}
            with open(path,'w') as output: json.dump(values,output)
            os.chmod(path,0o600)
            configured=configured_service(self.store,{'AGENTOS_DRIVE_LOCAL_ONLY':'1','AGENTOS_DRIVE_SECRET_FILE':path})
            self.assertEqual(configured.drive_web_oauth.client_id,'client')
            self.assertEqual(configured.drive_picker_config['developer_key'],'restricted-key')
            self.assertNotIn('secret-not-exposed',json.dumps(configured.settings()))
            with self.assertRaises(ValueError):
                local_drive_secret_values(self.store,{'AGENTOS_DRIVE_SECRET_FILE':str(self.store.root/'inside.json')})

    def test_drive_status_is_authenticated_and_redacted(self):
        self.store.claim(self.store.bootstrap.read_text(),'long-password-test')
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.service));thread=threading.Thread(target=server.serve_forever);thread.start()
        client=build_opener(HTTPCookieProcessor(CookieJar()));base='http://127.0.0.1:'+str(server.server_port)
        try:
            with self.assertRaises(HTTPError) as error: client.open(base+'/api/drive/status',timeout=3)
            self.assertEqual(error.exception.code,401)
            request=Request(base+'/api/login',data=json.dumps({'password':'long-password-test'}).encode(),headers={'Content-Type':'application/json'})
            client.open(request,timeout=3).read()
            with client.open(base+'/api/drive/status',timeout=3) as response: result=json.load(response)
            self.assertEqual(result,{'configured':False,'local_only':False,'state':'not-configured'})
        finally:
            server.shutdown();thread.join();server.server_close()

    def test_local_drive_handoff_rejects_bad_callback_without_login(self):
        key=Fernet.generate_key()
        drive=DriveWebOAuthHandoff(EncryptedDriveSecretStore(self.store,key),'client',
            'http://localhost:8787/oauth/google/callback','http://localhost:8787',allow_localhost=True,local_only=True)
        service=AgentService(self.store,ModelAdapter(self.transport),self.transport,drive_web_oauth=drive)
        offer=drive.begin(123)
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service));thread=threading.Thread(target=server.serve_forever);thread.start()
        try:
            base='http://127.0.0.1:'+str(server.server_port)
            with self.assertRaises(HTTPError) as error:
                build_opener().open(base+'/oauth/google/callback?state=not-valid',timeout=3)
            self.assertEqual(error.exception.code,400)
            self.assertNotIn(offer['state'], error.exception.read().decode())
        finally:
            server.shutdown();thread.join();server.server_close()

    def test_loopback_alias_is_accepted_for_the_tls_drive_handoff(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.service));thread=threading.Thread(target=server.serve_forever);thread.start()
        try:
            url='http://127.0.0.1:'+str(server.server_port)
            with build_opener().open(Request(url+'/api/status',headers={'Host':'agentos.localhost:'+str(server.server_port)}),timeout=3) as response:
                self.assertIn('claimed',json.load(response))
        finally:
            server.shutdown();thread.join();server.server_close()

    def test_local_picker_page_uses_one_time_grant_without_server_oauth_token(self):
        key=Fernet.generate_key()
        drive=DriveWebOAuthHandoff(EncryptedDriveSecretStore(self.store,key),'web-client',
            'http://localhost:8787/oauth/google/callback','http://localhost:8787',allow_localhost=True,local_only=True)
        offer=drive.begin(123); state=parse_qs(urlsplit(offer['button']['url']).query)['state'][0]
        drive.complete({'state':state,'code':'short-code'},123,lambda _:{'access_token':'server-only-token','scope':'https://www.googleapis.com/auth/drive.file'})
        grant=drive.create_picker_grant(123)
        service=AgentService(self.store,ModelAdapter(self.transport),self.transport,drive_web_oauth=drive)
        service.drive_picker_config={'client_id':'web-client','developer_key':'restricted-browser-key','app_id':'123'}
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service));thread=threading.Thread(target=server.serve_forever);thread.start()
        try:
            url='http://127.0.0.1:'+str(server.server_port)
            with build_opener().open(url+'/google-drive-picker?grant='+grant,timeout=3) as response:
                page=response.read().decode()
                csp=response.headers['Content-Security-Policy']
            self.assertIn('restricted-browser-key',page)
            self.assertNotIn('server-only-token',page)
            self.assertIn("/api/drive/picker-selection",page)
            self.assertIn("'nonce-",csp)
            self.assertNotIn("script-src 'self' 'unsafe-inline'",csp)
            self.assertIn('<script nonce="',page)
        finally:
            server.shutdown();thread.join();server.server_close()

    def test_drive_request_without_local_capability_never_falls_through_to_model(self):
        self.model(); self.assertTrue(self.service.test_model()['ok']); self.calls.clear()
        self.store.enqueue('구글 드라이브 연결해 보자','drive-not-configured',channel='telegram:g',chat_id=123)
        self.assertTrue(self.service.run_one())
        job=self.store.jobs()[0]
        self.assertEqual(job['status'],'failed')
        self.assertIn('not configured locally',job['error'])
        self.assertFalse(any(url.endswith('/api/chat') for url, _body, _headers in self.calls))

    def test_selected_drive_content_is_only_in_memory_for_the_model_turn(self):
        key=Fernet.generate_key()
        drive=DriveWebOAuthHandoff(EncryptedDriveSecretStore(self.store,key),'client',
            'http://localhost:8787/oauth/google/callback','http://localhost:8787',allow_localhost=True,local_only=True)
        offer=drive.begin(123); state=parse_qs(urlsplit(offer['button']['url']).query)['state'][0]
        drive.complete({'state':state,'code':'code'},123,lambda _:{'access_token':'server-token','scope':'https://www.googleapis.com/auth/drive.file'})
        drive.select_files(123,[{'id':'picked','name':'plan.txt'}])
        service=AgentService(self.store,ModelAdapter(self.transport),self.transport,drive_web_oauth=drive)
        service.drive_read=lambda _url,_body,_headers:b'private selected Drive plan body'
        service.save_model({'provider':'ollama','endpoint':'http://127.0.0.1:11434','model':'test-model'})
        self.assertTrue(service.test_model()['ok']); self.calls.clear()
        job_id=self.store.enqueue('구글 드라이브 파일을 요약해줘','selected-drive',channel='telegram:g',chat_id=123)
        self.assertTrue(service.run_one())
        self.assertEqual(self.store.job(job_id)['status'],'succeeded')
        self.assertNotIn('private selected Drive plan body',json.dumps(self.store.history()))
        self.assertNotIn('private selected Drive plan body',json.dumps(self.store.jobs()))
        self.assertNotIn('private selected Drive plan body',json.dumps(self.store.recent_tool_events()))
        model_call=next(body for url,body,_headers in self.calls if url.endswith('/api/chat'))
        self.assertIn('private selected Drive plan body',str(model_call))

    def test_rejected_drive_read_requires_reauthentication(self):
        key=Fernet.generate_key()
        drive=DriveWebOAuthHandoff(EncryptedDriveSecretStore(self.store,key),'client',
            'http://localhost:8787/oauth/google/callback','http://localhost:8787',allow_localhost=True,local_only=True)
        offer=drive.begin(123); state=parse_qs(urlsplit(offer['button']['url']).query)['state'][0]
        drive.complete({'state':state,'code':'code'},123,lambda _:{'access_token':'server-token','scope':'https://www.googleapis.com/auth/drive.file'})
        drive.select_files(123,[{'id':'picked','name':'plan.txt'}])
        service=AgentService(self.store,ModelAdapter(self.transport),self.transport,drive_web_oauth=drive)
        def rejected(_url,_body,_headers):
            raise HTTPError('https://www.googleapis.com/drive/v3/files/picked',401,'rejected',None,None)
        service.drive_read=rejected
        with self.assertRaisesRegex(ValueError,'다시 연결'):
            service.selected_drive_context(123)
        self.assertEqual(drive.status()['state'],'reauth-required')

    def test_workspace_is_opt_in_and_saved_results_survive_restart(self):
        workspace=self.service.create_workspace({'title':'UX 개선','purpose':'대화 경험 정리'})
        self.assertEqual(self.store.workspaces()[0]['id'],workspace['id'])
        job=self.store.enqueue('/note 작업공간 메모','workspace-note',workspace_id=workspace['id'])
        self.service.run_one()
        saved=self.service.save_workspace_result(workspace['id'],{'job_id':job})
        self.assertEqual(saved['results'][0]['job_id'],job)
        restarted=QuickStore(self.temp.name).workspace_detail(workspace['id'])
        self.assertEqual(restarted['messages'][0]['workspace_id'] if 'workspace_id' in restarted['messages'][0] else workspace['id'],workspace['id'])
        self.assertEqual(restarted['results'][0]['content'],'메모를 저장했습니다. /notes로 확인하거나 /summarize로 정리할 수 있습니다.')

    def test_personal_space_redacts_context_and_deletes_only_owner_items(self):
        self.store.enqueue('/note private memory','space-note');self.service.run_one()
        workspace=self.service.create_workspace({'title':'space'})
        job=self.store.enqueue('/note saved result','space-result',workspace_id=workspace['id']);self.service.run_one()
        self.service.save_workspace_result(workspace['id'],{'job_id':job})
        inbox=self.service.context_inbox();inbox.configure({'sources':{'text':True,'url':False}})
        inbox.capture({'source_kind':'text','content':'private context content'})
        with self.store.db() as db: db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',(job,'web_search','succeeded','{"query":"private"}',time.time()))
        space=self.store.personal_space()
        self.assertEqual(space['memory_count'],2);self.assertEqual(space['result_count'],1);self.assertNotIn('private context content',json.dumps(space))
        evidence_before=len(space['evidence']);result=space['results'][0]
        self.assertTrue(self.store.delete_personal_space_item('results',result['id'])['deleted'])
        self.assertFalse(self.store.delete_personal_space_item('results',result['id'])['deleted'])
        self.assertEqual(len(self.store.personal_space()['evidence']),evidence_before)

    def test_result_evidence_is_category_only_and_messages_link_to_its_job(self):
        job=self.store.enqueue('/note private planning detail','evidence-link')
        self.service.run_one()
        with self.store.db() as db:
            db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',(job,'web_search','succeeded',json.dumps({'query':'private search phrase','url':'https://private.example'}),time.time()))
            db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',(job,'read_file','succeeded',json.dumps({'path':'/Users/private/plan.md','content':'private document'}),time.time()))
        result=self.store.evidence_summary(job)
        self.assertEqual(result,['공개 웹 1곳 참고','내 컴퓨터의 문서 1개 사용'])
        self.assertNotIn('private',json.dumps(result))
        messages=self.store.history()
        self.assertEqual([message['job_id'] for message in messages], [job,job])

    def test_workspace_requires_explicit_selection(self):
        with self.assertRaises(ValueError):self.store.enqueue('hello','missing-workspace',workspace_id='missing')

    def test_initial_claim_requires_local_code_and_is_single_use(self):
        code=self.store.bootstrap.read_text()
        with self.assertRaises(ValueError):self.store.claim('bad','long-test-password')
        self.store.claim(code,'long-test-password')
        with self.assertRaises(ValueError):self.store.claim(code,'different-password')

    def test_model_switch_preserves_history_but_not_keys_to_new_hosts(self):
        self.model(key='private-key')
        self.assertTrue(self.service.test_model()['ok'])
        self.store.enqueue('hello','first')
        self.service.run_one()
        self.model('compatible','https://example.test/v1')
        self.assertEqual(self.store.secret('model_key'),'')
        self.assertTrue(self.service.test_model()['ok'])
        self.store.enqueue('continue','second')
        self.service.run_one()
        self.assertEqual(len(self.store.history()),4)
        sent=self.calls[-1][1]['messages']
        self.assertIn('Ollama response',[m.get('content','') for m in sent])
        self.assertEqual(self.store.jobs()[0]['provider'],'compatible')

    def test_strict_web_model_flow_allows_keyless_ollama(self):
        self.model('compatible','https://example.test/v1','private-key')
        draft={'provider':'ollama','endpoint':'http://127.0.0.1:11434',
               'model':'local-model','api_key':'','require_key':True}
        tested=self.service.test_model(draft,strict=True)
        self.assertTrue(tested['ok'])
        self.assertGreaterEqual(len(tested['test_proof']),32)
        draft['test_proof']=tested['test_proof']
        saved=self.service.save_model(draft,strict=True)
        self.assertEqual(saved['model']['provider'],'ollama')
        self.assertTrue(saved['model_ready'])
        self.assertEqual(self.store.secret('model_key'),'')

    def test_strict_model_save_requires_exact_single_use_server_proof(self):
        self.model('compatible','https://example.test/v1','old-key')
        draft={'provider':'openai','endpoint':'https://api.openai.com/v1',
               'model':'tested-model','api_key':'new-key','require_key':True}
        tested=self.service.test_model(draft,strict=True)
        with self.assertRaises(ValueError):
            self.service.save_model({**draft,'model':'untested','test_proof':tested['test_proof']},strict=True)
        with self.assertRaises(ValueError):
            self.service.save_model({**draft,'api_key':'different-key','test_proof':tested['test_proof']},strict=True)
        saved=self.service.save_model({**draft,'test_proof':tested['test_proof']},strict=True)
        self.assertTrue(saved['model_ready'])
        with self.assertRaises(ValueError):
            self.service.save_model({**draft,'test_proof':tested['test_proof']},strict=True)

    def test_all_model_protocols(self):
        for provider,endpoint in [('ollama','http://localhost:11434'),('compatible','https://example.test/v1'),('openai','https://api.openai.com/v1'),('anthropic','https://api.anthropic.com')]:
            self.model(provider,endpoint,'test-key')
            self.assertTrue(self.service.test_model()['ok'])
            self.assertTrue(self.service.settings()['model_test']['ok'])
        self.assertEqual(self.calls[-1][2]['anthropic-version'],'2023-06-01')
        self.assertEqual(self.calls[-1][1]['tool_choice'],{'type':'any'})

    def test_text_only_connection_is_not_marked_tool_ready(self):
        def text_only(url,body,headers=None,timeout=60):
            if body.get('tools'):return {'choices':[{'message':{'content':'I cannot use tools'}}]}
            return {'choices':[{'message':{'content':'hello'}}]}
        service=AgentService(self.store,ModelAdapter(text_only),text_only)
        service.save_model({'provider':'compatible','endpoint':'https://example.test/v1','model':'text-only'})
        result=service.test_model()
        self.assertFalse(result['ok'])
        self.assertTrue(result['text_ok'])
        self.assertFalse(result['tools_ok'])
        self.assertFalse(service.settings()['model_ready'])

    def test_stale_or_unverified_model_does_not_run_agent(self):
        self.model()
        self.store.enqueue('웹에서 찾아줘','unverified')
        self.service.run_one()
        self.assertEqual(self.store.jobs()[0]['status'],'failed')
        self.assertIn('도구 호출 연결',self.store.jobs()[0]['error'])
        self.assertEqual(self.calls,[])
        self.assertTrue(self.service.test_model()['ok'])
        checked=self.store.config('model_test');checked['time']=time.time()-90000;self.store.put('model_test',checked)
        self.store.enqueue('다시 찾아줘','stale')
        self.service.run_one()
        self.assertEqual(self.store.jobs()[0]['status'],'failed')
        self.assertEqual(len(self.calls),2)

    def test_notes_work_without_model_and_summarize_with_model(self):
        self.store.enqueue('/note 회의: 금요일 출시 검토','note')
        self.service.run_one()
        self.store.enqueue('/notes','list')
        self.service.run_one()
        self.assertIn('금요일',self.store.jobs()[0]['response'])
        self.model()
        self.assertTrue(self.service.test_model()['ok'])
        self.store.enqueue('/summarize','summary')
        self.service.run_one()
        self.assertTrue(any('금요일' in m.get('content','') for m in self.calls[-1][1]['messages'] if m['role']=='user'))
        self.assertEqual(len(QuickStore(self.temp.name).notes()),1)

    def test_conversation_summary_saves_real_workspace_markdown(self):
        reference=Path(self.temp.name)/'reference'; workspace=Path(self.temp.name)/'workspace';reference.mkdir();workspace.mkdir()
        original=reference/'meeting.txt';original.write_text('Aurora launch decision: ship October 12.',encoding='utf-8');before=original.read_bytes()
        password='long-password-test';self.store.claim(self.store.bootstrap.read_text(),password)
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.service));thread=threading.Thread(target=server.serve_forever);thread.start()
        client=build_opener(HTTPCookieProcessor(CookieJar()));base='http://127.0.0.1:'+str(server.server_port)
        def post(path,body):
            request=Request(base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
            with client.open(request,timeout=3) as response:return json.load(response)
        try:
            post('/api/login',{'password':password})
            with self.assertRaises(HTTPError):post('/api/file-workspace',{'references':['/'],'workspace':str(workspace)})
            state=post('/api/file-workspace',{'references':[str(reference)],'workspace':str(workspace)})
            self.model('compatible','http://127.0.0.1:11434/v1');self.assertTrue(self.service.test_model()['ok'])
            request=post('/api/chat',{'message':'“Aurora launch” 자료를 요약해 “Launch notes”로 저장해줘','request_key':'workspace-summary'})['id']
            self.assertTrue(self.service.run_one())
        finally:
            server.shutdown();thread.join();server.server_close()
        job=self.store.job(request);self.assertEqual(job['status'],'succeeded')
        created=list(workspace.glob('*.md'));self.assertEqual(len(created),1)
        self.assertIn('Compatible response',created[0].read_text(encoding='utf-8'));self.assertIn('meeting.txt',created[0].read_text(encoding='utf-8'))
        self.assertEqual(original.read_bytes(),before)
        self.assertEqual(request,self.store.enqueue('“Aurora launch” 자료를 요약해 “Launch notes”로 저장해줘','workspace-summary'))
        self.assertEqual(len(list(workspace.glob('*.md'))),1)
        script='''\
import json, sys, threading
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
from urllib.request import Request, build_opener, HTTPCookieProcessor
from personal_agent.quickstart_store import QuickStore
from personal_agent.quickstart_service import AgentService
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart import make_handler
store=QuickStore(sys.argv[1])
service=AgentService(store,ModelAdapter(lambda *_args,**_kwargs: {}),lambda *_args,**_kwargs: {})
server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service));thread=threading.Thread(target=server.serve_forever);thread.start()
client=build_opener(HTTPCookieProcessor(CookieJar()));base='http://127.0.0.1:'+str(server.server_port)
def post(path,body):
 request=Request(base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with client.open(request,timeout=3) as response:return json.load(response)
try:
 post('/api/login',{'password':'long-password-test'})
 job_id=post('/api/chat',{'message':'저장된 작업공간에서 “Compatible” 찾아줘','request_key':'workspace-search-after-restart'})['id']
 service.run_one();job=store.job(job_id)
 print(json.dumps({'status':job['status'],'response':job['response']}))
finally:
 server.shutdown();server.server_close();thread.join()
'''
        environment={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
        restarted=subprocess.run([sys.executable,'-c',script,self.temp.name],cwd=Path(__file__).resolve().parents[1],env=environment,text=True,capture_output=True,check=True)
        result=json.loads(restarted.stdout)
        self.assertEqual(result['status'],'succeeded');self.assertIn('Compatible response',result['response']);self.assertIn('meeting.txt',result['response'])

    def test_owner_dogfood_vertical_slice_runs_over_http_and_restarts(self):
        """Exercise the credential-free owner journey through the real local worker."""
        reference=Path(self.temp.name)/'reference';workspace=Path(self.temp.name)/'workspace'
        reference.mkdir();workspace.mkdir()
        original=reference/'launch.md';original.write_text('Launch review: ship October 12.',encoding='utf-8')
        before=original.read_bytes()
        password='owner-dogfood-password'

        def start_server(service):
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service))
            thread=threading.Thread(target=server.serve_forever);thread.start()
            service.start()
            client=build_opener(HTTPCookieProcessor(CookieJar()))
            base='http://127.0.0.1:'+str(server.server_port)
            return server,thread,client,base

        def request(client,base,path,body=None):
            req=Request(base+path,data=json.dumps(body).encode() if body is not None else None,
                        headers={'Content-Type':'application/json'} if body is not None else {})
            with client.open(req,timeout=3) as response:return json.load(response)

        def wait_for(client,base,job_id):
            for _ in range(100):
                state=request(client,base,'/api/state')
                job=next(item for item in state['jobs'] if item['id']==job_id)
                if job['status'] not in ('queued','running'):return job
                time.sleep(.03)
            self.fail('local worker did not finish the owner request')

        server,thread,client,base=start_server(self.service)
        try:
            request(client,base,'/api/claim',{'code':self.store.bootstrap.read_text(),'password':password})
            model={'provider':'compatible','endpoint':'https://example.test/v1','model':'test-model','api_key':'fixture-key'}
            tested=request(client,base,'/api/model/test',model)
            request(client,base,'/api/model',{**model,'test_proof':tested['test_proof']})
            self.assertTrue(request(client,base,'/api/model/test',{})['ok'])
            request(client,base,'/api/file-workspace',{'references':[str(reference)],'workspace':str(workspace)})
            request(client,base,'/api/documents/approval',{'approved':True})
            queued=request(client,base,'/api/chat',{
                'message':'“Launch review” 자료를 요약해 “Launch notes”로 저장해줘',
                'request_key':'owner-dogfood-summary'})
            first=wait_for(client,base,queued['id'])
            self.assertEqual(first['status'],'succeeded',first)
            self.assertEqual(len(list(workspace.glob('*.md'))),1)
            saved=next(workspace.glob('*.md'))
            self.assertIn('launch.md',saved.read_text(encoding='utf-8'))
            self.assertEqual(original.read_bytes(),before)
            self.assertTrue(self.store.config('file_workspace_document_jobs'))
        finally:
            self.service.stop.set()
            for worker in self.service.threads:worker.join(timeout=2)
            server.shutdown();thread.join();server.server_close()

        restarted=AgentService(QuickStore(self.temp.name),ModelAdapter(self.transport),self.transport)
        server,thread,client,base=start_server(restarted)
        try:
            request(client,base,'/api/login',{'password':password})
            queued=request(client,base,'/api/chat',{
                'message':'저장된 작업공간에서 “Launch notes” 찾아줘',
                'request_key':'owner-dogfood-reuse'})
            reused=wait_for(client,base,queued['id'])
            self.assertEqual(reused['status'],'succeeded')
            self.assertIn('Launch notes',reused['response'])
            self.assertIn('launch.md',reused['response'])
            self.assertEqual(request(client,base,'/api/home')['state'],'ready')
        finally:
            restarted.stop.set()
            for worker in restarted.threads:worker.join(timeout=2)
            server.shutdown();thread.join();server.server_close()

    def test_file_workspace_rejects_escape_and_cleans_up_failed_save(self):
        reference=Path(self.temp.name)/'reference';workspace=Path(self.temp.name)/'workspace';outside=Path(self.temp.name)/'outside.md'
        reference.mkdir();workspace.mkdir();outside.write_text('outside',encoding='utf-8')
        original=reference/'source.md';original.write_text('approved material',encoding='utf-8');before=original.read_bytes()
        state=self.service.configure_file_workspace({'references':[str(reference)],'workspace':str(workspace)})
        files=FileWorkspace(self.store);ref_id=state['references'][0]['id']
        with self.assertRaises(ValueError):self.service.configure_file_workspace({'references':[self.temp.name],'workspace':str(workspace)})
        with self.assertRaises(ValueError):self.service.configure_file_workspace({'references':[str(reference)],'workspace':self.temp.name})
        with self.assertRaises(ValueError):files.read(ref_id,'../outside.md')
        with self.assertRaises(ValueError):files.read(ref_id,str(outside))
        (reference/'linked.md').symlink_to(outside)
        with self.assertRaises(ValueError):files.read(ref_id,'linked.md')
        source=files.read(ref_id,'source.md')
        owner_file=workspace/'Summary.md';owner_file.write_text('owner content',encoding='utf-8')
        saved=files.save('once','Summary','saved summary',[source])
        self.assertEqual(saved['request_id'],'once');self.assertEqual(files.save('once','Summary','other text',[source])['id'],saved['id'])
        self.assertEqual(owner_file.read_text(encoding='utf-8'),'owner content');self.assertEqual(saved['path'],'Summary-2.md')
        self.assertEqual(len(list(workspace.glob('*.md'))),2);self.assertEqual(original.read_bytes(),before)
        with patch('personal_agent.file_workspace.os.link',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):files.save('failed','Failed','not persisted',[source])
        self.assertFalse((workspace/'Failed.md').exists())

    def test_file_workspace_refresh_omits_modified_renamed_and_deleted_sources(self):
        reference=Path(self.temp.name)/'reference';workspace=Path(self.temp.name)/'workspace';reference.mkdir();workspace.mkdir()
        self.service.configure_file_workspace({'references':[str(reference)],'workspace':str(workspace)});files=FileWorkspace(self.store);ref_id=files.status()['references'][0]['id']
        self.assertEqual(self.service.configure_file_workspace({'references':[str(reference)],'workspace':str(workspace)})['references'][0]['id'],ref_id)
        for index,operation in enumerate(('modify','rename','delete')):
            original=reference/f'source-{index}.md';original.write_text(f'original {operation}',encoding='utf-8')
            source=files.read(ref_id,original.name);files.save(f'refresh-{operation}',f'Result {index}',f'summary {operation}',[source])
            if operation=='modify': original.write_text('changed',encoding='utf-8')
            elif operation=='rename': original.rename(reference/f'renamed-{index}.md')
            else: original.unlink()
            self.assertEqual(files.search(f'summary {operation}'),[])
        with self.store.db() as db:self.assertEqual(db.execute("SELECT count(*) FROM file_workspace_results WHERE state='stale'").fetchone()[0],3)

    def test_file_workspace_rejects_same_content_replacement_and_other_workspace_file(self):
        reference=Path(self.temp.name)/'reference';first=Path(self.temp.name)/'first';second=Path(self.temp.name)/'second'
        reference.mkdir();first.mkdir();second.mkdir();original=reference/'source.txt';original.write_text('same bytes',encoding='utf-8')
        state=self.service.configure_file_workspace({'references':[str(reference)],'workspace':str(first)});files=FileWorkspace(self.store)
        source=files.read(state['references'][0]['id'],'source.txt');saved=files.save('bound','Summary','bound summary',[source])
        self.assertNotIn('same bytes',json.loads(saved['sources'])[0])
        original.rename(reference/'renamed.txt');(reference/'source.txt').write_text('same bytes',encoding='utf-8')
        self.assertEqual(files.search('bound summary'),[])
        second.joinpath(saved['path']).write_text('unrelated workspace result',encoding='utf-8')
        self.service.configure_file_workspace({'references':[str(reference)],'workspace':str(second)})
        self.assertEqual(files.search('unrelated'),[])

    def test_file_workspace_recovers_published_pending_result_after_interruption(self):
        reference=Path(self.temp.name)/'reference';workspace=Path(self.temp.name)/'workspace';reference.mkdir();workspace.mkdir()
        state=self.service.configure_file_workspace({'references':[str(reference)],'workspace':str(workspace)})
        original=reference/'source.txt';original.write_text('recovery source',encoding='utf-8')
        files=FileWorkspace(self.store);source=files.read(state['references'][0]['id'],'source.txt')
        with patch.object(files,'_mark_current',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):files.save('interrupted','Recovery','recovery summary',[source])
        with self.store.db() as db:self.assertEqual(db.execute("SELECT count(*) FROM file_workspace_results WHERE state='pending'").fetchone()[0],1)
        self.assertEqual(len(files.search('recovery')),1)
        with self.store.db() as db:self.assertEqual(db.execute("SELECT count(*) FROM file_workspace_results WHERE state='current'").fetchone()[0],1)

    def test_workspace_summary_blocks_unapproved_external_model_before_send(self):
        reference=Path(self.temp.name)/'reference';workspace=Path(self.temp.name)/'workspace';reference.mkdir();workspace.mkdir()
        (reference/'source.md').write_text('Aurora external boundary',encoding='utf-8')
        self.service.configure_file_workspace({'references':[str(reference)],'workspace':str(workspace)})
        self.model('compatible','https://example.test/v1','test-key');self.assertTrue(self.service.test_model()['ok'])
        self.assertFalse(self.service.set_document_approval({'approved':True})['requires_approval'])
        self.service.configure_file_workspace({'references':[str(reference)],'workspace':str(workspace)})
        self.assertTrue(self.service.document_boundary()['requires_approval'])
        before=len(self.calls);job_id=self.store.enqueue('/workspace-summary Aurora :: External summary','external-workspace')
        self.service.run_one();job=self.store.job(job_id)
        self.assertEqual(job['status'],'failed');self.assertIn('문서 공유 승인',job['error']);self.assertEqual(len(self.calls),before);self.assertEqual(list(workspace.glob('*.md')),[])

    def test_workspace_save_failure_never_reports_success(self):
        reference=Path(self.temp.name)/'reference';workspace=Path(self.temp.name)/'workspace';reference.mkdir();workspace.mkdir()
        (reference/'source.txt').write_text('Aurora storage failure',encoding='utf-8')
        self.service.configure_file_workspace({'references':[str(reference)],'workspace':str(workspace)})
        self.model('compatible','http://127.0.0.1:11434/v1');self.assertTrue(self.service.test_model()['ok'])
        job_id=self.store.enqueue('/workspace-summary Aurora :: Failure','workspace-storage-failure')
        with patch('personal_agent.file_workspace.os.link',side_effect=OSError('disk full')): self.assertTrue(self.service.run_one())
        job=self.store.job(job_id)
        self.assertEqual(job['status'],'failed');self.assertIn('disk full',job['error']);self.assertEqual(list(workspace.glob('*.md')),[])

    def test_natural_workspace_conversation_and_unapproved_history_boundary(self):
        reference=Path(self.temp.name)/'reference';workspace=Path(self.temp.name)/'workspace';reference.mkdir();workspace.mkdir()
        (reference/'source.txt').write_text('Aurora private source',encoding='utf-8')
        state=self.service.configure_file_workspace({'references':[str(reference)],'workspace':str(workspace)})
        self.model('compatible','http://127.0.0.1:11434/v1');self.assertTrue(self.service.test_model()['ok'])
        summary=self.store.enqueue('“Aurora” 자료를 요약해 “Launch notes”로 저장해줘','natural-summary');self.service.run_one()
        self.assertEqual(self.store.job(summary)['status'],'succeeded');self.assertTrue((workspace/'Launch notes.md').is_file())
        self.assertIn(summary,self.store.config('file_workspace_document_jobs',[]))
        files=FileWorkspace(self.store);source=files.read(state['references'][0]['id'],'source.txt');files.save('history-document','Stored','PRIVATE-DOCUMENT-TEXT',[source])
        searched=self.store.enqueue('저장된 작업공간에서 “PRIVATE-DOCUMENT-TEXT” 찾아줘','natural-search');self.service.run_one()
        self.assertIn('PRIVATE-DOCUMENT-TEXT',self.store.job(searched)['response'])
        self.model('compatible','https://example.test/v1','test-key');self.assertTrue(self.service.test_model()['ok']);before=len(self.calls)
        ordinary=self.store.enqueue('일반적인 다음 질문입니다.','ordinary-after-document');self.service.run_one()
        self.assertEqual(self.store.job(ordinary)['status'],'succeeded')
        self.assertNotIn('PRIVATE-DOCUMENT-TEXT',json.dumps(self.calls[before:],ensure_ascii=False))

    def test_workspace_summary_remains_rejected_for_subscription_engine(self):
        reference=Path(self.temp.name)/'reference';workspace=Path(self.temp.name)/'workspace';reference.mkdir();workspace.mkdir()
        (reference/'source.txt').write_text('Aurora subscription boundary',encoding='utf-8')
        self.service.configure_file_workspace({'references':[str(reference)],'workspace':str(workspace)})
        self.store.put('subscription_engine',{'id':'codex','connected_at':0})
        job_id=self.store.enqueue('“Aurora” 자료를 요약해 “Subscription”으로 저장해줘','subscription-workspace')
        self.service.run_one();job=self.store.job(job_id)
        self.assertEqual(job['status'],'failed');self.assertIn('구독 엔진',job['error']);self.assertEqual(list(workspace.glob('*.md')),[])

    def test_idempotent_requests_and_interrupted_recovery(self):
        task=self.store.enqueue('hello','same')
        self.assertEqual(task,self.store.enqueue('hello','same'))
        with self.assertRaises(ValueError):self.store.enqueue('different','same')
        with self.store.db() as db:db.execute("UPDATE jobs SET status='running',delivery='sending'")
        self.store.recover()
        self.assertEqual(self.store.jobs()[0]['status'],'interrupted')
        self.assertEqual(self.store.jobs()[0]['delivery'],'unknown')
        self.assertFalse(self.service.run_one())

    def pair(self):
        link=self.service.connect_telegram({'token':'123456:TEST_TOKEN'})['url']
        code=parse_qs(urlsplit(link).query)['start'][0]
        cfg=self.store.config('telegram')
        self.service.ingest_update({'update_id':10,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'/start '+code}},cfg['generation'])
        return cfg['generation']

    def test_botfather_token_is_local_only_and_never_appears_in_public_state(self):
        token='123456:TEST_TOKEN'
        link=self.service.connect_telegram({'token':token})['url']
        cfg=self.store.config('telegram')
        self.assertEqual(cfg['mode'],'owner-token')
        self.assertEqual(self.store.secret('telegram_token'),token)
        self.assertNotIn(token,json.dumps(self.service.settings()))
        self.assertNotIn(token,json.dumps(self.store.recent_tool_events()))
        self.assertNotIn('pair_code',json.dumps(self.service.settings()))
        self.assertIn('start=',link)
        self.service.disconnect_telegram()
        self.assertEqual(self.store.secret('telegram_token'),'')

    def test_botfather_codex_verification_acceptance_is_automatic_after_private_delivery(self):
        self.store.secret('telegram_token','123456:TEST_TOKEN')
        self.store.put('telegram',{'enabled':True,'mode':'owner-token','username':'owner_test_bot','generation':'safe','user_id':42})
        with self.store.db() as db:
            db.execute("INSERT INTO jobs(id,request_key,message,channel,chat_id,status,response,error,delivery,provider,model,created,workspace_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",('job','telegram-verify:safe','/search AgentOS personal assistant verification','telegram:safe',42,'succeeded','done',None,'sent','subscription','codex',time.time(),None))
            db.execute("INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)",('job','web_search','succeeded','{}',time.time()))
        from personal_agent.telegram_first_work_acceptance import report
        result=report(self.store)
        self.assertTrue(result['passed'])
        self.assertTrue(result['checks']['paired_delivery_confirmed'])
        self.assertNotIn('123456:TEST_TOKEN',json.dumps(result))

    def test_pairing_queues_one_idempotent_codex_connection_verification(self):
        self.store.put('subscription_engine',{'id':'codex'})
        self.pair()
        jobs=[job for job in self.store.jobs() if job['request_key'].startswith('telegram-verify:')]
        self.assertEqual(len(jobs),1)
        first=self.service.queue_telegram_connection_verification()
        second=self.service.queue_telegram_connection_verification()
        self.assertTrue(first['queued'])
        self.assertEqual(first['job_id'],second['job_id'])


    def test_botfather_connection_rejects_invalid_account_and_webhook(self):
        def invalid_account(url,body,headers=None,timeout=60):
            if url.endswith('/getMe'):return {'ok':True,'result':{'username':''}}
            if url.endswith('/getWebhookInfo'):return {'ok':True,'result':{'url':''}}
            raise AssertionError(url)
        service=AgentService(self.store,ModelAdapter(invalid_account),invalid_account)
        with self.assertRaises(ProviderError):service.connect_telegram({'token':'123456:TEST_TOKEN'})
        def webhook(url,body,headers=None,timeout=60):
            if url.endswith('/getMe'):return {'ok':True,'result':{'username':'owner_test_bot'}}
            if url.endswith('/getWebhookInfo'):return {'ok':True,'result':{'url':'https://example.test/hook'}}
            raise AssertionError(url)
        service=AgentService(self.store,ModelAdapter(webhook),webhook)
        with self.assertRaises(ValueError):service.connect_telegram({'token':'123456:TEST_TOKEN'})

    def test_legacy_personal_bot_config_is_recognized_as_botfather_setup(self):
        self.store.put('telegram',{'enabled':True,'username':'legacy_personal_bot','generation':'legacy','user_id':42})
        from personal_agent.telegram_first_work_acceptance import report
        self.assertTrue(report(self.store)['checks']['owner_botfather_bot'])

    def test_successful_telegram_poll_clears_stale_connection_error(self):
        self.pair()
        self.store.put('telegram_status',{'state':'error','message':'stale'})
        # The production loop writes connected after this same successful call.
        self.service.poll_telegram()
        self.service.mark_telegram_connected()
        self.assertEqual(self.store.config('telegram_status')['state'],'connected')

    def test_botfather_restart_resumes_durable_poll_cursor(self):
        self.pair()
        restarted=AgentService(QuickStore(self.temp.name),ModelAdapter(self.transport),self.transport)
        restarted.poll_telegram()
        poll=[call for call in self.calls if call[0].endswith('/getUpdates')][-1]
        self.assertEqual(poll[1]['offset'],11)

    def test_telegram_pairing_dedup_and_unauthorized_sender(self):
        generation=self.pair()
        self.assertEqual(self.store.config('telegram')['user_id'],42)
        self.assertNotIn('pair_code',json.dumps(self.service.settings()))
        self.service.run_one();self.service.deliver_one()
        update={'update_id':11,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'/note telegram note'}}
        self.service.ingest_update(update,generation);self.service.ingest_update(update,generation)
        self.service.run_one();self.service.deliver_one()
        self.service.ingest_update({'update_id':12,'message':{'from':{'id':99},'chat':{'id':99,'type':'private'},'text':'private data?'}},generation)
        self.assertEqual(len(self.store.jobs()),2)
        self.assertEqual(len(self.store.notes()),1)
        sends=[c for c in self.calls if c[0].endswith('/sendMessage')]
        self.assertEqual(len(sends),2)
        self.assertTrue(all(c[1]['chat_id']==42 for c in sends))
        self.assertNotIn('/start ',json.dumps(self.store.history()))

    def test_disconnect_cancels_outgoing_and_stale_updates(self):
        generation=self.pair()
        self.service.run_one()
        self.service.disconnect_telegram()
        self.service.deliver_one()
        self.assertEqual(self.store.jobs()[0]['delivery'],'cancelled')
        self.service.ingest_update({'update_id':20,'message':{}},generation)
        self.assertEqual(self.store.config('telegram')['cursor'],11)

    def test_ambiguous_send_not_automatically_repeated(self):
        self.pair();self.service.run_one()
        calls=[]
        def fail(*args,**kwargs):calls.append(1);raise ProviderError('timeout')
        self.service.telegram_transport=fail
        self.service.deliver_one();self.service.deliver_one()
        self.assertEqual(calls,[1])
        self.assertEqual(self.store.jobs()[0]['delivery'],'unknown')

    def test_group_chat_cannot_pair(self):
        self.service.connect_telegram({'token':'123456:TEST_TOKEN'})
        cfg=self.store.config('telegram')
        self.service.ingest_update({'update_id':1,'message':{'from':{'id':42},'chat':{'id':-42,'type':'group'},'text':'/start '+cfg['pair_code']}},cfg['generation'])
        self.assertIsNone(self.store.config('telegram')['user_id'])
        self.assertEqual(self.store.jobs(),[])

    def test_natural_language_task_card_has_safe_progress_and_queued_cancellation(self):
        generation=self.pair()
        self.service.run_one();self.service.deliver_one()
        request={'update_id':11,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'내일 회의 준비를 정리해 줘'}}
        self.service.ingest_update(request,generation)
        self.service.acknowledge_long_work(now=time.time()+10)  # the card is the long-work acknowledgement (#510)
        job=self.store.jobs()[0]
        card=self.store.task_card(job['id'])
        self.assertIsNotNone(card)
        create=[c for c in self.calls if c[0].endswith('/sendMessage')][-1]
        self.assertEqual(create[1]['reply_markup']['inline_keyboard'][0][1]['callback_data'],f"p7c:{job['id']}")
        callback_message={'chat':{'id':42,'type':'private'},'message_id':card['message_id']}
        self.service.ingest_callback({'id':'cancel-1','from':{'id':42},'message':callback_message,'data':f"p7c:{job['id']}"},generation)
        self.service.ingest_callback({'id':'cancel-2','from':{'id':42},'message':callback_message,'data':f"p7c:{job['id']}"},generation)
        self.assertEqual(self.store.jobs()[0]['status'],'cancelled')
        self.assertFalse(self.service.run_one())
        edits=[c for c in self.calls if c[0].endswith('/editMessageText')]
        self.assertEqual(len(edits),1)
        self.assertIn('취소됨',edits[0][1]['text'])

    def test_telegram_task_card_waits_briefly_for_cancellation(self):
        generation=self.pair()
        self.service.run_one();self.service.deliver_one()
        self.service.ingest_update({'update_id':11,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'잠시 뒤 실행할 요청'}},generation)
        self.service.acknowledge_long_work(now=time.time()+10)  # the card is the long-work acknowledgement (#510)
        job=self.store.jobs()[0]
        self.assertFalse(self.service.run_one())
        self.assertEqual(self.store.jobs()[0]['status'],'queued')
        card=self.store.task_card(job['id'])
        self.service.ingest_callback({'id':'cancel','from':{'id':42},'message':{'chat':{'id':42,'type':'private'},'message_id':card['message_id']},'data':f"p7c:{job['id']}"},generation)
        self.assertEqual(self.store.jobs()[0]['status'],'cancelled')

    def test_task_callbacks_require_owner_and_cannot_cancel_running_work(self):
        generation=self.pair()
        self.service.run_one();self.service.deliver_one()
        self.service.ingest_update({'update_id':11,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'작업 시작해 줘'}},generation)
        self.service.acknowledge_long_work(now=time.time()+10)  # the card is the long-work acknowledgement (#510)
        job=self.store.jobs()[0]
        callback={'id':'foreign','from':{'id':99},'message':{'chat':{'id':99,'type':'private'},'message_id':999},'data':f"p7c:{job['id']}"}
        self.service.ingest_callback(callback,generation)
        self.assertEqual(self.store.jobs()[0]['status'],'queued')
        self.make_due(job['id'])
        self.service.run_one()
        card=self.store.task_card(job['id'])
        self.service.ingest_callback({'id':'late','from':{'id':42},'message':{'chat':{'id':42,'type':'private'},'message_id':card['message_id']},'data':f"p7c:{job['id']}"},generation)
        self.assertIn(self.store.jobs()[0]['status'],('succeeded','failed'))

    def test_document_approval_notification_is_owner_bound_and_safe(self):
        generation=self.pair()
        self.service.run_one();self.service.deliver_one()
        while self.service.deliver_notification():pass
        def document_model(url,body,headers=None,timeout=60):
            if body.get('tools') and any((tool.get('function',{}).get('name') or tool.get('name'))=='agentos_connection_probe' for tool in body['tools']):
                return {'choices':[{'message':{'tool_calls':[{'id':'probe','function':{'name':'agentos_connection_probe','arguments':'{}'}}]}}]}
            if any(message.get('role')=='tool' for message in body.get('messages',[])):
                return {'choices':[{'message':{'content':'I need approval.'}}]}
            if body.get('tools'):
                return {'choices':[{'message':{'tool_calls':[{'id':'files','function':{'name':'find_files','arguments':'{"query":"confidential document"}'}}]}}]}
            return {'choices':[{'message':{'content':'I need approval.'}}]}
        self.service.adapter=ModelAdapter(document_model)
        self.model('compatible','https://example.test/v1','private-api-key')
        self.assertTrue(self.service.test_model()['ok'])
        self.service.ingest_update({'update_id':11,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'문서를 찾아 줘'}},generation)
        self.service.acknowledge_long_work(now=time.time()+10)  # the card is the long-work acknowledgement (#510)
        card=[c for c in self.calls if c[0].endswith('/sendMessage') and c[1]['text'].startswith('요청을 받았습니다.')][-1]
        self.assertNotIn('문서를 찾아',card[1]['text'])
        self.make_due(self.store.jobs()[0]['id'])
        self.service.run_one()
        self.assertTrue(self.service.deliver_notification())
        approval=[c for c in self.calls if c[0].endswith('/sendMessage') and c[1]['text'].startswith('연결 문서를')][-1]
        self.assertNotIn('private-api-key',json.dumps(approval[1]))
        self.assertNotIn('confidential document',json.dumps(approval[1]))
        approval_row=self.store.notification(approval[1]['reply_markup']['inline_keyboard'][0][0]['callback_data'].split(':')[1])
        callback_message={'chat':{'id':42,'type':'private'},'message_id':approval_row['message_id']}
        self.service.ingest_callback({'id':'foreign-approval','from':{'id':99},'message':{'chat':{'id':99,'type':'private'},'message_id':approval_row['message_id']},'data':f"p7a:{approval_row['id']}:approve"},generation)
        self.assertTrue(self.service.document_boundary()['requires_approval'])
        self.service.ingest_callback({'id':'approve','from':{'id':42},'message':callback_message,'data':f"p7a:{approval_row['id']}:approve"},generation)
        self.assertFalse(self.service.document_boundary()['requires_approval'])

    def test_telegram_guides_explicit_context_choice_without_exposing_content(self):
        generation=self.pair()
        self.service.run_one();self.service.deliver_one()
        inbox=self.service.context_inbox()
        inbox.configure({'sources':{'text':True}})
        item=inbox.capture({'source_kind':'text','content':'private roadmap detail'})
        request={'update_id':11,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'저장한 컨텍스트를 함께 참고해서 계획을 만들어 줘'}}
        self.service.ingest_update(request,generation)
        job=self.store.jobs()[0]
        self.assertEqual(job['status'],'awaiting_context')
        offer=[call[1] for call in self.calls if call[0].endswith('/sendMessage') and call[1].get('text','').startswith('이번 요청에 참고할')][-1]
        self.assertNotIn('private roadmap detail',json.dumps(offer))
        callback=offer['reply_markup']['inline_keyboard'][0][0]['callback_data']
        self.assertTrue(callback.startswith('p7x:'))
        choice=self.store.telegram_context_choice(callback[4:])
        self.assertEqual(choice['event_id'],item['id'])
        self.service.ingest_callback({'id':'foreign','from':{'id':99},'message':{'chat':{'id':99,'type':'private'},'message_id':choice['message_id']},'data':callback},generation)
        self.assertEqual(self.store.job(job['id'])['status'],'awaiting_context')
        self.service.ingest_callback({'id':'wrong-message','from':{'id':42},'message':{'chat':{'id':42,'type':'private'},'message_id':choice['message_id']+1},'data':callback},generation)
        self.assertEqual(self.store.job(job['id'])['status'],'awaiting_context')
        self.service.ingest_callback({'id':'choose','from':{'id':42},'message':{'chat':{'id':42,'type':'private'},'message_id':choice['message_id']},'data':callback},generation)
        self.assertEqual(self.store.job(job['id'])['status'],'queued')
        self.assertEqual(self.store.context_attachment(job['id'])['event_ids'],[item['id']])
        self.assertIsNotNone(self.store.task_card(job['id']))

    def test_telegram_context_is_explicit_source_evidenced_and_per_job_approved(self):
        generation=self.pair()
        self.service.run_one();self.service.deliver_one()
        while self.service.deliver_notification():pass
        self.model('compatible','https://example.test/v1','private-api-key')
        self.assertTrue(self.service.test_model()['ok'])
        inbox=self.service.context_inbox()
        inbox.configure({'sources':{'text':True}})
        item=inbox.capture({'source_kind':'text','content':'Aurora launches on Friday','retention_seconds':60})
        self.service.set_context_telegram_policy({'approved':True})
        self.service.ingest_update({'update_id':11,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':f"/context {item['id']} -- 출시일을 알려줘"}},generation)
        job=self.store.jobs()[0];self.make_due(job['id'])
        self.service.run_one()
        self.assertEqual(self.store.job(job['id'])['status'],'failed')
        self.assertFalse(any('Aurora launches' in json.dumps(call[1]) for call in self.calls if call[0].endswith('/chat/completions')))
        self.service.deliver_notification()
        approval=[call for call in self.calls if call[0].endswith('/sendMessage') and call[1]['text'].startswith('개인 컨텍스트')][-1]
        callback=approval[1]['reply_markup']['inline_keyboard'][0][0]['callback_data']
        notification_id=callback.split(':')[1]
        notification=self.store.notification(notification_id)
        self.service.ingest_callback({'id':'context-approve','from':{'id':42},'message':{'chat':{'id':42,'type':'private'},'message_id':notification['message_id']},'data':callback},generation)
        self.make_due(job['id']);self.service.run_one()
        self.assertEqual(self.store.job(job['id'])['status'],'succeeded')
        sent=[call[1] for call in self.calls if call[0].endswith('/chat/completions')]
        self.assertTrue(any('Aurora launches on Friday' in json.dumps(body) for body in sent))
        self.assertIn('컨텍스트:',self.store.job(job['id'])['response'])

    def test_task_card_progress_button_returns_safe_owner_bound_evidence(self):
        generation=self.pair()
        self.service.run_one();self.service.deliver_one()
        self.service.ingest_update({'update_id':11,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'private request secret'}},generation)
        self.service.acknowledge_long_work(now=time.time()+10)  # the card is the long-work acknowledgement (#510)
        job=self.store.jobs()[0]
        card=self.store.task_card(job['id'])
        initial=[c for c in self.calls if c[0].endswith('/sendMessage') and c[1].get('text','').startswith('요청을 받았습니다.')][-1]
        labels=[button['text'] for button in initial[1]['reply_markup']['inline_keyboard'][0]]
        self.assertEqual(labels,['진행 보기','작업 취소'])
        self.service.ingest_callback({'id':'foreign-progress','from':{'id':99},'message':{'chat':{'id':99,'type':'private'},'message_id':card['message_id']},'data':f"p7v:{job['id']}"},generation)
        self.assertFalse(any(c[0].endswith('/sendMessage') and c[1].get('text','').startswith('작업 상태:') for c in self.calls))
        self.service.ingest_callback({'id':'progress','from':{'id':42},'message':{'chat':{'id':42,'type':'private'},'message_id':card['message_id']},'data':f"p7v:{job['id']}"},generation)
        progress=[c for c in self.calls if c[0].endswith('/sendMessage') and c[1].get('text','').startswith('작업 상태:')][-1]
        self.assertIn('대기 중',progress[1]['text'])
        self.assertNotIn('private request',progress[1]['text'])
        self.assertNotIn(job['id'],progress[1]['text'])
        self.make_due(job['id'])
        self.service.run_one()
        edit=[c for c in self.calls if c[0].endswith('/editMessageText')][-1]
        self.assertEqual(edit[1]['reply_markup']['inline_keyboard'][0][0]['text'],'결과 상태 보기')

    def test_telegram_normal_request_has_one_terminal_answer_without_generic_completion(self):
        generation=self.pair()
        self.service.run_one();self.service.deliver_one()
        self.model();self.assertTrue(self.service.test_model()['ok'])
        baseline=len(self.calls)
        self.service.ingest_update({'update_id':11,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'오늘 할 일을 정리해 줘'}},generation)
        job=self.store.jobs()[0];self.make_due(job['id'])
        self.service.run_one();self.service.deliver_one()
        outbound=[call[1]['text'] for call in self.calls[baseline:] if call[0].endswith('/sendMessage')]
        # One bubble: the answer.  No received/running/completed card (#510).
        self.assertEqual(outbound,['Ollama response'])
        self.assertIsNone(self.store.task_card(job['id']))
        self.assertFalse(self.service.deliver_notification())
        self.assertEqual(self.store.job(job['id'])['delivery'],'sent')

    def test_telegram_long_terminal_answer_keeps_one_scannable_bubble(self):
        generation=self.pair()
        self.service.run_one();self.service.deliver_one()
        job_id=self.store.enqueue('long answer','long-answer',f'telegram:{generation}',42)
        original='가'* (TELEGRAM_RESULT_PREVIEW_CHARS+100)
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='succeeded',response=?,delivery='pending' WHERE id=?",(original,job_id))
        self.service.deliver_one()
        sent=[call[1]['text'] for call in self.calls if call[0].endswith('/sendMessage')][-1]
        self.assertEqual(sent[:TELEGRAM_RESULT_PREVIEW_CHARS],original[:TELEGRAM_RESULT_PREVIEW_CHARS])
        self.assertTrue(sent.endswith('전체 결과는 AgentOS 웹에서 확인하세요.'))
        self.assertEqual(self.store.job(job_id)['delivery'],'sent')

    def test_telegram_failure_has_one_terminal_answer_without_generic_failure_notice(self):
        generation=self.pair()
        self.service.run_one();self.service.deliver_one()
        baseline=len(self.calls)
        self.service.ingest_update({'update_id':11,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'도움을 줘'}},generation)
        job=self.store.jobs()[0];self.make_due(job['id'])
        self.service.run_one();self.service.deliver_one()
        outbound=[call[1]['text'] for call in self.calls[baseline:] if call[0].endswith('/sendMessage')]
        # One truthful bubble: what is blocked, what works now, where to connect (#510, #477).
        self.assertEqual(len(outbound),1)
        self.assertIn('아직 AI가 연결되지 않아',outbound[0])
        self.assertNotIn('구독 엔진',outbound[0])
        self.assertFalse(self.service.deliver_notification())
        self.assertEqual(self.store.job(job['id'])['delivery'],'sent')

    def test_task_card_progress_truthfully_explains_restart_and_uncertain_delivery(self):
        generation=self.pair()
        self.service.run_one();self.service.deliver_one()
        self.service.ingest_update({'update_id':11,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'private recovery request'}},generation)
        self.service.acknowledge_long_work(now=time.time()+10)  # the card is the long-work acknowledgement (#510)
        job=self.store.jobs()[0]
        card=self.store.task_card(job['id'])
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running',delivery='sending' WHERE id=?",(job['id'],))
        self.store.recover()
        self.service.ingest_callback({'id':'recovery-progress','from':{'id':42},'message':{'chat':{'id':42,'type':'private'},'message_id':card['message_id']},'data':f"p7v:{job['id']}"},generation)
        progress=[c for c in self.calls if c[0].endswith('/sendMessage') and c[1].get('text','').startswith('작업 상태:')][-1][1]['text']
        self.assertIn('중단됨',progress)
        self.assertIn('자동으로 다시 실행하지 않았습니다.',progress)
        self.assertIn('전달 여부를 확인할 수 없습니다.',progress)
        self.assertIn('자동으로 다시 보내지 않았습니다.',progress)
        self.assertNotIn('private recovery request',progress)
        self.assertNotIn(job['id'],progress)

    def test_terminal_notifications_survive_restart_without_ambiguous_retry(self):
        generation=self.pair()
        self.service.run_one();self.service.deliver_one()
        while self.service.deliver_notification():pass
        self.service.ingest_update({'update_id':11,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'모델 없이 실패해 줘'}},generation)
        self.make_due(self.store.jobs()[0]['id'])
        self.service.run_one()
        job=self.store.jobs()[0]
        self.assertIn(job['delivery'],('pending','sent'))
        restarted=AgentService(QuickStore(self.temp.name),ModelAdapter(self.transport),self.transport)
        restarted.deliver_one()
        self.assertEqual(restarted.store.job(job['id'])['delivery'],'sent')
        with restarted.store.db() as db:db.execute("UPDATE jobs SET delivery='sending' WHERE id=?",(job['id'],))
        restarted.store.recover()
        self.assertEqual(restarted.store.job(job['id'])['delivery'],'unknown')
        # The guarantee this test stopped one line short of: `deliver_one`
        # selects only delivery='pending', so running the restarted delivery
        # loop again must not re-send a message the owner may already have
        # read.  Asserting the terminal state without ever re-running the loop
        # left that to inspection of the SQL.
        sent=[call for call in self.calls if call[0].endswith('/sendMessage')]
        restarted.deliver_one()
        self.assertEqual(restarted.store.job(job['id'])['delivery'],'unknown')
        self.assertEqual([call for call in self.calls if call[0].endswith('/sendMessage')],sent)

    def test_owner_can_record_live_task_card_attestation_only_after_durable_evidence(self):
        generation=self.pair()
        with self.assertRaises(ValueError):
            self.service.attest_telegram_task_card_acceptance({'web_confirmed':True,'restart_confirmed':True})
        self.service.run_one();self.service.deliver_one()
        self.service.ingest_update({'update_id':11,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'safe request'}},generation)
        self.service.acknowledge_long_work(now=time.time()+10)  # the card is the long-work acknowledgement (#510)
        job=self.store.jobs()[0];card=self.store.task_card(job['id'])
        callback_message={'chat':{'id':42,'type':'private'},'message_id':card['message_id']}
        self.service.ingest_callback({'id':'cancel','from':{'id':42},'message':callback_message,'data':f"p7c:{job['id']}"},generation)
        approval=self.store.queue_notification(job['id'],42,generation,'approval_needed',self.service.document_fingerprint())
        self.store.update_notification(approval['id'],'approved')
        completed=self.store.queue_notification('other-job',42,generation,'completed')
        self.store.update_notification(completed['id'],'sent',123)
        self.store.enqueue('web evidence','web-evidence');self.service.run_one()
        result=self.service.attest_telegram_task_card_acceptance({'web_confirmed':True,'restart_confirmed':True})
        self.assertTrue(result['passed'])
        settings=self.service.settings()
        self.assertTrue(settings['telegram_task_card_acceptance']['passed'])

    def test_p7_live_acceptance_report_is_redacted_and_requires_observations(self):
        from personal_agent.telegram_task_card_acceptance import report
        generation=self.pair()
        self.service.run_one();self.service.deliver_one()
        self.service.ingest_update({'update_id':11,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'secret request'}},generation)
        self.service.acknowledge_long_work(now=time.time()+10)  # the card is the long-work acknowledgement (#510)
        job=self.store.jobs()[0];card=self.store.task_card(job['id'])
        self.service.ingest_callback({'id':'cancel','from':{'id':42},'message':{'chat':{'id':42,'type':'private'},'message_id':card['message_id']},'data':f"p7c:{job['id']}"},generation)
        approval=self.store.queue_notification(job['id'],42,generation,'approval_needed',self.service.document_fingerprint())
        self.store.update_notification(approval['id'],'approved')
        completed=self.store.queue_notification('another-job',42,generation,'completed')
        self.store.update_notification(completed['id'],'sent',123)
        self.store.enqueue('web evidence','web-evidence')
        self.service.run_one()
        result=report(self.store,web_confirmed=True,restart_confirmed=True)
        self.assertTrue(result['passed'])
        encoded=json.dumps(result)
        self.assertNotIn('secret request',encoded)
        self.assertNotIn(job['id'],encoded)
        self.assertNotIn('message_id',encoded)

    def test_start_response_does_not_default_to_command_guidance(self):
        generation=self.pair()
        self.service.run_one();self.service.deliver_one()
        self.service.ingest_update({'update_id':11,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'/start'}},generation)
        self.service.run_one()
        self.assertNotIn('/note',self.store.jobs()[0]['response'])

    def test_actual_router_model_and_free_catalog(self):
        from unittest.mock import patch
        from personal_agent.providers import ModelAdapter
        adapter=ModelAdapter(lambda *a,**kw:{'model':'test/actual:free','choices':[{'message':{'content':'hello'}}]})
        result=adapter.invoke({'provider':'compatible','endpoint':'https://openrouter.ai/api/v1','model':'openrouter/free'},'test',[])
        self.assertEqual(result.model,'test/actual:free')
        with patch('personal_agent.quickstart_service.request_json',return_value={'data':[
            {'id':'good:free','pricing':{'prompt':'0','completion':'0'},'supported_parameters':['tools','tool_choice']},
            {'id':'paid:free','pricing':{'prompt':'1','completion':'0'},'supported_parameters':['tools','tool_choice']},
            {'id':'text-only:free','pricing':{'prompt':'0','completion':'0'},'supported_parameters':['tools']},
            {'id':'missing:free'}]}):
            self.assertEqual([m['id'] for m in self.service.free_models()['models']],['good:free'])

    def test_easy_model_connections(self):
        from unittest.mock import patch
        with patch('personal_agent.quickstart_service.request_json',return_value={'key':'test-only-key'}) as transport:
            connected=self.service.connect_openrouter({'code':'test-code','verifier':'a'*64})
            self.assertTrue(connected['model_test']['ok'])
            self.assertEqual(self.store.config('model')['model'],'openrouter/free')
            self.assertEqual(self.store.secret('model_key'),'test-only-key')
            self.assertNotIn('test-only-key',str(self.service.settings()))
            self.assertEqual(transport.call_args.args[1]['code_challenge_method'],'S256')
        with patch('personal_agent.quickstart_service.request_json',return_value={'models':[{'name':'local-model','size':123},{}]}) as transport:
            self.assertEqual(self.service.local_models()['models'][0]['name'],'local-model')
            self.assertIsNone(transport.call_args.args[1])

    def test_optional_password_local_http(self):
        self.service.start()
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.service))
        thread=threading.Thread(target=server.serve_forever);thread.start()
        url='http://127.0.0.1:'+str(server.server_port)
        def post(path,body,headers=None):
            req=Request(url+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json',**(headers or {})})
            return build_opener().open(req,timeout=3)
        try:
            with self.assertRaises(HTTPError) as error:post('/api/claim',{}, {'Host':'evil.test'})
            self.assertEqual(error.exception.code,403)
            with post('/api/claim',{}) as r:self.assertEqual(r.status,200)
            self.assertTrue(self.store.config('local_access'))
            with self.assertRaises(HTTPError) as error:post('/api/local-login',{}, {'Origin':'https://evil.test'})
            self.assertEqual(error.exception.code,403)
            with post('/api/local-login',{}) as r:self.assertIn('HttpOnly',r.headers['Set-Cookie'])
        finally:
            self.service.stop.set();server.shutdown();thread.join();server.server_close()
            for worker in self.service.threads:worker.join(timeout=2)

    def test_exact_public_tunnel_host_accepts_one_time_mobile_pairing(self):
        self.store.claim(self.store.bootstrap.read_text(),'long-password-test')
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.service,['mobile.example.test'],'one-time-token'))
        thread=threading.Thread(target=server.serve_forever);thread.start()
        url='http://127.0.0.1:'+str(server.server_port)
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        client=build_opener(HTTPCookieProcessor(CookieJar()),NoRedirect())
        def request(path):
            return client.open(Request(url+path,headers={'Host':'mobile.example.test'}),timeout=3)
        try:
            with self.assertRaises(HTTPError) as paired:
                request('/?access=one-time-token')
            self.assertEqual(paired.exception.code,303)
            cookie=paired.exception.headers['Set-Cookie'].split(';',1)[0]
            with client.open(Request(url+'/api/status',headers={'Host':'mobile.example.test','Cookie':cookie}),timeout=3) as response:
                self.assertTrue(json.load(response)['authenticated'])
            with request('/?access=one-time-token') as reused:
                self.assertEqual(reused.status,200)
        finally:
            server.shutdown();thread.join();server.server_close()

    def test_http_setup_chat_csrf_and_logout(self):
        self.service.start()
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.service))
        thread=threading.Thread(target=server.serve_forever);thread.start()
        client=build_opener(HTTPCookieProcessor(CookieJar()))
        url='http://127.0.0.1:'+str(server.server_port)
        def request(path,body=None,headers=None):
            req=Request(url+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
            with client.open(req,timeout=3) as response:return json.load(response)
        try:
            self.assertFalse(request('/api/status')['authenticated'])
            with self.assertRaises(HTTPError) as error:request('/api/state')
            self.assertEqual(error.exception.code,401)
            with self.assertRaises(HTTPError) as error:request('/api/claim',{'password':'long-password-test','code':self.store.bootstrap.read_text()},{'Origin':'https://evil.test'})
            self.assertEqual(error.exception.code,403)
            request('/api/claim',{'password':'long-password-test'})
            self.assertTrue(request('/api/status')['authenticated'])
            package=self.store.root/'plugins'/'review.json';package.parent.mkdir(exist_ok=True)
            package.write_text(json.dumps({'version':1,'id':'review','enabled':True,'tools':[{'id':'review_notes','host_action':'list_notes','mode':'read_only'}],'roles':[{'id':'package_reviewer','name':'Package reviewer','instructions':'Review supplied material.','permissions':['read_only'],'tools':['review_notes']}]}))
            state=request('/api/state')
            self.assertEqual(state['settings']['packages'][1]['id'],'review')
            self.assertEqual(state['settings']['agents'][-1]['permissions'],['read_only'])
            request('/api/chat',{'message':'/note HTTP proof','request_key':'http'})
            for _ in range(30):
                state=request('/api/state')
                if state['notes']:break
                time.sleep(.1)
            self.assertEqual(state['notes'][0]['content'],'HTTP proof')
            request('/api/logout',{})
            self.assertFalse(request('/api/status')['authenticated'])
        finally:
            self.service.stop.set();server.shutdown();thread.join();server.server_close()
            for worker in self.service.threads:worker.join(timeout=2)

    def test_document_approval_http_api(self):
        self.store.claim(self.store.bootstrap.read_text(),'long-password-test')
        self.service.save_model({'provider':'compatible','endpoint':'https://example.test/v1','model':'test-model','api_key':'test-key'})
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.service))
        thread=threading.Thread(target=server.serve_forever);thread.start()
        client=build_opener(HTTPCookieProcessor(CookieJar()));url='http://127.0.0.1:'+str(server.server_port)
        def post(path,body):
            request=Request(url+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
            with client.open(request,timeout=3) as response:return json.load(response)
        try:
            post('/api/login',{'password':'long-password-test'})
            self.assertTrue(post('/api/documents/approval',{'approved':True})['approved'])
            self.assertFalse(self.service.document_boundary()['requires_approval'])
        finally:
            server.shutdown();thread.join();server.server_close()


class GmailConnectorWiringTests(unittest.TestCase):
    """The shipped deployment's half of the PA1-CONV-01 connector handoff.

    #393 built prerequisite detection, parking and exactly-once resume behind
    a tested adapter boundary and deliberately left the deployment inert:
    `configured_service` passed neither `connector_registry=` nor `gmail=`,
    and no route completed an OAuth callback, so no parked Work could ever
    resume.  PA1-INT-01 owns that boundary, so these tests are about the
    boundary - configuration, the two routes, and what an installation with
    no Gmail configuration still does - rather than about the child
    contracts, which keep their own suites.

    Every OAuth exchange here is a **fixture**.  No live Google call is made,
    and nothing below is evidence that a live Gmail connection works.
    """

    CHAT=4242
    OWNER='telegram:4242'
    GENERATION='wiring-generation'
    MAIL_REQUEST='메일에서 예산 관련 내용 찾아줘'
    CALENDAR_REQUEST='내일 오후 3시에 팀 회의 일정 잡아줘'
    CLIENT_SECRET='never-return-this-gmail-secret'

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=QuickStore(self.temp.name)
        self.sent=[]
        self.exchanges=[]
        self.gmail_calls=[]
        self.env={'AGENTOS_GMAIL_LOCAL_ONLY':'1','AGENTOS_GMAIL_CLIENT_ID':'gmail-client',
                  'AGENTOS_GMAIL_CLIENT_SECRET':self.CLIENT_SECRET,'AGENTOS_GMAIL_LOCAL_PORT':'8787',
                  'AGENTOS_GMAIL_ENCRYPTION_KEY':Fernet.generate_key().decode()}
        self.store.put('telegram',{'enabled':True,'mode':'owner-token','username':'ownerbot',
                                   'generation':self.GENERATION,'cursor':0,'user_id':self.CHAT})
        self.keys=iter(range(1000))

    # -- fixtures ---------------------------------------------------------
    def telegram(self,url,body,headers=None,timeout=60):
        if url.endswith('/sendMessage') or url.endswith('/editMessageText'):
            self.sent.append(body)
            return {'ok':True,'result':{'message_id':len(self.sent)}}
        raise AssertionError('unexpected outbound call: '+url)

    def gmail_transport(self,method,endpoint,params,headers):
        self.gmail_calls.append((method,endpoint))
        if endpoint.endswith('/messages'):
            return {'messages':[{'id':'m_1','threadId':'t_1'}]}
        return {'id':'m_1','threadId':'t_1','payload':{'headers':[
            {'name':'Subject','value':'예산 승인 안내'},
            {'name':'From','value':'Finance <finance@example.test>'},
            {'name':'Date','value':'Mon, 1 Sep 2026 10:00:00 +0000'}]}}

    def exchange(self,request):
        """The fixture token endpoint the route calls instead of Google."""
        self.exchanges.append(dict(request))
        return {'access_token':'fixture-access','refresh_token':'fixture-refresh',
                'expires_in':3600,'scope':GMAIL_READONLY_SCOPE}

    def configured(self,env=None):
        """One service built exactly the way the shipped entry point builds it."""
        service=configured_service(self.store,self.env if env is None else env)
        service.telegram_transport=self.telegram
        service.adapter=ModelAdapter(self.telegram)
        if service.gmail is not None:
            service.gmail.transport=self.gmail_transport
            service.gmail_token_exchange=self.exchange
        return service

    def serve(self,service,public_hosts=()):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service,public_hosts,'pairing-token'))
        thread=threading.Thread(target=server.serve_forever);thread.start()
        def shutdown():
            server.shutdown();thread.join();server.server_close()
        self.addCleanup(shutdown)
        return 'http://127.0.0.1:'+str(server.server_port)

    def enqueue(self,message):
        return self.store.enqueue(message,f'wiring-{next(self.keys)}',
                                  channel=f'telegram:{self.GENERATION}',chat_id=self.CHAT)

    def park(self,service):
        """Run one mail request and assert the shipped service parked it."""
        job_id=self.enqueue(self.MAIL_REQUEST)
        self.assertTrue(service.run_one())
        self.assertEqual(self.store.job(job_id)['status'],'awaiting_connection')
        return job_id

    def authorization_state(self,service):
        """Begin an authorization the way `/google-gmail` does, and read its state."""
        url=service.begin_gmail_connection()['authorization_url']
        return parse_qs(urlsplit(url).query)['state'][0]

    def login(self,base):
        self.store.claim(self.store.bootstrap.read_text(),'long-password-test')
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        client=build_opener(HTTPCookieProcessor(CookieJar()),NoRedirect())
        client.open(Request(base+'/api/login',data=json.dumps({'password':'long-password-test'}).encode(),
                            headers={'Content-Type':'application/json'}),timeout=3).read()
        return client

    def searches(self):
        """How many Gmail *list* calls happened - one per executed mail Work."""
        return len([call for call in self.gmail_calls if call[1].endswith('/messages')])

    # -- configuration ----------------------------------------------------
    def test_gmail_is_offered_only_when_every_owner_local_value_is_present(self):
        self.assertIsNone(configured_service(self.store,{}).gmail)
        without_switch={key:value for key,value in self.env.items() if key!='AGENTOS_GMAIL_LOCAL_ONLY'}
        self.assertIsNone(configured_service(self.store,without_switch).gmail)
        partial={key:value for key,value in self.env.items() if key!='AGENTOS_GMAIL_CLIENT_SECRET'}
        self.assertIsNone(configured_service(self.store,partial).gmail)
        self.assertIsNone(configured_service(self.store,partial).connector_registry)
        service=configured_service(self.store,self.env)
        self.assertEqual(service.gmail.redirect_uri,'http://localhost:8787/oauth/gmail/callback')
        self.assertIs(service.gmail.registry,service.connector_registry)
        self.assertIsNotNone(service.connector_handoff)
        # The deployment supplies its own token-exchange transport, the way it
        # supplies `drive_token_exchange`; the connector never holds the secret.
        self.assertTrue(callable(service.gmail_token_exchange))
        self.assertNotIn(self.CLIENT_SECRET,json.dumps(service.settings()))
        with self.assertRaisesRegex(ValueError,'valid TCP port'):
            configured_service(self.store,{**self.env,'AGENTOS_GMAIL_LOCAL_PORT':'not-a-port'})

    def test_owner_only_gmail_secret_file_configures_without_environment_secrets(self):
        with tempfile.TemporaryDirectory() as external:
            path=os.path.join(external,'gmail-secrets.json')
            with open(path,'w') as output:
                json.dump({'client_id':'file-client','client_secret':self.CLIENT_SECRET,
                           'encryption_key':Fernet.generate_key().decode()},output)
            os.chmod(path,0o600)
            service=configured_service(self.store,{'AGENTOS_GMAIL_LOCAL_ONLY':'1','AGENTOS_GMAIL_SECRET_FILE':path})
            self.assertEqual(service.gmail.client_id,'file-client')
            self.assertEqual(service.gmail.redirect_uri,'http://localhost:8787/oauth/gmail/callback')
            self.assertNotIn(self.CLIENT_SECRET,json.dumps(service.settings()))
            incomplete=os.path.join(external,'incomplete.json')
            with open(incomplete,'w') as output:
                json.dump({'client_id':'only-this'},output)
            os.chmod(incomplete,0o600)
            with self.assertRaisesRegex(ValueError,'every required'):
                configured_service(self.store,{'AGENTOS_GMAIL_LOCAL_ONLY':'1','AGENTOS_GMAIL_SECRET_FILE':incomplete})

    def test_drive_and_gmail_token_exchanges_keep_their_own_client_secrets(self):
        """Both exchanges are closures over `configured_service` locals.

        Reusing one variable name for both client secrets would send the
        Gmail secret to the Drive token endpoint - one external destination
        receiving another connector's secret - and no other test would
        notice, because each connector is correct in isolation.
        """
        env={**self.env,'AGENTOS_DRIVE_LOCAL_ONLY':'1','AGENTOS_DRIVE_CLIENT_ID':'drive-client',
             'AGENTOS_DRIVE_CLIENT_SECRET':'drive-only-secret','AGENTOS_DRIVE_PICKER_API_KEY':'picker-key',
             'AGENTOS_DRIVE_ENCRYPTION_KEY':Fernet.generate_key().decode(),
             'AGENTOS_DRIVE_LOCAL_PORT':'8787'}
        service=configured_service(self.store,env)
        posted=[]
        class Response:
            def __enter__(inner):return inner
            def __exit__(inner,*args):return False
            def read(inner):return b'{"access_token":"fixture"}'
        def fake_urlopen(request,timeout=None):
            posted.append(request.data.decode())
            return Response()
        with patch('personal_agent.quickstart.urlopen',fake_urlopen):
            service.drive_token_exchange({'code':'drive-code'})
            service.gmail_token_exchange({'code':'gmail-code'})
        self.assertIn('client_secret=drive-only-secret',posted[0])
        self.assertNotIn(self.CLIENT_SECRET,posted[0])
        self.assertIn('client_secret='+self.CLIENT_SECRET,posted[1])
        self.assertNotIn('drive-only-secret',posted[1])

    # -- registration is not authorization --------------------------------
    def test_registering_gmail_declares_a_capability_and_grants_nothing(self):
        service=self.configured()
        self.assertEqual([spec.connector_id for spec in service.connector_registry.definitions()],
                         [GMAIL_CONNECTOR_ID])
        # Registration wrote no owner row at all: the durable connector state
        # does not exist until an owner completes an authorization.
        self.assertIsNone(self.store.config(CONNECTOR_STATE_KEY,None))
        for owner in (self.OWNER,'local-owner'):
            status=service.connector_registry.status(owner,GMAIL_CONNECTOR_ID)
            self.assertEqual(status.state,ConnectorState.DISCONNECTED)
            self.assertEqual(status.granted_scopes,())
        with self.assertRaises(GmailError) as caught:
            service.gmail.search(self.OWNER,'예산')
        self.assertEqual(caught.exception.reason,'connection_required')
        self.assertEqual(self.gmail_calls,[])
        # The observable owner-side proof: the request is parked rather than
        # executed, so a registered connector is not a connected one.
        job_id=self.park(service)
        self.assertIn('연결이 아직 없어',self.store.job(job_id)['response'])
        self.assertEqual(self.searches(),0)

    def test_calendar_stays_unregistered_so_its_request_still_refuses_cleanly(self):
        """Records the integration finding, and holds the behaviour it protects.

        No shipped code can obtain a Calendar credential: `CalendarCreate`
        injects `_LegacyCreateProvider`, which POSTs to a relative path with
        no API root, and `GoogleCalendar` is constructed only in its own test
        module.  `AgentService` has no `calendar=` parameter either.  So both
        Calendar connectors would be permanently DISCONNECTED here.

        Registering their specs anyway is not free, because
        `CONNECTOR_BY_INTENT` maps `calendar-create` to the write connector:
        it would convert this clean refusal into Work parked for a connection
        no route can complete, which only a later request for the same
        connector would ever release.  That is why Calendar is left out.
        """
        service=self.configured()
        job_id=self.enqueue(self.CALENDAR_REQUEST)
        self.assertTrue(service.run_one())
        job=self.store.job(job_id)
        self.assertEqual(job['status'],'failed')
        self.assertIn('구성되어 있지 않습니다',job['error'])
        self.assertIsNone(self.store.config(CONNECTOR_STATE_KEY,None))

    # -- the callback route -----------------------------------------------
    def test_the_callback_route_completes_a_fixture_exchange_and_resumes_work_once(self):
        service=self.configured()
        job_id=self.park(service)
        base=self.serve(service)
        client=self.login(base)
        with self.assertRaises(HTTPError) as redirect:
            client.open(base+'/google-gmail',timeout=3)
        self.assertEqual(redirect.exception.code,303)
        state=parse_qs(urlsplit(redirect.exception.headers['Location']).query)['state'][0]
        callback=base+'/oauth/gmail/callback?code=fixture-code&state='+state
        # The browser arrives from Google without the SameSite=Strict cookie,
        # so this half is deliberately opened by an unauthenticated client.
        with build_opener().open(callback,timeout=3) as response:
            self.assertEqual(response.status,200)
            self.assertIn(b'Gmail connected',response.read())
        self.assertEqual(len(self.exchanges),1)
        self.assertEqual(self.exchanges[0]['code'],'fixture-code')
        self.assertEqual(self.exchanges[0]['redirect_uri'],'http://localhost:8787/oauth/gmail/callback')
        status=service.connector_registry.status(self.OWNER,GMAIL_CONNECTOR_ID)
        self.assertEqual(status.state,ConnectorState.CONNECTED)
        self.assertEqual(status.granted_scopes,(GMAIL_READONLY_SCOPE,))
        # The Work the owner parked from Telegram is re-queued and then runs.
        self.assertEqual(self.store.job(job_id)['status'],'queued')
        self.assertTrue(service.run_one())
        self.assertEqual(self.store.job(job_id)['status'],'succeeded')
        self.assertIn('예산 승인 안내',self.store.job(job_id)['response'])
        self.assertEqual(self.searches(),1)
        # Firing the identical callback again is the exactly-once case: it is
        # refused, and it re-queues and re-runs nothing.
        with self.assertRaises(HTTPError) as replay:
            build_opener().open(callback,timeout=3)
        self.assertEqual(replay.exception.code,400)
        self.assertEqual(self.store.job(job_id)['status'],'succeeded')
        self.assertFalse(service.run_one())
        self.assertEqual(self.searches(),1)
        self.assertEqual(len(self.exchanges),1)
        self.assertFalse(self.store.secret(CONVERSATION_RESUME_KEY))

    def test_a_denied_authorization_fails_the_parked_work_and_tells_the_owner(self):
        service=self.configured()
        job_id=self.park(service)
        state=self.authorization_state(service)
        base=self.serve(service)
        with self.assertRaises(HTTPError) as error:
            build_opener().open(base+'/oauth/gmail/callback?error=access_denied&state='+state,timeout=3)
        self.assertEqual(error.exception.code,400)
        job=self.store.job(job_id)
        self.assertEqual(job['status'],'failed')
        self.assertIn('연결이 승인되지 않아',job['error'])
        self.assertTrue(any('연결이 승인되지 않아' in str(body.get('text','')) for body in self.sent))
        self.assertEqual(service.connector_registry.status(self.OWNER,GMAIL_CONNECTOR_ID).state,
                         ConnectorState.DISCONNECTED)
        self.assertEqual(self.exchanges,[])
        # The failure is terminal: connecting afterwards must not revive it.
        with build_opener().open(base+'/oauth/gmail/callback?code=later&state='+self.authorization_state(service),
                                 timeout=3) as response:
            self.assertEqual(response.status,200)
        self.assertEqual(self.store.job(job_id)['status'],'failed')
        self.assertFalse(service.run_one())
        self.assertEqual(self.searches(),0)

    def test_a_guessed_callback_neither_connects_nor_fails_parked_work(self):
        service=self.configured()
        job_id=self.park(service)
        self.authorization_state(service)
        base=self.serve(service)
        messages=len(self.sent)
        for query in ('?code=stolen&state=not-the-issued-state',
                      '?error=access_denied&state=not-the-issued-state',
                      '?code=stolen'):
            with self.assertRaises(HTTPError) as error:
                build_opener().open(base+'/oauth/gmail/callback'+query,timeout=3)
            self.assertEqual(error.exception.code,400)
            # Anyone who can reach the loopback port can send these, so they
            # must not be able to fail the owner's parked request either.
            self.assertEqual(self.store.job(job_id)['status'],'awaiting_connection')
        self.assertEqual(service.connector_registry.status(self.OWNER,GMAIL_CONNECTOR_ID).state,
                         ConnectorState.DISCONNECTED)
        self.assertEqual(self.exchanges,[])
        self.assertEqual(len(self.sent),messages)

    def test_the_callback_is_refused_on_a_public_tunnel_host(self):
        service=self.configured()
        job_id=self.park(service)
        state=self.authorization_state(service)
        base=self.serve(service,['mobile.example.test'])
        with self.assertRaises(HTTPError) as error:
            build_opener().open(Request(base+'/oauth/gmail/callback?code=fixture-code&state='+state,
                                        headers={'Host':'mobile.example.test'}),timeout=3)
        self.assertEqual(error.exception.code,400)
        self.assertEqual(self.store.job(job_id)['status'],'awaiting_connection')
        self.assertEqual(self.exchanges,[])
        # Refusing the tunnel host did not consume the owner's pending state:
        # the same callback still completes from loopback.
        with build_opener().open(base+'/oauth/gmail/callback?code=fixture-code&state='+state,timeout=3) as response:
            self.assertEqual(response.status,200)
        self.assertEqual(self.store.job(job_id)['status'],'queued')

    def test_the_authorization_start_route_requires_the_owner_session(self):
        service=self.configured()
        base=self.serve(service)
        with self.assertRaises(HTTPError) as error:
            build_opener().open(base+'/google-gmail',timeout=3)
        self.assertEqual(error.exception.code,401)
        client=self.login(base)
        with self.assertRaises(HTTPError) as redirect:
            client.open(base+'/google-gmail',timeout=3)
        self.assertEqual(redirect.exception.code,303)
        location=redirect.exception.headers['Location']
        self.assertTrue(location.startswith('https://accounts.google.com/'))
        query=parse_qs(urlsplit(location).query)
        self.assertEqual(query['scope'],[GMAIL_READONLY_SCOPE])
        self.assertEqual(query['redirect_uri'],['http://localhost:8787/oauth/gmail/callback'])
        self.assertEqual(query['include_granted_scopes'],['false'])
        self.assertNotIn(self.CLIENT_SECRET,location)
        # Issuing an authorization URL is not a connection and not a Grant.
        self.assertEqual(service.connector_registry.status(self.OWNER,GMAIL_CONNECTOR_ID).state,
                         ConnectorState.DISCONNECTED)

    # -- the unconfigured installation ------------------------------------
    def test_an_installation_without_gmail_configuration_is_unchanged(self):
        service=configured_service(self.store,{})
        service.telegram_transport=self.telegram
        self.assertIsNone(service.gmail)
        self.assertIsNone(service.connector_registry)
        self.assertIsNone(service.connector_handoff)
        self.assertIsNone(service.gmail_token_exchange)
        job_id=self.enqueue(self.MAIL_REQUEST)
        self.assertTrue(service.run_one())
        job=self.store.job(job_id)
        self.assertEqual(job['status'],'failed')
        self.assertIn('구성되어 있지 않습니다',job['error'])
        base=self.serve(service)
        for path in ('/oauth/gmail/callback?code=c&state=s','/google-gmail'):
            with self.assertRaises(HTTPError) as error:
                build_opener().open(base+path,timeout=3)
            self.assertIn(error.exception.code,(400,401))
        # Nothing about connectors was created by the request or the routes.
        self.assertIsNone(self.store.config(CONNECTOR_STATE_KEY,None))
        self.assertIsNone(self.store.config(PENDING_WORK_KEY,None))
        self.assertFalse(self.store.secret(CONVERSATION_RESUME_KEY))


if __name__=='__main__':unittest.main()

"""WEB-ADMIN-01 governance and interaction regressions."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import parse_qs, urlsplit

from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore

ROOT = Path(__file__).resolve().parents[1]


class WebManagementReadinessTests(unittest.TestCase):
    def test_mirrored_contract_is_ready_but_not_selected_or_completed(self):
        source = (ROOT / 'delivery-plan.yaml').read_bytes()
        self.assertEqual(source, (ROOT / 'src/personal_agent/delivery-plan.yaml').read_bytes())
        plan = json.loads(source)
        entries = [item for item in plan['iterations'] if item['id'] == 'WEB-ADMIN-01']
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry['issue'], 382)
        self.assertEqual(entry['activation_status'], 'parent-controlled')
        self.assertEqual(entry['contract'], 'web-management-contract.en.md')
        self.assertEqual(set(entry['depends_on']), {'GOV-USE-01', 'DOGFOOD-01', 'PA1-FDN-01'})
        self.assertEqual(entry['program'], 'EPIC-PA1')
        self.assertEqual(entry['parallel_group'], 'pa1-wave-1')
        completed = plan['history']['documented_completed_iterations']
        self.assertTrue({'GOV-USE-01', 'DOGFOOD-01'}.issubset(completed))
        self.assertNotIn('PA1-FDN-01', completed)
        self.assertNotIn('WEB-ADMIN-01', completed)
        self.assertNotEqual(plan['next_goal']['status'], 'active')
        self.assertEqual(plan['next_goal']['id'], 'EPIC-PA1')
        self.assertNotEqual(plan['next_goal']['id'], 'WEB-ADMIN-01')
        self.assertTrue((ROOT / 'docs' / entry['contract']).is_file())

    def test_historical_top02_validation_is_not_weakened(self):
        plan = json.loads((ROOT / 'delivery-plan.yaml').read_text())
        entry = next(item for item in plan['iterations'] if item['id'] == 'TOP-02')
        self.assertEqual(entry['tests'], [
            'python3 -m pytest -q tests',
            'python3 -m unittest discover -s tests -q',
        ])

    def test_prompt_checks_existing_readiness_before_activation(self):
        prompt = (ROOT / 'docs/design/utility-v1/CODEX_PROMPT.txt').read_text()
        self.assertIn('READINESS AND ACTIVATION GATE', prompt)
        self.assertIn('dependency-satisfied goal-ready record in both', prompt)
        self.assertIn('Do not infer activation from this document', prompt)
        self.assertIn('Do not continue into W1-W3 in that same preparation invocation', prompt)
        self.assertIn('Do not execute #381 or other successor goals', prompt)

    def test_management_is_the_only_default_product_surface(self):
        html = (ROOT / 'src/personal_agent/web/index.html').read_text()
        self.assertEqual(html.count('data-view="tasks"'), 1)
        self.assertEqual(html.count('data-view="records"'), 1)
        self.assertEqual(html.count('data-view="settings"'), 1)
        self.assertNotIn('id="chat-form"', html)
        self.assertNotIn('id="messages"', html)
        self.assertNotIn('대화</button>', html)
        self.assertIn('data-settings="ai"', html)
        self.assertIn('data-settings="files"', html)
        self.assertIn('data-settings="external"', html)
        self.assertIn('data-settings="privacy"', html)

    def test_source_derived_task_record_and_model_regressions(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node is needed for JavaScript behavior checks')
        script = r"""
const assert=require('node:assert/strict');
const ui=require(process.argv[1]);
(async()=>{
const old={tasks:[{id:'one',status:'running',status_kind:'active',events:[{id:1}],response:null},{id:'two',events:[{id:2}]}]};
const fresh={tasks:[{id:'one',status:'succeeded',status_kind:'finished',result_available:true},{id:'two',status:'failed'}]};
const merged=ui.mergeTaskProgress(fresh,old,[{id:'one',response:'fresh text',message:'owner request',channel:'telegram:fixture'}]);
assert.equal(merged.tasks[0].status,'succeeded');
assert.equal(merged.tasks[0].response,'fresh text');
assert.deepEqual(merged.tasks[0].events,[{id:1}]);
assert.equal(merged.tasks[1].id,'two');
const incoherent=ui.mergeTaskProgress({tasks:[{id:'race',status:'running',status_kind:'active'}]},null,[{id:'race',status:'succeeded',response:'too early'}]).tasks[0];
assert.equal(incoherent.response,undefined);
assert.deepEqual([ui.statusText(incoherent),ui.taskOutcome(incoherent).title],['진행 중','진행 중']);
const coherent=ui.mergeTaskProgress({tasks:[{id:'done',status:'succeeded',status_kind:'finished'}]},null,[{id:'done',status:'succeeded',response:'terminal result',channel:'telegram:fixture'}]).tasks[0];
assert.deepEqual([ui.statusText(coherent),ui.taskOutcome(coherent).title,ui.requestSource(coherent)],['완료','결과','Telegram']);
const partial=ui.mergeTaskProgress({tasks:[{id:'partial',status:'partial',status_kind:'finished',error:'second half unavailable'}]},null,[{id:'partial',response:'first half'}]).tasks[0];
assert.equal(partial.error,'second half unavailable');
assert.match(ui.taskOutcome(partial).text,/second half unavailable/);
assert.deepEqual(ui.taskOutcome({status:'cancelled'}),{title:'취소됨',text:'이 작업은 취소되어 더 이상 실행되지 않습니다.',kind:'attention'});
assert(ui.isDiagnosticTask({title:'/start abc'}));
assert(!ui.isDiagnosticTask({title:'compare flights'}));
const proofA=ui.modelDraftFingerprint({provider:'openai',endpoint:'https://api.example/v1/',model:'m',credential_revision:1});
const proofB=ui.modelDraftFingerprint({provider:'openai',endpoint:'https://api.example/v1',model:'m',credential_revision:2});
assert.notEqual(proofA,proofB);
const records=ui.recordItems({memories:[{id:'n',content:'note'},{id:'m',memory_key:'pref',content:'memory'}],context:[{id:'c',source_kind:'text'}],results:[{id:'r',content:'artifact'}]});
assert.deepEqual(records.map(x=>[x.id,x.type,x.deleteKind]),[['n','saved','memories'],['m','memory','memories'],['c','temporary',undefined],['r','artifact','results']]);
const long='x'.repeat(300)+'needle-after-truncation';
const space={memories:[{id:'exact',memory_key:'durable-key',content:'exact durable memory'},{id:'long',content:long}]};
assert.deepEqual(ui.filterLocalRecords(space,'durable-key','all').map(x=>x.id),['exact']);
assert.deepEqual(ui.filterLocalRecords(space,'durable-key','saved').map(x=>x.id),['exact']);
assert.deepEqual(ui.filterLocalRecords(space,'needle-after-truncation','all').map(x=>x.id),['long']);
assert.deepEqual(ui.workspaceSaveCandidates([{id:'unassigned',status:'succeeded'},{id:'here',workspace_id:'w',status:'partial'},{id:'elsewhere',workspace_id:'other',status:'succeeded'},{id:'queued',status:'queued'}],'w',[{job_id:'here'}]).map(x=>x.id),['unassigned']);
assert.deepEqual(ui.modelPresetDraft({provider:'compatible',endpoint:'https://openrouter.ai/api/v1/',model:'fixture/free'}),{provider:'compatible',endpoint:'https://openrouter.ai/api/v1',model:'fixture/free',api_key:''});
assert.deepEqual(ui.capabilityActions({id:'google-drive-read',state:'enabled'}),['pause','disconnect']);
assert.deepEqual(ui.capabilityActions({id:'google-drive-read',state:'paused'}),['resume']);
assert.deepEqual(ui.capabilityActions({id:'google-drive-read',state:'disconnected'}),[]);
assert.deepEqual(ui.capabilityActions({id:'isolated-runtime-placeholder',state:'enabled'}),[]);
assert.match(ui.contextSharingWarning({sharing_requires_policy_and_per_request_approval:true}),/각 Telegram 작업마다/);
assert.equal(ui.settingsFeedbackId('subscription'),'subscription-feedback');
const disclosureStore=new Map(),nested={open:true},technical={open:true,querySelector:selector=>selector==='details'?nested:null};
ui.rememberTaskDisclosures(disclosureStore,'task',technical);technical.open=false;nested.open=false;ui.restoreTaskDisclosures(disclosureStore,'task',technical,nested);assert.equal(technical.open,true);assert.equal(nested.open,true);
assert.equal(ui.isOpenRouterCompletion({origin:'http://owner.local',data:{type:'agentos-openrouter-connected'}},'http://owner.local'),true);
assert.equal(ui.isOpenRouterCompletion({origin:'http://attacker.local',data:{type:'agentos-openrouter-connected'}},'http://owner.local'),false);
assert.equal(ui.shouldRenderWorkspaceDetail('second','first',1,2),false);
assert.equal(ui.shouldRenderWorkspaceDetail('second','second',2,2),true);
assert.deepEqual(ui.workspaceResultSummary({results:[{id:'one'},{id:'two'}]}),{count:2,capped:false,label:'2개 완료 결과'});
assert.deepEqual(ui.workspaceResultSummary({results:Array.from({length:30},(_,id)=>({id}))}),{count:30,capped:true,label:'30개 이상 완료 결과'});
const removed=[];assert.equal(ui.clearMobileDetailWhenEmpty({classList:{remove:value=>removed.push(value)}},[]),true);assert.deepEqual(removed,['mobile-detail']);
let detailLoads=0;
await ui.refreshSelectedTaskDetail({id:'one',events_count:1,observed_at:10,status:'running',events:[{id:1}]},{id:'one',events_count:2,observed_at:11,status:'running'},async id=>{detailLoads++;return {id,events:[{id:1},{id:2}]};});
assert.equal(detailLoads,1);
await ui.refreshSelectedTaskDetail({id:'one',events_count:2,observed_at:11,status:'running',events:[{id:1},{id:2}]},{id:'one',events_count:2,observed_at:11,status:'running'},async()=>{detailLoads++;});
assert.equal(detailLoads,1);
const guard=ui.createModelDraftGuard();
let resolveOld,testRequests=0,saveRequests=0,current={provider:'openai',endpoint:'https://example.test/v1',model:'first',api_key:'old'};
const pending=guard.test(current,()=>{testRequests++;return new Promise(resolve=>{resolveOld=resolve;});},()=>current);
current={...current,api_key:'new'};guard.invalidate();resolveOld({ok:true});
assert.deepEqual(await pending,{accepted:false,stale:true,result:{ok:true}});
assert.equal(guard.canApply(current),false);
const verified=await guard.test(current,async()=>{testRequests++;return {ok:true};},()=>current);
assert.equal(verified.accepted,true);assert.equal(guard.canApply(current),true);
assert.equal(await guard.apply(current,async payload=>{saveRequests++;assert.equal('credential_revision' in payload,false);}),true);
assert.equal(testRequests,2);assert.equal(saveRequests,1);
console.log(JSON.stringify({checks:32}));
})().catch(error=>{console.error(error);process.exit(1);});
"""
        result = subprocess.run(
            [node, '-e', script, str(ROOT / 'src/personal_agent/web/app.js')],
            check=True, capture_output=True, text=True, timeout=20)
        self.assertEqual(json.loads(result.stdout)['checks'], 32)

    def test_model_apply_has_one_explicit_test_and_credential_revision(self):
        app = (ROOT / 'src/personal_agent/web/app.js').read_text()
        apply_body = app[app.index("$('model-form').onsubmit"):app.index('function renderExecutionConnection')]
        self.assertNotIn("api('/api/model/test'", apply_body)
        self.assertIn('credential_revision', app)
        self.assertIn('modelGuard.test', app)
        self.assertIn('modelGuard.apply', app)
        self.assertIn("method||(body===undefined?'GET':'POST')", app)
        self.assertIn("'/api/personal-space/'+item.deleteKind", app)
        self.assertEqual(app.count("invalidateModelDraft('연결 결과가 바뀌었습니다. 적용 전에 다시 테스트하세요.')"), 2)

    def test_project_detail_and_result_save_actions_remain_available(self):
        app = (ROOT / 'src/personal_agent/web/app.js').read_text()
        html = (ROOT / 'src/personal_agent/web/index.html').read_text()
        self.assertIn('id="workspace-detail"', html)
        self.assertIn("api('/api/workspaces/'+encodeURIComponent(id))", app)
        self.assertIn("'/save-result'", app)
        self.assertIn('workspaceSaveCandidates', app)
        self.assertIn('shouldRenderWorkspaceDetail(selectedWorkspaceId,workspaceId,request,workspaceDetailSequence)', app)
        self.assertIn('loadWorkspaceResultSummaries(home.workspaces)', app)
        self.assertNotIn('workspaceResultCount(lastSpace', app)

    def test_oauth_refresh_and_file_drafts_have_independent_stale_guards(self):
        app = (ROOT / 'src/personal_agent/web/app.js').read_text()
        self.assertIn('if(refreshing){refreshQueued=true;return;}', app)
        self.assertIn('requestedModelRevision===modelLoadRevision', app)
        self.assertIn('if(refreshQueued){refreshQueued=false;void refresh();}', app)
        self.assertGreaterEqual(app.count('invalidateModelLoad()'), 4)
        hydration = app[app.index('if(!modelLoaded){if(requestedModelRevision'):app.index("$('task-refresh-state').textContent='방금 확인'")]
        self.assertNotIn("$('root-paths').value", hydration.split('if(!fileSettingsLoaded)')[0])
        self.assertIn("$('root-paths').value", hydration.split('if(!fileSettingsLoaded)')[1])

    def test_capability_lifecycle_uses_existing_confirmed_settings_route(self):
        app = (ROOT / 'src/personal_agent/web/app.js').read_text()
        html = (ROOT / 'src/personal_agent/web/index.html').read_text()
        self.assertIn('id="capability-controls"', html)
        self.assertIn("api('/api/settings/request',{operation:'draft'", app)
        self.assertIn("api('/api/settings/request',{operation:'confirm'", app)
        self.assertIn("api('/api/settings/request',{operation:'cancel'", app)
        self.assertIn("$('brand-home').onclick", app)
        self.assertIn("setError('subscription-feedback',error)", app)
        self.assertIn('각 Telegram 작업마다 공유 승인이 필요합니다.', app)

    def test_browser_fixture_and_exact_runner_transcript_are_checked_in(self):
        fixture = ROOT / 'tests/web_management_browser_fixture.py'
        transcript = (ROOT / 'tests/fixtures/web_management_browser_transcript.txt').read_text()
        subprocess.run(
            [shutil.which('python3') or 'python3', '-m', 'py_compile', str(fixture)],
            check=True, capture_output=True, text=True, timeout=20)
        self.assertIn('python3 tests/web_management_browser_fixture.py --port 18782', transcript)
        self.assertIn('bash "$PWCLI" resize 390 844', transcript)
        self.assertIn('"task_polls": 4', transcript)
        self.assertIn('"focused":true,"value":"durable-key","start":8', transcript)
        self.assertIn('snapshot still showed 삭제 확인', transcript)
        self.assertIn('go-back', transcript)
        self.assertIn('no POST, PUT', transcript)
        self.assertIn('"method":"DELETE","path":"/api/observer-probe"', transcript)
        self.assertIn('positive control above proves', transcript)
        self.assertIn('test_requests=2', transcript)
        self.assertIn('{"technical":true,"original":true,"events":2}', transcript)
        self.assertIn('{"detailClass":"panel detail","empty":true}', transcript)
        self.assertIn('"popupClosed":true,"key":"","provider":"compatible"', transcript)
        self.assertIn('"beforeOAuthApplyDisabled":false', transcript)
        self.assertIn('"afterOAuthApplyDisabled":true', transcript)
        self.assertIn('다른 프로젝트 · 30개 이상 완료 결과', transcript)
        self.assertIn('{"selected":["다른 프로젝트"],"detail":"다른 프로젝트"', transcript)
        self.assertIn('"root":"/tmp/unsaved-root","reference":"/tmp/unsaved-reference"', transcript)
        self.assertIn('does not run AgentService', transcript)

    def test_browser_fixture_observer_captures_every_mutating_http_verb(self):
        process = subprocess.Popen(
            [shutil.which('python3') or 'python3', str(ROOT / 'tests/web_management_browser_fixture.py'), '--port', '0'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            line = process.stdout.readline().strip()
            base = line.removeprefix('fixture-only ')
            self.assertTrue(base.startswith('http://127.0.0.1:'))
            reset = urlrequest.Request(base + '/control/reset-observation', data=b'{}', method='POST', headers={'Content-Type': 'application/json'})
            with urlrequest.urlopen(reset, timeout=5) as response:
                self.assertEqual(response.status, 200)
            for method in ('PUT', 'PATCH', 'DELETE'):
                probe = urlrequest.Request(base + '/api/observer-probe', data=b'{}', method=method, headers={'Content-Type': 'application/json'})
                with self.assertRaises(urlerror.HTTPError) as caught:
                    urlrequest.urlopen(probe, timeout=5)
                self.assertEqual(caught.exception.code, 405)
            with urlrequest.urlopen(base + '/control/requests', timeout=5) as response:
                observed = json.load(response)['requests']
            self.assertEqual(observed, [
                {'method': 'PUT', 'path': '/api/observer-probe'},
                {'method': 'PATCH', 'path': '/api/observer-probe'},
                {'method': 'DELETE', 'path': '/api/observer-probe'},
            ])
        finally:
            process.terminate()
            process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()

    def test_synthetic_telegram_request_reaches_web_read_models_without_web_chat(self):
        calls = []

        def telegram_fixture(url, body, headers=None, timeout=60):
            calls.append((url, body))
            if url.endswith('/getMe'):
                return {'ok': True, 'result': {'username': 'fixture_bot'}}
            if url.endswith('/getWebhookInfo'):
                return {'ok': True, 'result': {'url': ''}}
            if url.endswith('/sendMessage'):
                return {'ok': True, 'result': {'message_id': len(calls)}}
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as folder:
            store = QuickStore(folder)
            service = AgentService(store, telegram_transport=telegram_fixture)
            link = service.connect_telegram({'token': '123456:FIXTURE_TOKEN'})['url']
            code = parse_qs(urlsplit(link).query)['start'][0]
            generation = store.config('telegram')['generation']
            service.ingest_update({'update_id': 1, 'message': {
                'from': {'id': 42}, 'chat': {'id': 42, 'type': 'private'},
                'text': '/start ' + code}}, generation)
            service.ingest_update({'update_id': 2, 'message': {
                'from': {'id': 42}, 'chat': {'id': 42, 'type': 'private'},
                'text': '/note browser-visible'}}, generation)
            self.assertTrue(service.run_one())
            service.deliver_one()
            self.assertTrue(service.run_one())
            service.deliver_one()
            job = store.jobs()[0]
            self.assertTrue(job['channel'].startswith('telegram:'))
            self.assertIn('메모를 저장했습니다', job['response'])
            self.assertEqual(job['delivery'], 'sent')
            self.assertEqual(store.notes()[0]['content'], 'browser-visible')
            selected = service.task_progress(job['id'])['selected']
            self.assertEqual(selected['id'], job['id'])
            self.assertTrue(selected['result_available'])
            html = (ROOT / 'src/personal_agent/web/index.html').read_text()
            self.assertNotIn('id="chat-form"', html)


if __name__ == '__main__':
    unittest.main()

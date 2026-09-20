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
console.log(JSON.stringify({checks:15}));
})().catch(error=>{console.error(error);process.exit(1);});
"""
        result = subprocess.run(
            [node, '-e', script, str(ROOT / 'src/personal_agent/web/app.js')],
            check=True, capture_output=True, text=True, timeout=20)
        self.assertEqual(json.loads(result.stdout)['checks'], 15)

    def test_model_apply_has_one_explicit_test_and_credential_revision(self):
        app = (ROOT / 'src/personal_agent/web/app.js').read_text()
        apply_body = app[app.index("$('model-form').onsubmit"):app.index('function renderExecutionConnection')]
        self.assertNotIn("api('/api/model/test'", apply_body)
        self.assertIn('credential_revision', app)
        self.assertIn('modelGuard.test', app)
        self.assertIn('modelGuard.apply', app)
        self.assertIn("method||(body===undefined?'GET':'POST')", app)
        self.assertIn("'/api/personal-space/'+item.deleteKind", app)

    def test_project_detail_and_result_save_actions_remain_available(self):
        app = (ROOT / 'src/personal_agent/web/app.js').read_text()
        html = (ROOT / 'src/personal_agent/web/index.html').read_text()
        self.assertIn('id="workspace-detail"', html)
        self.assertIn("api('/api/workspaces/'+encodeURIComponent(id))", app)
        self.assertIn("'/save-result'", app)

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

"""WEB-ADMIN-01 governance and interaction regressions."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
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
const old={tasks:[{id:'one',status:'running',status_kind:'active',events:[{id:1}],response:null},{id:'two',events:[{id:2}]}]};
const fresh={tasks:[{id:'one',status:'succeeded',status_kind:'finished',result_available:true},{id:'two',status:'failed'}]};
const merged=ui.mergeTaskProgress(fresh,old,[{id:'one',response:'fresh text',message:'owner request',channel:'telegram:fixture'}]);
assert.equal(merged.tasks[0].status,'succeeded');
assert.equal(merged.tasks[0].response,'fresh text');
assert.deepEqual(merged.tasks[0].events,[{id:1}]);
assert.equal(merged.tasks[1].id,'two');
assert(ui.isDiagnosticTask({title:'/start abc'}));
assert(!ui.isDiagnosticTask({title:'compare flights'}));
const proofA=ui.modelDraftFingerprint({provider:'openai',endpoint:'https://api.example/v1/',model:'m',credential_revision:1});
const proofB=ui.modelDraftFingerprint({provider:'openai',endpoint:'https://api.example/v1',model:'m',credential_revision:2});
assert.notEqual(proofA,proofB);
const records=ui.recordItems({memories:[{id:'n',content:'note'},{id:'m',memory_key:'pref',content:'memory'}],context:[{id:'c',source_kind:'text'}],results:[{id:'r',content:'artifact'}]});
assert.deepEqual(records.map(x=>[x.id,x.type,x.deleteKind]),[['n','saved','memories'],['m','memory','memories'],['c','temporary',undefined],['r','artifact','results']]);
console.log(JSON.stringify({checks:6}));
"""
        result = subprocess.run(
            [node, '-e', script, str(ROOT / 'src/personal_agent/web/app.js')],
            check=True, capture_output=True, text=True, timeout=20)
        self.assertEqual(json.loads(result.stdout)['checks'], 6)

    def test_model_apply_has_one_explicit_test_and_credential_revision(self):
        app = (ROOT / 'src/personal_agent/web/app.js').read_text()
        apply_body = app[app.index("$('model-form').onsubmit"):app.index('function renderExecutionConnection')]
        self.assertNotIn("api('/api/model/test'", apply_body)
        self.assertIn('credential_revision', app)
        self.assertIn('sequence!==testSequence', app)
        self.assertIn('proof!==modelDraftFingerprint(modelDraft())', app)
        self.assertIn("method||(body===undefined?'GET':'POST')", app)
        self.assertIn("'/api/personal-space/'+item.deleteKind", app)

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

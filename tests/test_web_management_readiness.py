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

from delivery_state_invariants import (
    assert_declared_goal_shape,
    assert_no_unauthorised_execution_authority,
)
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore

ROOT = Path(__file__).resolve().parents[1]


class WebManagementReadinessTests(unittest.TestCase):
    def test_mirrored_contract_is_a_parent_controlled_substep_that_never_self_selects(self):
        source = (ROOT / 'delivery-plan.yaml').read_bytes()
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
        # The original form asserted PA1-FDN-01 and WEB-ADMIN-01 were *not*
        # documented complete. That was a snapshot of the delivery order, not
        # an invariant, and PA1-INT-01's tracker reconciliation makes it false.
        # The rule underneath it survives and is stronger: a substep may not be
        # recorded complete before the dependencies it declares.
        # Applied to every declared dependency, not just this entry's own, so
        # the PA1-FDN-01 half of the pair this replaced is covered too rather
        # than silently dropped.
        for name in sorted({'WEB-ADMIN-01', *entry['depends_on']}):
            if name not in completed:
                continue
            declared = next((item.get('depends_on', []) for item in plan['iterations']
                             if item['id'] == name), [])
            missing = [dep for dep in declared if dep not in completed]
            self.assertEqual(missing, [],
                             f'{name} is documented complete before {missing}')
        self.assertNotEqual(plan['next_goal']['status'], 'active')
        # WEB-ADMIN-01 is a parent-controlled substep and can never be the
        # declared top-level goal, whichever program currently holds
        # authority -- and it is not a program, so it cannot become one.
        self.assertNotEqual(plan['next_goal']['id'], 'WEB-ADMIN-01')
        self.assertNotIn('WEB-ADMIN-01', plan['programs'])
        # A declared goal is always a program. After closeout there is no
        # declared goal, which has to be a fully quiesced state rather than
        # simply an unchecked one.
        shape = assert_declared_goal_shape(self, plan)
        if shape == 'goal-ready':
            self.assertIn(plan['next_goal']['id'], plan['programs'])
        else:
            self.assertIsNone(plan['next_goal']['id'])
        # `EPIC-PA1 is owner-paused` used to stand in the terminal branch.
        # It was a cast pin and it only ran in one shape; the rule behind it
        # -- a closeout never hands authority to a successor -- is asserted
        # for every program in both shapes instead.
        assert_no_unauthorised_execution_authority(self, plan)
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
        # The J6 MemoryCandidate control is a management control inside the
        # existing records view: it adds no top-level view and no second
        # conversation surface.
        self.assertEqual(html.count('id="memory-candidates"'), 1)
        self.assertGreater(html.index('id="memory-candidates"'), html.index('id="view-records"'))
        self.assertLess(html.index('id="memory-candidates"'), html.index('id="view-settings"'))

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
const projected=ui.recordItems({items:[{id:'old',type:'note',label:'메모',content:'authoritative',deleteKind:'memories'}]});
assert.deepEqual(projected,[{id:'old',type:'note',label:'메모',content:'authoritative',deleteKind:'memories'}]);
assert.equal(ui.recordPageMatches({query:'durable-key',filter:'all'},' durable-key ','all'),true);
assert.equal(ui.recordPageMatches({query:'durable-key',filter:'all'},'other','all'),false);
const long='x'.repeat(300)+'needle-after-truncation';
const space={memories:[{id:'exact',memory_key:'durable-key',content:'exact durable memory'},{id:'long',content:long}]};
assert.deepEqual(ui.filterLocalRecords(space,'durable-key','all').map(x=>x.id),['exact']);
assert.deepEqual(ui.filterLocalRecords(space,'durable-key','saved').map(x=>x.id),['exact']);
assert.deepEqual(ui.filterLocalRecords(space,'needle-after-truncation','all').map(x=>x.id),['long']);
assert.deepEqual(ui.workspaceSaveCandidates([{id:'unassigned',status:'succeeded'},{id:'here',workspace_id:'w',status:'partial'},{id:'elsewhere',workspace_id:'other',status:'succeeded'},{id:'queued',status:'queued'}],'w',['here']).map(x=>x.id),['unassigned']);
assert.deepEqual(ui.modelPresetDraft({provider:'compatible',endpoint:'https://openrouter.ai/api/v1/',model:'fixture/free'}),{provider:'compatible',endpoint:'https://openrouter.ai/api/v1',model:'fixture/free',api_key:''});
assert.deepEqual(ui.capabilityActions({id:'google-drive-read',state:'enabled'}),['pause','disconnect']);
assert.deepEqual(ui.capabilityActions({id:'google-drive-read',state:'paused'}),['resume']);
assert.deepEqual(ui.capabilityActions({id:'google-drive-read',state:'disconnected'}),[]);
assert.deepEqual(ui.capabilityActions({id:'isolated-runtime-placeholder',state:'enabled'}),[]);
assert.match(ui.contextSharingWarning({sharing_requires_policy_and_per_request_approval:true}),/각 Telegram 작업마다/);
assert.equal(ui.settingsFeedbackId('subscription'),'active-ai-feedback');
assert.equal(ui.routeText({kind:'subscription',engine:'codex',status:'failed'}),'Codex 구독 CLI · 실행했지만 실패');
assert.equal(ui.routeText({kind:'direct-api',model:'gpt-4o-mini',status:'succeeded'}),'직접 API · gpt-4o-mini');
assert.match(ui.routeText(null),/기록 없음/);
assert.equal(ui.routeText({kind:'subscription',engine:'codex',status:'interrupted'}),'Codex 구독 CLI · 중단됨');
assert.equal(ui.routeText({kind:'direct-api',model:'m',status:'failed'}),'직접 API · m · 실행했지만 실패');
const disclosureStore=new Map(),nested={open:true},technical={open:true,querySelector:selector=>selector==='details'?nested:null};
ui.rememberTaskDisclosures(disclosureStore,'task',technical);technical.open=false;nested.open=false;ui.restoreTaskDisclosures(disclosureStore,'task',technical,nested);assert.equal(technical.open,true);assert.equal(nested.open,true);
assert.equal(ui.isOpenRouterCompletion({origin:'http://owner.local',data:{type:'agentos-openrouter-connected'}},'http://owner.local'),true);
assert.equal(ui.isOpenRouterCompletion({origin:'http://attacker.local',data:{type:'agentos-openrouter-connected'}},'http://owner.local'),false);
const openRouterFlow={verifier:'v'.repeat(64),state:'12345678-1234-1234-1234-123456789abc',url:'https://openrouter.ai/auth?callback_url=x',expires:2000};
assert.deepEqual(ui.parseOpenRouterFlow(JSON.stringify(openRouterFlow),1000),openRouterFlow);
assert.equal(ui.parseOpenRouterFlow(JSON.stringify({...openRouterFlow,expires:999}),1000),null);
assert.equal(ui.parseOpenRouterFlow(JSON.stringify({...openRouterFlow,url:'https://attacker.example/auth'}),1000),null);
assert.equal(ui.parseOpenRouterFlow('{malformed',1000),null);
assert.equal(ui.shouldRenderWorkspaceDetail('second','first',1,2),false);
assert.equal(ui.shouldRenderWorkspaceDetail('second','second',2,2),true);
assert.equal(ui.shouldInvalidateWorkspaceDetailForDeletion({deleteKind:'memories'},'second'),false);
assert.equal(ui.shouldInvalidateWorkspaceDetailForDeletion({deleteKind:'results',workspace_id:'first'},'second'),false);
assert.equal(ui.shouldInvalidateWorkspaceDetailForDeletion({deleteKind:'results',workspace_id:'second'},'second'),true);
assert.deepEqual(ui.workspaceResultSummary({result_count:42,results:[{id:'one'},{id:'two'}]}),{count:42,label:'42개 완료 결과'});
assert.deepEqual(ui.workspaceResultSummary({results:[{id:'one'},{id:'two'}]}),{count:2,label:'2개 완료 결과'});
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
const verified=await guard.test(current,async()=>{testRequests++;return {ok:true,test_proof:'p'.repeat(43)};},()=>current);
assert.equal(verified.accepted,true);assert.equal(guard.canApply(current),true);
assert.equal(await guard.apply(current,async payload=>{saveRequests++;assert.equal('credential_revision' in payload,false);assert.equal(payload.test_proof,'p'.repeat(43));}),true);
const missingProof=await guard.test(current,async()=>({ok:true}),()=>current);
assert.equal(missingProof.accepted,false);assert.equal(guard.canApply(current),false);
assert.equal(testRequests,2);assert.equal(saveRequests,1);
console.log(JSON.stringify({checks:40}));
})().catch(error=>{console.error(error);process.exit(1);});
"""
        result = subprocess.run(
            [node, '-e', script, str(ROOT / 'src/personal_agent/web/app.js')],
            check=True, capture_output=True, text=True, timeout=20)
        self.assertEqual(json.loads(result.stdout)['checks'], 40)

    def test_model_apply_has_one_explicit_test_and_credential_revision(self):
        app = (ROOT / 'src/personal_agent/web/app.js').read_text()
        apply_body = app[app.index("$('model-form').onsubmit"):app.index('function renderExecutionConnection')]
        self.assertNotIn("api('/api/model/test'", apply_body)
        self.assertIn('credential_revision', app)
        self.assertIn('modelGuard.test', app)
        self.assertIn('modelGuard.apply', app)
        self.assertIn("method||(body===undefined?'GET':'POST')", app)
        self.assertIn("'/api/personal-space/'+item.deleteKind", app)
        deletion = app[app.index("if(item.deleteKind)"):app.index("$('record-search').onsubmit")]
        self.assertIn('recordLoadSequence++', deletion)
        self.assertNotIn("api('/api/personal-space')", deletion)
        self.assertLess(deletion.index('lastRecords.items=lastRecords.items.filter'),
                        deletion.index('await loadRecords({refreshLoaded:true,throwOnError:true})'))
        self.assertIn('recordPageMatches(lastRecords', app)
        self.assertIn("if(activeView==='records')void refreshLoadedRecords()", app)
        self.assertIn('if(taskDetailInflight.has(id))return taskDetailInflight.get(id)', app)
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
        for draft in ('root-path-input', 'workspace-reference-input', 'file-workspace-path'):
            self.assertNotIn(f"$('{draft}').value", hydration)
        self.assertIn('if(requestedRootsRevision===rootsLoadRevision)renderRootList(', hydration)
        self.assertIn('if(requestedFileWorkspaceRevision===fileWorkspaceLoadRevision)renderFileWorkspace(', hydration)
        self.assertIn('requestedRootsRevision===rootsLoadRevision', app)
        self.assertIn('requestedFileWorkspaceRevision===fileWorkspaceLoadRevision', app)
        self.assertIn('shouldInvalidateWorkspaceDetailForDeletion(item,selectedWorkspaceId)', app)

    def test_workspace_result_projection_is_complete_and_duplicate_save_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            store = QuickStore(directory)
            workspace = store.create_workspace('durable projection')
            jobs = [store.enqueue(f'/note result {index}', f'projection-{index}') for index in range(31)]
            with store.db() as db:
                for index, job_id in enumerate(jobs):
                    db.execute("UPDATE jobs SET status='succeeded',response=? WHERE id=?", (f'result {index}', job_id))
            for job_id in jobs:
                store.save_workspace_result(workspace['id'], job_id)
            detail = store.workspace_detail(workspace['id'])
            self.assertEqual(detail['result_count'], 31)
            self.assertEqual(len(detail['results']), 30)
            self.assertEqual(set(detail['saved_job_ids']), set(jobs))
            revision = detail['updated']
            with self.assertRaisesRegex(ValueError, '이미 프로젝트에 저장'):
                store.save_workspace_result(workspace['id'], jobs[0])
            self.assertEqual(store.workspace(workspace['id'])['updated'], revision)
            deleted = store.delete_personal_space_item('results', detail['results'][0]['id'])
            self.assertEqual(deleted['workspace_id'], workspace['id'])
            self.assertEqual(store.workspace_detail(workspace['id'])['result_count'], 30)
            self.assertGreater(store.workspace(workspace['id'])['updated'], revision)

    def test_personal_records_search_counts_and_pagination_cover_all_durable_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            store = QuickStore(directory)
            workspace = store.create_workspace('authoritative records')
            with store.db() as db:
                for index in range(60):
                    content = 'unique-oldest-note' if index == 0 else f'note {index}'
                    db.execute('INSERT INTO notes VALUES (?,?,?)',
                               (f'note-{index}', content, float(index)))
                for index in range(55):
                    content = 'unique-oldest-artifact' if index == 0 else f'artifact {index}'
                    db.execute('INSERT INTO workspace_results VALUES (?,?,?,?,?,?)',
                               (f'result-{index}', workspace['id'], f'job-{index}', content, '',
                                float(100 + index)))

            first = store.personal_records(limit=50)
            self.assertEqual(first['counts']['note'], 60)
            self.assertEqual(first['counts']['artifact'], 55)
            self.assertEqual(first['match_count'], 115)
            self.assertEqual(len(first['items']), 50)
            self.assertTrue(first['has_more'])
            second = store.personal_records(limit=50, offset=50)
            third = store.personal_records(limit=50, offset=100)
            self.assertEqual(len(second['items']), 50)
            self.assertEqual(len(third['items']), 15)
            self.assertFalse(third['has_more'])
            self.assertEqual(store.personal_records('unique-oldest-note')['items'][0]['id'], 'note-0')
            artifact = store.personal_records('unique-oldest-artifact', 'artifact')
            self.assertEqual(artifact['match_count'], 1)
            self.assertEqual(artifact['items'][0]['id'], 'result-0')

    def test_personal_records_search_uses_one_unicode_normalization(self):
        with tempfile.TemporaryDirectory() as directory:
            store = QuickStore(directory)
            with store.db() as db:
                db.execute('INSERT INTO notes VALUES (?,?,?)',('accent','CAFÉ',1))
                db.execute('INSERT INTO notes VALUES (?,?,?)',('eszett','Straße',2))
                db.execute('INSERT INTO notes VALUES (?,?,?)',('combining','Cafe\u0301',3))
            self.assertEqual({item['id'] for item in store.personal_records('café')['items']},
                             {'accent','combining'})
            self.assertEqual([item['id'] for item in store.personal_records('STRASSE')['items']],
                             ['eszett'])

    def test_capability_lifecycle_uses_existing_confirmed_settings_route(self):
        app = (ROOT / 'src/personal_agent/web/app.js').read_text()
        html = (ROOT / 'src/personal_agent/web/index.html').read_text()
        self.assertIn('id="capability-controls"', html)
        self.assertIn("api('/api/settings/request',{operation:'draft'", app)
        self.assertIn("api('/api/settings/request',{operation:'confirm'", app)
        self.assertIn("api('/api/settings/request',{operation:'cancel'", app)
        self.assertIn("$('brand-home').onclick", app)
        self.assertIn("setError('active-ai-feedback',error)", app)
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
        self.assertIn('다른 프로젝트 · 31개 완료 결과', transcript)
        self.assertIn('{"selected":["다른 프로젝트"],"detail":"다른 프로젝트"', transcript)
        self.assertIn('"root":"/tmp/unsaved-root","reference":"/tmp/unsaved-reference"', transcript)
        self.assertIn('"root":"/tmp/saved-root","reference":"/tmp/unsaved-reference"', transcript)
        self.assertIn('"taskId":"","selectedRows":0', transcript)
        self.assertIn('"detail":"다른 프로젝트","saveButtons":0', transcript)
        self.assertIn('"root":"/tmp/race-saved-root","reference":"/tmp/race-saved-reference"', transcript)
        self.assertIn('"deletedVisible":false,"visibleResults":29', transcript)
        self.assertIn('{"selected":"다른 프로젝트","detail":"다른 프로젝트","results":30}', transcript)
        self.assertIn('{"selectedAfterReturn":"extra durable note 104","latePageRetained":true}', transcript)
        self.assertIn('{"deleted":"memory-exact","memoryCount":0,"resurrected":false}', transcript)
        self.assertIn('"projectA":"회귀 프로젝트 · 0개 완료 결과","results":30', transcript)
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

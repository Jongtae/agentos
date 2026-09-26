"""SEC-PROFILE-01 (#658): owner profile facts in canonical Memory.

Profile facts (allergies, food preferences, home/work places, preferred
stores) are ordinary ``memories`` rows under the ``profile.`` key namespace.
Nothing here adds a store or a classifier: the model chooses the key when
the owner states a fact in conversation, the owner types it in Settings, and
deterministic code validates only the key shape.

Three surfaces are exercised:

- **conversation**: the existing ``save_memory`` tool through the shipped
  worker, with the existing ``explicit_memory_request`` judgment (a fixture
  DecisionEngine) and the value-coverage rules deciding canonical row versus
  MemoryCandidate;
- **Settings API**: list / add / correct on ``/api/personal-space/profile``
  and delete on the existing type-bound Memory delete;
- **Settings UI**: the 프로필 group renderer, run in Node against a DOM stub.

**Evidence class: local, offline, fixture-transport integration** for the
first two (the only injected seams are the outbound model transport and the
DecisionEngine) and a Node DOM-stub unit check for the third.  No live
provider is exercised and no claim is made about a live model's judgment of
any sentence.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from personal_agent.agent_runtime import API_TOOL_GUIDANCE, DEFINITIONS
from personal_agent.conversation_handoff import MEMORY_REQUEST_PROPOSITION
from personal_agent.decision import OUTCOME_DECIDED, BinaryDecision, FixtureDecisionEngine, fixture_confidence
from personal_agent.memory_service import PROFILE_KEY_GUIDANCE, MemoryService
from test_pa1_memory_candidate_owner_path import _OwnerSurface

WEB = Path(__file__).resolve().parents[1] / 'src' / 'personal_agent' / 'web'


def judging(answer):
    """A DecisionEngine that answers only the explicit-memory judgment."""
    def judge(context, proposition):
        if context.purpose != 'explicit-memory-request':
            return None
        if answer is None:
            return None
        return BinaryDecision(OUTCOME_DECIDED, answer, fixture_confidence())
    return FixtureDecisionEngine(judge=judge)


class ProfileJudgmentAndGuidance(unittest.TestCase):
    """What the model is told; the judgment itself stays the model's."""

    def test_the_memory_proposition_covers_asserted_first_person_facts_and_excludes_hedged_ones(self):
        """#658: one clause, for the judge, not a regex.  A scripted fixture
        cannot show how a live judge reads it; this pins the text that is
        sent."""
        self.assertIn('in the first person and without hedging', MEMORY_REQUEST_PROPOSITION)
        self.assertIn('an allergy or dietary restriction', MEMORY_REQUEST_PROPOSITION)
        self.assertIn('where they live or work', MEMORY_REQUEST_PROPOSITION)
        self.assertIn('even without the word "remember"', MEMORY_REQUEST_PROPOSITION)
        self.assertIn('hedged, uncertain or hypothetical rather than asserted', MEMORY_REQUEST_PROPOSITION)
        self.assertIn('This judgment does not write anything.', MEMORY_REQUEST_PROPOSITION)

    def test_save_memory_and_the_tool_guidance_name_the_profile_namespace(self):
        [save_memory] = [tool['function'] for tool in DEFINITIONS if tool['function']['name'] == 'save_memory']
        self.assertIn(PROFILE_KEY_GUIDANCE, save_memory['description'])
        self.assertIn('profile.allergy.peanut', save_memory['description'])
        self.assertEqual(sorted(save_memory['parameters']['properties']), ['content', 'memory_key'],
                         'no new argument: the model already chooses memory_key')
        self.assertIn('"profile." memory_key', API_TOOL_GUIDANCE)
        self.assertIn('owner profile section', API_TOOL_GUIDANCE)


class ProfileFactsInConversation(_OwnerSurface):
    def propose(self, key, content):
        self.model_plan = [('save_memory', json.dumps({'memory_key': key, 'content': content}, ensure_ascii=False))]
        self.model_text = '알겠습니다.'

    def test_an_explicit_statement_lands_under_a_profile_key(self):
        """The judged-explicit statement is stored where the model keyed it."""
        self.service.use_decision_engine(judging(True))
        self.propose('profile.allergy.peanut', '땅콩 알러지')
        job = self.ask('나 땅콩 알러지 있어')
        self.model_plan = []
        rows = self.store.memories()
        self.assertEqual([(row['memory_key'], row['content'], row['state']) for row in rows],
                         [('profile.allergy.peanut', '땅콩 알러지', 'current')])
        self.assertEqual(self.store.memory_candidates(), [], 'nothing left pending')
        self.assertEqual(self.store.job(job)['status'], 'succeeded')
        [link] = next(task for task in self.web('/api/tasks')['tasks'] if task['id'] == job)['retained']
        self.assertEqual((link['kind'], link['label']), ('memory', 'profile.allergy.peanut'))
        # The Settings group and the prompt snapshot see the same row.
        listed = self.web('/api/personal-space/profile')
        self.assertEqual([row['id'] for row in listed['memories']], [rows[0]['id']])
        snapshot = MemoryService(self.store, private_read_sink=MemoryService.NO_EGRESS_GUARD).profile_snapshot('local-owner')
        self.assertIn('profile.allergy.peanut: 땅콩 알러지 (saved ', snapshot['text'])

    def test_a_hedged_statement_becomes_a_candidate_not_a_profile_row(self):
        """Judged not explicit: the same proposed write stays a MemoryCandidate."""
        self.service.use_decision_engine(judging(False))
        self.propose('profile.allergy.peanut', '땅콩 알러지')
        job = self.ask('아마 땅콩 알러지 있을걸')
        self.model_plan = []
        self.assertEqual(self.store.memories(), [])
        [pending] = self.store.memory_candidates()
        self.assertEqual((pending['memory_key'], pending['content'], pending['state']),
                         ('profile.allergy.peanut', '땅콩 알러지', 'pending'))
        # #488: a withheld write is not a completed turn, and the reason is visible.
        self.assertEqual(self.store.job(job)['status'], 'failed')
        self.assertEqual(self.web('/api/personal-space/profile')['memories'], [])
        self.assertEqual(self.web('/api/personal-space')['memory_candidate_count'], 1)

    def test_an_unavailable_judgment_also_leaves_a_candidate(self):
        self.service.use_decision_engine(judging(None))
        self.propose('profile.place.home', '서울 마포구')
        self.ask('집은 서울 마포구야')
        self.model_plan = []
        self.assertEqual(self.store.memories(), [])
        self.assertEqual([row['memory_key'] for row in self.store.memory_candidates()], ['profile.place.home'])

    def test_a_profile_key_does_not_widen_what_the_model_may_write(self):
        """Judged explicit, but the value is not the owner's: still a candidate.

        The ``profile.`` namespace is a key convention, not a second path;
        the existing value-coverage refusal applies to it unchanged.
        """
        self.service.use_decision_engine(judging(True))
        self.propose('profile.allergy.shrimp', '새우 알러지')
        self.ask('나 땅콩 알러지 있어')
        self.model_plan = []
        self.assertEqual(self.store.memories(), [])
        [pending] = self.store.memory_candidates()
        self.assertEqual(pending['memory_key'], 'profile.allergy.shrimp')


class ProfileFactsInSettings(_OwnerSurface):
    def remember(self, key, content):
        return self.web('/api/personal-space/profile/request',
                        {'operation': 'remember', 'memory_key': key, 'content': content})

    def profile(self):
        return self.web('/api/personal-space/profile')

    def test_settings_lists_only_profile_rows_in_key_order(self):
        self.store.save_memory('meeting-time', 'mornings')
        self.remember('profile.store.books', '교보문고')
        self.remember('profile.allergy.peanut', '땅콩')
        listed = self.profile()
        self.assertEqual(listed['state'], 'current')
        self.assertEqual([(row['memory_key'], row['content']) for row in listed['memories']],
                         [('profile.allergy.peanut', '땅콩'), ('profile.store.books', '교보문고')])
        self.assertTrue(listed['private_content_included'])
        # The general Memory list still carries the rows, keyed, so the
        # 기억과 메모 list can label them 프로필.
        records = self.web('/api/personal-records?filter=saved')['items']
        self.assertEqual(sorted(row['memory_key'] for row in records),
                         ['meeting-time', 'profile.allergy.peanut', 'profile.store.books'])

    def test_add_is_canonical_and_the_same_key_corrects(self):
        first = self.remember('profile.place.home', '서울 마포구')
        self.assertEqual(first['state'], 'current')
        self.assertEqual(self.store.memory_candidates(), [], 'an owner write is not a candidate')
        second = self.remember('profile.place.home', '서울 마포구 합정동')
        self.assertEqual(second['supersedes'], first['id'])
        rows = self.profile()['memories']
        self.assertEqual([(row['id'], row['content']) for row in rows], [(second['id'], '서울 마포구 합정동')])
        # The exact-item view opens the current row as Memory with its key.
        opened = self.web(f"/api/personal-space/items/memory/{second['id']}")['item']
        self.assertEqual((opened['kind'], opened['memory_key']), ('memory', 'profile.place.home'))

    def test_delete_follows_the_existing_forget_semantics(self):
        first = self.remember('profile.allergy.peanut', '땅콩')
        second = self.remember('profile.allergy.peanut', '땅콩, 호두')
        deleted = self.web(f"/api/personal-space/memories/{second['id']}", method='DELETE')
        self.assertEqual((deleted['deleted'], deleted['kind'], deleted['deleted_memory_count']), (True, 'memories', 2),
                         'the whole supersession chain is forgotten, not only the current value')
        self.assertEqual(self.profile()['memories'], [])
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM memories').fetchone()[0], 0)
        # A repeated delete, or one aimed at the superseded version, reports
        # "not deleted" rather than inventing a second deletion.
        for memory_id in (second['id'], first['id']):
            self.assertFalse(self.web(f"/api/personal-space/memories/{memory_id}", method='DELETE')['deleted'])

    def test_only_a_profile_shaped_key_and_a_value_are_accepted(self):
        for key in ('allergy.peanut', 'profile.', 'profile..x', 'profile.al lergy', '', None):
            status, message = self.refused('/api/personal-space/profile/request',
                                           {'operation': 'remember', 'memory_key': key, 'content': '땅콩'})
            self.assertEqual(status, 400, key)
            self.assertIn('profile.', message)
        self.assertEqual(self.refused('/api/personal-space/profile/request',
                                      {'operation': 'remember', 'memory_key': 'profile.allergy', 'content': ' '})[0], 400)
        self.assertEqual(self.refused('/api/personal-space/profile/request', {'operation': 'forget'})[0], 400)
        self.assertEqual(self.store.memories(), [])

    def test_the_profile_surface_needs_the_owner_session(self):
        from http.cookiejar import CookieJar
        from urllib.request import HTTPCookieProcessor, build_opener
        stranger = build_opener(HTTPCookieProcessor(CookieJar()))
        self.assertNotEqual(self.refused('/api/personal-space/profile', opener=stranger)[0], 200)
        self.assertNotEqual(self.refused('/api/personal-space/profile/request',
                                         {'operation': 'remember', 'memory_key': 'profile.x', 'content': 'y'},
                                         opener=stranger)[0], 200)
        self.assertEqual(self.store.memories(), [])


UI_CHECK = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const app=fs.readFileSync(process.argv[1],'utf8'),ids=new Map();
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.className='';this.hidden=false;this._text='';}
 set id(value){this._id=value;ids.set(value,this);} get id(){return this._id;}
 set textContent(value){this._text=String(value);this.children=[];} get textContent(){return this._text+this.children.map(node=>typeof node==='string'?node:node.textContent).join('');}
 append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}
 setAttribute(key,value){this.attrs[key]=value;} focus(){} get isConnected(){return true;}
 get classList(){const node=this;return {toggle(name,on){node._cls=Boolean(on);},add(){},remove(){},contains:()=>Boolean(node._cls)};}
 querySelector(){return null;} querySelectorAll(){return [];}
}
function descendants(node){return node.children.flatMap(child=>typeof child==='string'?[]:[child,...descendants(child)]);}
for(const id of ['owner-profile-list','owner-profile-feedback','saved-memory-list','saved-memory-feedback'])new Element('div').id=id;
const $=id=>ids.get(id),document={getElementById:$,createElement:tag=>new Element(tag)};
const part=(start,end)=>app.slice(app.indexOf(start),app.indexOf(end)),line=start=>{const at=app.indexOf(start);return app.slice(at,app.indexOf('\n',at)+1);};
const source=part('const LANGUAGES=','function normalizeEndpoint(')+line('function formatTimeParts(')+part('function element(','function setError(')+
 'let ownerProfile=null,ownerProfileLoadSequence=0,ownerProfileEdit=null,ownerProfileDeletePending=null,savedMemory=null;function __setSaved(rows){savedMemory=rows;}\n'+
 part('function renderSavedMemory(','// Reload the list on the existing poll')+part('const PROFILE_PREFIX=','function rememberWorkspaceResultSummary(');
const calls=[];let refreshes=0;
const ctx={document,$,console,calls,
 api:async(path,body,method)=>{calls.push({path,body,method:method||(body===undefined?'GET':'POST')});if(path==='/api/personal-space/profile')return {memories:ctx.profileRows};return {deleted:true};},
 refresh:async()=>{refreshes++;},busy:async(button,fn)=>fn(),loadSavedMemory:async()=>{},
 setError:(id,error)=>{$(id).textContent=error?.message||String(error||'');},setFeedback:(id,text)=>{$(id).textContent=text||'';},
 itemLink:(kind,id,text,className)=>{const a=new Element('a');a.textContent=text;a.className=className;a.href='#item/'+kind+'/'+id;return a;},
 itemTitle:row=>row.memory_key||row.content,itemLabel:kind=>kind==='memory'?'기억':'메모'};
vm.createContext(ctx);vm.runInContext(source,ctx);vm.runInContext("setLanguage('ko')",ctx);
const rows=()=>$('owner-profile-list').children.filter(node=>node.tag==='div'&&node.className.split(' ')[0]==='settings-row');
const texts=(node,cls)=>descendants(node).filter(n=>n.className===cls).map(n=>n.textContent);
const buttons=node=>descendants(node).filter(n=>n.tag==='button').map(n=>n.textContent);
(async()=>{
 // Empty group: an honest empty state, nothing invented.
 ctx.profileRows=[];await ctx.loadOwnerProfile();
 assert.equal($('owner-profile-list').children.length,1);assert.equal($('owner-profile-list').children[0].className,'settings-empty');
 // Rows: title without the namespace, content with the saved time, the 프로필 state, and 수정/삭제/열기.
 ctx.profileRows=[{id:'m1',memory_key:'profile.allergy.peanut',content:'땅콩 알러지',created:1700000000},{id:'m2',memory_key:'profile.place.home',content:'서울 마포구',created:1700000000}];
 await ctx.loadOwnerProfile();
 assert.deepEqual(rows().map(r=>texts(r,'settings-row-title')[0]),['allergy.peanut','place.home']);
 assert(texts(rows()[0],'settings-row-description')[0].startsWith('땅콩 알러지 · '));
 assert.deepEqual(rows().map(r=>texts(r,'settings-state neutral')[0]),['프로필','프로필']);
 assert.deepEqual(buttons(rows()[0]),['수정','삭제']);
 assert.equal(descendants(rows()[0]).find(n=>n.tag==='a').href,'#item/memory/m1');
 // Delete is two presses: the first press asks, calls nothing; the second deletes through the existing Memory delete.
 const first=descendants(rows()[0]).find(n=>n.tag==='button'&&n.textContent==='삭제');await first.onclick({currentTarget:first});
 assert.equal(calls.filter(c=>c.method==='DELETE').length,0,'first press deletes nothing');
 assert.deepEqual(buttons(rows()[0]),['수정','취소','삭제 확인']);
 assert(texts(rows()[0],'confirm-text')[0].includes('되돌릴 수 없습니다'));
 assert.equal(buttons(rows()[1]).includes('삭제 확인'),false,'only the pressed row is armed');
 const confirm=descendants(rows()[0]).find(n=>n.tag==='button'&&n.textContent==='삭제 확인');ctx.profileRows=[ctx.profileRows[1]];await confirm.onclick({currentTarget:confirm});
 assert.deepEqual(calls.filter(c=>c.method==='DELETE').map(c=>c.path),['/api/personal-space/memories/m1']);
 assert.equal($('owner-profile-feedback').textContent,'지웠습니다.');assert.equal(rows().length,1);assert(refreshes>0);
 // Edit: the key is fixed, the value is editable, saving is the keyed owner write to the same key.
 const edit=descendants(rows()[0]).find(n=>n.tag==='button'&&n.textContent==='수정');edit.onclick({currentTarget:edit});
 const form=descendants($('owner-profile-list')).find(n=>n.tag==='form');assert(form,'an inline edit form');
 const area=descendants(form).find(n=>n.tag==='textarea');assert.equal(area.value,'서울 마포구');
 assert.equal(descendants($('owner-profile-list')).some(n=>n.tag==='input'),false,'the key is not re-typed on edit');
 area.value='서울 마포구 합정동';await form.onsubmit({preventDefault(){}});
 const saved=calls.find(c=>c.path==='/api/personal-space/profile/request');
 assert.equal(JSON.stringify(saved.body),JSON.stringify({operation:'remember',memory_key:'profile.place.home',content:'서울 마포구 합정동'}));
 assert.equal($('owner-profile-feedback').textContent,'프로필을 저장했습니다.');
 assert.equal(descendants($('owner-profile-list')).some(n=>n.tag==='form'),false,'the edit form closes after saving');
 // The 기억과 메모 list labels a profile row 프로필 and any other Memory 기억.
 ctx.__setSaved({items:[{id:'m2',type:'memory',memory_key:'profile.place.home',content:'서울',created:1},{id:'m3',type:'memory',memory_key:'meeting-time',content:'mornings',created:1},{id:'n1',type:'note',content:'우유',created:1}],has_more:false});
 ctx.renderSavedMemory();
 assert.deepEqual(descendants($('saved-memory-list')).filter(n=>n.className.startsWith('settings-state')).map(n=>n.textContent),['프로필','기억','메모']);
 // Key shape only: the helper never judges content.
 for(const key of ['profile.allergy','profile.place.home','profile.알러지'])assert(ctx.isProfileKey(key),key);
 for(const key of ['profile','profile.','allergy','profile.a b',null])assert(!ctx.isProfileKey(key),String(key));
 console.log('ok');
})().catch(error=>{console.error(error);process.exit(1);});
"""


class ProfileSettingsUi(unittest.TestCase):
    def test_profile_group_lists_edits_and_deletes_with_the_existing_grammar(self):
        node = shutil.which('node')
        if node is None:
            raise unittest.SkipTest('Node is needed for the DOM-stub check')
        result = subprocess.run([node, '-e', UI_CHECK, str(WEB / 'app.js')], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines()[-1], 'ok')


if __name__ == '__main__':
    unittest.main()

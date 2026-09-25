"""PRESENCE-TRACE-01 (#559): the conversation trace projects recorded state only.

Evidence class: unit behaviour of the shipped ``app.js`` renderer under Node
(with a minimal DOM stand-in) plus the task read model of ``AgentService``.
No server, model, CLI, DecisionEngine provider or Telegram is contacted.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from personal_agent.quickstart_service import AgentService

ROOT = Path(__file__).parents[1] / "src" / "personal_agent" / "web"
APP = (ROOT / "app.js").read_text(encoding="utf-8")


def node_run(script):
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("Node is needed for JavaScript behaviour checks")
    return subprocess.run([node, "-e", script, str(ROOT / "app.js")], check=True,
                          capture_output=True, text=True, timeout=20).stdout


def ok(out):
    return json.loads(out.strip().splitlines()[-1])


FOLLOWUP = "{kind:'choose',purpose:'conversation-followup',outcome:'decided',answer:'retry',at:5}"
ROUTES = {
    "api": "{provider:'openai',model:'gpt-4o-mini',requested_model:'gpt-4o-mini',observed_model:'gpt-4o-mini-2024-07-18',route:'direct_api'}",
    "jev": "{provider:'typesafe',engine:'jev',model:'jev-latest',requested_model:'jev-latest',observed_model:'not reported',route:'jev'}",
    "cli": "{provider:'codex',engine:'codex',model:'small',requested_model:'small',model_policy:'lowest_qualified',observed_model:'not reported',route:'subscription_cli'}",
}


class SemanticTrace(unittest.TestCase):
    def test_followup_decision_and_continuity_read_as_meaning_in_time_order(self):
        out = node_run(r"""
const assert=require('node:assert/strict');const ui=require(process.argv[1]);ui.setLanguage('ko');
const task={status:'succeeded',status_kind:'finished',response:'ok',observed_at:20,relation:{kind:'retry',work_id:'w1'},
 events:[{id:1,tool:'conversation_continuity',status:'succeeded',created:6,summary:'s',details:{relation:'retry',executed:true}},
         {id:2,tool:'subscription_engine',status:'running',created:7,summary:'s',details:{engine:'codex'}},
         {id:3,tool:'subscription_engine',status:'succeeded',created:9,summary:'s',details:{engine:'codex'}}],
 decisions:[{...""" + FOLLOWUP + r""",...""" + ROUTES["api"] + r"""}]};
const rows=ui.semanticTrace(task);
assert.deepEqual(rows.map(r=>r.text),['이전 요청의 후속으로 해석','이전 요청을 다시 실행','구독 CLI 실행 완료','답변']);
const text=JSON.stringify(rows);
for(const leaked of ['gpt-4o-mini','openai','direct_api','conversation-followup','decided'])assert(!text.includes(leaked),leaked+' stays out of the semantic trace');
console.log(JSON.stringify({ok:true}));
""")
        self.assertEqual(ok(out), {"ok": True})

    def test_the_semantic_trace_is_the_same_for_every_decision_route(self):
        routes = ",".join(f"{name}:{value}" for name, value in ROUTES.items())
        out = node_run(r"""
const assert=require('node:assert/strict');const ui=require(process.argv[1]);ui.setLanguage('ko');
const routes={""" + routes + r"""};
const trace=route=>ui.semanticTrace({status:'succeeded',status_kind:'finished',response:'x',observed_at:9,relation:{kind:'correction',work_id:'w0'},events:[],decisions:[{...""" + FOLLOWUP + r""",...route}]}).map(r=>[r.text,r.tone]);
const api=trace(routes.api);
assert.deepEqual(api,[['이전 요청의 후속으로 해석','neutral'],['답변','ok']]);
assert.deepEqual(trace(routes.jev),api,'Jev keeps the same owner-facing trace');
assert.deepEqual(trace(routes.cli),api,'a subscription route keeps the same owner-facing trace');
console.log(JSON.stringify({ok:true}));
""")
        self.assertEqual(ok(out), {"ok": True})

    def test_ambiguous_or_unavailable_judgments_never_draw_a_relation(self):
        out = node_run(r"""
const assert=require('node:assert/strict');const ui=require(process.argv[1]);ui.setLanguage('ko');
const base={status:'succeeded',status_kind:'finished',response:'x',observed_at:9,events:[]};
const none=ui.semanticTrace({...base,decisions:[{purpose:'conversation-followup',outcome:'decided',answer:'none-of-these',at:1}]});
assert.deepEqual(none.map(r=>r.text),['이전 대화와 연결하지 않음','답변']);
// A confident-looking engine answer without a recorded relation is still not a relation.
const unconfirmed=ui.semanticTrace({...base,decisions:[{purpose:'conversation-followup',outcome:'decided',answer:'retry',at:1}]});
assert.equal(unconfirmed[0].text,'이전 대화와 연결하지 않음');
for(const outcome of ['provider_unavailable','timeout','malformed','context_rejected','cancelled']){
 const row=ui.semanticTrace({...base,decisions:[{purpose:'conversation-followup',outcome,at:1}]})[0];
 assert.deepEqual([row.text,row.tone],['이전 대화와의 관계를 판단하지 못해 연결하지 않음','unknown'],outcome);}
// Unknown purpose or no recorded time: technical detail only, no guessed line.
assert.deepEqual(ui.semanticTrace({...base,decisions:[{purpose:'presence',outcome:'decided',at:1},{purpose:'conversation-followup',outcome:'decided'}]}).map(r=>r.text),['답변']);
console.log(JSON.stringify({ok:true}));
""")
        self.assertEqual(ok(out), {"ok": True})

    def test_continuity_rows_say_whether_anything_actually_ran(self):
        out = node_run(r"""
const assert=require('node:assert/strict');const ui=require(process.argv[1]);ui.setLanguage('ko');
const step=(kind,executed)=>ui.continuityStep({details:executed===undefined?{relation:kind}:{relation:kind,executed}},{relation:{kind,work_id:'w'}});
assert.deepEqual(step('retry',true),{text:'이전 요청을 다시 실행',tone:'ok'});
assert.deepEqual(step('retry',false),{text:'이전 요청을 자동으로 다시 실행하지 않음',tone:'attention'});
assert.deepEqual(step('cancel',false),{text:'이전 요청을 취소하지 못함',tone:'attention'});
assert.equal(step('cancel',true).text,'이전 요청을 취소');
assert.equal(step('correction',false).text,'이전 요청을 정정');assert.equal(step('reference',false).text,'이전 요청 결과를 참조');
assert.equal(step('retry').text,'이전 요청과 연결','an older record without the executed flag claims nothing');
assert.equal(ui.laterRelationText('correction'),'이후 요청에서 정정함');assert.equal(ui.laterRelationText('retry'),'이후 다시 시도함');
console.log(JSON.stringify({ok:true}));
""")
        self.assertEqual(ok(out), {"ok": True})

    def test_repeated_transitions_collapse_and_statuses_stay_distinct(self):
        out = node_run(r"""
const assert=require('node:assert/strict');const ui=require(process.argv[1]);ui.setLanguage('ko');
const ev=(id,tool,status,details={},summary='s')=>({id,tool,status,created:id,summary,details});
const rows=ui.semanticTrace({status:'succeeded',status_kind:'finished',response:'x',observed_at:99,events:[
 ev(1,'web_search','succeeded',{evidence:true}),ev(2,'web_search','succeeded'),ev(3,'web_search','succeeded'),
 ev(4,'local_authority','requested',{authority:'folder'}),ev(5,'save_note','denied'),ev(6,'mystery_tool','withheld'),
 ev(7,'model','failed',{},'첫 실패'),ev(8,'model','failed',{},'두 번째 실패')]});
assert.deepEqual(rows.map(r=>r.text),['웹 검색 완료 (3회)','폴더 권한 요청함','메모 저장 거부됨','도구 실행 보내지 않음','AI 응답 실패','AI 응답 실패','답변']);
assert.equal(rows[0].note,'근거 확인');assert.deepEqual(rows[0].eventIds,[1,2,3]);
assert.deepEqual(rows.slice(1,4).map(r=>r.tone),['attention','danger','attention']);
assert.deepEqual([rows[4].note,rows[5].note],['첫 실패','두 번째 실패'],'different failures are not merged');
assert(!JSON.stringify(rows).includes('mystery_tool'),'unknown tool ids stay under technical detail');
const parked=ui.semanticTrace({status:'succeeded',status_kind:'finished',response:'x',observed_at:9,events:[ev(1,'find_files','succeeded',{setup_required:true},'p')]});
assert.equal(parked[0].note,'연결 설정이 필요해 확인하지 못함','a setup-required read never says a source was checked');
console.log(JSON.stringify({ok:true}));
""")
        self.assertEqual(ok(out), {"ok": True})


TECHNICAL_DOM = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const app=fs.readFileSync(process.argv[1],'utf8');
class Element{constructor(tag){this.tag=tag;this.children=[];this.className='';this._t='';}
 set textContent(v){this._t=String(v);this.children=[];} get textContent(){return this._t+this.children.map(c=>c.textContent).join('\n');}
 append(...n){this.children.push(...n);}}
const part=(a,b)=>app.slice(app.indexOf(a),app.indexOf(b,app.indexOf(a)));
const source=part('const LANGUAGES=','function normalizeEndpoint(')+part('function formatTimeParts(','\n')+'\n'+part('const DECISION_ROLE=','function traceWindow(')+
 part('function routeText(','function workspaceSaveCandidates(')+part('function element(','\n')+'\n'+part('function technicalView(','function renderTasks(){');
const ctx={document:{createElement:tag=>new Element(tag)},console};vm.createContext(ctx);vm.runInContext(source,ctx);vm.runInContext("setLanguage('ko')",ctx);
const all=n=>n.children.flatMap(c=>[c,...all(c)]);
const box=new Element('details');
ctx.technicalView({id:'w2',status:'succeeded',status_kind:'finished',started_at:1,observed_at:2,channel:'telegram:x',relation:{kind:'retry',work_id:'w1'},
 route:{kind:'subscription',engine:'codex',status:'succeeded'},provenance:{route:'subscription',engine:'codex',requested_model:null,reported_model:null},events:[],
 decisions:[{purpose:'conversation-followup',outcome:'decided',answer:'retry',provider:'openai',model:'gpt-4o-mini',requested_model:'gpt-4o-mini',observed_model:'gpt-4o-mini-2024-07-18',route:'direct_api',elapsed_seconds:1.67,at:1}]},box);
const headings=all(box).filter(n=>n.tag==='h4').map(n=>n.textContent);
assert.deepEqual(headings,['실행','보조 판단'],'execution and auxiliary judgment are separate roles');
const lists=box.children.filter(n=>n.tag==='dl');
const pairs=dl=>{const out={};for(let i=0;i<dl.children.length;i+=2)out[dl.children[i].textContent]=dl.children[i+1].textContent;return out;};
const execution=pairs(lists[1]),decision=pairs(lists[2]);
assert.equal(execution['사용한 AI'],'Codex 구독 CLI');assert.equal(execution['요청한 모델'],'지정 안 함 (CLI 기본값)');assert.equal(execution['보고된 모델'],'보고되지 않음');
assert(!JSON.stringify(execution).includes('gpt-4o-mini'),'the auxiliary model never appears as the executing model');
assert.equal(decision['관측 모델'],'gpt-4o-mini-2024-07-18');assert.equal(decision['제공자'],'openai');assert.equal(decision['기록된 관계'],'retry → w1');
assert.equal(decision['역할'],'대화 해석');
// No decision: no auxiliary section at all.
const bare=new Element('details');ctx.technicalView({id:'w3',status:'failed',status_kind:'finished',events:[]},bare);
assert.deepEqual(all(bare).filter(n=>n.tag==='h4').map(n=>n.textContent),['실행']);
// Unreported models are said to be unreported, never filled in.
const facts=Object.fromEntries(ctx.decisionFacts({purpose:'conversation-followup',outcome:'provider_unavailable',route:'subscription_cli',engine:'claude-code',model_policy:'engine_default'},{}));
assert.equal(facts['관측 모델'],'보고되지 않음');assert.equal(facts['요청 모델'],'엔진 기본값');assert.equal(facts['제공자'],'보고되지 않음');
assert.equal(facts['결과'],'provider_unavailable');assert.equal(facts['기록된 관계'],'없음');assert(!('엔진 답' in facts));
console.log(JSON.stringify({ok:true}));
"""


class TechnicalProvenance(unittest.TestCase):
    def test_execution_and_auxiliary_judgment_are_separate_roles(self):
        self.assertEqual(ok(node_run(TECHNICAL_DOM)), {"ok": True})

    def test_raw_material_stays_in_developer_mode(self):
        view = APP[APP.index("function technicalView("):APP.index("function renderTasks(){")]
        for raw in ("argv", "prompt_envelope", "record.instructions"):
            self.assertNotIn(raw, view)
        render = APP[APP.index("function renderTasks(){"):APP.index("function recordKey(item){")]
        self.assertIn("technicalView(task,box);if(developerMode())box.append(provenanceView(task));", render)
        developer = APP[APP.index("function provenanceView("):APP.index("if(typeof module!=='undefined'")]
        self.assertNotIn("decisions", developer, "DecisionEngine calls are summarized once, in 기술 정보")


class RecordedRelationsOnly(unittest.TestCase):
    def test_the_earlier_turn_shows_only_recorded_relations(self):
        render = APP[APP.index("function renderTasks(){"):APP.index("function recordKey(item){")]
        index = render[render.index("const later=new Map()"):]
        index = index[:index.index("\n")]
        self.assertIn("if(item.relation?.work_id)", index)
        self.assertNotIn("title", index, "the reverse link comes from task.relation, never from wording")
        self.assertIn("laterRelationText(next.relation.kind)", render)


class TaskReadModel(unittest.TestCase):
    def test_progress_events_expose_content_free_continuity_flags_only(self):
        event = {"id": 1, "job_id": "w", "tool": "conversation_continuity", "status": "succeeded", "created": 1,
                 "trace": {"relation": "retry", "related_work_id": "w0", "executed": False,
                           "reason": "이전 요청이 개인 문서 내용을 사용해 자동으로 다시 실행하지 않았습니다."}}
        details = AgentService._progress_event(event)["details"]
        self.assertEqual(details, {"relation": "retry", "executed": False})
        search = AgentService._progress_event({"id": 2, "job_id": "w", "tool": "web_search", "status": "succeeded", "created": 2,
                                               "trace": {"scope": "public-web", "evidence": {"urls": ["https://example.invalid/private-query"]}}})
        self.assertEqual(search["details"], {"scope": "public-web", "evidence": True}, "evidence is a flag, never its content")
        self.assertEqual(search["summary"], "근거를 확인했습니다.")
        # Review finding (PR #590): a setup-required read consulted nothing, as in evidence_summary().
        parked = AgentService._progress_event({"id": 3, "job_id": "w", "tool": "find_files", "status": "succeeded", "created": 3,
                                               "trace": {"evidence": {"qualifiers": ["setup-required"], "count": 0}}})
        self.assertEqual(parked["details"], {"setup_required": True})
        self.assertNotEqual(parked["summary"], "근거를 확인했습니다.")


if __name__ == "__main__":
    unittest.main()

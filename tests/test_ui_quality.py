"""UI-QUALITY-01 (#558): presentation rules the local web must keep.

Static checks read the shipped files; behaviour checks execute the real
``app.js`` under Node with a minimal DOM stand-in, the same way
``tests/test_settings_ui.py`` does.  Nothing here contacts a server.
"""
import json

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1] / "src" / "personal_agent" / "web"
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "style.css").read_text(encoding="utf-8")


def node_run(script):
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("Node is needed for JavaScript behaviour checks")
    return subprocess.run([node, "-e", script, str(ROOT / "app.js")], check=True,
                          capture_output=True, text=True, timeout=20).stdout


class TokensAndChrome(unittest.TestCase):
    def test_style_declares_the_token_set(self):
        for token in ("--ok:", "--attn:", "--danger:", "--run:", "--unknown:", "--accent:",
                      "--fs-1:", "--fs-6:", "--sp-1:", "--sp-7:", "--r-1:", "--r-2:", "--r-pill:"):
            self.assertIn(token, CSS)
        self.assertIn("prefers-reduced-motion", CSS)
        self.assertIn(":focus-visible", CSS)
        self.assertNotIn("transition:all", CSS.replace(" ", ""))
        self.assertNotIn("outline:none", CSS.replace(" ", ""))
        self.assertNotIn("user-scalable=no", HTML)
        self.assertNotIn("maximum-scale", HTML)

    def test_template_chrome_is_gone(self):
        self.assertNotIn("eyebrow", HTML)
        self.assertNotIn("eyebrow", APP)
        self.assertNotIn("count-chip", APP)
        for label in ("OWNER-LOCAL", ">WORK<", ">RECORDS<", ">SETTINGS<"):
            self.assertNotIn(label, HTML)
        self.assertNotIn("innerHTML", APP)
        self.assertNotIn("insertAdjacentHTML", APP)
        self.assertNotIn("toLocaleString()", APP)
        self.assertIn("Intl.RelativeTimeFormat", APP)
        self.assertIn("Intl.DateTimeFormat", APP)

    def test_records_search_is_live_and_counts_live_in_the_filter(self):
        search = HTML[HTML.index('id="record-search"'):HTML.index('id="record-search-feedback"')]
        self.assertNotIn("<button", search)
        self.assertIn('type="search"', search)
        self.assertIn("recordCountLabels", APP)
        self.assertIn("option.textContent=labels[option.value]", APP)

    def test_status_and_destructive_grammar(self):
        self.assertIn("function badge(", APP)
        self.assertIn("function taskTone(", APP)
        self.assertIn(".destructive.confirm", CSS)
        self.assertIn("'삭제 확인'", APP)
        self.assertIn("telegramDisconnectPending", APP)
        self.assertIn('id="telegram-disconnect-cancel"', HTML)
        self.assertIn('class="switch"', HTML)
        self.assertIn("saveContextSources", APP)
        self.assertNotIn("수집 설정 저장", HTML)
        self.assertIn('id="context-policy"', HTML)
        self.assertIn("OFFLINE_MESSAGE", APP)
        self.assertNotIn("Failed to fetch", APP)
        self.assertIn('id="global-error" role="alert" class="error banner"', HTML)

    def test_internal_ids_stay_under_technical_details(self):
        self.assertIn("const TOOL_NAMES=", APP)
        self.assertIn("toolName(event.tool)", APP)
        self.assertIn("'기술 세부 정보'", APP)
        self.assertIn("fact('Work ID',task.id)", APP)
        self.assertNotIn("`요청 ID ${task.id}", APP)


class RenderingBehaviour(unittest.TestCase):
    def test_rich_text_is_safe_and_formatted(self):
        out = node_run(r"""
const assert=require('node:assert/strict');const ui=require(process.argv[1]);
const text='# 제목\n\n**굵게** 와 `code` 그리고 [링크](https://example.invalid/a) [나쁜](javascript:alert(1)) <b>raw</b>\n\n- 항목 1\n- 항목 2\n\n1. 첫째\n2. 둘째\n\n```\nx<y\n```\nhttps://example.invalid/bare';
const blocks=ui.parseRichText(text);
assert.deepEqual(blocks.map(b=>b.type),['heading','paragraph','list','list','pre','paragraph']);
const inlines=blocks[1].lines[0];
assert.deepEqual(inlines.filter(i=>i.type==='link').map(i=>i.href),['https://example.invalid/a']);
assert(inlines.some(i=>i.type==='text'&&i.text.includes('[나쁜](javascript:alert(1))')),'non-http link stays literal text');
assert(inlines.some(i=>i.type==='text'&&i.text.includes('<b>raw</b>')),'html stays literal text');
assert.equal(inlines.find(i=>i.type==='strong').text,'굵게');
assert.equal(inlines.find(i=>i.type==='code').text,'code');
assert.equal(blocks[2].ordered,false);assert.equal(blocks[3].ordered,true);
assert.equal(blocks[4].text,'x<y');
assert.equal(blocks[5].lines[0][0].href,'https://example.invalid/bare');
assert.deepEqual(ui.parseRichText(''),[]);
assert.equal(ui.parseRichText('**미완성').length,1);
console.log(JSON.stringify({ok:true}));
""")
        self.assertEqual(json.loads(out.strip().splitlines()[-1]), {"ok": True})

    def test_rich_text_renderer_uses_nodes_only(self):
        out = node_run(r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const app=fs.readFileSync(process.argv[1],'utf8');
class Element{constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.className='';this._text='';}
 set textContent(v){this._text=String(v);this.children=[];}get textContent(){return this._text+this.children.map(n=>typeof n==='string'?n:n.textContent).join('');}
 append(...n){this.children.push(...n);}setAttribute(k,v){this.attrs[k]=v;}}
const part=(a,b)=>app.slice(app.indexOf(a),app.indexOf(b));
const source=part('const TIME_CLOCK=','const TOOL_NAMES=')+part('function element(','function focusSettingsTarget(');
const ctx={document:{createElement:t=>new Element(t)},console};vm.createContext(ctx);vm.runInContext(source,ctx);
const box=ctx.renderRichText('<script>alert(1)</script> [x](https://e.invalid/p) [y](javascript:x)');
const all=n=>n.children.flatMap(c=>typeof c==='string'?[c]:[c,...all(c)]);
const nodes=all(box);
assert(!nodes.some(n=>typeof n!=='string'&&n.tag==='script'),'no script element');
assert(nodes.some(n=>typeof n==='string'&&n.includes('<script>alert(1)</script>')),'script text stays text');
const links=nodes.filter(n=>typeof n!=='string'&&n.tag==='a');
assert.deepEqual(links.map(l=>[l.href,l.rel,l.target]),[['https://e.invalid/p','noopener noreferrer','_blank']]);
assert.equal(ctx.renderRichText('').textContent,'내용이 제공되지 않았습니다.');
const time=ctx.timeNode(Math.floor(Date.now()/1000)-120);
assert.equal(time.tag,'time');assert.equal(time.textContent,'2분 전');assert(time.title.length>0);assert(time.dateTime.endsWith('Z'));
assert.equal(ctx.timeNode(0).textContent,'시간 정보 없음');
assert.equal(ctx.badge('완료','ok').className,'badge ok');
console.log(JSON.stringify({ok:true}));
""")
        self.assertEqual(json.loads(out.strip().splitlines()[-1]), {"ok": True})

    def test_time_and_tone_helpers(self):
        out = node_run(r"""
const assert=require('node:assert/strict');const ui=require(process.argv[1]);
const now=Date.UTC(2026,8,24,12,0,0);
const at=seconds=>ui.formatTimeParts(now/1000-seconds,now).relative;
assert.equal(at(10),'방금');assert.equal(at(300),'5분 전');assert.equal(at(7200),'2시간 전');assert.equal(at(86400),'어제');assert.equal(at(86400*3),'3일 전');
assert.match(at(86400*30),/월 \d+일$/);
assert.match(ui.formatTimeParts(now/1000-86400*400,now).relative,/^\d{4}년/);
assert.deepEqual(ui.formatTimeParts(0,now),{relative:'시간 정보 없음',absolute:'',iso:''});
assert.equal(ui.taskTone({status_kind:'active'}),'run');
assert.equal(ui.taskTone({status:'failed',status_kind:'finished'}),'danger');
assert.equal(ui.taskTone({status:'partial',status_kind:'finished'}),'attention');
assert.equal(ui.taskTone({status:'cancelled',status_kind:'finished'}),'neutral');
assert.equal(ui.taskTone({status:'succeeded',status_kind:'finished',delivery:'unknown'}),'unknown');
assert.equal(ui.taskTone({status:'succeeded',status_kind:'finished'}),'ok');
assert.equal(ui.outcomeTone({status:'failed'},{kind:'attention'}),'danger');
assert.equal(ui.outcomeTone({status:'succeeded',waits:['x']},{kind:'attention'}),'attention');
assert.equal(ui.outcomeTone({status:'succeeded',status_kind:'finished'},{kind:''}),'ok');
assert.equal(ui.toolName('subscription_engine'),'구독 CLI 실행');assert.equal(ui.toolName('anything-else'),'도구 실행');
assert.equal(ui.eventTone('failed'),'danger');assert.equal(ui.eventStatusText('running'),'실행 중');
assert.match(ui.taskOutcome({waits:['첫째','둘째']}).text,/첫째\n둘째/);
console.log(JSON.stringify({ok:true}));
""")
        self.assertEqual(json.loads(out.strip().splitlines()[-1]), {"ok": True})


class ConversationTrace(unittest.TestCase):
    def test_tasks_view_is_a_chronological_turn_trace(self):
        tasks = HTML[HTML.index('id="view-tasks"'):HTML.index('id="view-records"')]
        self.assertIn('<ol id="task-list" class="trace"', tasks)
        self.assertNotIn('id="task-detail"', tasks)
        self.assertNotIn("master-detail", tasks)
        self.assertIn("(a.started_at||0)-(b.started_at||0)", APP)
        self.assertIn("'어떻게 처리했는지'", APP)
        self.assertIn("'기술 정보'", APP)

    def test_trace_is_derived_from_observed_state_only(self):
        out = node_run(r"""
const assert=require('node:assert/strict');const ui=require(process.argv[1]);
const events=[{id:1,tool:'subscription_engine',status:'running',created:10,summary:'s'},{id:2,tool:'web_search',status:'succeeded',created:11,summary:'s'},{id:3,tool:'subscription_engine',status:'succeeded',created:12,summary:'s'}];
const done=ui.semanticTrace({status:'succeeded',status_kind:'finished',observed_at:13,events:[events[0],{...events[0],id:4,status:'succeeded',created:12}]});
assert.deepEqual(done.map(r=>r.text),['구독 CLI 실행 완료','답변'],'running->succeeded of one tool collapses to one line');
assert.deepEqual(done[0].eventIds,[1,4]);
const mixed=ui.semanticTrace({status:'succeeded',status_kind:'finished',observed_at:13,events});
assert.equal(mixed.length,4,'different tools are not merged');
const failed=ui.semanticTrace({status:'failed',status_kind:'finished',observed_at:5,events:[{id:9,tool:'subscription_engine',status:'running',created:1,summary:'a'},{id:10,tool:'subscription_engine',status:'failed',created:4,summary:'폴더 없음'}]});
assert.deepEqual(failed.map(r=>[r.text,r.tone]),[['구독 CLI 실행 실패','danger'],['실패','danger']]);
assert.equal(failed[0].note,'폴더 없음');
const running=ui.semanticTrace({status:'running',status_kind:'active',events:[events[0]]});
assert.deepEqual(running.map(r=>r.text),['구독 CLI 실행 시작'],'an active Work gets no invented closing line');
const unknown=ui.semanticTrace({status:'succeeded',status_kind:'finished',delivery:'unknown',observed_at:3,events:[]});
assert.deepEqual(unknown.map(r=>[r.text,r.tone]),[['전달 여부 알 수 없음','unknown']],'unknown delivery is not shown as an answer');
const partial=ui.semanticTrace({status:'partial',status_kind:'finished',observed_at:3,events:[]});
assert.deepEqual(partial.map(r=>r.tone),['attention']);
assert.equal(ui.relationText('retry'),'다시 시도한 요청');assert.equal(ui.relationText('correction'),'이전 요청을 정정');
assert.equal(ui.relationText('something-new'),'이전 요청과 연결됨');
console.log(JSON.stringify({ok:true}));
""")
        self.assertEqual(json.loads(out.strip().splitlines()[-1]), {"ok": True})

    def test_relations_are_never_inferred_in_the_renderer(self):
        render = APP[APP.index("function renderTasks(){"):APP.index("function recordKey(item){")]
        self.assertIn("if(task.relation){", render)
        self.assertIn("sameAsPrevious=!task.relation&&", render)
        self.assertIn("'바로 앞과 같은 내용'", render)
        self.assertNotIn("relation:{", render)


if __name__ == "__main__":
    unittest.main()

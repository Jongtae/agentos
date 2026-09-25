"""UI-QUALITY-01 (#558): presentation rules the local web must keep.

Static checks read the shipped files; behaviour checks execute the real
``app.js`` under Node with a minimal DOM stand-in, the same way
``tests/test_settings_ui.py`` does.  Nothing here contacts a server.
"""
import json
import re
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
const assert=require('node:assert/strict');const ui=require(process.argv[1]);ui.setLanguage('ko');
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
const source=part('const LANGUAGES=','function normalizeEndpoint(')+part('function formatTimeParts(','const TOOL_NAMES=')+part('function element(','function focusSettingsTarget(');
const ctx={document:{createElement:tag=>new Element(tag)},console};vm.createContext(ctx);vm.runInContext(source,ctx);vm.runInContext("setLanguage('ko')",ctx);
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
const assert=require('node:assert/strict');const ui=require(process.argv[1]);ui.setLanguage('ko');
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
const assert=require('node:assert/strict');const ui=require(process.argv[1]);ui.setLanguage('ko');
const events=[{id:1,tool:'subscription_engine',status:'running',created:10,summary:'s'},{id:2,tool:'web_search',status:'succeeded',created:11,summary:'s'},{id:3,tool:'subscription_engine',status:'succeeded',created:12,summary:'s'}];
const done=ui.semanticTrace({status:'succeeded',status_kind:'finished',response:'answer',observed_at:13,events:[events[0],{...events[0],id:4,status:'succeeded',created:12}]});
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
        self.assertIn("'직전 요청과 같은 내용'", render)
        self.assertNotIn("relation:{", render)


HANGUL = re.compile("[가-힣]")


def ui_source_keys():
    """Korean source strings the UI can show, collected from the shipped files."""
    body = APP[:APP.index("// I18N-CATALOG-START")] + APP[APP.index("// I18N-CATALOG-END"):]
    keys = set(m.group(1) for m in re.finditer(r"\bt\('((?:[^'\\]|\\.)*)'", body) if HANGUL.search(m.group(1)))
    for table in ("TOOL_NAMES", "RELATION_TEXT", "OFFLINE_MESSAGE", "providers", "providerNames",
                  "CONNECTOR_STATES", "CONNECTOR_NAMES", "CONNECTOR_PURPOSE", "ENGINE_IDLE_STATE"):
        line = body[body.index("const " + table + "="):]
        line = line[:line.index("\n")]
        keys |= {v for v in re.findall(r"'([^']*)'", line) if HANGUL.search(v)}
    records = body[body.index("function recordItems("):body.index("function filterLocalRecords(")]
    keys |= {v for v in re.findall(r"label:[^,]*?'([^']*[가-힣][^']*)'", records)}
    for text in re.findall(r">([^<>]*)<", HTML):
        if HANGUL.search(text.strip()):
            keys.add(text.strip())
    keys |= {v for v in re.findall(r'(?:placeholder|aria-label|title)="([^"]*)"', HTML) if HANGUL.search(v)}
    keys.discard("한국어")
    return sorted(keys)


class Languages(unittest.TestCase):
    def catalog(self):
        return json.loads(node_run("process.stdout.write(JSON.stringify(require(process.argv[1]).I18N))"))

    def test_every_ui_string_has_english_chinese_and_japanese(self):
        catalog = self.catalog()
        keys = ui_source_keys()
        self.assertGreater(len(keys), 400)
        for language in ("en", "zh-CN", "ja"):
            missing = [key for key in keys if not str(catalog[language].get(key, "")).strip() and key != "개"]
            self.assertEqual(missing, [], language)

    def test_translations_keep_placeholders_and_english_has_no_korean(self):
        catalog = self.catalog()
        for key in catalog["en"]:
            wanted = sorted(re.findall(r"\{(\w+)\}", key))
            for language in ("en", "zh-CN", "ja"):
                self.assertEqual(sorted(re.findall(r"\{(\w+)\}", catalog[language][key])), wanted, (language, key))
            if key != "한국어":
                self.assertIsNone(HANGUL.search(catalog["en"][key]), key)

    def test_english_is_the_default_and_the_owner_can_choose(self):
        self.assertEqual(HTML.count("data-language-select"), 2)
        self.assertIn("localStorage.setItem('agentos-language'", APP)
        self.assertIn("setLanguage(storedLanguage()||'en')", APP)
        out = node_run(r"""
const assert=require('node:assert/strict');const ui=require(process.argv[1]);
assert.deepEqual(Object.keys(ui.LANGUAGES),['en','ko','zh-CN','ja']);
assert.equal(ui.statusText({status_kind:'active'}),'In progress');
assert.equal(ui.relationText('retry'),'Retry of');
assert.equal(ui.routeText({kind:'subscription',engine:'codex',status:'failed'}),'Codex subscription CLI · ran but failed');
assert.equal(ui.t('{count}개 일치',{count:3}),'3 matches');
assert.equal(ui.t('server text the catalog does not know'),'server text the catalog does not know','unknown text is shown as sent');
ui.setLanguage('ja');assert.equal(ui.statusText({status_kind:'active'}),'進行中');
ui.setLanguage('zh-CN');assert.equal(ui.statusText({status_kind:'active'}),'进行中');
ui.setLanguage('ko');assert.equal(ui.statusText({status_kind:'active'}),'진행 중');
assert.equal(ui.setLanguage('xx'),'en','an unknown choice falls back to English');
console.log(JSON.stringify({ok:true}));
""")
        self.assertEqual(json.loads(out.strip().splitlines()[-1]), {"ok": True})


class ReviewRegressions(unittest.TestCase):
    """Findings from the independent review of PR #563."""

    def test_ready_badge_requires_a_connected_ai_and_unknown_state_is_not_green(self):
        self.assertIn("home.state==='ready'?(home.model_connected?['준비됨','ok']:['AI 연결 안 됨','attention']):['상태 알 수 없음','unknown']", APP)

    def test_sharing_policy_allowed_only_for_the_model_it_was_approved_for(self):
        self.assertIn("contextPolicyApprovedFor===contextPolicyModelKey()", APP)
        self.assertIn("contextPolicyApprovedFor=contextPolicyModelKey()", APP)
        self.assertNotIn("contextPolicyApprovedThisSession", APP)

    def test_closing_line_never_claims_an_answer_that_was_not_given(self):
        out = node_run(r"""
const assert=require('node:assert/strict');const ui=require(process.argv[1]);
assert.deepEqual(ui.semanticTrace({status:'succeeded',status_kind:'finished',observed_at:2,events:[]}).map(r=>r.text),['Done'],'no response means Done, not Answered');
assert.deepEqual(ui.semanticTrace({status:'succeeded',status_kind:'finished',response:'x',observed_at:2,events:[]}).map(r=>r.text),['Answered']);
assert.deepEqual(ui.semanticTrace({status:'awaiting_connection',status_kind:'attention',waits:['연결 대기'],observed_at:2,events:[]}),[],'a waiting Work gets no closing line');
assert.equal(ui.outcomeTone({status:'cancelled'},ui.taskOutcome({status:'cancelled'})),ui.taskTone({status:'cancelled',status_kind:'finished'}),'badge and body share one tone');
const blocks=ui.parseRichText('see https://example.invalid/x.');
assert.deepEqual(blocks[0].lines[0].map(p=>[p.type,p.text]),[['text','see '],['link','https://example.invalid/x'],['text','.']]);
console.log(JSON.stringify({ok:true}));
""")
        self.assertEqual(json.loads(out.strip().splitlines()[-1]), {"ok": True})

    def test_japanese_removal_confirm_does_not_say_delete(self):
        catalog = json.loads(node_run("process.stdout.write(JSON.stringify(require(process.argv[1]).I18N))"))
        self.assertNotIn("削除", catalog["ja"]["제거 확인"])
        self.assertIn("外す", catalog["ja"]["제거 확인"])

    def test_open_disclosures_do_not_rebuild_the_trace(self):
        render = APP[APP.index("function renderTasks(){"):APP.index("function recordKey(item){")]
        fingerprint = render[render.index("const fingerprint=JSON.stringify("):]
        fingerprint = fingerprint[:fingerprint.index(";")]
        self.assertNotIn("openTraces", fingerprint)
        self.assertNotIn("openTechnical", fingerprint)
        self.assertNotIn("openOriginals", fingerprint)
        disclosure = APP[APP.index("function traceDisclosure("):APP.index("function renderTasks(){")]
        self.assertIn("if(box.open===openSet.has(task.id))return;", disclosure)
        self.assertNotIn("taskRenderFingerprint=''", disclosure)


class TaskScopedContext(unittest.TestCase):
    """web/AGENTS.md: original request context is task-scoped and explicitly expanded."""

    def test_trace_defaults_to_the_redacted_title_and_expands_the_original_per_turn(self):
        render = APP[APP.index("function renderTasks(){"):APP.index("function recordKey(item){")]
        self.assertIn("const summary=String(task.title||'').trim()", render)
        self.assertIn("user.append(element('p',summary||t('요청 내용 없음'),'turn-text'))", render)
        self.assertNotIn("task.request||task.title", render)
        self.assertNotIn("target.request", render)
        # the raw request is added to the DOM only inside the opened disclosure
        self.assertIn("if(box.open)box.append(element('p',original,'turn-text'))", render)
        self.assertIn("box.open=openOriginals.has(task.id)", render)


class TraceNavigation(unittest.TestCase):
    """#572: long traces open at the latest exchange with a bounded, day-grouped window."""

    def test_window_keeps_the_latest_turns_newest_first_by_day(self):
        out = node_run(r"""
const assert=require('node:assert/strict');const ui=require(process.argv[1]);ui.setLanguage('ko');
const now=Date.UTC(2026,8,25,12,0,0),day=86400;
const tasks=[];for(let i=0;i<45;i++)tasks.push({id:'t'+i,started_at:now/1000-(44-i)*3*3600});
const view=ui.traceWindow(tasks,20,new Set(),now);
assert.equal(view.hidden,25,'older turns are hidden, not dropped');
const shown=view.groups.flatMap(g=>g.tasks.map(x=>x.id));
assert.equal(shown.length,20);assert.equal(shown[0],'t44','#578: the latest turn is first');
assert.deepEqual(shown,tasks.slice(25).map(x=>x.id).reverse(),'newest first');
assert(view.groups.length>=2,'turns are split by day');
assert.equal(view.groups[0].label,'오늘','today comes first');
const yesterday=view.groups.find(g=>g.label==='어제');assert(yesterday,'yesterday is labelled');
assert(view.groups.indexOf(yesterday)>0,'past days come after today');
const collapsed=ui.traceWindow(tasks,20,new Set([yesterday.key,ui.dayKey(now/1000)]),now);
assert.equal(collapsed.groups.find(g=>g.key===yesterday.key).collapsed,true,'a past day can be collapsed');
assert.equal(collapsed.groups[0].collapsed,false,'today is never collapsed');
assert.equal(ui.traceWindow(tasks.slice(0,5),20,new Set(),now).hidden,0);
ui.setLanguage('en');assert.equal(ui.dayLabel(now/1000,now),'today');
console.log(JSON.stringify({ok:true}));
""")
        self.assertEqual(json.loads(out.strip().splitlines()[-1]), {"ok": True})

    def test_render_puts_older_at_the_end_and_keeps_the_reading_position(self):
        render = APP[APP.index("function renderTasks(){"):APP.index("let traceObserver=null;")]
        self.assertIn("traceWindow(ordered,traceLimit,collapsedDays)", render)
        self.assertLess(render.index("'trace-top'"), render.index("group.tasks.forEach"), "the top sentinel precedes the turns")
        self.assertGreater(render.index("'trace-earlier'"), render.index("group.tasks.forEach"), "older turns load at the end")
        self.assertIn("if(anchor&&!traceNearTop)keepTraceAnchor(list,anchor);", render)
        self.assertIn("anchor=traceNearTop?null:traceAnchor(list)", render, "no layout read while at the top")
        self.assertIn("if(run!==traceAnchorRun||!same.isConnected)return;", APP, "stale settling frames stop")
        self.assertIn("if(grew&&!traceNearTop){traceUnseen+=arrived;", render)
        self.assertIn("window.scrollTo(0,0)", APP, "jump goes to the newest exchange at the top")
        self.assertIn('id="trace-jump-latest"', HTML)
        self.assertIn("IntersectionObserver", APP)
        self.assertIn("content-visibility:auto", CSS.replace(" ", ""))
        focus = APP[APP.index("function focusTurn("):APP.index("function turnHead(")]
        self.assertIn("traceLimit=Math.max(traceLimit,ordered.length-position)", focus, "a relation jump reveals an older turn")
        self.assertIn("grew=Boolean(previousNewest)&&newest.id!==previousNewest.id", render, "growth is detected by the newest turn, not the capped count")
        self.assertIn("previous=ordered[index-1]", render, "repeat detection uses the full chronological order")
        self.assertIn("user,agent", render, "inside one exchange the request still precedes the answer")
        self.assertNotIn(":last-of-type", APP)
        self.assertNotIn("trace-end", APP + CSS)


class EngineAuthUi(unittest.TestCase):
    """#571: login state, token entry and recovery are explicit and never echo the token."""

    def test_recovery_is_shown_only_for_auth_failures_and_switches_are_explicit(self):
        self.assertIn("if(task.failure_class==='auth')body.append(authRecovery(task))", APP)
        recovery = APP[APP.index("function authRecovery("):APP.index("function turnHead(")]
        self.assertIn("'/api/subscription-engines/login-status'", recovery)
        self.assertIn("'/api/ai-route',{route:'direct-api'}", recovery)
        self.assertIn("engine.login?.state!=='signed-in'", recovery, "only signed-in CLIs are offered")
        self.assertNotIn("setInterval", recovery)

    def test_token_form_is_write_only(self):
        form = APP[APP.index("function claudeTokenForm("):APP.index("// Routes are listed once in #active-ai")]
        self.assertIn("input.type='password'", form)
        self.assertIn("input.autocomplete='off'", form)
        self.assertIn("input.value=''", form)
        self.assertNotIn("engine.credential)input.value", form)
        self.assertNotIn("token:engine", form)

    def test_token_save_reports_next_to_the_field(self):
        """#578: success and failure appear beside the token field, and survive the re-render."""
        out = node_run(r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');const app=fs.readFileSync(process.argv[1],'utf8');
class El{constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.className='';this._t='';this.value='';this.classList={toggle:(c,on)=>{this.cls=this.cls||new Set();on?this.cls.add(c):this.cls.delete(c);},contains:c=>Boolean(this.cls&&this.cls.has(c))};}
 set textContent(v){this._t=String(v);this.children=[];} get textContent(){return this._t+this.children.map(c=>c.textContent).join(' ');}
 append(...n){this.children.push(...n);} setAttribute(k,v){this.attrs[k]=v;} focus(){}}
const all=n=>n.children.flatMap(c=>[c,...all(c)]);const active=new El('div');
const document={createElement:t=>new El(t)};const part=(a,b)=>app.slice(app.indexOf(a),app.indexOf(b));
const source=part('const LANGUAGES=','function normalizeEndpoint(')+part('function element(','function setError(')+part('const ENGINE_LOGIN_TEXT=','function renderSubscriptionEngines(');
let fail=null,refreshed=0;const ctx={document,$:()=>active,console,busy:async(b,fn)=>fn(),refresh:async()=>{refreshed++;},
 api:async(path,body)=>{if(fail)throw new Error(fail);return {engines:[{id:'claude-code',login:{state:'token-saved'}}]};}};
vm.createContext(ctx);vm.runInContext(source,ctx);vm.runInContext("setLanguage('ko')",ctx);
const statusOf=form=>all(form).find(n=>n.attrs.role==='status');
let form=ctx.claudeTokenForm({credential:false});const input=all(form).find(n=>n.tag==='input');
input.value='';form.onsubmit({preventDefault(){}});
assert.match(statusOf(form).textContent,/붙여 넣은 뒤/,'an empty save explains itself');
fail='경로를 찾을 수 없습니다.';input.value='tok-123456789012345678901';
(async()=>{await form.onsubmit({preventDefault(){}});
 assert.match(statusOf(form).textContent,/저장하지 못했습니다: 경로를 찾을 수 없습니다/,'a failed save is shown beside the field');
 assert.equal(refreshed,0);
 fail=null;await form.onsubmit({preventDefault(){}});assert.equal(refreshed,1);
 form=ctx.claudeTokenForm({credential:true});
 assert.match(statusOf(form).textContent,/토큰을 저장했습니다\. 토큰 저장됨/,'the saved notice survives the re-render with the login state');
 assert.equal(statusOf(ctx.claudeTokenForm({credential:true})).textContent,'','the notice is shown once');
 console.log(JSON.stringify({ok:true}));})().catch(e=>{console.error(e);process.exit(1);});
""")
        self.assertEqual(json.loads(out.strip().splitlines()[-1]), {"ok": True})


if __name__ == "__main__":
    unittest.main()

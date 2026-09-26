from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).parents[1] / "src" / "personal_agent" / "web"
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "style.css").read_text(encoding="utf-8")


DOM_CHECKS = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const app=fs.readFileSync(process.argv[1],'utf8'),ids=new Map();
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.className='';this.hidden=false;this._text='';}
 set id(value){this._id=value;ids.set(value,this);} get id(){return this._id;}
 set textContent(value){this._text=String(value);this.children=[];} get textContent(){return this._text+this.children.map(node=>typeof node==='string'?node:node.textContent).join('');}
 append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}
 setAttribute(key,value){this.attrs[key]=value;} focus(){} get isConnected(){return true;}
 get classList(){const node=this;return {toggle(name,on){node._cls=Boolean(on);},add(){},remove(){},contains:()=>Boolean(node._cls)};}
 querySelector(selector){return descendants(this).find(node=>selector[0]==='.'?node.className.split(' ').includes(selector.slice(1)):node.tag===selector)||null;}
}
function descendants(node){return node.children.flatMap(child=>typeof child==='string'?[]:[child,...descendants(child)]);}
for(const id of ['active-ai','ai-chooser-list','ai-chooser-consequence','ai-chooser-feedback','ai-chooser-apply','telegram-current','telegram-change','telegram-form','telegram-status','telegram-feedback','telegram-submit','disconnect','new-pair','telegram-pair','connector-controls','connector-feedback','google-disconnect','google-disconnect-cancel','google-disconnect-confirm','google-disconnect-retry'])new Element('div').id=id;
const $=id=>ids.get(id),document={getElementById:$,createElement:tag=>new Element(tag)};
const part=(start,end)=>app.slice(app.indexOf(start),app.indexOf(end));
const source=part('const LANGUAGES=','function normalizeEndpoint(')+
 part('function element(', 'function setError(')+
 part('const providers=', 'let claimed=')+
 part('function renderExecutionConnection(', 'function renderSubscriptionEngines(')+
 part('const DECISION_TRANSPORT_LABEL=','function decisionFailedSuffix(')+part('function decisionActiveTitle(','function decisionCheckText(')+
 part('function renderTelegram(', "$('telegram-change').onclick");
const calls=[];let refreshes=0,failRoute=false;
const ctx={document,$,telegramDraftOpen:false,console,api:async(path,body)=>{calls.push({path,body});if(failRoute)throw new Error('switch refused');return {};},refresh:async()=>{refreshes++;},busy:async(button,fn)=>fn(),setError:(id,error)=>{$(id).textContent=error?.message||String(error||'');},setFeedback:(id,text)=>{$(id).textContent=text||'';}};
vm.createContext(ctx);vm.runInContext(source,ctx);vm.runInContext("setLanguage('ko')",ctx);
const buttonIn=id=>descendants($(id)).find(node=>node.tag==='button');
// #619: one Main AI card with a subordinate Judgment AI line; the chooser keeps a fixed order.
const dialog=new Element('dialog');dialog.id='ai-chooser';dialog.open=false;dialog.showModal=()=>{dialog.open=true;};dialog.close=()=>{dialog.open=false;dialog.onclose&&dialog.onclose();};
const api=(id,extra={})=>({id,kind:'api',name:{openai:'OpenAI',anthropic:'Anthropic',openrouter:'OpenRouter'}[id],destination:{openai:'api.openai.com',anthropic:'api.anthropic.com',openrouter:'openrouter.ai'}[id],model:'m-'+id,key:{saved:false,saved_at:null,pending:false},check:null,...extra});
const sub=(id,extra={})=>({id,kind:'subscription',name:{codex:'Codex','claude-code':'Claude Code'}[id],destination:{codex:'OpenAI (Codex 구독 계정)','claude-code':'Anthropic (Claude Code 구독 계정)'}[id],installed:true,login:{state:'signed-in',checked_at:1700000000},credential:false,check:null,...extra});
const routesFor=(overrides={})=>['codex','claude-code','openai','anthropic','openrouter'].map(id=>overrides[id]||(id==='codex'||id==='claude-code'?sub(id):api(id)));
const follow={openai:{available:true,model:'gpt-4o-mini',destination:'api.openai.com'},anthropic:{available:true,model:'claude-haiku-4-5',destination:'api.anthropic.com'},openrouter:{available:true,model:'openai/gpt-4o-mini',destination:'openrouter.ai'},'claude-code':{available:true,model:'haiku',destination:'Anthropic (Claude Code 구독 계정)'},codex:{available:false,reason:'Codex는 따라갈 수 없습니다.'}};
const settingsFor=(current,overrides={},decision={})=>({model:{provider:'anthropic',endpoint:'https://api.anthropic.com',model:'m-anthropic'},model_ready:true,subscription_engines:{selected:['codex','claude-code'].includes(current)?current:'',engines:[]},
 main_ai:{current,order:['codex','claude-code','openai','anthropic','openrouter'],routes:routesFor(overrides),last_check:{state:'ok',checked_at:1700000000}},
 decision_route:{mode:'follow_main',main:current,follow:follow[current]||{available:false,reason:'-'},follow_candidates:follow,active:{transport:'direct_api',source:'follow',requested_model:'claude-haiku-4-5',destination:'api.anthropic.com',available:true},...decision}});
const rowsOf=()=>descendants($('active-ai')).filter(node=>node.className.startsWith('settings-row')&&node.tag==='div'&&node.className.split(' ')[0]==='settings-row');
const titles=()=>descendants($('active-ai')).filter(node=>node.className==='settings-row-title').map(node=>node.textContent);
const buttonsIn=id=>descendants($(id)).filter(node=>node.tag==='button');const same=(a,b,m)=>assert.equal(JSON.stringify(a),JSON.stringify(b),m);
const currentCount=()=>descendants($('active-ai')).filter(node=>node.className==='settings-state active'&&node.textContent==='현재 사용 중').length;
let settings=settingsFor('anthropic',{anthropic:api('anthropic',{key:{saved:true,saved_at:1700000000,pending:false}})});
ctx.renderExecutionConnection(settings);const changeButton=buttonsIn('active-ai').find(node=>node.textContent==='변경');ctx.renderExecutionConnection(JSON.parse(JSON.stringify(settings)));
assert.equal(buttonsIn('active-ai').find(node=>node.textContent==='변경'),changeButton,'unchanged AI polling preserves the focused action node');
same(titles(),['Anthropic · API','판단 AI (대화 해석)'],'exactly one Main AI card with a subordinate Judgment AI line');
assert.equal(currentCount(),1,'exactly one current route');
assert($('active-ai').textContent.includes('기본 AI와 같은 계정의 가벼운 모델 (claude-haiku-4-5)'),'the Judgment AI line names its light model');
assert($('active-ai').textContent.includes('전송 대상: api.anthropic.com'),'destinations stay on the scan path');
assert.equal(descendants($('active-ai')).filter(node=>node.tag==='details').length,1,'no per-row disclosures; one card-level 기술 세부 정보');
assert(!$('active-ai').textContent.includes('다른 선택지'),'no second list of routes on the card');
(async()=>{
 // 확인 re-probes without switching.
 const check=buttonsIn('active-ai').find(node=>node.textContent==='확인');await check.onclick({currentTarget:check});
 same(calls.pop(),{path:'/api/main-ai/check',body:{}});
 // The chooser opens as a modal dialog with the fixed order, whatever is current.
 ctx.openAiChooser(changeButton);assert(dialog.open,'the chooser is a modal <dialog>');
 const order=()=>descendants($('ai-chooser-list')).filter(node=>node.tag==='input'&&node.type==='radio').map(node=>node.value);
 same(order(),['codex','claude-code','openai','anthropic','openrouter']);
 const radio=id=>descendants($('ai-chooser-list')).find(node=>node.tag==='input'&&node.type==='radio'&&node.value===id);
 assert(radio('anthropic').checked,'the current Main AI is preselected');
 // A saved key is 저장됨 · date; never an input or a partial value.
 const anthropicRow=descendants($('ai-chooser-list')).find(node=>node.className==='chooser-row'&&node.textContent.includes('Anthropic'));
 assert(anthropicRow.textContent.includes('키 저장됨 ·'),'saved key shows 저장됨 · date');
 assert(!descendants(anthropicRow).some(node=>node.tag==='input'&&node.type==='password'),'no key input while a key is saved');
 assert(descendants(anthropicRow).some(node=>node.tag==='button'&&node.textContent==='바꾸기')&&descendants(anthropicRow).some(node=>node.tag==='button'&&node.textContent==='지우기'));
 // A provider without a key cannot be chosen until a key is saved.
 assert(radio('openai').disabled,'no key, not selectable');
 // Selecting another route never re-sorts; the consequence lists both destinations.
 radio('claude-code').onchange();same(order(),['codex','claude-code','openai','anthropic','openrouter'],'switching the selection does not reorder');
 assert($('ai-chooser-consequence').textContent.includes('기본 AI 전송 대상: Anthropic (Claude Code 구독 계정)'));
 assert($('ai-chooser-consequence').textContent.includes('판단 AI도 함께 바뀝니다 → haiku'));
 radio('codex').onchange();assert($('ai-chooser-consequence').textContent.includes('따라갈 수 없어 설정 안 됨이 됩니다'),'Codex: follow is unavailable with the reason');
 // 확인하고 사용: one request; failure stays in the dialog and changes nothing.
 failRoute=true;await ctx.applyAiChoice($('ai-chooser-apply'));
 same(calls.pop(),{path:'/api/main-ai/activate',body:{route:'codex'}});
 assert(dialog.open,'a refused switch keeps the chooser open');assert.equal($('ai-chooser-feedback').textContent,'switch refused');
 failRoute=false;refreshes=0;await ctx.applyAiChoice($('ai-chooser-apply'));
 assert(!dialog.open,'a passed switch closes the chooser');assert.equal(refreshes,1);
 // Key entry: 키 입력 opens a password field in place; saving never activates.
 ctx.openAiChooser(changeButton);const keyButton=descendants($('ai-chooser-list')).find(node=>node.tag==='button'&&node.textContent==='키 입력');keyButton.onclick({currentTarget:keyButton});
 const keyForm=descendants($('ai-chooser-list')).find(node=>node.tag==='form'&&node.className==='chooser-key');const keyInput=descendants(keyForm).find(node=>node.tag==='input');
 assert.equal(keyInput.type,'password');keyInput.value='sk-synthetic';calls.length=0;await keyForm.onsubmit({preventDefault(){}});
 same(calls,[{path:'/api/main-ai/key',body:{provider:'openai',key:'sk-synthetic'}}],'saving a key is its own request and never activates');
 dialog.close();
 // Needs-attention states stay on the card.
 ctx.renderExecutionConnection(settingsFor('anthropic',{},{active:{transport:'off',source:'follow',available:false},follow_check:{state:'failed',failure:'auth'}}));
 assert.equal(currentCount(),0,'a route without a saved key is not presented as in use');
 assert($('active-ai').textContent.includes('저장된 API 키가 없어 요청이 실패합니다'));
 assert($('active-ai').textContent.includes('기본 AI를 따라 gpt-4o-mini을(를) 쓰려면 확인이 필요합니다')||$('active-ai').textContent.includes('쓰려면 확인이 필요합니다'),'a failed judgment probe is shown as needing attention');
 ctx.renderExecutionConnection(settingsFor('codex',{},{follow:follow.codex,active:{transport:'off',source:'follow',available:false}}));
 assert($('active-ai').textContent.includes('기본 AI를 따라갈 수 없습니다: Codex는 따라갈 수 없습니다.'),'Codex shows why the Judgment AI is not set');
 ctx.renderExecutionConnection(settingsFor('codex',{codex:sub('codex',{installed:false})}));
 assert($('active-ai').textContent.includes('선택한 CLI를 찾지 못했습니다'));assert.equal(currentCount(),0,'a missing CLI is not presented as in use');
 ctx.renderExecutionConnection({...settingsFor('other'),model:{provider:'ollama',endpoint:'http://127.0.0.1:11434',model:'llama'},main_ai:{...settingsFor('other').main_ai,other:{provider:'ollama',model:'llama',destination:'http://127.0.0.1:11434'}}});
 assert($('active-ai').textContent.includes('확인 필요')&&$('active-ai').textContent.includes('변경 목록에 없습니다'),'an existing Ollama route renders truthfully');
 ctx.renderExecutionConnection(settingsFor(''));
 assert.equal(currentCount(),0);assert($('active-ai').textContent.includes('작업을 실행할 AI가 없습니다'));
})().catch(error=>{console.error(error);process.exit(1);});
ctx.renderTelegram({telegram:{enabled:true,paired:true,username:'fixture'},telegram_status:{message:'ok'}});
const telegramButton=buttonIn('telegram-current');ctx.renderTelegram({telegram:{enabled:true,paired:true,username:'fixture'},telegram_status:{message:'ok'}});
assert.equal(buttonIn('telegram-current'),telegramButton,'unchanged Telegram polling preserves its action node');
// Connection state matrix (#506): every contract state, an unknown value and a long label.
const stateOf=row=>descendants(row).find(node=>node.className.startsWith('settings-state'));
const actionOf=row=>descendants(row).find(node=>node.tag==='a'&&node.className.includes('settings-row-action'));
const matrix=[
 [{connector_id:'google-gmail-read',label:'Gmail',state:'connected',required_scopes:['gmail.readonly'],connect_path:'/google-gmail'},'Google Gmail','연결됨','active','다시 연결'],
 [{connector_id:'google-calendar',label:'google-calendar',state:'disconnected',required_scopes:['calendar.readonly'],connect_path:'/google-calendar'},'Google Calendar','연결 안 됨','neutral','연결'],
 [{connector_id:'google-calendar-write',label:'Google Calendar 일정 만들기',state:'reauth_required',required_scopes:['calendar.events'],connect_path:'/google-calendar'},'Google Calendar 일정 만들기','다시 인증 필요','attention','다시 연결'],
 [{connector_id:'fixture-blocked',label:'Blocked',state:'blocked',required_scopes:[],connect_path:'/blocked'},'Blocked','차단됨','attention',null],
 [{connector_id:'fixture-unknown',label:'Unknown',state:'surprising',required_scopes:[],connect_path:'/unknown'},'Unknown','확인 필요','attention',null],
 [{connector_id:'google-drive-read',label:'Google Drive',state:'disconnected',required_scopes:['drive.file'],connect_path:'',connect_hint:'Telegram에서 Google Drive 파일을 요청하면 연결 링크를 보냅니다.',detail_state:'expired'},'Google Drive','연결 안 됨','neutral',null],
];
for(const [connector,name,label,kind,action] of matrix){
 ctx.renderConnectors([connector]);const row=$('connector-controls').children[0],title=descendants(row).find(node=>node.className==='settings-row-title');
 assert.equal(title.textContent,name,`${connector.connector_id} shows the owner service name`);
 assert.equal(stateOf(row).textContent,label,`${connector.connector_id} state label`);assert(stateOf(row).className.endsWith(kind),`${connector.connector_id} tone`);
 const link=actionOf(row);if(action){assert.equal(link?.textContent,action,`${connector.connector_id} offers one action`);assert.equal(link.href,connector.connect_path);}else assert.equal(link,undefined,`${connector.connector_id} offers no action it cannot complete`);
 const details=descendants(row).find(node=>node.tag==='details');assert(details&&details.textContent.includes(`연결 ID: ${connector.connector_id}`),'connector ID only inside 세부 정보');
 assert(!descendants(row).filter(node=>node.tag!=='details'&&!descendants(details).includes(node)&&node!==details).some(node=>node._text&&node._text.includes(connector.connector_id)&&connector.connector_id!==name),'no raw connector ID outside 세부 정보');
}
ctx.renderConnectors([matrix[5][0]]);assert($('connector-controls').textContent.includes('Telegram에서 Google Drive'),'Drive explains where a connection starts');assert($('connector-controls').textContent.includes('세부 상태: expired'),'the raw Drive handoff state stays inspectable');
ctx.renderConnectors([]);assert($('connector-controls').textContent.includes('연결할 수 있는 Google 서비스가 없습니다'));
assert(app.includes("'ArrowLeft','ArrowRight'"),'settings tabs handle horizontal arrow keys');
console.log('settings DOM regressions passed');
"""


def test_settings_uses_goal_oriented_owner_language():
    assert "AI 연결" in HTML
    assert "파일 · 저장" in HTML
    assert "외부 연결" in HTML
    assert "내 기록" not in HTML
    assert "AI가 찾아볼 폴더" in HTML
    assert "정리 결과 만들기" in HTML
    assert "결과 저장 폴더" in HTML
    assert "<textarea id=\"root-paths\"" not in HTML
    assert "프로젝트는 대화와 결과" in HTML
    assert "현재 상태를 먼저 확인" in HTML


def test_ai_chooser_switches_in_one_explicit_request():
    # #619 AC5: 확인하고 사용 probes and switches; keys are saved separately.
    assert "api('/api/main-ai/activate',body)" in APP
    assert "api('/api/main-ai/key'" in APP
    assert "/api/model/test" not in APP
    assert 'id="ai-chooser-apply" class="primary" type="button">확인하고 사용<' in HTML


def test_refresh_does_not_replace_active_editing_surfaces():
    assert "contextDraftDirty" in APP
    assert "if(!contextDraftDirty" in APP
    assert "telegramDraftOpen" in APP
    assert "if(!telegramDraftOpen)" in APP


def test_mobile_checkbox_is_not_full_width_input():
    assert ".check-row input{width:auto" in CSS
    assert "@media(max-width:620px)" in CSS


def test_owner_flow_has_two_destinations_and_optional_projects():
    # #562: 작업 현황 and 설정 only; 내 기록 is no longer a destination.
    for destination in ('data-view="tasks"', 'data-view="settings"'):
        assert HTML.count(destination) == 1
    assert HTML.count('data-view="') == 2
    assert 'data-view="records"' not in HTML
    assert 'id="chat-form"' not in HTML
    # Projects stay reachable as optional grouping under 파일 · 저장.
    files = HTML[HTML.index('id="settings-files"'):HTML.index('id="settings-external"')]
    assert 'id="projects"' in files and 'id="workspace-form"' in files
    assert "setup-checklist" not in APP


def test_guidance_preserves_observed_progress_and_ai_state_boundaries():
    assert "어떻게 처리했는지" in APP
    assert "관찰된 실행 이벤트가 없습니다" in APP
    assert "결과 정보 없음" in APP
    assert "모델 정보 미제공" in APP
    assert "실제 실행은 작업에서 확인" in APP


def test_settings_uses_one_accessible_preferences_navigation():
    assert 'id="settings-nav" class="settings-nav" role="tablist"' in HTML
    for key, panel in (("ai", "settings-ai"), ("files", "settings-files"),
                       ("external", "settings-external"), ("privacy", "settings-privacy")):
        assert f'data-settings="{key}"' in HTML
        assert f'aria-controls="{panel}"' in HTML
        assert f'id="{panel}" class="settings-pane" role="tabpanel"' in HTML
    assert ".settings-layout{" in CSS
    assert "@media(max-width:620px)" in CSS


def test_setting_rows_translate_internal_connection_ids_and_keep_details_disclosed():
    assert "function settingsRow(" in APP
    assert "CONNECTOR_NAMES" in APP
    assert "CAPABILITY_NAMES" not in APP
    assert "settingsDisclosure(t('세부 정보'),view.lines)" in APP
    assert "element('strong',capability.id)" not in APP
    assert "(connector?.required_scopes||[]).join(', ')" in APP
    assert ".settings-row-action.destructive" in CSS


def test_exact_items_keep_each_owner_record_type_distinct():
    for label in ("t('메모')", "t('기억')", "t('저장된 결과')", "t('저장 전 기억 후보')"):
        assert label in APP
    # Deletion stays type-bound: a saved result never goes to a Memory endpoint.
    assert "const kind=item.kind==='artifact'?'results':'memories'" in APP
    # Temporary material keeps its own Settings list and delete confirmation.
    assert "api('/api/context-inbox/delete',{id:item.id})" in APP
    assert "function showRecords()" not in APP


def test_settings_renderers_preserve_polling_controls_and_truthful_route_state():
    node = shutil.which("node")
    if node is None:
        return
    subprocess.run(
        [node, "-e", DOM_CHECKS, str(ROOT / "app.js")],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )


FOLDER_CHECKS = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const app=fs.readFileSync(process.argv[1],'utf8'),ids=new Map();
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.className='';this.hidden=false;this.value='';this._text='';this.listeners={};}
 set id(value){this._id=value;ids.set(value,this);} get id(){return this._id;}
 set textContent(value){this._text=String(value);this.children=[];} get textContent(){return this._text+this.children.map(node=>typeof node==='string'?node:node.textContent).join('');}
 append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}
 setAttribute(key,value){this.attrs[key]=value;} addEventListener(type,fn){this.listeners[type]=fn;} focus(){focused=this;}
 querySelector(selector){return descendants(this).find(node=>selector[0]==='.'?node.className.split(' ').includes(selector.slice(1)):node.tag===selector.split('[')[0])||null;}
}
let focused=null;
function descendants(node){return node.children.flatMap(child=>typeof child==='string'?[]:[child,...descendants(child)]);}
for(const id of ['root-list','roots-feedback','root-path-input','roots-form','file-workspace-list','file-workspace-form','workspace-reference-list','workspace-reference-input','workspace-reference-add','file-workspace-path','file-workspace-feedback','file-workspace-cancel','document-boundary','document-boundary-feedback'])new Element('div').id=id;
const $=id=>ids.get(id),document={getElementById:$,createElement:tag=>new Element(tag)};
const part=(start,end)=>app.slice(app.indexOf(start),app.indexOf(end));
const source=part('const LANGUAGES=','function normalizeEndpoint(')+part('function element(', 'function focusSettingsTarget(')+part('let savedRoots=', 'function renderTelegram(');
const calls=[];let refreshes=0,refuse=null,revisions=0,gate=null;
const ctx={document,$,console,invalidateRootsLoad:()=>revisions++,invalidateFileWorkspaceLoad:()=>revisions++,
 api:async(path,body)=>{calls.push({path,body});if(gate)await gate;if(refuse)throw new Error(refuse);if(path==='/api/files/roots')return {roots:body.paths.map(path=>({path}))};if(path==='/api/file-workspace')return {references:body.references.map(path=>({path})),workspace:body.workspace};return {};},
 refresh:async()=>{refreshes++;},busy:async(button,fn)=>fn(),setError:(id,error)=>{$(id).textContent=error?.message||String(error||'');},setFeedback:(id,text)=>{$(id).textContent=text||'';}};
vm.createContext(ctx);vm.runInContext(source,ctx);vm.runInContext("setLanguage('ko')",ctx);
const same=(actual,expected,message)=>assert.equal(JSON.stringify(actual),JSON.stringify(expected),message);
const buttons=id=>descendants($(id)).filter(node=>node.tag==='button');
const press=async(id,label)=>{const button=buttons(id).find(node=>node.textContent===label);assert(button,`${label} in ${id}`);await button.onclick({currentTarget:button});};
(async()=>{
 ctx.renderRootList([]);
 assert($('root-list').textContent.includes('아직 연결한 폴더가 없습니다'),'empty AI folder list is explicit');
 ctx.renderRootList(['/tmp/a/Research','/tmp/b/Notes']);
 assert($('root-list').textContent.includes('Research'),'folder name is the row title');
 assert($('root-list').textContent.includes('/tmp/a/Research'),'full path stays visible');
 assert.equal(descendants($('root-list')).filter(node=>node.className==='settings-state active'&&node.textContent==='연결됨').length,2,'state column shows connection state');
 assert($('root-list').textContent.includes('읽기 전용'),'role is in the description');
 const first=buttons('root-list')[0];ctx.renderRootList(['/tmp/a/Research','/tmp/b/Notes']);
 assert.equal(buttons('root-list')[0],first,'unchanged polling keeps row nodes');
 $('root-path-input').value='  /tmp/c/New  ';
 await $('roots-form').onsubmit({preventDefault(){},submitter:new Element('button')});
 same(calls.pop(),{path:'/api/files/roots',body:{paths:['/tmp/a/Research','/tmp/b/Notes','/tmp/c/New']}},'add posts the full resulting list');
 assert.equal($('root-path-input').value,'','accepted draft is cleared');
 refuse='전체 홈이나 시스템 루트 대신 작업용 하위 폴더를 선택하세요.';
 $('root-path-input').value='/Users/me';
 await $('roots-form').onsubmit({preventDefault(){},submitter:new Element('button')});
 assert.equal($('roots-feedback').textContent,refuse,'refusal shown next to the input');
 assert.equal($('root-path-input').value,'/Users/me','refused draft is kept');
 assert.equal(focused,$('root-path-input'),'focus returns to the refused input');
 refuse=null;const before=calls.length;
 await press('root-list','제거');
 assert.equal(calls.length,before,'remove asks before saving');
 assert.equal(focused?.textContent,'제거 확인','confirm button receives focus');
 assert($('root-list').textContent.includes('제거할까요?'));
 await press('root-list','취소');assert(!$('root-list').textContent.includes('제거할까요?'));
 await press('root-list','제거');await press('root-list','제거 확인');
 same(calls.pop().body,{paths:['/tmp/b/Notes','/tmp/c/New']},'remove drops exactly one folder');
 assert($('roots-feedback').textContent.includes('파일은 그대로'),'removal says files are untouched');
 const blockedReason='인증 정보나 시스템 설정이 있는 폴더는 연결할 수 없습니다';
 ctx.renderRootList([{path:'/tmp/blocked-a',blocked:blockedReason},{path:'/tmp/blocked-b',blocked:blockedReason},{path:'/tmp/ordinary'}]);
 await press('root-list','제거');await press('root-list','제거 확인');
 same(calls.pop().body,{paths:['/tmp/blocked-b','/tmp/ordinary']},'removing one blocked root keeps the other blocked root in the request');
 ctx.renderRootList(['/tmp/b/Notes','/tmp/c/New']);
 $('root-path-input').value='/tmp/b/Notes/';const count=calls.length;
 await $('roots-form').onsubmit({preventDefault(){},submitter:new Element('button')});
 assert.equal(calls.length,count,'duplicate with trailing slash is not posted');
 let release;gate=new Promise(resolve=>release=resolve);
 await press('root-list','제거');const inflight=descendants($('root-list')).find(node=>node.textContent==='제거 확인');const pendingSave=inflight.onclick({currentTarget:inflight});
 $('root-path-input').value='/tmp/d/Other';await $('roots-form').onsubmit({preventDefault(){},submitter:new Element('button')});
 const rootPosts=calls.filter(call=>call.path==='/api/files/roots');
 assert.equal(JSON.stringify(rootPosts[rootPosts.length-1].body),JSON.stringify({paths:['/tmp/c/New']}),'second save is refused while one is in flight');
 assert($('roots-feedback').textContent.includes('저장하는 중'),'blocked add explains why');
 gate=null;release();await pendingSave;
 assert.equal(calls.filter(call=>call.path==='/api/files/roots').length,rootPosts.length,'no stale second POST after the first lands');
 ctx.renderRootList(['/tmp/c/New']);await press('root-list','제거');ctx.renderRootList([]);ctx.renderRootList(['/tmp/c/New']);
 assert(!$('root-list').textContent.includes('제거할까요?'),'stale pending removal is cleared when the folder disappears');

 ctx.renderRootList([{path:'/tmp/ok'},{path:'/Users/me/.ssh',blocked:'인증 정보나 시스템 설정이 있는 폴더는 연결할 수 없습니다'}]);
 assert.equal(descendants($('root-list')).filter(node=>node.className==='settings-state attention'&&node.textContent==='사용 중지됨').length,1,'a stored folder the rules now forbid is disclosed, not hidden');
 assert($('root-list').textContent.includes('인증 정보나 시스템 설정'),'the block reason is shown');
 ctx.renderFileWorkspace({references:[{path:'/Users/me/.aws',blocked:'인증 정보나 시스템 설정이 있는 폴더는 연결할 수 없습니다'}],workspace:'/tmp/out',workspace_blocked:null});
 assert($('file-workspace-list').textContent.includes('사용 중지됨'));
 ctx.renderFileWorkspace({references:[],workspace:null});
 assert($('file-workspace-list').textContent.includes('설정하지 않음'));
 assert.equal($('file-workspace-form').hidden,true,'edit form closed by default');
 await press('file-workspace-list','설정');
 assert.equal($('file-workspace-form').hidden,false);assert.equal($('file-workspace-list').hidden,true);
 $('workspace-reference-input').value='/tmp/src/Meetings';ctx.addWorkspaceReference();
 ctx.renderFileWorkspace({references:[{path:'/tmp/other'}],workspace:'/tmp/other-out'});
 assert.equal($('file-workspace-form').hidden,false,'polling does not close an open edit');
 assert($('workspace-reference-list').textContent.includes('Meetings'),'polling keeps the draft references');
 assert($('workspace-reference-list').textContent.includes('저장 전'),'unsaved source is marked as not yet saved');
 $('file-workspace-path').value='';
 await $('file-workspace-form').onsubmit({preventDefault(){},submitter:new Element('button')});
 assert.equal($('file-workspace-feedback').textContent,'결과 저장 폴더를 입력하세요.');
 $('workspace-reference-input').value='/tmp/src/Typed';$('file-workspace-path').value='/tmp/out/Results';
 await $('file-workspace-form').onsubmit({preventDefault(){},submitter:new Element('button')});
 same(calls.pop(),{path:'/api/file-workspace',body:{references:['/tmp/src/Meetings','/tmp/src/Typed'],workspace:'/tmp/out/Results'}},'paired save includes a typed but unadded source');
 assert.equal($('file-workspace-form').hidden,true);
 assert($('file-workspace-list').textContent.includes('결과 저장 · 새 파일'));
 assert($('file-workspace-list').textContent.includes('원본 · 읽기 전용'));
 await press('file-workspace-list','폴더 변경');
 refuse='참고 폴더와 관리 작업공간은 겹치지 않게 연결하세요.';$('file-workspace-path').value='/tmp/src/Meetings';
 await $('file-workspace-form').onsubmit({preventDefault(){},submitter:new Element('button')});
 assert.equal($('file-workspace-feedback').textContent,refuse);assert.equal($('file-workspace-form').hidden,false,'refused edit stays open');
 refuse=null;$('file-workspace-cancel').onclick();assert.equal($('file-workspace-form').hidden,true);
 assert.equal(focused?.textContent,'폴더 변경','closing the editor returns focus to its opener');

 ctx.renderDocumentBoundary({external_model:true,approved:false});
 assert($('document-boundary').textContent.includes('승인 필요'));
 await press('document-boundary','전송 승인');
 same(calls.pop(),{path:'/api/documents/approval',body:{approved:true}});
 ctx.renderDocumentBoundary({external_model:true,approved:true});assert($('document-boundary').textContent.includes('승인됨'));
 ctx.renderDocumentBoundary({external_model:false});assert($('document-boundary').textContent.includes('보내지 않음'));
 console.log('folder settings DOM checks passed');
})().catch(error=>{console.error(error);process.exit(1);});
"""


def test_folder_settings_render_rows_and_preserve_drafts():
    node = shutil.which("node")
    if node is None:
        return
    subprocess.run(
        [node, "-e", FOLDER_CHECKS, str(ROOT / "app.js")],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )

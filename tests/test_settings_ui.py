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
 setAttribute(key,value){this.attrs[key]=value;}
 querySelector(selector){return descendants(this).find(node=>selector[0]==='.'?node.className.split(' ').includes(selector.slice(1)):node.tag===selector)||null;}
}
function descendants(node){return node.children.flatMap(child=>typeof child==='string'?[]:[child,...descendants(child)]);}
for(const id of ['active-ai','telegram-current','telegram-change','telegram-form','telegram-status','telegram-feedback','telegram-submit','disconnect','new-pair','telegram-pair','capability-controls','connector-controls'])new Element('div').id=id;
const $=id=>ids.get(id),document={getElementById:$,createElement:tag=>new Element(tag)};
const part=(start,end)=>app.slice(app.indexOf(start),app.indexOf(end));
const source=part('const LANGUAGES=','function normalizeEndpoint(')+part('function capabilityActions(', 'function clearMobileDetailWhenEmpty(')+
 part('function element(', 'function setError(')+
 part('const providers=', 'let claimed=')+
 part('function renderExecutionConnection(', 'function renderSubscriptionEngines(')+
 part('const CONNECTOR_STATES=', 'async function requestCapabilityDraft(')+
 part('function renderTelegram(', 'function renderCapabilityPreview(');
const calls=[];let refreshes=0,failRoute=false;
const ctx={document,$,telegramDraftOpen:false,requestCapabilityDraft:async()=>{},console,api:async(path,body)=>{calls.push({path,body});if(failRoute)throw new Error('switch refused');return {};},refresh:async()=>{refreshes++;},busy:async(button,fn)=>fn(),setError:(id,error)=>{$(id).textContent=error?.message||String(error||'');},setFeedback:(id,text)=>{$(id).textContent=text||'';}};
vm.createContext(ctx);vm.runInContext(source,ctx);vm.runInContext("setLanguage('ko')",ctx);
const buttonIn=id=>descendants($(id)).find(node=>node.tag==='button');
const settings={model:{provider:'ollama',endpoint:'http://127.0.0.1:11434',model:'stored-api-model'},model_ready:true,subscription_engines:{selected:'codex',engines:[{id:'codex',name:'Codex',installed:true,connected:true}]}};
ctx.renderExecutionConnection(settings);const routeButton=buttonIn('active-ai');ctx.renderExecutionConnection(JSON.parse(JSON.stringify(settings)));
assert.equal(buttonIn('active-ai'),routeButton,'unchanged AI polling preserves the focused action node');
assert($( 'active-ai').textContent.includes('모델 정보 미제공'),'active CLI does not inherit the inactive API model identity');
assert($('active-ai').textContent.includes('Ollama'),'provider title remains provider-specific');
const buttonsIn=id=>descendants($(id)).filter(node=>node.tag==='button');
const useApi=buttonsIn('active-ai').find(node=>node.textContent==='이 연결 사용');
assert(useApi,'a verified direct API offers an explicit switch');
assert($('active-ai').textContent.includes('사용 가능'));
const currentCount=()=>descendants($('active-ai')).filter(node=>node.className==='settings-state active'&&node.textContent==='현재 사용 중').length;
assert.equal(currentCount(),1,'exactly one current route');
assert.equal(descendants($('active-ai')).find(node=>node.className==='settings-row-title').textContent,'Codex','the current route is listed first');
assert(!$('active-ai').textContent.includes('직접 API를 설정하거나 테스트해도'),'dense precedence prose is gone');
(async()=>{
 await useApi.onclick({currentTarget:useApi});
 assert.equal(JSON.stringify(calls),JSON.stringify([{path:'/api/ai-route',body:{route:'direct-api'}}]));assert.equal(refreshes,1);
 failRoute=true;await useApi.onclick({currentTarget:useApi});
 assert.equal(refreshes,1,'a refused switch does not claim a new route');
 assert.equal($('active-ai-feedback').textContent,'switch refused');
 failRoute=false;await useApi.onclick({currentTarget:useApi});assert.equal($('active-ai-feedback').textContent,'','a new attempt clears the stale refusal');
 ctx.renderExecutionConnection({...settings,model_ready:false});
 assert(!buttonsIn('active-ai').some(node=>node.textContent==='이 연결 사용'),'an unverified API cannot be selected');
 assert(buttonsIn('active-ai').some(node=>node.textContent==='연결 확인'));
 assert($('active-ai').textContent.includes('확인 필요'),'unverified saved API shows the attention state');assert($('active-ai').textContent.includes('저장돼 있지만 확인되지 않았습니다'),'configured is stated separately from verified');
 ctx.renderExecutionConnection({...settings,subscription_engines:{selected:'',engines:settings.subscription_engines.engines.map(e=>({...e,connected:false}))}});
 assert.equal(currentCount(),1,'direct API is the one current route once selected');
 assert.equal(descendants($('active-ai')).find(node=>node.className==='settings-row-title').textContent,'Ollama');
 ctx.renderExecutionConnection({...settings,subscription_engines:{selected:'',engines:settings.subscription_engines.engines}});
 const back=buttonsIn('active-ai').find(node=>node.textContent==='이 CLI 사용');assert(back,'switching back to a CLI is offered in the same list with a verb label');
 calls.length=0;await back.onclick({currentTarget:back});
 assert.equal(JSON.stringify(calls),JSON.stringify([{path:'/api/subscription-engines/connect',body:{engine:'codex',officially_authenticated:true}}]));
 ctx.renderExecutionConnection({model:{},model_ready:false,subscription_engines:{selected:'',engines:[]}});
 assert.equal(currentCount(),0);assert($('active-ai').textContent.includes('사용할 AI 연결이 설정되지 않았습니다'));
 ctx.renderExecutionConnection({...settings,subscription_engines:{selected:'codex',engines:[{id:'codex',name:'Codex',installed:false,connected:true}]}});
 assert($('active-ai').textContent.includes('선택한 CLI를 찾지 못했습니다'));assert.equal(currentCount(),0,'a missing CLI is not presented as in use');
 ctx.renderExecutionConnection({...settings,model_ready:false,subscription_engines:{selected:'',engines:[]}});
 assert($('active-ai').textContent.includes('연결 확인이 필요합니다'));assert.equal(currentCount(),0,'an unverified current API is not presented as in use');
 ctx.renderExecutionConnection({...settings,subscription_engines:{selected:'retired-engine',engines:settings.subscription_engines.engines}});
 assert($('active-ai').textContent.includes('선택된 연결을 이 컴퓨터에서 확인할 수 없습니다'),'an unknown selection is surfaced');
})().catch(error=>{console.error(error);process.exit(1);});
ctx.renderTelegram({telegram:{enabled:true,paired:true,username:'fixture'},telegram_status:{message:'ok'}});
const telegramButton=buttonIn('telegram-current');ctx.renderTelegram({telegram:{enabled:true,paired:true,username:'fixture'},telegram_status:{message:'ok'}});
assert.equal(buttonIn('telegram-current'),telegramButton,'unchanged Telegram polling preserves its action node');
const states={available:['사용 가능','neutral'],'connected-disabled':['사용 안 함','neutral'],enabled:['사용 설정됨','active'],paused:['일시 정지','neutral'],'auth-required':['다시 인증 필요','attention'],error:['오류','attention'],disconnected:['연결 안 됨','neutral']};
for(const [state,[label,kind]] of Object.entries(states)){ctx.renderCapabilities({capabilities:[{id:'google-drive-read',kind:'mcp',state}]});const row=$('capability-controls').children[0],stateNode=descendants(row).find(node=>node.className.startsWith('settings-state'));assert(row.textContent.includes(label),`${state} keeps its lifecycle label`);assert(stateNode.className.endsWith(kind),`${state} uses the correct status tone`);assert(row.textContent.includes(`상태: ${state}`),`${state} remains in technical disclosure`);assert(!row.textContent.includes('로컬 기능 권한'),'Google capability must never be described as local');}
ctx.renderCapabilities({capabilities:[{id:'google-drive-read',kind:'mcp',state:'disconnected'}]});
assert($('capability-controls').textContent.includes('외부 연결 권한 · Google'));
assert($('capability-controls').textContent.includes('연결 안 됨'));
ctx.renderConnectors([{connector_id:'google-calendar',label:'google-calendar',state:'disconnected'}]);
assert($('connector-controls').textContent.includes('Google Calendar'));
assert(!descendants($('connector-controls')).find(node=>node.className==='settings-row-title').textContent.includes('google-calendar'));
assert(app.includes("'ArrowLeft','ArrowRight'"),'settings tabs handle horizontal arrow keys');
console.log('settings DOM regressions passed');
"""


def test_settings_uses_goal_oriented_owner_language():
    assert "AI 연결" in HTML
    assert "파일 · 저장" in HTML
    assert "외부 연결" in HTML
    assert "내 기록" in HTML
    assert "AI가 찾아볼 폴더" in HTML
    assert "정리 결과 만들기" in HTML
    assert "결과 저장 폴더" in HTML
    assert "<textarea id=\"root-paths\"" not in HTML
    assert "프로젝트는 대화와 결과" in HTML
    assert "현재 상태를 먼저 확인" in HTML


def test_model_flow_tests_exact_draft_before_apply_and_requires_new_destination_key():
    assert "api('/api/model/test',value)" in APP
    assert "modelGuard.test" in APP
    assert "modelGuard.apply" in APP
    assert "credential_revision" in APP
    assert "apply-model" in HTML
    assert "require_key" in APP


def test_refresh_does_not_replace_active_editing_surfaces():
    assert "contextDraftDirty" in APP
    assert "if(!contextDraftDirty" in APP
    assert "if(!modelLoaded)" in APP
    assert "telegramDraftOpen" in APP
    assert "if(!telegramDraftOpen)" in APP


def test_mobile_checkbox_is_not_full_width_input():
    assert ".check-row input{width:auto" in CSS
    assert "@media(max-width:620px)" in CSS


def test_owner_flow_has_three_management_destinations_and_optional_projects():
    for destination in ('data-view="tasks"', 'data-view="records"', 'data-view="settings"'):
        assert HTML.count(destination) == 1
    assert 'id="chat-form"' not in HTML
    assert 'id="projects"' in HTML
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
    assert "CAPABILITY_NAMES" in APP
    assert "settingsDisclosure(t('세부 정보'),lines)" in APP
    assert "element('strong',capability.id)" not in APP
    assert "(connector.required_scopes||[]).join(', ')" in APP
    assert ".settings-row-action.destructive" in CSS


def test_records_surface_each_owner_record_type():
    for label in ("메모", "기억", "임시 자료", "저장된 결과"):
        assert label in APP
    assert "recordItems" in APP
    assert "deleteKind:'results'" in APP
    assert "function showRecords()" in APP


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

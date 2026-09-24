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
for(const id of ['active-ai','telegram-current','telegram-change','telegram-form','telegram-status','disconnect','new-pair','telegram-pair','capability-controls','connector-controls'])new Element('div').id=id;
const $=id=>ids.get(id),document={getElementById:$,createElement:tag=>new Element(tag)};
const part=(start,end)=>app.slice(app.indexOf(start),app.indexOf(end));
const source=part('function capabilityActions(', 'function clearMobileDetailWhenEmpty(')+
 part('function element(', 'function setError(')+
 part('const providers=', 'let claimed=')+
 part('function renderExecutionConnection(', 'function renderSubscriptionEngines(')+
 part('const CONNECTOR_STATES=', 'async function requestCapabilityDraft(')+
 part('function renderTelegram(', 'function renderCapabilityPreview(');
const calls=[];let refreshes=0,failRoute=false;
const ctx={document,$,telegramDraftOpen:false,requestCapabilityDraft:async()=>{},console,api:async(path,body)=>{calls.push({path,body});if(failRoute)throw new Error('switch refused');return {};},refresh:async()=>{refreshes++;},busy:async(button,fn)=>fn(),setError:(id,error)=>{$(id).textContent=error?.message||String(error||'');}};
vm.createContext(ctx);vm.runInContext(source,ctx);
const buttonIn=id=>descendants($(id)).find(node=>node.tag==='button');
const settings={model:{provider:'ollama',endpoint:'http://127.0.0.1:11434',model:'stored-api-model'},model_ready:true,subscription_engines:{selected:'codex',engines:[{id:'codex',name:'Codex',installed:true,connected:true}]}};
ctx.renderExecutionConnection(settings);const routeButton=buttonIn('active-ai');ctx.renderExecutionConnection(JSON.parse(JSON.stringify(settings)));
assert.equal(buttonIn('active-ai'),routeButton,'unchanged AI polling preserves the focused action node');
assert($( 'active-ai').textContent.includes('모델 정보 미제공'),'active CLI does not inherit the inactive API model identity');
assert($('active-ai').textContent.includes('Ollama'),'provider title remains provider-specific');
const buttonsIn=id=>descendants($(id)).filter(node=>node.tag==='button');
const useApi=buttonsIn('active-ai').find(node=>node.textContent==='이 연결 사용');
assert(useApi,'a verified direct API offers an explicit switch');
assert($('active-ai').textContent.includes('사용 가능 · 현재 사용 안 함'));
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
 assert($('active-ai').textContent.includes('설정됨 · 확인 필요'));
 ctx.renderExecutionConnection({...settings,subscription_engines:{selected:'',engines:settings.subscription_engines.engines.map(e=>({...e,connected:false}))}});
 assert($('active-ai').textContent.includes('현재 요청 경로'),'direct API is shown as the current route once selected');
 assert(!$('active-ai').textContent.includes('현재 사용 안 함'));
})().catch(error=>{console.error(error);process.exit(1);});
ctx.renderTelegram({telegram:{enabled:true,paired:true,username:'fixture'},telegram_status:{message:'ok'}});
const telegramButton=buttonIn('telegram-current');ctx.renderTelegram({telegram:{enabled:true,paired:true,username:'fixture'},telegram_status:{message:'ok'}});
assert.equal(buttonIn('telegram-current'),telegramButton,'unchanged Telegram polling preserves its action node');
const states={available:['사용 가능','neutral'],'connected-disabled':['연결됨 · 사용 안 함','neutral'],enabled:['사용 설정됨','active'],paused:['일시 정지','neutral'],'auth-required':['다시 인증 필요','attention'],error:['오류','attention'],disconnected:['연결 안 됨','neutral']};
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
    assert "참고 폴더" in HTML
    assert "결과 저장 폴더" in HTML
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
    assert "관찰된 과정" in APP
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
    assert "settingsDisclosure('세부 정보',lines)" in APP
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

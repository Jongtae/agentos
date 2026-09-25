"""DECISION-ROUTE-01 / #580 (and the #506 route-choice rows): Settings › AI › 대화 해석.

Evidence class: DOM behaviour of the shipped renderer in a Node VM with
synthetic settings read models and a recording API stub.  No server, model,
CLI or credential is involved.
"""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).parents[1] / "src" / "personal_agent" / "web"
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "app.js").read_text(encoding="utf-8")

DOM_CHECKS = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const app=fs.readFileSync(process.argv[1],'utf8'),ids=new Map();
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.className='';this.hidden=false;this._text='';this.value='';this.checked=false;}
 set id(value){this._id=value;ids.set(value,this);} get id(){return this._id;}
 set textContent(value){this._text=String(value);this.children=[];} get textContent(){return this._text+this.children.map(node=>typeof node==='string'?node:node.textContent).join('');}
 append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}
 setAttribute(key,value){this.attrs[key]=value;} getAttribute(key){return this.attrs[key];} focus(){}
 get classList(){const node=this;return {toggle(){},add(){},remove(){},contains:()=>false};}
 querySelector(selector){return descendants(this).find(node=>selector[0]==='.'?node.className.split(' ').includes(selector.slice(1)):node.tag===selector)||null;}
}
function descendants(node){return node.children.flatMap(child=>typeof child==='string'?[]:[child,...descendants(child)]);}
new Element('section').id='decision-route';
const $=id=>ids.get(id),document={getElementById:$,createElement:tag=>new Element(tag)};
const part=(start,end)=>app.slice(app.indexOf(start),app.indexOf(end));
const source=part('const LANGUAGES=','function normalizeEndpoint(')+part('const DECISION_ROLE=','function traceWindow(')+
 part('function element(','function setError(')+part('const DECISION_TRANSPORT_LABEL=','function openMobileDetail(');
const calls=[];let refreshes=0,failNext=null;
const ctx={document,$,console,safeTime:()=>'T',
 api:async(path,body)=>{calls.push({path,body});if(failNext){const error=failNext;failNext=null;throw error;}return {model_override:true};},
 refresh:async()=>{refreshes++;},busy:async(button,fn)=>fn(),
 setError:(id,error)=>{$(id).textContent=error?.message||String(error||'');},setFeedback:(id,text)=>{$(id).textContent=text||'';}};
vm.createContext(ctx);vm.runInContext(source,ctx);vm.runInContext("setLanguage('ko')",ctx);
const box=()=>$('decision-route'),all=()=>descendants(box());
const rows=()=>all().filter(node=>node.className==='settings-row');
const rowTitled=title=>rows().find(row=>descendants(row).some(node=>node.className==='settings-row-title'&&node.textContent===title));
const stateOf=row=>descendants(row).find(node=>node.className.startsWith('settings-state'));
const button=(row,label)=>descendants(row).find(node=>node.tag==='button'&&node.textContent===label);
const engines=(selection='unchecked')=>[
 {id:'codex',name:'Codex',installed:true,login:'signed-in',model_selection:selection,destination:'OpenAI (Codex 구독 계정)',isolated_deployment:false},
 {id:'claude-code',name:'Claude Code',installed:false,login:'unchecked',model_selection:'unchecked',destination:'Anthropic (Claude Code 구독 계정)',isolated_deployment:false}];
const base=(active,extra={})=>({decision_route:{active,suite_version:'decision-qualification/1',
 direct_api:{configured:true,model:'gpt-4o-mini',destination:'api.openai.com'},jev:{configured:false,model:'jev-latest',destination:'api.typesafe.ai'},
 subscription_cli:engines(extra.selection),...extra.route}});
(async()=>{
 // Default: the #417 default route, role-labelled, never "현재 사용 중".
 ctx.renderDecisionRoute(base({transport:'direct_api',source:'default',requested_model:'gpt-4o-mini',destination:'api.openai.com'}));
 assert.equal(calls.length,0,'rendering calls nothing');
 assert(box().textContent.includes('대화 해석'));
 const method=rowTitled('사용 방식');assert.equal(stateOf(method).textContent,'대화 해석에 사용 중');assert(stateOf(method).className.endsWith('active'));
 assert(method.textContent.includes('OpenAI API · gpt-4o-mini'));assert(method.textContent.includes('전송 대상: api.openai.com'));
 assert(!box().textContent.includes('현재 사용 중'),'the decision route is never presented as the current Work AI');
 assert(box().textContent.includes('여기서 바꿔도 작업 실행 AI는 바뀌지 않습니다'),'the role boundary is stated');
 const jevRow=rowTitled('Jev (TypeSafe) · jev-latest');assert.equal(stateOf(jevRow).textContent,'키 필요');assert(jevRow.textContent.includes('api.typesafe.ai'));
 assert.equal(stateOf(rowTitled('구독 AI · Codex')).textContent,'선택 가능','configured-but-inactive is distinct from active');
 assert.equal(stateOf(rowTitled('구독 AI · Claude Code')).textContent,'설치 안 됨');
 assert(!rowTitled('OpenAI API · gpt-4o-mini'),'the active option is not listed again as another choice');
 const first=box().children[1];ctx.renderDecisionRoute(base({transport:'direct_api',source:'default',requested_model:'gpt-4o-mini',destination:'api.openai.com'}));
 assert.equal(box().children[1],first,'unchanged polling keeps the nodes (and focus)');
 // Saving a Jev key is a separate action from using it.
 await button(jevRow,'설정').onclick({currentTarget:button(jevRow,'설정')});
 const keyForm=descendants(rowTitled('Jev (TypeSafe) · jev-latest')).find(node=>node.tag==='form');assert(keyForm,'the key form opens in place');
 const [keyInput]=descendants(keyForm).filter(node=>node.tag==='input');assert.equal(keyInput.type,'password');keyInput.value='ts-key';
 await keyForm.onsubmit({preventDefault(){}});
 assert.deepEqual(JSON.parse(JSON.stringify(calls)),[{path:'/api/decision-route/credential',body:{transport:'jev',key:'ts-key',model:'jev-latest'}}]);
 assert(!calls.some(call=>call.path==='/api/decision-route/activate'),'saving never activates');
 assert($('decision-route-feedback').textContent.includes('아직 대화 해석 경로는 바뀌지 않았습니다'));
 // Subscription AI: before the CLI's model flag is verified only the engine default is offered.
 calls.length=0;box().dataset.state='';ctx.renderDecisionRoute(base({transport:'direct_api',source:'default',destination:'api.openai.com'}));
 let codex=rowTitled('구독 AI · Codex');await button(codex,'사용').onclick({currentTarget:button(codex,'사용')});
 let form=descendants(rowTitled('구독 AI · Codex')).find(node=>node.tag==='form');
 let radios=descendants(form).filter(node=>node.tag==='input'&&node.type==='radio').map(node=>node.value);
 assert.deepEqual(radios,['engine_default'],'explicit / lowest_qualified are not offered before verification');
 assert(descendants(form).some(node=>node.tag==='button'&&node.textContent==='모델 지정 지원 확인'));
 await form.onsubmit({preventDefault(){}});
 assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1))),{path:'/api/decision-route/activate',body:{transport:'subscription_cli',engine:'codex',model_policy:'engine_default'}});
 // Unsupported: still only the engine default, with the limitation stated.
 box().dataset.state='';ctx.renderDecisionRoute(base({transport:'direct_api',source:'default',destination:'api.openai.com'},{selection:'unsupported'}));
 codex=rowTitled('구독 AI · Codex');await button(codex,'사용').onclick({currentTarget:button(codex,'사용')});
 form=descendants(rowTitled('구독 AI · Codex')).find(node=>node.tag==='form');
 assert.deepEqual(descendants(form).filter(node=>node.type==='radio').map(node=>node.value),['engine_default']);
 assert(form.textContent.includes('모델 지정을 지원하지 않아'));
 // Supported: all three policies; lowest_qualified sends the owner's ordered candidates.
 ctx.openDecisionChooser('');box().dataset.state='';ctx.renderDecisionRoute(base({transport:'direct_api',source:'default',destination:'api.openai.com'},{selection:'supported'}));
 codex=rowTitled('구독 AI · Codex');await button(codex,'사용').onclick({currentTarget:button(codex,'사용')});
 form=descendants(rowTitled('구독 AI · Codex')).find(node=>node.tag==='form');
 const inputs=descendants(form).filter(node=>node.tag==='input');
 assert.deepEqual(inputs.filter(node=>node.type==='radio').map(node=>node.value),['lowest_qualified','explicit','engine_default']);
 inputs.find(node=>node.value==='engine_default').checked=false;inputs.find(node=>node.value==='lowest_qualified').checked=true;
 inputs.filter(node=>node.type==='text')[1].value=' tiny, small ';
 failNext=new Error('후보 모델 중 적격성 검사를 통과한 모델이 없습니다. 현재 대화 해석 경로는 그대로 유지됩니다.');const before=refreshes;
 await form.onsubmit({preventDefault(){}});
 assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1).body)),{transport:'subscription_cli',engine:'codex',model_policy:'lowest_qualified',candidates:'tiny, small'});
 assert.equal(refreshes,before,'a refused switch does not refresh into a new route');
 assert($('decision-route-feedback').textContent.includes('그대로 유지'));
 assert.equal(stateOf(rowTitled('사용 방식')).textContent,'대화 해석에 사용 중','the previous route is still shown as active');
 // An owner-selected subscription route: engine, policy, requested vs observed model.
 box().dataset.state='';ctx.openDecisionChooser('');
 ctx.renderDecisionRoute(base({transport:'subscription_cli',source:'owner',engine:'codex',model_policy:'lowest_qualified',requested_model:'small',available:true,
  destination:'OpenAI (Codex 구독 계정)',cli_version:'codex-cli 0.153.4',qualification:{suite_version:'decision-qualification/1',model:'small'}},
  {selection:'supported',route:{subscription_cli:engines('supported').map(e=>e.id==='codex'?{...e,check:{state:'active',observed_model:'not reported',checked_at:1}}:e)}}));
 assert.equal(stateOf(rowTitled('구독 엔진')).textContent,'Codex');
 const policyRow=rowTitled('판단 모델');assert.equal(stateOf(policyRow).textContent,'자동 · 적합한 가벼운 모델');
 assert(policyRow.textContent.includes('요청 모델: small'),'the requested model is named, not presented as observed');
 assert(!rowTitled('구독 AI · Codex'),'the active engine is not listed again as another choice');
 assert(rowTitled('구독 AI · Claude Code'));
 assert(rowTitled('사용 방식').textContent.includes('OpenAI (Codex 구독 계정)'));
 const change=button(policyRow,'변경');await change.onclick({currentTarget:change});
 const policyForm=descendants(rowTitled('판단 모델')).find(node=>node.tag==='form');
 assert.deepEqual(descendants(policyForm).filter(node=>node.type==='radio').map(node=>node.value),['lowest_qualified','explicit','engine_default'],'the policy is changed in place');
 ctx.openDecisionChooser('cli:codex');
 assert(rowTitled('OpenAI API · gpt-4o-mini'),'the direct API becomes another choice');
 const details=all().find(node=>node.tag==='details').textContent;
 for(const line of ['역할: 대화 해석(DecisionEngine) — 작업 실행 경로와 별개','경로: subscription_cli','모델 정책: lowest_qualified','요청 모델: small','관측 모델: 보고되지 않음','적격성 검사: decision-qualification/1 통과 (small)','CLI 버전: codex-cli 0.153.4'])
  assert(details.includes(line),line);
 // Needs attention and failed checks stay visible; nothing is silently switched.
 box().dataset.state='';
 ctx.renderDecisionRoute(base({transport:'jev',source:'owner',requested_model:'jev-latest',available:false,destination:'api.typesafe.ai'},
  {route:{jev:{configured:false,model:'jev-latest',destination:'api.typesafe.ai',check:{state:'failed',failure:'auth',checked_at:1}}}}));
 assert.equal(stateOf(rowTitled('사용 방식')).textContent,'확인 필요');
 box().dataset.state='';
 ctx.renderDecisionRoute(base({transport:'direct_api',source:'owner',destination:'api.openai.com',available:true},
  {route:{jev:{configured:true,model:'jev-latest',destination:'api.typesafe.ai',check:{state:'failed',failure:'auth',checked_at:1}}}}));
 assert(rowTitled('Jev (TypeSafe) · jev-latest').textContent.includes('마지막 확인: 실패 · 로그인 또는 인증 실패'));
 assert.equal(stateOf(rowTitled('Jev (TypeSafe) · jev-latest')).textContent,'선택 가능');
 // An active direct route keeps its decision-only key manageable (rotate / remove).
 box().dataset.state='';calls.length=0;
 ctx.renderDecisionRoute(base({transport:'direct_api',source:'owner',destination:'api.openai.com',available:true},
  {route:{direct_api:{configured:true,has_decision_key:true,model:'gpt-4o-mini',destination:'api.openai.com'}}}));
 const methodRow=rowTitled('사용 방식'),changeKey=button(methodRow,'키 변경');assert(changeKey,'the active direct key can be changed');
 await changeKey.onclick({currentTarget:changeKey});
 const remove=descendants(rowTitled('사용 방식')).find(node=>node.tag==='button'&&node.textContent==='키 제거');assert(remove,'a saved key can be removed');
 assert(remove.className.includes('destructive'));
 await remove.onclick({currentTarget:remove});
 assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1))),{path:'/api/decision-route/credential',body:{transport:'direct_api',key:''}});
 assert(!calls.some(call=>call.path==='/api/decision-route/activate'));
 // A changed CLI binary is shown as needing a re-check, not as in use.
 box().dataset.state='';ctx.openDecisionChooser('');
 ctx.renderDecisionRoute(base({transport:'subscription_cli',source:'owner',engine:'codex',model_policy:'explicit',requested_model:'small',available:false,requalification_needed:true,destination:'OpenAI (Codex 구독 계정)'}));
 assert.equal(stateOf(rowTitled('사용 방식')).textContent,'확인 필요');assert(rowTitled('사용 방식').textContent.includes('CLI가 바뀌어 다시 확인해야 합니다'));
 // A CLI refused for its tool surface is a visible needs-attention state with the reason, not an absence.
 box().dataset.state='';ctx.openDecisionChooser('');
 ctx.renderDecisionRoute(base({transport:'direct_api',source:'owner',destination:'api.openai.com',available:true},
  {route:{subscription_cli:engines('supported').map(e=>e.id==='codex'?{...e,tool_surface:'tool-features-enabled',tool_surface_detail:'unified_exec'}:e)}}));
 const refused=rowTitled('구독 AI · Codex');assert(refused,'the refused engine is still listed');
 assert.equal(stateOf(refused).textContent,'사용할 수 없음');assert(stateOf(refused).className.endsWith('attention'));
 assert(refused.textContent.includes('도구 기능을 모두 끌 수 없어')&&refused.textContent.includes('unified_exec'),'the reason is named');
 assert(button(refused,'다시 확인'),'a re-check stays available after a CLI update');assert(!button(refused,'사용'));
 // Off is an explicit owner choice.
 box().dataset.state='';
 ctx.renderDecisionRoute(base({transport:'direct_api',source:'owner',destination:'api.openai.com',available:true},
  {route:{jev:{configured:true,model:'jev-latest',destination:'api.typesafe.ai',check:{state:'failed',failure:'auth',checked_at:1}}}}));
 const off=button(rowTitled('사용 방식'),'끄기');await off.onclick({currentTarget:off});
 assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1))),{path:'/api/decision-route/activate',body:{transport:'off'}});
 // Technical provenance (#559): route/policy/requested/observed are separate facts.
 const facts=Object.fromEntries(ctx.decisionFacts({purpose:'conversation-followup',outcome:'decided',route:'subscription_cli',engine:'codex',model_policy:'explicit',requested_model:'small',observed_model:'not reported',elapsed_seconds:1.5},{relation:{kind:'retry',work_id:'w0'}}));
 assert.equal(facts['판단 경로'],'subscription_cli / codex');assert.equal(facts['모델 정책'],'explicit');assert.equal(facts['요청 모델'],'small');assert.equal(facts['관측 모델'],'보고되지 않음');
 assert.equal(facts['역할'],'대화 해석');assert.equal(facts['기록된 관계'],'retry → w0');
 const legacy=Object.fromEntries(ctx.decisionFacts({purpose:'p',outcome:'decided',model:'gpt-4o-mini',observed_model:'gpt-4o-mini-2024-07-18'},{}));
 assert(legacy['요청 모델']==='gpt-4o-mini'&&legacy['관측 모델']==='gpt-4o-mini-2024-07-18'&&legacy['판단 경로']==='direct_api');
 assert(!('기록된 관계' in legacy),'only a follow-up judgment has a recorded relation');
 console.log('decision route DOM checks passed');
})().catch(error=>{console.error(error);process.exit(1);});
"""


def test_decision_route_section_is_a_separate_role_in_the_ai_settings():
    assert '<section id="decision-route"' in HTML
    ai = HTML[HTML.index('id="settings-ai"'):HTML.index('id="settings-files"')]
    assert 'id="decision-route"' in ai
    assert "renderDecisionRoute(settings)" in APP
    # The decision UI only talks to its own endpoints, never the Work route switch.
    block = APP[APP.index("const DECISION_TRANSPORT_LABEL="):APP.index("function openMobileDetail(")]
    assert "/api/ai-route" not in block and "/api/subscription-engines/connect" not in block
    assert "/api/decision-route/activate" in block and "/api/decision-route/credential" in block


def test_decision_route_renderer_behaviour():
    node = shutil.which("node")
    if node is None:
        return
    result = subprocess.run([node, "-e", DOM_CHECKS, str(ROOT / "app.js")], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "decision route DOM checks passed" in result.stdout

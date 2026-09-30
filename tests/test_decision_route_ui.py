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
function matches(node,selector){
 if(selector.includes(','))return selector.split(',').some(part=>matches(node,part));
 if(selector.includes(':not(:disabled)')){if(node.disabled)return false;selector=selector.replace(':not(:disabled)','');}
 if(selector.endsWith(':checked')){if(!node.checked)return false;selector=selector.slice(0,-8);}
 const tag=selector.match(/^[a-z]+/);if(tag&&node.tag!==tag[0])return false;
 for(const match of selector.matchAll(/\.([\w-]+)/g))if(!node.className.split(' ').includes(match[1]))return false;
 for(const match of selector.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g)){
  const key=match[1],value=key.startsWith('data-')?node.dataset[key.slice(5).replace(/-([a-z])/g,(_,letter)=>letter.toUpperCase())]:node[key]??node.attrs[key];
  if(match[2]===undefined?!value:String(value)!==match[2])return false;
 }return true;
}
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.className='';this.hidden=false;this._text='';this.value='';this.disabled=false;this.parentNode=null;this._root=false;}
 set id(value){this._id=value;ids.set(value,this);} get id(){return this._id;}
 set textContent(value){this.replaceChildren();this._text=String(value);} get textContent(){return this._text+this.children.map(node=>typeof node==='string'?node:node.textContent).join('');}
 append(...nodes){for(const node of nodes){if(typeof node!=='string'){if(node.parentNode)node.parentNode.children=node.parentNode.children.filter(item=>item!==node);node.parentNode=this;}this.children.push(node);}}
 replaceChildren(...nodes){for(const child of this.children)if(typeof child!=='string')child.parentNode=null;this._text='';this.children=[];this.append(...nodes);}
 setAttribute(key,value){this.attrs[key]=String(value);} getAttribute(key){return this.attrs[key];} focus(){document.activeElement=this;} get isConnected(){return this.parentNode?this.parentNode.isConnected:this._root;}
 remove(){if(this.parentNode)this.parentNode.children=this.parentNode.children.filter(child=>child!==this);this.parentNode=null;}
 replaceWith(node){if(this.parentNode)this.parentNode.replaceChild(node,this);}
 replaceChild(node,old){const index=this.children.indexOf(old);if(index<0)return;if(node.parentNode)node.parentNode.children=node.parentNode.children.filter(child=>child!==node);this.children[index]=node;node.parentNode=this;old.parentNode=null;}
 scrollIntoView(options){this.lastScroll=options;}
 contains(node){return this===node||descendants(this).includes(node);}
 showModal(){this.open=true;} close(){this.open=false;this.onclose?.();}
 setSelectionRange(start,end){this.selectionStart=start;this.selectionEnd=end;}
 get classList(){const node=this;return {toggle(name,on){const parts=new Set(node.className.split(' ').filter(Boolean));if(on===undefined)on=!parts.has(name);if(on)parts.add(name);else parts.delete(name);node.className=[...parts].join(' ');},add(name){this.toggle(name,true);},remove(name){this.toggle(name,false);},contains(name){return node.className.split(' ').includes(name);}};}
 querySelectorAll(selector){return descendants(this).filter(node=>matches(node,selector));}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}
function descendants(node){return node.children.flatMap(child=>typeof child==='string'?[]:[child,...descendants(child)]);}
const root=new Element('section');root.id='decision-route';root._root=true;
const $=id=>ids.get(id),document={activeElement:null,getElementById:$,createElement:tag=>new Element(tag)};
const part=(start,end)=>app.slice(app.indexOf(start),app.indexOf(end));
const source=part('const LANGUAGES=','function normalizeEndpoint(')+part('const DECISION_ROLE=','function traceWindow(')+
 part('function element(','function setError(')+part('function openJudgmentChooser(','const ENGINE_LOGIN_TEXT=')+part('const DECISION_TRANSPORT_LABEL=','function openMobileDetail(');
const calls=[];let refreshes=0,failNext=null,gate=null,refreshSettings=null;
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return{promise,resolve,reject};};
const ctx={document,$,console,safeTime:()=>'T',
 api:async(path,body)=>{calls.push({path,body});if(gate)return gate.promise;if(failNext){const error=failNext;failNext=null;throw error;}
  if(path.startsWith('/api/decision-route/models'))return {route:'codex',source:'codex debug models --bundled',models:[{id:'gpt-5.6-luna',efforts:['low','medium'],rank:1,label:'목록에 있음(검증 전)'},{id:'gpt-5.5',efforts:['low'],rank:null,label:'목록에 있음(검증 전)'}]};
  return {model_override:true};},
 refresh:async()=>{refreshes++;if(refreshSettings)ctx.renderDecisionRoute(refreshSettings);},busy:async(button,fn)=>fn(),
 setError:(id,error)=>{$(id).textContent=error?.message||String(error||'');},setFeedback:(id,text)=>{$(id).textContent=text||'';}};
vm.createContext(ctx);vm.runInContext(source,ctx);vm.runInContext("setLanguage('ko')",ctx);
const box=()=>$('decision-route'),all=()=>descendants(box());
// Older route assertions explicitly discard between fixtures; dedicated dirty-flow cases below use the public default.
const switchEditor=id=>ctx.openDecisionChooser(id,true);
const rows=()=>all().filter(node=>node.className==='settings-row');
const rowTitled=title=>rows().find(row=>descendants(row).some(node=>node.className==='settings-row-title'&&node.textContent===title));
const stateOf=row=>descendants(row).find(node=>node.className.startsWith('settings-state'));
const button=(row,label)=>descendants(row).find(node=>node.tag==='button'&&node.textContent===label);
const engines=(selection='unchecked')=>[
 {id:'codex',name:'Codex',installed:true,login:'signed-in',model_selection:selection,destination:'OpenAI (Codex 구독 계정)',isolated_deployment:false,
  ranked_models:['gpt-5.6-luna','gpt-5.6-terra'],model_efforts:{'gpt-5.6-luna':['low','medium'],'gpt-5.6-terra':['low']}},
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
 assert(box().textContent.includes('여기서 바꿔도 기본 AI는 바뀌지 않습니다'),'the role boundary is stated');
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
 // #679: the default is the cheapest qualified model (ranked list prefilled), even before the model flag was
 // checked (activation checks it); the engine default is offered but never preselected.
 calls.length=0;box().dataset.state='';ctx.renderDecisionRoute(base({transport:'direct_api',source:'default',destination:'api.openai.com'}));
 let codex=rowTitled('구독 AI · Codex');await button(codex,'사용').onclick({currentTarget:button(codex,'사용')});
 let form=descendants(rowTitled('구독 AI · Codex')).find(node=>node.tag==='form');
 let radios=descendants(form).filter(node=>node.tag==='input'&&node.type==='radio');
 assert.deepEqual(radios.map(node=>node.value),['lowest_qualified','explicit','engine_default']);
 assert.equal(radios.find(node=>node.checked).value,'lowest_qualified','engine_default (Opus for Claude Code) is not preselected');
 assert(descendants(form).some(node=>node.tag==='button'&&node.textContent==='모델 지정 지원 확인'));
 assert(form.textContent.includes('모델 목록은 새로고침을 눌렀을 때만 가져옵니다.'));
 assert(!calls.some(call=>call.path.startsWith('/api/decision-route/models')),'no model list on render');
 await form.onsubmit({preventDefault(){}});
 assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1))),{path:'/api/decision-route/activate',body:{transport:'subscription_cli',engine:'codex',model_policy:'lowest_qualified',candidates:'gpt-5.6-luna, gpt-5.6-terra'}});
 // 모델 목록 새로고침 is the only thing that lists models; entries are labelled as unverified.
 codex=rowTitled('구독 AI · Codex');await button(codex,'사용').onclick({currentTarget:button(codex,'사용')});
 form=descendants(rowTitled('구독 AI · Codex')).find(node=>node.tag==='form');
 const refreshModels=descendants(form).find(node=>node.tag==='button'&&node.textContent==='모델 목록 새로고침');
 await refreshModels.onclick({currentTarget:refreshModels});
 assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1))),{path:'/api/decision-route/models',body:{route:'codex'}},'a POST (review P2-2)');
 form=descendants(rowTitled('구독 AI · Codex')).find(node=>node.tag==='form');
 const options=descendants(form).filter(node=>node.tag==='option'&&node.value.startsWith('gpt'));
 assert(options.some(node=>node.textContent==='gpt-5.6-luna · 목록에 있음(검증 전)'),'a listed model is not called verified');
 assert(form.textContent.includes('2개 모델이 목록에 있습니다 (codex debug models --bundled)'));
 radios=descendants(form).filter(node=>node.tag==='input'&&node.type==='radio');radios.forEach(node=>{node.checked=node.value==='explicit';});
 const modelInput=descendants(form).find(node=>node.tag==='input'&&node.type==='text'&&node.attrs['aria-label']==='직접 선택할 모델 이름');
 modelInput.value='gpt-5.6-luna';modelInput.oninput();
 const effortSelect=descendants(form).find(node=>node.tag==='select');
 assert.deepEqual(descendants(effortSelect).map(node=>node.value),['','low','medium'],'only the efforts that model supports');
 effortSelect.value='medium';failNext=new Error('모델을 확인하지 못했습니다. 현재 대화 해석 경로는 그대로 유지됩니다.');
 await form.onsubmit({preventDefault(){}});
 assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1).body)),{transport:'subscription_cli',engine:'codex',model_policy:'explicit',model:'gpt-5.6-luna',effort:'medium'});
 assert($('decision-route-feedback').textContent.includes('그대로 유지'),'a failed qualification keeps the previous route and says why');
 modelInput.value='haiku';modelInput.oninput();assert(effortSelect.disabled,'no effort choice where the model has none');
 switchEditor('');
 // Unsupported: still only the engine default, with the limitation stated.
 box().dataset.state='';ctx.renderDecisionRoute(base({transport:'direct_api',source:'default',destination:'api.openai.com'},{selection:'unsupported'}));
 codex=rowTitled('구독 AI · Codex');await button(codex,'사용').onclick({currentTarget:button(codex,'사용')});
 form=descendants(rowTitled('구독 AI · Codex')).find(node=>node.tag==='form');
 assert.deepEqual(descendants(form).filter(node=>node.type==='radio').map(node=>node.value),['engine_default']);
 assert(form.textContent.includes('모델 지정을 지원하지 않아'));
 // Supported: all three policies; lowest_qualified sends the owner's ordered candidates.
 switchEditor('');box().dataset.state='';ctx.renderDecisionRoute(base({transport:'direct_api',source:'default',destination:'api.openai.com'},{selection:'supported'}));
 codex=rowTitled('구독 AI · Codex');await button(codex,'사용').onclick({currentTarget:button(codex,'사용')});
 form=descendants(rowTitled('구독 AI · Codex')).find(node=>node.tag==='form');
 const inputs=descendants(form).filter(node=>node.tag==='input');
 assert.deepEqual(inputs.filter(node=>node.type==='radio').map(node=>node.value),['lowest_qualified','explicit','engine_default']);
 inputs.find(node=>node.value==='engine_default').checked=false;inputs.find(node=>node.value==='lowest_qualified').checked=true;
 inputs.filter(node=>node.type==='text')[0].value=' tiny, small ';
 failNext=new Error('후보 모델 중 적격성 검사를 통과한 모델이 없습니다. 현재 대화 해석 경로는 그대로 유지됩니다.');const before=refreshes;
 await form.onsubmit({preventDefault(){}});
 assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1).body)),{transport:'subscription_cli',engine:'codex',model_policy:'lowest_qualified',candidates:'tiny, small'});
 assert.equal(refreshes,before,'a refused switch does not refresh into a new route');
 assert($('decision-route-feedback').textContent.includes('그대로 유지'));
 assert.equal(stateOf(rowTitled('사용 방식')).textContent,'대화 해석에 사용 중','the previous route is still shown as active');
 // An owner-selected subscription route: engine, policy, requested vs observed model.
 box().dataset.state='';switchEditor('');
 ctx.renderDecisionRoute(base({transport:'subscription_cli',source:'owner',engine:'codex',model_policy:'lowest_qualified',requested_model:'small',available:true,
  destination:'OpenAI (Codex 구독 계정)',cli_version:'codex-cli 0.153.4',qualification:{suite_version:'decision-qualification/1',model:'small'}},
  {selection:'supported',route:{subscription_cli:engines('supported').map(e=>e.id==='codex'?{...e,check:{state:'active',observed_model:'not reported',checked_at:1}}:e)}}));
 assert.equal(stateOf(rowTitled('구독 엔진')).textContent,'Codex');
 const policyRow=rowTitled('판단 모델');assert.equal(stateOf(policyRow).textContent,'자동 · 가장 저렴한 적격 모델');
 assert(policyRow.textContent.includes('요청 모델: small'),'the requested model is named, not presented as observed');
 assert(!rowTitled('구독 AI · Codex'),'the active engine is not listed again as another choice');
 assert(rowTitled('구독 AI · Claude Code'));
 assert(rowTitled('사용 방식').textContent.includes('OpenAI (Codex 구독 계정)'));
 const change=button(policyRow,'변경');await change.onclick({currentTarget:change});
 const policyForm=descendants(rowTitled('판단 모델')).find(node=>node.tag==='form');
 assert.deepEqual(descendants(policyForm).filter(node=>node.type==='radio').map(node=>node.value),['lowest_qualified','explicit','engine_default'],'the policy is changed in place');
 switchEditor('cli:codex');
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
 box().dataset.state='';switchEditor('');
 ctx.renderDecisionRoute(base({transport:'subscription_cli',source:'owner',engine:'codex',model_policy:'explicit',requested_model:'small',available:false,requalification_needed:true,destination:'OpenAI (Codex 구독 계정)'}));
 assert.equal(stateOf(rowTitled('사용 방식')).textContent,'확인 필요');assert(rowTitled('사용 방식').textContent.includes('CLI가 바뀌어 다시 확인해야 합니다'));
 // A CLI refused for its tool surface is a visible needs-attention state with the reason, not an absence.
 box().dataset.state='';switchEditor('');
 ctx.renderDecisionRoute(base({transport:'direct_api',source:'owner',destination:'api.openai.com',available:true},
  {route:{subscription_cli:engines('supported').map(e=>e.id==='codex'?{...e,tool_surface:'tool-features-enabled',tool_surface_detail:'unified_exec'}:e)}}));
 const refused=rowTitled('구독 AI · Codex');assert(refused,'the refused engine is still listed');
 assert.equal(stateOf(refused).textContent,'사용할 수 없음');assert(stateOf(refused).className.endsWith('attention'));
 assert(refused.textContent.includes('도구 기능을 모두 끌 수 없어')&&refused.textContent.includes('unified_exec'),'the reason is named');
 assert(button(refused,'다시 확인'),'a re-check stays available after a CLI update');assert(!button(refused,'사용'));
 // #679: the direct API model is chosen from the (refreshed) list or typed, and qualified before use.
 box().dataset.state='';switchEditor('');calls.length=0;
 ctx.renderDecisionRoute(base({transport:'jev',source:'owner',requested_model:'jev-latest',available:true,destination:'api.typesafe.ai'},
  {route:{direct_api:{configured:true,model:'gpt-4o-mini',destination:'api.openai.com',ranked_models:['gpt-4o-mini','gpt-6-luna']}}}));
 const openai=rowTitled('OpenAI API · gpt-4o-mini');await button(openai,'모델 선택').onclick({currentTarget:button(openai,'모델 선택')});
 const directForm=descendants(rowTitled('OpenAI API · gpt-4o-mini')).find(node=>node.tag==='form');
 assert(directForm.textContent.includes('gpt-4o-mini → gpt-6-luna'),'the cheapest-first default is named');
 assert(!descendants(directForm).some(node=>node.tag==='select'),'no effort choice for the API route');
 descendants(directForm).find(node=>node.tag==='input'&&node.type==='text').value='gpt-6-luna';
 await directForm.onsubmit({preventDefault(){}});
 assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1))),{path:'/api/decision-route/activate',body:{transport:'direct_api',model:'gpt-6-luna'}});
 // #679: the #417 default says it is a fallback and why, instead of reading as "follow Main AI".
 box().dataset.state='';switchEditor('');
 ctx.renderDecisionRoute(base({transport:'direct_api',source:'default',requested_model:'gpt-4o-mini',destination:'api.openai.com',available:true},
  {route:{effective:{state:'fallback',template:'구독 판단을 쓸 수 없어 OpenAI API({model})를 쓰는 중: {reason}',params:{model:'gpt-4o-mini'},
   reason_template:'기본 AI({main})를 따르는 구독 판단을 아직 확인하지 않았습니다. 확인을 누르면 가장 저렴한 모델부터 검증합니다.',reason_params:{main:'Codex'},destination:'api.openai.com'}}}));
 assert(rowTitled('사용 방식').textContent.includes('구독 판단을 쓸 수 없어 OpenAI API(gpt-4o-mini)를 쓰는 중: 기본 AI(Codex)를 따르는 구독 판단을 아직 확인하지 않았습니다.'));
 // An active strict Codex route states the profile, effort and a non-empty instruction file (size only).
 box().dataset.state='';
 ctx.renderDecisionRoute(base({transport:'subscription_cli',source:'owner',engine:'codex',model_policy:'lowest_qualified',requested_model:'gpt-5.6-luna',effort:'low',available:true,
  destination:'OpenAI (Codex 구독 계정)',strict_profile:{version:'0.153.4',platform:'darwin'},instruction_files_present:[{file:'AGENTS.md',bytes:120}]}));
 assert(rowTitled('구독 엔진').textContent.includes('엄격 격리'));assert(rowTitled('구독 엔진').textContent.includes('AGENTS.md (120 B)'));
 assert(rowTitled('판단 모델').textContent.includes('추론 강도: low'));
 assert(all().find(node=>node.tag==='details').textContent.includes('엄격 격리 검증: 0.153.4 · darwin'));
 // Off is an explicit owner choice.
 box().dataset.state='';
 ctx.renderDecisionRoute(base({transport:'direct_api',source:'owner',destination:'api.openai.com',available:true},
  {route:{jev:{configured:true,model:'jev-latest',destination:'api.typesafe.ai',check:{state:'failed',failure:'auth',checked_at:1}}}}));
 const off=button(rowTitled('사용 방식'),'끄기');await off.onclick({currentTarget:off});
 assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1))),{path:'/api/decision-route/activate',body:{transport:'off'}});
 // #609: Jev's model comes from TypeSafe's own list on explicit refresh; saving it never activates, and an active
 // Jev route applies a differing saved model only through an explicit, checked 사용.
 box().dataset.state='';switchEditor('');calls.length=0;
 const jevActive=(saved)=>base({transport:'jev',source:'owner',requested_model:'jev-latest',available:true,destination:'api.typesafe.ai'},
  {route:{jev:{configured:true,model:saved,destination:'api.typesafe.ai'}}});
 ctx.renderDecisionRoute(jevActive('jev-latest'));
 assert(!button(rowTitled('사용 방식'),'저장한 모델 사용'),'nothing to apply while the saved model is the active one');
 assert.equal(calls.length,0,'rendering calls nothing');
 box().dataset.state='';ctx.renderDecisionRoute(jevActive('jev-1.13.0'));
 const applySaved=button(rowTitled('사용 방식'),'저장한 모델 사용');assert(applySaved,'a differing saved model can be applied');
 await applySaved.onclick({currentTarget:applySaved});
 assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1))),{path:'/api/decision-route/activate',body:{transport:'jev'}});
 calls.length=0;const pick=button(rowTitled('사용 방식'),'모델 선택');await pick.onclick({currentTarget:pick});
 const jevForm=descendants(rowTitled('사용 방식')).find(node=>node.tag==='form');assert(jevForm,'the Jev model form opens in place');
 assert(jevForm.textContent.includes('모델 목록은 새로고침을 눌렀을 때만 가져옵니다.'));
 const jevModel=descendants(jevForm).find(node=>node.tag==='input'&&node.type==='text');assert.equal(jevModel.value,'jev-1.13.0');
 const refreshJev=button(jevForm,'모델 목록 새로고침');await refreshJev.onclick({currentTarget:refreshJev});
 assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1))),{path:'/api/decision-route/models',body:{route:'jev'}});
 const jevForm2=descendants(rowTitled('사용 방식')).find(node=>node.tag==='form');
 assert(jevForm2.textContent.includes('확인 판단 한 번으로'),'Jev activation is a probe, not the qualification suite');
 descendants(jevForm2).find(node=>node.tag==='input'&&node.type==='text').value='jev-1.12.0';calls.length=0;
 await jevForm2.onsubmit({preventDefault(){}});
 assert.deepEqual(JSON.parse(JSON.stringify(calls)),[{path:'/api/decision-route/credential',body:{transport:'jev',model:'jev-1.12.0'}}],'saving a model never activates');
 assert($('decision-route-feedback').textContent.includes('아직 대화 해석 경로는 바뀌지 않았습니다'));
 // #806 review: another tab's saved model rebases a clean editor but cannot overwrite a dirty draft.
 switchEditor('');box().dataset.state='';ctx.renderDecisionRoute(jevActive('jev-before'));switchEditor('jev:model');
 const cleanJev=box().querySelector('form'),cleanJevInput=cleanJev.querySelector('input');cleanJevInput.focus();calls.length=0;
 ctx.renderDecisionRoute(jevActive('jev-from-other-tab'));
 const freshJev=box().querySelector('form'),freshJevInput=freshJev.querySelector('input');
 assert.notEqual(freshJev,cleanJev);assert.equal(freshJevInput.value,'jev-from-other-tab');assert.equal(document.activeElement,freshJevInput,'clean rebase retains focus');
 freshJevInput.value='unsaved-owner-choice';freshJevInput.setSelectionRange(2,5);
 ctx.renderDecisionRoute(jevActive('jev-later-tab'));
 assert.equal(box().querySelector('form'),freshJev);assert.equal(freshJevInput.value,'unsaved-owner-choice');assert.equal(freshJev.parentNode.tag,'fieldset');assert.equal(freshJev.parentNode.disabled,true);assert.equal(calls.length,0,'polling never saves a stale or draft model');
 // #784: changed polling refreshes the observed summary without replacing the active editor.
 switchEditor('');box().dataset.state='';calls.length=0;
 let polling=base({transport:'direct_api',source:'owner',requested_model:'server-before',destination:'api.openai.com',available:true},{selection:'supported'});
 ctx.renderDecisionRoute(polling);switchEditor('cli:codex');
 const pollForm=box().querySelector('form'),pollInputs=descendants(pollForm).filter(node=>node.tag==='input');
 const pollRadios=pollInputs.filter(node=>node.type==='radio');pollRadios.forEach(node=>node.checked=node.value==='explicit');
 const pollCandidates=pollInputs.find(node=>node.type==='text'&&node.attrs['aria-label'].startsWith('후보 모델'));
 const pollModel=pollInputs.find(node=>node.attrs['aria-label']==='직접 선택할 모델 이름');
 pollCandidates.value='custom-small, custom-next';pollModel.value='gpt-5.6-luna';pollModel.oninput();
 const pollEffort=descendants(pollForm).find(node=>node.tag==='select');pollEffort.value='medium';pollModel.focus();pollModel.setSelectionRange(2,7);
 const pollFeedback=$('decision-route-feedback');ctx.setError('decision-route-feedback',new Error('synthetic editable error'));
 polling=JSON.parse(JSON.stringify(polling));polling.decision_route.active.requested_model='server-after';polling.decision_route.qualification={state:'running',progress:1};
 ctx.renderDecisionRoute(polling);
 assert.equal(box().querySelector('form'),pollForm,'ordinary changed polling keeps the same policy form');
 assert.equal(pollCandidates.value,'custom-small, custom-next');assert.equal(pollRadios.find(node=>node.checked).value,'explicit');assert.equal(pollModel.value,'gpt-5.6-luna');assert.equal(pollEffort.value,'medium');
 assert.equal(document.activeElement,pollModel);assert.equal(pollModel.selectionStart,2);assert.equal(pollModel.selectionEnd,7);assert.equal($('decision-route-feedback').textContent,'synthetic editable error');
 assert(rowTitled('사용 방식').textContent.includes('server-after'),'the observed summary still updates while preserving the editor');
 assert.equal(calls.length,0);
 const unavailable=JSON.parse(JSON.stringify(polling));unavailable.decision_route.subscription_cli=[];ctx.renderDecisionRoute(unavailable);
 assert.equal(box().querySelector('form'),pollForm,'unavailable route retains the existing draft');assert.equal(pollForm.parentNode.tag,'fieldset');assert.equal(pollForm.parentNode.disabled,true,'unavailable editor cannot submit');assert(pollForm.parentNode.textContent.includes('입력은 보관'));
 ctx.renderDecisionRoute(polling);assert.equal(box().querySelector('form'),pollForm);assert.notEqual(pollForm.parentNode.tag,'fieldset','a restored route moves the form out of the disabled wrapper');assert.equal(pollModel.value,'gpt-5.6-luna');assert.equal(pollCandidates.value,'custom-small, custom-next');
 // Password and its adjacent model draft survive independent qualification updates too.
 switchEditor('jev');const pollSecretForm=box().querySelector('form');assert.notEqual(pollSecretForm,pollForm,'an explicit chooser switch rebuilds the editor');
 const pollSecret=descendants(pollSecretForm).find(node=>node.type==='password'),pollSecretModel=descendants(pollSecretForm).find(node=>node.type==='text');
 pollSecret.value='synthetic-polling-secret';pollSecretModel.value='jev-owner-draft';pollSecret.focus();pollSecret.setSelectionRange(3,9);ctx.setError('decision-route-feedback',new Error('synthetic credential error'));
 polling=JSON.parse(JSON.stringify(polling));polling.decision_route.qualification={state:'running',progress:2};ctx.renderDecisionRoute(polling);
 assert.equal(box().querySelector('form'),pollSecretForm);assert.equal(pollSecret.value,'synthetic-polling-secret');assert.equal(pollSecretModel.value,'jev-owner-draft');assert.equal(document.activeElement,pollSecret);assert.equal(pollSecret.selectionStart,3);assert.equal(pollSecret.selectionEnd,9);assert.equal($('decision-route-feedback').textContent,'synthetic credential error');
 assert.equal(calls.length,0,'polling sends no credential or model request');
 // Existing explicit invalidation (save/apply/list refresh) may rebuild from current state.
 box().dataset.state='';ctx.renderDecisionRoute(polling);assert.notEqual(box().querySelector('form'),pollSecretForm);assert.equal(box().querySelector('form').querySelector('input').value,'');
 // #784: late activation cannot clear a newly opened modal/editor or admit a duplicate request.
 for(const id of ['judgment-chooser','judgment-follow','judgment-feedback','active-ai']){const node=new Element('div');node.id=id;node._root=true;}
 ctx.aiSettings=polling;ctx.openJudgmentChooser();switchEditor('cli:codex');
 calls.length=0;gate=deferred();const activationGate=gate;
 const activation=ctx.decisionActivate({transport:'subscription_cli',engine:'codex',model_policy:'explicit',model:'submitted'},new Element('button'));
 $('judgment-chooser').close();ctx.openJudgmentChooser();switchEditor('jev');
 const reopenedForm=box().querySelector('form'),reopenedSecret=reopenedForm.querySelector('input[type="password"]');
 reopenedSecret.value='new-modal-secret';reopenedSecret.focus();reopenedSecret.setSelectionRange(2,5);ctx.setError('decision-route-feedback','new modal feedback');
 await ctx.decisionActivate({transport:'off'},new Element('button'));assert.equal(calls.length,1,'activation is guarded across close/reopen');
 refreshSettings=JSON.parse(JSON.stringify(polling));refreshSettings.decision_route.active.requested_model='new-server-result';
 activationGate.resolve({});await activation;gate=null;
 assert.equal(box().querySelector('form'),reopenedForm);assert.equal(reopenedSecret.value,'new-modal-secret');assert.equal(document.activeElement,reopenedSecret);assert.equal(reopenedSecret.selectionStart,2);assert.equal(reopenedSecret.selectionEnd,5);assert.equal($('decision-route-feedback').textContent,'new modal feedback');assert(rowTitled('사용 방식').textContent.includes('new-server-result'));
 // A late refusal likewise leaves newer feedback intact and releases the operation guard.
 gate=deferred();const refusedGate=gate;const lateRefused=ctx.decisionActivate({transport:'off'},new Element('button'));
 switchEditor('cli:codex');ctx.setError('decision-route-feedback','new editor error');refusedGate.reject(new Error('old activation failure'));await lateRefused;gate=null;
 assert.equal($('decision-route-feedback').textContent,'new editor error');
 const countAfterRefusal=calls.length;await ctx.decisionActivate({transport:'off'},new Element('button'));assert.equal(calls.length,countAfterRefusal+1,'finally releases the activation guard');
 // Accepted credential save clears only its submitted input, preserving a newer editor through real refresh.
 switchEditor('jev');const submittedForm=box().querySelector('form'),submittedSecret=submittedForm.querySelector('input[type="password"]');submittedSecret.value='submitted-secret';
 gate=deferred();const credentialGate=gate;const credentialSave=submittedForm.onsubmit({preventDefault(){}});
 switchEditor('cli:codex');const newPolicy=box().querySelector('form'),newModel=newPolicy.querySelector('input[aria-label="직접 선택할 모델 이름"]');newModel.value='retained-owner-model';ctx.setError('decision-route-feedback','new policy feedback');
 refreshSettings=JSON.parse(JSON.stringify(refreshSettings));refreshSettings.decision_route.jev.configured=true;
 credentialGate.resolve({});await credentialSave;gate=null;
 assert.equal(submittedSecret.value,'');assert.equal(box().querySelector('form'),newPolicy);assert.equal(newModel.value,'retained-owner-model');assert.equal($('decision-route-feedback').textContent,'new policy feedback');
 // The model list is cached globally, but an old completion never rebuilds the current secret editor.
 const listButton=button(newPolicy,'모델 목록 새로고침');gate=deferred();const modelGate=gate;const modelRefresh=listButton.onclick({currentTarget:listButton});
 switchEditor('jev');const newSecretForm=box().querySelector('form'),newSecret=newSecretForm.querySelector('input[type="password"]');newSecret.value='model-refresh-secret';ctx.setError('decision-route-feedback','new secret feedback');
 modelGate.resolve({route:'codex',source:'synthetic latest catalog',models:[{id:'new-listed-model'}]});await modelRefresh;gate=null;
 assert.equal(box().querySelector('form'),newSecretForm);assert.equal(newSecret.value,'model-refresh-secret');assert.equal($('decision-route-feedback').textContent,'new secret feedback');assert.equal(ctx.decisionModelList('codex').models[0].id,'new-listed-model');
 // Model-only credential saves have the same editor identity fence.
 switchEditor('jev:model');const savedModelForm=box().querySelector('form');savedModelForm.querySelector('input[type="text"]').value='jev-submitted-model';
 gate=deferred();const savedModelGate=gate;const savedModelRequest=savedModelForm.onsubmit({preventDefault(){}});
 switchEditor('direct_api');const afterModelForm=box().querySelector('form'),afterModelSecret=afterModelForm.querySelector('input[type="password"]');afterModelSecret.value='new-api-secret';ctx.setError('decision-route-feedback','new API feedback');
 savedModelGate.resolve({});await savedModelRequest;gate=null;assert.equal(box().querySelector('form'),afterModelForm);assert.equal(afterModelSecret.value,'new-api-secret');assert.equal($('decision-route-feedback').textContent,'new API feedback');
 // A failed old credential request leaves its submitted value and the newer error untouched.
 gate=deferred();const failedCredentialGate=gate;const failedCredential=afterModelForm.onsubmit({preventDefault(){}});
 switchEditor('jev');const afterFailureForm=box().querySelector('form');ctx.setError('decision-route-feedback','new credential editor error');
 failedCredentialGate.reject(new Error('old credential refused'));await failedCredential;gate=null;assert.equal(afterModelSecret.value,'new-api-secret');assert.equal(box().querySelector('form'),afterFailureForm);assert.equal($('decision-route-feedback').textContent,'new credential editor error');
 // Following the main AI uses the same operation guard and session fence.
 ctx.aiSettings=base({transport:'direct_api',requested_model:'explicit'}, {route:{mode:'explicit',follow:{available:true,model:'light',destination:'example.invalid'}}});
 ctx.renderJudgmentFollow();gate=deferred();const followGate=gate,followButton=button($('judgment-follow'),'따라가기 사용');const followRequest=followButton.onclick({currentTarget:followButton});
 switchEditor('cli:codex');const afterFollowForm=box().querySelector('form');ctx.setError('judgment-feedback','new follow feedback');ctx.setError('decision-route-feedback','new draft feedback');
 const pendingFollowCalls=calls.length;await ctx.decisionActivate({transport:'off'},new Element('button'));assert.equal(calls.length,pendingFollowCalls);
 followGate.resolve({});await followRequest;gate=null;assert.equal(box().querySelector('form'),afterFollowForm);assert.equal($('judgment-feedback').textContent,'new follow feedback');assert.equal($('decision-route-feedback').textContent,'new draft feedback');
 refreshSettings=null;
 // #784: actual dirty editor survives close/reopen; switching requires one keep/discard choice.
 const draftSettings=base({transport:'direct_api',requested_model:'stable-main'}, {selection:'supported'});
 switchEditor('');box().dataset.state='';ctx.renderDecisionRoute(draftSettings);ctx.aiSettings=draftSettings;ctx.openJudgmentChooser();ctx.openDecisionChooser('jev');
 const retainedDraft=box().querySelector('form'),retainedPassword=retainedDraft.querySelector('input[type="password"]');retainedPassword.value='draft-stays-in-dom';retainedPassword.setSelectionRange(2,6);
 $('judgment-chooser').close();ctx.openJudgmentChooser();assert.equal(box().querySelector('form'),retainedDraft);assert.equal(retainedPassword.value,'draft-stays-in-dom');assert.equal(retainedPassword.selectionStart,2);assert.equal(retainedPassword.selectionEnd,6);
 const beforeDiscardRequests=calls.length;ctx.openDecisionChooser('cli:codex');assert.equal(box().querySelector('form'),retainedDraft);assert.equal(box().querySelectorAll('[id="decision-discard"]').length,1);
 const keepDraft=button($('decision-discard'),'계속 편집');keepDraft.onclick();assert.equal(box().querySelector('form'),retainedDraft);assert.equal(retainedPassword.value,'draft-stays-in-dom');assert.equal(box().querySelectorAll('[id="decision-discard"]').length,0);
 ctx.openDecisionChooser('direct_api');ctx.openDecisionChooser('cli:codex');assert.equal(box().querySelectorAll('[id="decision-discard"]').length,1,'one inline decision replaces the previous destination');
 button($('decision-discard'),'변경 사항 버리기').onclick();const changedEditor=box().querySelector('form');assert.notEqual(changedEditor,retainedDraft);assert.equal(changedEditor.querySelector('input').type,'radio');assert.equal(calls.length,beforeDiscardRequests,'local discard never changes credentials or active route');
 // A supported-to-unsupported capability update retains the exact draft but disables its old controls.
 const originalCapabilityForm=changedEditor,capabilityModel=changedEditor.querySelector('input[aria-label="직접 선택할 모델 이름"]');capabilityModel.value='draft-for-original-capability';
 const unsupportedSettings=JSON.parse(JSON.stringify(draftSettings));unsupportedSettings.decision_route.subscription_cli[0].model_selection='unsupported';ctx.renderDecisionRoute(unsupportedSettings);
 assert.equal(box().querySelector('form'),originalCapabilityForm);assert.equal(originalCapabilityForm.parentNode.tag,'fieldset');assert.equal(originalCapabilityForm.parentNode.disabled,true);assert.equal(capabilityModel.value,'draft-for-original-capability');assert(originalCapabilityForm.parentNode.textContent.includes('설정 정보가 바뀌어'));
 // An unchanged poll stays disabled; restoration of the original contract re-enables the same draft.
 ctx.renderDecisionRoute(unsupportedSettings);assert.equal(originalCapabilityForm.parentNode.disabled,true);ctx.renderDecisionRoute(draftSettings);assert.equal(box().querySelector('form'),originalCapabilityForm);assert.notEqual(originalCapabilityForm.parentNode.tag,'fieldset');
 ctx.renderDecisionRoute(unsupportedSettings);const reopenCapability=button(box(),'현재 설정으로 다시 열기');reopenCapability.onclick();assert.equal(box().querySelector('form'),originalCapabilityForm);button($('decision-discard'),'계속 편집').onclick();assert.equal(originalCapabilityForm.parentNode.disabled,true);
 button(box(),'현재 설정으로 다시 열기').onclick();button($('decision-discard'),'변경 사항 버리기').onclick();const refreshedCapabilityForm=box().querySelector('form');assert.notEqual(refreshedCapabilityForm,originalCapabilityForm);assert.notEqual(refreshedCapabilityForm.parentNode.tag,'fieldset');assert.equal(refreshedCapabilityForm.querySelectorAll('input[type="radio"]').length,1);assert.equal(refreshedCapabilityForm.querySelector('input[type="radio"]').value,'engine_default');assert.equal(refreshedCapabilityForm.querySelector('input[type="text"]'),null);assert.equal(calls.length,beforeDiscardRequests);
 // Completion clears a discard prompt opened against the submitted editor, not a later editor.
 const pendingForm=box().querySelector('form');pendingForm.querySelector('input').checked=false;
 gate=deferred();const sameEditorGate=gate,sameEditorApply=pendingForm.onsubmit({preventDefault(){}});
 ctx.openDecisionChooser('jev');assert(box().querySelector('[id="decision-discard"]'));
 refreshSettings=unsupportedSettings;sameEditorGate.resolve({});await sameEditorApply;gate=null;refreshSettings=null;
 assert.equal(box().querySelector('[id="decision-discard"]'),null,'accepted same-editor apply removes its obsolete discard prompt');
 // Reopening keeps the same DOM input, so a late save must not clear a newer value on that input.
 switchEditor('jev');const reopenedSaveForm=box().querySelector('form'),reopenedSaveInput=reopenedSaveForm.querySelector('input[type="password"]');reopenedSaveInput.value='submitted-before-reopen';
 gate=deferred();const reopenSaveGate=gate,reopenSaveRequest=reopenedSaveForm.onsubmit({preventDefault(){}});
 const recordedSave=calls.at(-1);assert.equal(recordedSave.body.key,'submitted-before-reopen');
 $('judgment-chooser').close();ctx.aiSettings=unsupportedSettings;ctx.openJudgmentChooser();assert.equal(box().querySelector('form'),reopenedSaveForm);
 reopenedSaveInput.value='typed-after-reopen';ctx.setError('decision-route-feedback','new session feedback');refreshSettings=unsupportedSettings;
 reopenSaveGate.resolve({});await reopenSaveRequest;gate=null;refreshSettings=null;
 assert.equal(box().querySelector('form'),reopenedSaveForm);assert.equal(reopenedSaveInput.value,'typed-after-reopen');assert.equal($('decision-route-feedback').textContent,'new session feedback');assert.equal(recordedSave.body.key,'submitted-before-reopen','only the captured value was sent');
 // Editing during the same pending request also leaves the new draft in place.
 gate=deferred();const editedSaveGate=gate,editedSaveRequest=reopenedSaveForm.onsubmit({preventDefault(){}});reopenedSaveInput.value='typed-during-save';
 editedSaveGate.resolve({});await editedSaveRequest;gate=null;assert.equal(box().querySelector('form'),reopenedSaveForm);assert.equal(reopenedSaveInput.value,'typed-during-save');
 // A newer adjacent model draft is not erased merely because the key text is unchanged.
 gate=deferred();const adjacentModelGate=gate,adjacentModelRequest=reopenedSaveForm.onsubmit({preventDefault(){}});reopenedSaveForm.querySelector('input[type="text"]').value='model-edited-during-save';
 adjacentModelGate.resolve({});await adjacentModelRequest;gate=null;assert.equal(box().querySelector('form'),reopenedSaveForm);assert.equal(reopenedSaveInput.value,'typed-during-save');assert.equal(reopenedSaveForm.querySelector('input[type="text"]').value,'model-edited-during-save');
 // Retained drafts still protect a browser reload when the Judgment dialog itself is closed.
 for(const id of ['ai-chooser','root-path-input']){const node=new Element('div');node.id=id;node.value='';node.open=false;node._root=true;}
 let unloadHandler;ctx.window={addEventListener:(name,handler)=>{if(name==='beforeunload')unloadHandler=handler;}};ctx.chooserDraftDirty=()=>false;ctx.searchDraftDirty=()=>false;ctx.workspaceDraft=null;ctx.telegramDraftOpen=false;
 vm.runInContext(app.split('\n').find(line=>line.startsWith("window.addEventListener('beforeunload'")),ctx);
 $('judgment-chooser').close();let unloadPrevented=false;const dirtyUnload={preventDefault(){unloadPrevented=true;}};unloadHandler(dirtyUnload);assert(unloadPrevented);assert.equal(dirtyUnload.returnValue,'');
 ctx.openJudgmentChooser();ctx.openDecisionChooser('cli:codex');button($('decision-discard'),'변경 사항 버리기').onclick();$('judgment-chooser').close();unloadPrevented=false;unloadHandler({preventDefault(){unloadPrevented=true;}});assert.equal(unloadPrevented,false,'an unchanged clean editor does not warn');
 // Same-session model-list completion retains custom policy/model/caret and updates capability availability.
 switchEditor('');const asyncSettings=base({transport:'direct_api',requested_model:'before-async'}, {route:{jev:{configured:true,model:'jev-latest',destination:'api.typesafe.ai'}}});box().dataset.state='';ctx.renderDecisionRoute(asyncSettings);switchEditor('cli:codex');
 const dirtyCatalogForm=box().querySelector('form'),dirtyCatalogInput=dirtyCatalogForm.querySelector('input[aria-label="직접 선택할 모델 이름"]');dirtyCatalogInput.value='custom-before-catalog';dirtyCatalogInput.focus();dirtyCatalogInput.setSelectionRange(2,8);
 gate=deferred();const dirtyCatalogGate=gate,dirtyCatalogButton=button(dirtyCatalogForm,'모델 목록 새로고침'),dirtyCatalogRequest=dirtyCatalogButton.onclick({currentTarget:dirtyCatalogButton});
 dirtyCatalogGate.resolve({route:'codex',source:'updated synthetic catalog',models:[{id:'catalog-after-draft',efforts:['low']}]});await dirtyCatalogRequest;gate=null;
 assert.equal(box().querySelector('form'),dirtyCatalogForm);assert.equal(dirtyCatalogInput.value,'custom-before-catalog');assert.equal(dirtyCatalogInput.selectionStart,2);assert.equal(dirtyCatalogInput.selectionEnd,8);assert.equal(dirtyCatalogForm.parentNode.disabled,true,'changed cached catalogue is part of render and capability fingerprints');assert.equal(ctx.decisionModelList('codex').models[0].id,'catalog-after-draft');
 // A capability check can update the current contract without discarding an already dirty custom model.
 switchEditor('');box().dataset.state='';ctx.renderDecisionRoute(asyncSettings);switchEditor('cli:codex');const dirtyCapabilityForm=box().querySelector('form'),dirtyCapabilityInput=dirtyCapabilityForm.querySelector('input[aria-label="직접 선택할 모델 이름"]');dirtyCapabilityInput.value='custom-capability-draft';
 gate=deferred();const dirtyCapabilityGate=gate,dirtyCapabilityButton=button(dirtyCapabilityForm,'모델 지정 지원 확인'),dirtyCapabilityRequest=dirtyCapabilityButton.onclick({currentTarget:dirtyCapabilityButton});
 refreshSettings=JSON.parse(JSON.stringify(asyncSettings));refreshSettings.decision_route.subscription_cli[0].model_selection='supported';dirtyCapabilityGate.resolve({model_override:true});await dirtyCapabilityRequest;gate=null;refreshSettings=null;
 assert.equal(box().querySelector('form'),dirtyCapabilityForm);assert.equal(dirtyCapabilityInput.value,'custom-capability-draft');assert.equal(dirtyCapabilityForm.parentNode.disabled,true);assert($('decision-route-feedback').textContent.includes('지정을 지원합니다'));
 // Model-only save sends the snapshot while retaining model text edited during the same request.
 switchEditor('jev:model');const sameSessionModelForm=box().querySelector('form'),sameSessionModel=sameSessionModelForm.querySelector('input[type="text"]');sameSessionModel.value='jev-submitted';
 gate=deferred();const sameSessionModelGate=gate,sameSessionModelRequest=sameSessionModelForm.onsubmit({preventDefault(){}});const sameSessionModelCall=calls.at(-1);sameSessionModel.value='jev-next-draft';
 refreshSettings=JSON.parse(JSON.stringify(asyncSettings));refreshSettings.decision_route.jev.model='jev-submitted';sameSessionModelGate.resolve({});await sameSessionModelRequest;gate=null;refreshSettings=null;
 assert.equal(sameSessionModelCall.body.model,'jev-submitted');assert.equal(box().querySelector('form'),sameSessionModelForm);assert.equal(sameSessionModel.value,'jev-next-draft');assert($('decision-route-feedback').textContent.includes('모델을 저장했습니다'));
 // Activation likewise preserves edits made to the submitted model while reporting actual server success.
 switchEditor('cli:codex');const sameSessionActivationForm=box().querySelector('form'),sameSessionActivationModel=sameSessionActivationForm.querySelector('input[aria-label="직접 선택할 모델 이름"]');for(const radio of sameSessionActivationForm.querySelectorAll('input[type="radio"]'))radio.checked=radio.value==='explicit';sameSessionActivationModel.value='submitted-activation-model';
 gate=deferred();const sameSessionActivationGate=gate,sameSessionActivationRequest=sameSessionActivationForm.onsubmit({preventDefault(){}}),sameSessionActivationCall=calls.at(-1);sameSessionActivationModel.value='activation-next-draft';
 refreshSettings=JSON.parse(JSON.stringify(asyncSettings));refreshSettings.decision_route.active={transport:'subscription_cli',engine:'codex',model_policy:'explicit',requested_model:'submitted-activation-model'};sameSessionActivationGate.resolve({});await sameSessionActivationRequest;gate=null;refreshSettings=null;
 assert.equal(sameSessionActivationCall.body.model,'submitted-activation-model');assert.equal(box().querySelector('form'),sameSessionActivationForm);assert.equal(sameSessionActivationModel.value,'activation-next-draft');assert(box().textContent.includes('요청 모델: submitted-activation-model'));assert($('decision-route-feedback').textContent.includes('경로를 바꿨습니다'));
 // Follow-main success also leaves an independent unsaved model editor intact in the same dialog.
 ctx.aiSettings={...asyncSettings,decision_route:{...asyncSettings.decision_route,mode:'explicit',follow:{available:true,model:'light',destination:'example.invalid'}}};ctx.renderJudgmentFollow();
 gate=deferred();const dirtyFollowGate=gate,dirtyFollowButton=button($('judgment-follow'),'따라가기 사용'),dirtyFollowRequest=dirtyFollowButton.onclick({currentTarget:dirtyFollowButton});
 refreshSettings=ctx.aiSettings;dirtyFollowGate.resolve({});await dirtyFollowRequest;gate=null;refreshSettings=null;assert.equal(box().querySelector('form'),sameSessionActivationForm);assert.equal(sameSessionActivationModel.value,'activation-next-draft');
 // Technical provenance (#559): route/policy/requested/observed are separate facts.
 const facts=Object.fromEntries(ctx.decisionFacts({purpose:'conversation-followup',outcome:'decided',route:'subscription_cli',engine:'codex',model_policy:'explicit',requested_model:'small',observed_model:'not reported',elapsed_seconds:1.5},{relation:{kind:'retry',work_id:'w0'}}));
 assert.equal(facts['판단 경로'],'subscription_cli / codex');assert.equal(facts['모델 정책'],'explicit');assert.equal(facts['요청 모델'],'small');assert.equal(facts['관측 모델'],'보고되지 않음');
 assert.equal(facts['역할'],'대화 해석');assert.equal(facts['기록된 관계'],'retry → w0');
 const legacy=Object.fromEntries(ctx.decisionFacts({purpose:'p',outcome:'decided',model:'gpt-4o-mini',observed_model:'gpt-4o-mini-2024-07-18'},{}));
 assert(legacy['요청 모델']==='gpt-4o-mini'&&legacy['관측 모델']==='gpt-4o-mini-2024-07-18'&&legacy['판단 경로']==='direct_api');
 assert(!('기록된 관계' in legacy),'only a follow-up judgment has a recorded relation');
 // #794: the model's reported confidence is shown, labelled as uncalibrated; absent when not reported.
 const confident=Object.fromEntries(ctx.decisionFacts({purpose:'p',outcome:'decided',confidence:0.874},{}));
 assert.equal(confident['확신도'],'87% · 모델이 보고한 값, 보정되지 않음');assert(!('확신도' in legacy),'no confidence row without a reported value');
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

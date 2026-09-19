'use strict';
const $=id=>document.getElementById(id);
let claimed=false, authenticated=false, modelLoaded=false, stateFingerprint='', refreshing=false, activeWorkspace='', activeSettingsCategory='connections';
let modelDraftVerified='', contextDraftDirty=false, conversationSettingsFingerprint='', activeModelDestination='', selectedTaskId='', taskProgressState=null, taskProgressLoading=false;
const expandedTaskEvents=new Set();
let bootstrap=new URLSearchParams(location.hash.slice(1)).get('setup')||'';
if(bootstrap)history.replaceState(null,'',location.pathname+location.search);
async function api(path,body){
 const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 const data=await response.json();
 if(!response.ok)throw new Error(data.error||'요청을 처리할 수 없습니다.');
 return data;
}
function error(id,e){$(id).textContent=e.message||String(e);}
async function busy(button,fn){const text=button.textContent;button.disabled=true;button.textContent='처리 중…';try{await fn();}finally{button.disabled=false;button.textContent=text;}}
async function status(){
 let s=await api('/api/status');
 if(!s.claimed){await api('/api/claim',{code:bootstrap});s=await api('/api/status');}
 claimed=s.claimed;authenticated=s.authenticated;
 if(!authenticated&&s.local_access){await api('/api/local-login',{});authenticated=true;}
 $('welcome').hidden=authenticated;$('workspace').hidden=!authenticated;$('logout').hidden=!authenticated||s.local_access;
 $('auth-title').textContent=claimed?'다시 만나서 반갑습니다.':'나만의 에이전트를 시작하세요.';
 $('auth-step').textContent=claimed?'개인 환경 로그인':'처음 시작하기';
 $('auth-help').textContent=claimed?'설정한 비밀번호로 로그인하세요.':'설정 없이 바로 시작할 수 있습니다. 이 PC를 함께 쓰는 사람이 있다면 비밀번호를 설정하세요.';
 $('auth-submit').textContent=claimed?'로그인':'바로 시작하기';
 $('password').required=claimed;$('password-option').open=claimed;$('password').minLength=claimed?1:12;$('password').autocomplete=claimed?'current-password':'new-password';
 $('password-label').textContent=claimed?'비밀번호':'사용할 비밀번호';
 if(authenticated){await refresh();await finishOpenRouter();}
}
$('auth-form').addEventListener('submit',async e=>{e.preventDefault();$('auth-error').textContent='';await busy($('auth-submit'),async()=>{try{await api(claimed?'/api/login':'/api/claim',{password:$('password').value,code:bootstrap});bootstrap='';$('password').value='';await status();}catch(e){error('auth-error',e);}});});
$('logout').onclick=async()=>{try{await api('/api/logout',{});modelLoaded=false;stateFingerprint='';await status();}catch(e){error('global-error',e);}};
const providers={ollama:{endpoint:'http://127.0.0.1:11434',help:'Ollama 서버의 주소입니다. 모델은 Ollama에 미리 설치되어 있어야 합니다.'},compatible:{endpoint:'https://openrouter.ai/api/v1',help:'OpenRouter 호환 서버의 주소입니다. 필요한 경우 /v1을 포함하세요.',model:'openrouter/free'},openai:{endpoint:'https://api.openai.com/v1',help:'OpenAI API 서버입니다. 기존 OpenAI API 키를 입력하면 GPT-4o mini를 연결합니다.',model:'gpt-4o-mini'},anthropic:{endpoint:'https://api.anthropic.com',help:'Anthropic에서 사용 가능한 모델 ID와 API 키를 입력하세요.'}};
const providerNames={compatible:'OpenRouter',openai:'OpenAI',ollama:'Ollama',anthropic:'Anthropic'};
function displayProvider(model){return model.provider==='compatible'&&model.endpoint==='https://api.openai.com/v1'?'openai':model.provider;}
function modelDraft(){if(!activeModelDestination)activeModelDestination=[$('provider').value,$('endpoint').value.replace(/\/$/,'')].join('|');const endpoint=$('endpoint').value.replace(/\/$/,'');return {provider:$('provider').value,endpoint,model:$('model-name').value,api_key:$('api-key').value,require_key:activeModelDestination!==[$('provider').value,endpoint].join('|')};}
function modelDraftFingerprint(d){return [d.provider,d.endpoint,d.model].join('|');}
$('provider').onchange=()=>{const p=providers[$('provider').value];$('endpoint').value=p.endpoint;if(p.model)$('model-name').value=p.model;$('endpoint-help').textContent=p.help;$('api-key').value='';modelDraftVerified='';$('apply-model').disabled=true;$('model-feedback').textContent='연결 대상이 바뀌면 새 키가 필요합니다. 이 설정을 테스트한 뒤 적용하세요.';};
['endpoint','model-name','api-key'].forEach(id=>$(id).addEventListener('input',()=>{modelDraftVerified='';$('apply-model').disabled=true;}));
$('model-form').onsubmit=async e=>{e.preventDefault();const draft=modelDraft();if(modelDraftVerified!==modelDraftFingerprint(draft)){$('model-feedback').textContent='먼저 현재 입력한 설정을 테스트하세요.';return;}await busy(e.submitter,async()=>{try{await api('/api/model',draft);$('api-key').value='';$('model-feedback').textContent='테스트한 설정을 현재 사용 모델로 적용했습니다.';modelDraftVerified='';$('apply-model').disabled=true;modelLoaded=false;await refresh();await api('/api/model/test',{});await refresh();}catch(e){error('model-feedback',e);}});};
$('test-model').onclick=async()=>busy($('test-model'),async()=>{const draft=modelDraft();try{const data=await api('/api/model/test',draft);if(!data.ok)throw new Error(data.error||'도구 호출을 확인하지 못했습니다.');modelDraftVerified=modelDraftFingerprint(draft);$('apply-model').disabled=false;$('model-feedback').textContent='이 설정의 텍스트 응답과 도구 호출을 확인했습니다. 성공한 설정만 적용할 수 있습니다.';}catch(e){modelDraftVerified='';$('apply-model').disabled=true;error('model-feedback',e);}});
function showPair(data){$('pair-link').href=data.url;$('telegram-pair').hidden=false;$('telegram-token').value='';}
$('telegram-form').onsubmit=async e=>{e.preventDefault();await busy(e.submitter,async()=>{try{showPair(await api('/api/telegram',{token:$('telegram-token').value}));await refresh();}catch(e){error('telegram-status',e);}});};
$('new-pair').onclick=async()=>{try{showPair(await api('/api/telegram/pair',{}));}catch(e){error('telegram-status',e);}};
$('disconnect').onclick=async()=>{try{await api('/api/telegram/disconnect',{});$('telegram-pair').hidden=true;await refresh();}catch(e){error('telegram-status',e);}};
function openConnections(){ $('connections').hidden=false;$('settings-panel').scrollIntoView({behavior:'smooth',block:'start'});}
$('toggle-settings').onclick=openConnections;
$('task-status-link').onclick=()=>{openConnections();$('task-status-panel').scrollIntoView({behavior:'smooth',block:'start'});};
$('nav-task-status').onclick=()=>{$('task-status-panel').scrollIntoView({behavior:'smooth',block:'start'});};
$('nav-records').onclick=()=>{$('records-section').scrollIntoView({behavior:'smooth',block:'start'});};
$('nav-projects').onclick=()=>{$('workspace-management').scrollIntoView({behavior:'smooth',block:'start'});};
$('nav-settings').onclick=()=>{$('settings-panel').scrollIntoView({behavior:'smooth',block:'start'});};
$('workspace-link').onclick=()=>{openConnections();$('workspace-management').scrollIntoView({behavior:'smooth',block:'start'});};
$('close-settings').onclick=()=>{$('connections').hidden=true;window.scrollTo({top:0,behavior:'smooth'});};
$('try-ai').onclick=openConnections;
$('try-note').onclick=()=>{$('message').value='메모: ';$('message').focus();};
$('chat-form').onsubmit=async e=>{e.preventDefault();const message=$('message').value.trim();if(!message)return;if(!hasModel&&!/^(메모:|기록:|\/note(?:s)?(?:\s|$)|\/help$)/.test(message)){openConnections();$('easy-feedback').textContent='AI를 연결하면 작성한 메시지를 보낼 수 있어요. 입력한 내용은 그대로 남겨 두었습니다.';return;}await busy(e.submitter,async()=>{try{await api('/api/chat',{message,request_key:crypto.randomUUID(),workspace_id:activeWorkspace||undefined});$('message').value='';$('global-error').textContent='';await refresh();}catch(e){error('global-error',e);}});};
document.querySelectorAll('[data-message]').forEach(button=>button.onclick=()=>{$('message').value=button.dataset.message;$('message').focus();});
function element(tag,text,className){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
function showDocumentBoundary(boundary){
 let box=$('document-boundary');if(!box){box=element('div',undefined,'document-boundary');box.id='document-boundary';$('roots-feedback').after(box);}
 box.replaceChildren();if(!boundary)return;
 if(!boundary.external_model){box.append(element('p','문서 발췌문은 이 컴퓨터에서 실행되는 모델에만 전달됩니다.'));return;}
 if(boundary.approved){box.append(element('p','문서 공유 승인됨 · 현재 선택 모델과 연결한 폴더의 필요한 발췌문만 외부 AI에 전달됩니다. 모델이나 폴더를 바꾸면 다시 승인해야 합니다.'));return;}
 box.append(element('p','문서는 이 컴퓨터에서 읽습니다. 외부 AI가 문서 검색 결과나 발췌문을 받기 전에는 명시적 승인이 필요합니다.'));const button=element('button','문서 발췌문 전송 승인');button.type='button';button.onclick=()=>busy(button,async()=>{try{await api('/api/documents/approval',{approved:true});await refresh();}catch(e){error('roots-feedback',e);}});box.append(button);
}
function showContextInbox(inbox){
 if(!inbox)return;if(!contextDraftDirty&&!['context-text','context-url'].includes(document.activeElement?.id)){$('context-text').checked=!!inbox.sources?.text;$('context-url').checked=!!inbox.sources?.url;}
 const list=$('context-items');list.replaceChildren();const items=inbox.items||[];
 if(!items.length){list.append(element('p','저장된 컨텍스트가 없습니다.'));return;}
 for(const item of items){const row=element('div');row.append(element('span',`${item.source_kind} · ${new Date(item.captured_at*1000).toLocaleString()} · ${new Date(item.expires_at*1000).toLocaleDateString()} 만료 `));const remove=element('button','삭제');remove.type='button';remove.onclick=()=>busy(remove,async()=>{try{await api('/api/context-inbox/delete',{id:item.id});await refresh();}catch(e){error('context-feedback',e);}});row.append(remove);list.append(row);}
}
function showPersonalSpace(space){
 let box=$('personal-space-items');if(!box){const section=element('section');section.id='personal-space';section.append(element('h2','기록 찾기'),element('p','메모·기억·저장된 결과를 찾아보고, 임시 자료 원문과 실행 세부 내용은 별도로 관리합니다.'));box=element('div');box.id='personal-space-items';section.append(box);$('workspace-management').before(section);}
 const previousQuery=box.querySelector('input')?.value||'';const queryFocused=document.activeElement===box.querySelector('input');box.replaceChildren();box.append(element('p',`메모 ${space.memory_count}개 · 기억 ${space.memories?.filter(item=>item.memory_key)?.length||0}개 · 저장된 결과 ${space.result_count}개 · 임시 자료 ${space.context_count}개`));
 const form=element('form');const input=element('input');input.placeholder='개인 공간에서 찾기';input.maxLength=160;input.required=true;input.value=previousQuery;const button=element('button','로컬에서 찾기');button.type='submit';const output=element('div');output.setAttribute('role','status');form.append(input,button);form.onsubmit=async e=>{e.preventDefault();await busy(button,async()=>{try{const result=await api('/api/personal-knowledge',{query:input.value});output.replaceChildren(element('p',result.response));for(const row of result.results||[])output.append(element('p',`${row.source} · ${row.excerpt} · ${row.match_reason}`));}catch(e){output.replaceChildren(element('p',e.message||String(e)));}});};box.append(form,output);if(queryFocused)input.focus();
 for(const item of [...(space.memories||[]),...(space.results||[])].slice(0,8)){const row=element('div','', 'record-row');row.append(element('span',`${item.memory_key?'기억':'메모'} · ${item.content}`));const remove=element('button','삭제');remove.type='button';remove.onclick=()=>busy(remove,async()=>{try{await fetch('/api/personal-space/memories/'+encodeURIComponent(item.id),{method:'DELETE'});await refresh();}catch(e){error('context-feedback',e);}});row.append(remove);box.append(row);}
}
function showConversationSettings(model){return;
 let box=$('conversation-settings');if(!box){const section=element('section');section.id='conversation-settings-section';section.append(element('h2','Connections'),element('p','대화와 이 화면은 같은 미리보기·명시 확인 경계를 사용합니다. 연결 정보나 비밀값은 표시하지 않습니다.'));box=element('div');box.id='conversation-settings';section.append(box);$('workspace-management').before(section);}
 box.replaceChildren();const nav=element('div',undefined,'settings-nav');for(const section of model?.manual_sections||[]){const button=element('button',section.label,section.id===activeSettingsCategory?'selected':'');button.type='button';button.onclick=()=>{activeSettingsCategory=section.id;showConversationSettings(model);};nav.append(button);}box.append(nav);const section=(model?.manual_sections||[]).find(x=>x.id===activeSettingsCategory)||{};box.append(element('p',section.description||''));if(activeSettingsCategory==='activity'){for(const event of model?.activity||[])box.append(element('p',`${event.target||'setting'} · ${event.before||''} → ${event.after||''} · ${event.terminal||''}`));if(!(model?.activity||[]).length)box.append(element('p','표시할 설정 활동이 없습니다.'));return;}if(activeSettingsCategory!=='connections'){box.append(element('p','이 범주는 로컬 보조 화면에서만 읽기 전용으로 안내합니다. 변경은 Connections의 동일한 preview/confirm 경계를 사용합니다.'));return;}for(const item of model?.capabilities||[]){const row=element('div',undefined,'conversation-setting');row.append(element('strong',item.id));row.append(element('p',`${item.kind} · ${item.state} · ${item.health} · ${item.recovery}`));if(item.state==='enabled'){for(const action of ['pause','disconnect']){const button=element('button',action==='pause'?'일시 정지 초안':'연결 해제 초안');button.type='button';button.onclick=()=>busy(button,async()=>{try{const draft=await api('/api/settings/request',{operation:'draft',intent:`${item.id} ${action}`});const preview=draft.preview;const confirm=element('button',`Confirm ${preview.id}`);confirm.type='button';confirm.onclick=()=>busy(confirm,async()=>{try{await api('/api/settings/request',{operation:'confirm',draft_id:preview.id,digest:preview.digest});await refresh();}catch(e){error('global-error',e);}});row.append(element('p',`${preview.effect} · 10분 내 확인`),confirm);}catch(e){error('global-error',e);}});row.append(button);}}else if(item.state==='paused'){const button=element('button','다시 시작 초안');button.type='button';button.onclick=()=>busy(button,async()=>{try{const draft=await api('/api/settings/request',{operation:'draft',intent:`${item.id} resume`});const preview=draft.preview;const confirm=element('button',`Confirm ${preview.id}`);confirm.type='button';confirm.onclick=()=>busy(confirm,async()=>{try{await api('/api/settings/request',{operation:'confirm',draft_id:preview.id,digest:preview.digest});await refresh();}catch(e){error('global-error',e);}});row.append(confirm);}catch(e){error('global-error',e);}});row.append(button);}box.append(row);}
}
$('context-config').onsubmit=async e=>{e.preventDefault();await busy(e.submitter,async()=>{try{await api('/api/context-inbox/config',{sources:{text:$('context-text').checked,url:$('context-url').checked}});contextDraftDirty=false;$('context-feedback').textContent='수집 설정을 저장했습니다.';await refresh();}catch(e){error('context-feedback',e);}});};
['context-text','context-url'].forEach(id=>$(id).addEventListener('change',()=>{contextDraftDirty=true;}));
$('context-capture').onsubmit=async e=>{e.preventDefault();await busy(e.submitter,async()=>{try{await api('/api/context-inbox/capture',{source_kind:$('context-kind').value,content:$('context-content').value});$('context-content').value='';$('context-feedback').textContent='이 컴퓨터의 인박스에만 저장했습니다.';await refresh();}catch(e){error('context-feedback',e);}});};
$('context-telegram-policy').onclick=async()=>busy($('context-telegram-policy'),async()=>{try{await api('/api/context-inbox/telegram-policy',{approved:true});$('context-feedback').textContent='현재 모델의 Telegram 컨텍스트 공유 정책을 승인했습니다. 외부 모델 작업은 Telegram에서 다시 한 번 승인해야 합니다.';await refresh();}catch(e){error('context-feedback',e);}});
function showSubscriptionEngines(subscription){
 let box=$('subscription-engines');if(!box){box=element('section');box.id='subscription-engines';box.className='subscription-engines';const title=element('h2','구독으로 연결하기');const help=element('p','Codex 또는 Claude Code의 공식 CLI에 먼저 로그인하세요. AgentOS는 API 키를 요구하거나 로그인 정보를 읽지 않습니다.');box.append(title,help);$('settings-panel').prepend(box);}
 for(const old of [...box.querySelectorAll('.subscription-engine')])old.remove();
 for(const engine of subscription?.engines||[]){const card=element('div',undefined,'subscription-engine');card.append(element('strong',engine.name));if(engine.connected){card.append(element('p','연결됨 · 공식 로그인은 사용자 확인으로만 기록되었습니다. AgentOS는 API 키나 로그인 정보를 읽지 않고, 제한된 AgentOS 도구로만 이 엔진을 실행합니다.'));box.append(card);continue;}if(!engine.installed){const p=element('p',`CLI를 찾지 못했습니다. 공식 설치 안내에서 설치한 뒤 ${engine.login_command} 명령으로 로그인하세요. `);const link=element('a','공식 안내 ↗');link.href=engine.login_url;link.target='_blank';link.rel='noreferrer noopener';p.append(link);card.append(p);box.append(card);continue;}card.append(element('p',`터미널에서 ${engine.login_command}을 실행해 공식 로그인 후 연결하세요.`));const button=element('button',`${engine.name} 로그인 완료 · 연결`);button.type='button';button.onclick=()=>busy(button,async()=>{try{await api('/api/subscription-engines/connect',{engine:engine.id,officially_authenticated:true});await refresh();}catch(e){error('global-error',e);}});card.append(button);box.append(card);}
}
function showOnboarding(guide){
 const box=$('onboarding-guide');box.replaceChildren(element('h2','설치 및 복구 안내'));
 for(const step of guide.steps||[]){const row=element('p',(step.state==='ready'?'✓ ':step.state==='attention'?'! ':'→ ')+step.message);row.className='onboarding-'+step.state;box.append(row);}
 box.append(element('small','이 안내는 연결 여부와 작업 상태만 표시합니다. API 키, BotFather 토큰, 로그인 정보와 대화 내용은 표시하지 않습니다.'));
}
function showWorkspaces(home,state){
 const list=$('workspace-list');list.replaceChildren();const workspaces=home.workspaces||[];
 for(const workspace of workspaces){const row=element('div',undefined,'workspace-row');const text=element('div');text.append(element('strong',workspace.title,activeWorkspace===workspace.id?'workspace-active':''));if(workspace.purpose)text.append(element('p',workspace.purpose));row.append(text);const button=element('button',activeWorkspace===workspace.id?'선택됨':'이곳에서 이어가기');button.type='button';button.onclick=()=>{activeWorkspace=workspace.id;showWorkspaces(home,state);};row.append(button);list.append(row);}
 if(!workspaces.length)list.append(element('p','아직 작업공간이 없습니다.'));
 const results=$('workspace-results');results.replaceChildren();if(!activeWorkspace)return;
 const title=workspaces.find(item=>item.id===activeWorkspace)?.title||'선택한 작업공간';results.append(element('h3',title));
 for(const job of state.jobs.filter(item=>item.workspace_id===activeWorkspace&&['succeeded','partial'].includes(item.status)).slice(0,5)){const row=element('div',undefined,'workspace-result');row.append(element('p',job.response||'완료된 결과'));const save=element('button','결과 저장');save.type='button';save.onclick=()=>busy(save,async()=>{try{await api('/api/workspaces/'+encodeURIComponent(activeWorkspace)+'/save-result',{job_id:job.id});$('workspace-feedback').textContent='결과를 작업공간에 저장했습니다.';await refresh();}catch(e){error('workspace-feedback',e);}});row.append(save);results.append(row);}
}
function taskStatusText(task){return task.status_kind==='active'?'진행 중':task.status_kind==='attention'?'확인 필요':'완료';}
async function selectTask(id){
 if(taskProgressLoading)return;
 selectedTaskId=id;showTaskProgress(taskProgressState||{});
 taskProgressLoading=true;
 try{
  const detail=await api('/api/tasks/'+encodeURIComponent(id));
  if(taskProgressState)taskProgressState={...taskProgressState,tasks:taskProgressState.tasks.map(task=>task.id===id?detail.selected:task)};
  showTaskProgress(taskProgressState);
 }catch(e){error('global-error',e);}finally{taskProgressLoading=false;}
}
function showTaskProgress(progress){
 const list=$('task-list'), detail=$('task-detail');if(!list||!detail)return;const tasks=progress?.tasks||[];list.replaceChildren();
 if(!tasks.length){list.append(element('p','최근 요청이 없습니다.'));detail.replaceChildren(element('p','작업을 선택하면 과정과 결과를 확인할 수 있어요.'));return;}
 if(!selectedTaskId||!tasks.some(task=>task.id===selectedTaskId))selectedTaskId=tasks[0].id;
 for(const task of tasks){const row=element('button',undefined,'task-row '+(task.id===selectedTaskId?'selected':''));row.type='button';row.onclick=()=>selectTask(task.id);const title=element('strong',task.title);const meta=element('span',`${taskStatusText(task)} · ${new Date(task.started_at*1000).toLocaleString()}${task.result_available?' · 결과 있음':''}`);row.append(title,meta);list.append(row);}
 const task=tasks.find(item=>item.id===selectedTaskId);const openEvents=[...detail.querySelectorAll('.task-event[open]')].map(item=>item.dataset.eventId);for(const id of openEvents)expandedTaskEvents.add(id);detail.replaceChildren();detail.append(element('h3',task.title));detail.append(element('p',`${taskStatusText(task)} · 요청 ID ${task.id.slice(0,8)} · 시작 ${new Date(task.started_at*1000).toLocaleString()}`));
 const models=element('div',undefined,'task-models');models.append(element('p',`설정된 AI/runtime: ${task.configured.provider||'알 수 없음'} · ${task.configured.model||'알 수 없음'} · ${task.configured.runtime||'알 수 없음'}`));models.append(element('p',`관찰된 AI/runtime: ${task.observed.provider||'알 수 없음'} · ${task.observed.model||'알 수 없음'} · ${task.observed.runtime||'알 수 없음'}`));detail.append(models);
 if(task.waits?.length)detail.append(element('p','대기: '+task.waits.join(' · '),'task-attention'));
 if(task.error)detail.append(element('p','오류: '+task.error,'error'));
 if(task.source_references?.length){detail.append(element('p','사용한 근거: '+task.source_references.join(' · '),'task-sources'));}
 const timeline=element('div',undefined,'task-timeline');timeline.append(element('h4','관찰된 과정'));if(!task.events?.length)timeline.append(element('p',progress.unknown_detail_message));
 for(const event of task.events||[]){const item=element('details','', 'task-event');item.dataset.eventId=String(event.id);item.open=expandedTaskEvents.has(String(event.id));item.addEventListener('toggle',()=>{if(item.open)expandedTaskEvents.add(item.dataset.eventId);else expandedTaskEvents.delete(item.dataset.eventId);});const summary=element('summary',`${event.tool} · ${event.status==='succeeded'?'완료':event.status==='failed'?'실패':event.status==='running'?'실행 중':'관찰됨'} · ${new Date(event.created*1000).toLocaleTimeString()}`);item.append(summary,element('p',event.summary));const safe=Object.entries(event.details||{});if(safe.length){const detailText=safe.map(([key,value])=>`${key}: ${value}`).join(' · ');item.append(element('small',detailText));}timeline.append(item);}detail.append(timeline);
 const artifacts=element('div',undefined,'task-artifacts');artifacts.append(element('h4','결과'));if(!task.artifacts?.length&&!task.result_available)artifacts.append(element('p','관찰된 결과 artifact가 없습니다.'));for(const artifact of task.artifacts||[]){const row=element('p',`${artifact.kind} · ${artifact.path||'프로젝트 결과'} · ${artifact.state}`);if(artifact.workspace_id){const link=element('a','프로젝트 보기');link.href='#workspace-management';link.onclick=()=>{$('workspace-management').scrollIntoView({behavior:'smooth'});};row.append(' · ',link);}artifacts.append(row);}detail.append(artifacts);detail.append(element('small',progress.unknown_detail_message));
}
$('workspace-form').onsubmit=async e=>{e.preventDefault();await busy(e.submitter,async()=>{try{const workspace=await api('/api/workspaces',{title:$('workspace-title').value,purpose:$('workspace-purpose').value});activeWorkspace=workspace.id;$('workspace-title').value='';$('workspace-purpose').value='';$('workspace-feedback').textContent='작업공간을 만들었습니다. 다음 요청부터 이곳에 이어집니다.';await refresh();}catch(e){error('workspace-feedback',e);}});};
async function refresh(){
 if(!authenticated||refreshing)return;refreshing=true;
 try{
 const previousTaskProgress=taskProgressState;const nextTaskProgress=await api('/api/tasks');if(previousTaskProgress?.tasks){nextTaskProgress.tasks=nextTaskProgress.tasks.map(task=>{const previous=previousTaskProgress.tasks.find(item=>item.id===task.id);return previous?.events?{...task,...previous}:task;});}taskProgressState=nextTaskProgress;showTaskProgress(taskProgressState);const selectedTask=taskProgressState.tasks.find(task=>task.id===selectedTaskId);if(selectedTask&&!selectedTask.events&&!taskProgressLoading)selectTask(selectedTask.id);
 const home=await api('/api/home');const state=await api('/api/state');const space=await api('/api/personal-space');const guide=await api('/api/onboarding');const settings=state.settings;const model=settings.model;const tg=settings.telegram;hasModel=home.model_connected;showSubscriptionEngines(settings.subscription_engines);showOnboarding(guide);showWorkspaces(home,state);showPersonalSpace(space);const settingsFingerprint=JSON.stringify(settings.conversation_settings);if(settingsFingerprint!==conversationSettingsFingerprint){conversationSettingsFingerprint=settingsFingerprint;showConversationSettings(settings.conversation_settings);}$('home-next-action').textContent=home.next_action;const suggestion=$('workspace-suggestion');suggestion.replaceChildren();if(home.workspace_suggestion){suggestion.hidden=false;suggestion.append(document.createTextNode('이 대화를 프로젝트로 정리할까요? '));const button=element('button','프로젝트 만들기');button.type='button';button.onclick=()=>{$('workspace-link').click();$('workspace-title').focus();};suggestion.append(button);}else suggestion.hidden=true;
 const delivery=settings.delivery||{};let deliveryView=$('delivery-status');if(!deliveryView){deliveryView=element('div',undefined);deliveryView.id='delivery-status';document.querySelector('.workspace-heading').append(deliveryView);}deliveryView.replaceChildren();if(delivery.active){deliveryView.append(element('p',`전달 루프 · ${delivery.milestone||''} ${delivery.active} · ${delivery.status||'대기'}`));deliveryView.append(element('p',`최근 검증: ${delivery.last_validation==='passed'?'통과':delivery.last_validation==='failed'?'보류':'아직 없음'}`));if(String(delivery.status||'').startsWith('blocked-')){const reasons={'blocked-validation-failed':'실제 인수 검증이 아직 통과하지 않았습니다.','blocked-external-rate-limit':'외부 서비스 한도를 기다리고 있습니다.','blocked-approval':'사람의 승인 또는 권한이 필요합니다.'};deliveryView.append(element('p',reasons[delivery.status]||'전달 루프가 검증 문제를 해결할 때까지 대기 중입니다.'));}if(delivery.next_retry_at)deliveryView.append(element('p','다음 재시도: '+new Date(delivery.next_retry_at*1000).toLocaleString()));const issue=delivery.issue||(delivery.issues||{})[delivery.active];if(issue){const link=element('a','GitHub 이터레이션 보기');link.href='https://github.com/Jongtae/personal-agentos/issues/'+encodeURIComponent(issue);link.target='_blank';link.rel='noreferrer noopener';deliveryView.append(link);}}else deliveryView.append(element('p','전달 루프 · 아직 실행 기록이 없습니다.'));
 const acceptance=settings.telegram_task_card_acceptance;let acceptanceView=$('telegram-task-card-acceptance');if(!acceptanceView){acceptanceView=element('div',undefined);acceptanceView.id='telegram-task-card-acceptance';document.querySelector('.workspace-heading').append(acceptanceView);}acceptanceView.replaceChildren();if(tg.paired&&acceptance){const checks=acceptance.checks||{};const observed=['shared_web_evidence_observed','restart_continuity_observed'];const automatic=['paired_private_owner','task_card_cancellation','document_approval_callback','terminal_notification'].every(k=>checks[k]);if(acceptance.passed){acceptanceView.append(element('p','Telegram 실제 사용 확인이 기록되었습니다. 다음 릴리스 검증에 반영됩니다.'));}else if(automatic&&Object.values(acceptance.message_channels||{}).every(Boolean)){acceptanceView.append(element('p','Telegram 카드·취소·문서 승인·알림을 확인했다면, 웹 기록과 재시작 후 연속성도 확인했음을 기록하세요.'));const button=element('button','실제 Telegram 흐름 확인 기록');button.type='button';button.onclick=()=>busy(button,async()=>{try{await api('/api/telegram/task-card-acceptance',{web_confirmed:true,restart_confirmed:true});await refresh();}catch(e){error('global-error',e);}});acceptanceView.append(button);}else{acceptanceView.append(element('p','Telegram 실제 사용 확인 대기 중 · 카드 취소, 문서 승인, 완료 알림을 차례로 확인하면 여기에서 마무리할 수 있습니다.'));}}
 const shownProvider=displayProvider(model);const active=$('active-ai');active.replaceChildren();active.append(element('strong','현재 사용 중인 AI'));active.append(element('p',model.model?`${providerNames[shownProvider]||shownProvider} · ${model.model}`:'아직 연결되지 않음'));active.append(element('p',settings.model_ready?'준비됨 · 도구 호출 확인됨':settings.model_test?.error?'확인 실패 · '+settings.model_test.error:'확인 필요'));if(settings.model_test?.time)active.append(element('small','마지막 확인: '+new Date(settings.model_test.time*1000).toLocaleString()));
 const currentTool=(state.tool_events||[]).find(e=>e.job_id===state.jobs[0]?.id);
 $('tool-status').textContent=currentTool?({running:'실행 중',succeeded:'실행 완료',failed:'실행 실패'}[currentTool.status]+' · '+currentTool.tool+' · 내 AgentOS에서 실행'):'';
 $('tool-history').replaceChildren();for(const e of state.tool_events||[]){const trace=e.trace||{};const attempt=trace.attempt?' · '+trace.attempt+'회차':'';const error=trace.error?' · '+trace.error:'';$('tool-history').append(element('div',new Date(e.created*1000).toLocaleTimeString()+' · '+e.tool+' · '+({running:'실행 중',succeeded:'완료',failed:'실패'}[e.status]||e.status)+attempt+error));}
 $('runtime-badge').textContent=home.state==='working'?'작업 중':home.state==='attention'?'확인 필요':'준비됨';
 if(!modelLoaded){if(model.provider){$('provider').value=displayProvider(model);$('endpoint').value=model.endpoint;$('model-name').value=model.model;activeModelDestination=[model.provider,model.endpoint].join('|');}$('endpoint-help').textContent=providers[$('provider').value].help;$('root-paths').value=(settings.file_roots||[]).map(r=>r.path).join('\n');$('file-reference-paths').value=(settings.file_workspace?.references||[]).map(r=>r.path).join('\n');$('file-workspace-path').value=settings.file_workspace?.workspace||'';modelLoaded=true;}showDocumentBoundary(settings.document_boundary);showContextInbox(settings.context_inbox);
 const tested=settings.model_test;
 $('model-label').textContent=home.model_connected?'AI 연결됨':'메모 준비됨';
 $('key-hint').textContent=settings.has_api_key?'키가 저장되어 있습니다. 빈칸으로 저장하면 같은 연결의 키를 유지합니다.':'키는 대화 기록과 분리된 개인 설정 파일에 저장합니다.';
 $('telegram-status').textContent=settings.telegram_status?.message||'아직 연결되지 않았습니다.';
 $('disconnect').hidden=!tg.enabled;$('new-pair').hidden=!tg.enabled;
 if(tg.paired)$('telegram-pair').hidden=true;
 const fingerprint=JSON.stringify([state.messages,state.jobs,state.notes]);
 if(fingerprint!==stateFingerprint){stateFingerprint=fingerprint;
 const container=$('messages');const nearBottom=container.scrollHeight-container.scrollTop-container.clientHeight<90;
 if(state.messages.length){container.replaceChildren();for(const m of state.messages){const item=element('article',undefined,'message '+m.role);item.append(element('div',(m.role==='user'?'나':'AgentOS')+' · '+(m.channel.startsWith('telegram:')?'Telegram':'웹'),'message-meta'));const bubble=element('div',undefined,'bubble');for(const part of m.content.split(/(https?:\/\/[^\s<>]+)/g)){if(/^https?:\/\//.test(part)){const a=element('a',part);a.href=part;a.target='_blank';a.rel='noreferrer noopener';bubble.append(a);}else bubble.append(document.createTextNode(part));}item.append(bubble);const evidence=(m.role==='assistant'&&m.job_id&&(state.evidence||{})[m.job_id])||[];if(evidence.length){const source=element('p','사용한 근거: '+evidence.join(' · '),'message-evidence');source.title='원문, 파일 경로, 검색어는 여기에서 표시하지 않습니다.';item.append(source);}container.append(item);}if(nearBottom||container.scrollTop===0)container.scrollTop=container.scrollHeight;}
 const pending=state.jobs.filter(j=>j.status==='queued'||j.status==='running');const failed=state.jobs.slice(0,1).find(j=>j.status==='failed'||j.status==='partial'||j.status==='interrupted'||j.delivery==='unknown');
 $('job-status-message').textContent=pending.length?`${pending.length}개 작업 처리 중…`:failed?(failed.delivery==='unknown'?'결과가 Telegram에 도착했는지 확인할 수 없어요. 웹에서 결과를 확인한 뒤, 필요하면 새로 요청하세요.':failed.status==='interrupted'?'작업이 중단됐어요. 자동으로 다시 실행하지 않았습니다. 결과를 확인한 뒤 필요하면 다시 요청하세요.':failed.error?'이 요청을 마치지 못했어요. 내용을 확인하고 다시 요청해 주세요.':'일부 작업을 마치지 못했어요. 내용을 확인하고 다시 요청해 주세요.') :'';const current=pending[0]||failed;$('current-task-link').hidden=!current;if(current){selectedTaskId=current.id;$('current-task-link').onclick=()=>{openConnections();selectTask(current.id);$('task-status-panel').scrollIntoView({behavior:'smooth',block:'start'});};}
 $('note-count').textContent=String(state.notes.length);$('notes-list').replaceChildren();for(const n of state.notes)$('notes-list').append(element('article',n.content));if(!state.notes.length)$('notes-list').append(element('p','메모가 없습니다.'));
 }
 }catch(e){error('global-error',e);}finally{refreshing=false;}
}
status().catch(e=>error('global-error',e));setInterval(()=>{if(authenticated)refresh();},2000);

let hasModel=false;
$('connect-openrouter').onclick=async()=>{
 const popup=window.open('about:blank','agentos-openrouter');
 try {
 const bytes=crypto.getRandomValues(new Uint8Array(48));
 const verifier=btoa(String.fromCharCode(...bytes)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
 const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier));
 const challenge=btoa(String.fromCharCode(...new Uint8Array(digest))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
 sessionStorage.setItem('agentos-draft',$('message').value);
 const state=crypto.randomUUID();localStorage.setItem('openrouter-flow',JSON.stringify({verifier,state,expires:Date.now()+600000}));
 const callback=location.origin+'/?state='+encodeURIComponent(state);
 const url='https://openrouter.ai/auth?'+new URLSearchParams({callback_url:callback,code_challenge:challenge,code_challenge_method:'S256'});
 const flow=JSON.parse(localStorage.getItem('openrouter-flow'));flow.url=url;localStorage.setItem('openrouter-flow',JSON.stringify(flow));
 $('resume-openrouter').hidden=false;$('easy-feedback').textContent='새 창에서 가입 또는 로그인하고 연결을 승인해 주세요. 이 대화는 그대로 유지됩니다. 가입 후 승인 화면이 나오지 않으면 연결 이어가기를 눌러 주세요.';
 if(popup)popup.location.href=url;else $('easy-feedback').textContent='새 창이 차단됐습니다. 연결 이어가기를 눌러 새 창을 열어 주세요.';
 }catch(e){error('easy-feedback',e);}
};
async function finishOpenRouter(){
 const params=new URLSearchParams(location.search);if(!params.has('code'))return;
 const code=params.get('code'),returnedState=params.get('state');history.replaceState(null,'',location.pathname);
 openConnections();$('message').value=sessionStorage.getItem('agentos-draft')||'';sessionStorage.removeItem('agentos-draft');
 try{
 const flow=JSON.parse(localStorage.getItem('openrouter-flow')||'null');
 if(!flow||flow.state!==returnedState||Date.now()>flow.expires)throw new Error('연결 시간이 지났습니다. 계정 연결을 다시 눌러 주세요.');
 const connected=await api('/api/openrouter/connect',{code,verifier:flow.verifier});localStorage.removeItem('openrouter-flow');localStorage.setItem('openrouter-connected',String(Date.now()));modelLoaded=false;await refresh();$('easy-feedback').textContent=connected.model_test?.ok?'OpenRouter 무료 모델과 도구 호출을 확인했습니다. 이제 Telegram과 웹에서 바로 대화할 수 있습니다.':(connected.model_test?.error||'OpenRouter는 연결됐지만 도구 호출 모델을 확인하지 못했습니다. 아래 목록에서 다른 무료 모델을 선택해 주세요.');
 $('easy-feedback').textContent='계정이 연결됐습니다. “도구 지원 무료 모델 보기”에서 모델 하나를 선택해 확인해 주세요.';$('message').focus();if(window.opener)window.close();
 }catch(e){error('easy-feedback',e);$('resume-openrouter').hidden=false;}
}
$('find-local').onclick=()=>busy($('find-local'),async()=>{
 $('local-models').replaceChildren();
 try{
 const data=await api('/api/ollama/models',{});
 $('local-help').textContent=data.models.length?'사용할 모델을 선택하세요.':'Ollama는 실행 중이지만 모델이 없습니다. Ollama에서 모델을 먼저 다운로드해 주세요.';
 for(const m of data.models){const button=element('button',m.name);button.type='button';button.onclick=()=>busy(button,async()=>{try{await api('/api/model',{provider:'ollama',endpoint:'http://127.0.0.1:11434',model:m.name});modelLoaded=false;await refresh();$('local-help').textContent='연결했습니다. 대화창에서 메시지를 보내세요.';}catch(e){error('local-help',e);}});$('local-models').append(button);}
 }catch(e){$('local-help').textContent='실행 중인 Ollama를 찾지 못했습니다. 아래 설치 안내에서 설치하고 실행한 뒤 다시 찾아 주세요.';}
});

$('resume-openrouter').onclick=()=>{
 const flow=JSON.parse(localStorage.getItem('openrouter-flow')||'null');
 if(flow&&flow.expires>Date.now()&&flow.url){window.open(flow.url,'agentos-openrouter');}
 else $('connect-openrouter').click();
};
if(localStorage.getItem('openrouter-flow')){$('resume-openrouter').hidden=false;}
window.addEventListener('storage',async e=>{if(e.key==='openrouter-connected'){modelLoaded=false;await refresh();$('resume-openrouter').hidden=true;$('easy-feedback').textContent='계정이 연결됐습니다. 도구 지원 무료 모델을 골라 확인해 주세요.';$('message').focus();}});
$('load-free-models').onclick=()=>busy($('load-free-models'),async()=>{
 try{const data=await api('/api/openrouter/models',{});$('free-model-list').replaceChildren();
 for(const m of data.models){const button=element('button',m.name+' · '+m.id);button.type='button';button.onclick=()=>busy(button,async()=>{try{await api('/api/model',{provider:'compatible',endpoint:'https://openrouter.ai/api/v1',model:m.id});const checked=await api('/api/model/test',{});modelLoaded=false;await refresh();$('easy-feedback').textContent=checked.ok?'무료 모델과 도구 호출을 연결했습니다. 이제 메시지를 보내 보세요.':(checked.error||'이 무료 모델의 도구 호출을 확인하지 못했습니다. 다른 모델을 골라 주세요.');}catch(e){error('easy-feedback',e);}});$('free-model-list').append(button);}
 if(!data.models.length)$('free-model-list').append(element('p','현재 확인된 도구 지원 무료 모델이 없습니다. 잠시 후 다시 확인하세요.'));
 }catch(e){$('free-model-list').replaceChildren(element('p','목록을 가져오지 못했습니다. 잠시 후 다시 시도하세요.'));}
});

$('roots-form').onsubmit=async e=>{e.preventDefault();await busy(e.submitter,async()=>{try{await api('/api/files/roots',{paths:$('root-paths').value.split('\n').map(p=>p.trim()).filter(Boolean)});$('roots-feedback').textContent='폴더를 연결했습니다. 대화창에서 파일을 찾아 달라고 요청하세요.';}catch(e){error('roots-feedback',e);}});};
$('file-workspace-form').onsubmit=async e=>{e.preventDefault();await busy(e.submitter,async()=>{try{await api('/api/file-workspace',{references:$('file-reference-paths').value.split('\n').map(p=>p.trim()).filter(Boolean),workspace:$('file-workspace-path').value.trim()});$('file-workspace-feedback').textContent='파일 작업공간을 연결했습니다. “자료를 요약해 파일로 저장해줘”라고 요청해 보세요.';modelLoaded=false;await refresh();}catch(e){error('file-workspace-feedback',e);}});};

// Owner-facing IA stays small: five destinations, one explicit first-use path.
async function renderOwnerFlow(){
 if(!authenticated||!$('workspace'))return;
 let home,state;try{[home,state]=await Promise.all([api('/api/home'),api('/api/state')]);}catch(e){return;}
 let nav=document.querySelector('.top-nav');if(!nav){nav=element('nav',undefined,'top-nav');nav.setAttribute('aria-label','주요 메뉴');[['conversation','대화'],['task-status-panel','작업 현황'],['records-section','내 기록'],['workspace-management','프로젝트'],['settings-panel','설정']].forEach(([id,label])=>{const button=element('button',label);button.type='button';button.dataset.view=id;nav.append(button);});$('workspace').prepend(nav);nav.addEventListener('click',event=>{const button=event.target.closest('[data-view]');if(!button)return;const target=button.dataset.view;if(target==='conversation'){document.querySelector('.chat-panel')?.scrollIntoView({behavior:'smooth'});}else{openConnections();$(target)?.scrollIntoView({behavior:'smooth'});}nav.querySelectorAll('button').forEach(item=>item.classList.toggle('active',item===button));});}
 const ready=!!home.model_connected, files=!!(state.settings.file_roots?.length||state.settings.file_workspace?.references?.length||state.settings.file_workspace?.workspace), firstRequest=!!home.conversation?.length;
 let checklist=$('setup-checklist');if(!checklist){checklist=element('section',undefined,'setup-checklist');checklist.id='setup-checklist';const intro=element('div');intro.append(element('p','처음 사용하기','eyebrow'),element('h2','내 작업 흐름을 3단계로 준비해요'));intro.append(element('p','필요한 것만 연결하고, 첫 요청의 실제 결과를 확인하면 준비가 끝납니다.'));const steps=element('div',undefined,'setup-steps');steps.id='setup-steps';checklist.append(intro,steps);const more=element('details');more.innerHTML='<summary>더 알아보기</summary><p>진행률이나 예상 시간은 추정하지 않고 AgentOS가 실제로 관찰한 상태만 보여줍니다.</p>';checklist.append(more);$('workspace-suggestion').after(checklist);}
 checklist.hidden=ready&&files&&firstRequest;const steps=$('setup-steps');steps.replaceChildren();const items=[['AI 연결',ready,'AI를 연결하고, 정확히 이 설정을 테스트한 뒤 적용하세요.',()=>{openConnections();$('settings-panel').scrollIntoView({behavior:'smooth'});}],["파일 위치 설정",files,'참고 폴더와 결과 저장 폴더를 구분해 지정하세요.',()=>{openConnections();$('files-section').scrollIntoView({behavior:'smooth'});}],["첫 요청 실행",firstRequest,'대화에서 요청을 보내고 관찰된 과정과 결과를 확인하세요.',()=>{$('message').focus();}]];items.forEach(([title,done,help,action],index)=>{const row=element('div',undefined,'setup-step '+(done?'done':''));row.append(element('span',done?'✓':String(index+1),'setup-step-mark'));const copy=element('div');copy.append(element('strong',title),element('p',done?'완료됨':help));row.append(copy);if(!done){const button=element('button',index===2?'요청 작성':'설정하기');button.type='button';button.onclick=action;row.append(button);}steps.append(row);});
 const card=$('active-ai');if(card&&!card.querySelector('[data-ai-state]')){const stateBox=element('div',undefined,'ai-state-grid');stateBox.dataset.aiState='true';stateBox.append(element('p','저장된 설정 · 아래 편집 화면에 저장된 값','ai-state-muted'),element('p','테스트한 설정 · 성공한 초안만 적용 가능','ai-state-muted'),element('p','현재 사용 모델 · 대화에 적용된 모델','ai-state-muted'),element('p','최근 응답 모델 · 작업 현황에서 관찰된 값','ai-state-muted'));card.append(stateBox);}
}
setInterval(()=>{if(authenticated)renderOwnerFlow();},2500);

"""#588 Settings › 외부 연결: Google disconnect preview → confirm → truthful receipt.

The backend contract (#644) is tested in test_connector_revocation.py; these DOM
checks cover only what the owner sees and which requests the UI sends.
"""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).parents[1] / "src" / "personal_agent" / "web"
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "app.js").read_text(encoding="utf-8")


DOM_CHECKS = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const app=fs.readFileSync(process.argv[1],'utf8'),ids=new Map();let focused=null;
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.className='';this.hidden=false;this.disabled=false;this._text='';}
 set id(value){this._id=value;ids.set(value,this);} get id(){return this._id;}
 set textContent(value){this._text=String(value);this.children=[];} get textContent(){return this._text+this.children.map(node=>typeof node==='string'?node:node.textContent).join('');}
 append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}
 setAttribute(key,value){this.attrs[key]=value;} focus(){focused=this;} get isConnected(){return true;}
 contains(node){return node===this||descendants(this).includes(node);}
 get classList(){const node=this;return {toggle(name,on){node._cls=Boolean(on);},add(){},remove(){},contains:()=>Boolean(node._cls)};}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
 querySelectorAll(selector){const tags=selector.split(',');return descendants(this).filter(node=>selector==='[data-focus-key]'?Boolean(node.dataset.focusKey):tags.includes(node.tag));}
}
function descendants(node){return node.children.flatMap(child=>typeof child==='string'?[]:[child,...descendants(child)]);}
for(const id of ['connector-controls','connector-feedback','google-disconnect-title','google-disconnect-summary','google-disconnect-effects','google-disconnect-feedback','google-disconnect-cancel','google-disconnect-confirm','google-disconnect-retry'])new Element(id.endsWith('cancel')||id.endsWith('confirm')||id.endsWith('retry')?'button':'div').id=id;
const dialog=new Element('dialog');dialog.id='google-disconnect';dialog.open=false;dialog.showModal=()=>{dialog.open=true;};dialog.close=()=>{dialog.open=false;dialog.onclose&&dialog.onclose();};
const $=id=>ids.get(id),document={getElementById:$,createElement:tag=>new Element(tag),get activeElement(){return focused;},body:null};
const part=(start,end)=>app.slice(app.indexOf(start),app.indexOf(end));
const source=part('const LANGUAGES=','function normalizeEndpoint(')+part('function element(','function setError(')+part('function rememberFocus(','function clockNode(')+
 'function focusKey(node,key){node.dataset.focusKey=key;return node;}\n'+part('// Owner-visible words for the four contract states.',"$('telegram-change').onclick");
const calls=[],answers={};let refreshes=0;
const ctx={document,$,console,lastState:null,
 api:async(path,body)=>{calls.push({path,body});const answer=answers[path];if(answer instanceof Error)throw answer;return typeof answer==='function'?answer(body):(answer||{});},
 refresh:async()=>{refreshes++;},busy:async(button,fn)=>fn(),
 setError:(id,error)=>{$(id).textContent=error?.message||String(error||'');$(id)._error=true;},setFeedback:(id,text)=>{$(id).textContent=text||'';$(id)._error=false;}};
vm.createContext(ctx);vm.runInContext(source,ctx);vm.runInContext("setLanguage('ko')",ctx);
const same=(a,b,m)=>assert.equal(JSON.stringify(a),JSON.stringify(b),m);
const buttons=()=>descendants($('connector-controls')).filter(node=>node.tag==='button');
const button=text=>buttons().find(node=>node.textContent===text);
const gmail={connector_id:'google-gmail-read',label:'Gmail',state:'connected',required_scopes:['gmail.readonly'],connect_path:'/google-gmail'};
const effects={local_access:'stop',local_credentials:'delete',provider_revocation:'request',provider_destination:'oauth2.googleapis.com',retained_data:'preserve',remote_data_deletion:'none'};
const receipt=(extra={})=>({connector_id:'google-gmail-read',operation:'disconnect',local_access:'stopped',local_credentials:'deleted',provider_revocation:'revoked',provider_request:'observed',provider_destination:'oauth2.googleapis.com',retained_data:'preserved',retry_available:false,label:'Gmail',state:'disconnected',message:'server text',...extra});
const text=id=>$(id).textContent;
let previews=0;
answers['/api/connections/google/revocations']={pending_provider_revocations:[]};
(async()=>{
 // Only a connected or reauth_required row offers 연결 해제, next to its existing reconnect link.
 const rows=[gmail,{...gmail,connector_id:'google-calendar-write',state:'reauth_required'},{...gmail,connector_id:'google-calendar',state:'disconnected'},{...gmail,connector_id:'google-drive-read',state:'blocked'},{...gmail,connector_id:'google-drive-read',state:'surprising'}];
 for(const row of rows){ctx.renderConnectors([row]);assert.equal(Boolean(button('연결 해제')),['connected','reauth_required'].includes(row.state),`${row.state}: disconnect offered only for a live connection`);}
 ctx.renderConnectors([gmail]);const opener=button('연결 해제');assert(opener.className.includes('destructive'),'destructive grammar');
 assert(descendants($('connector-controls')).some(node=>node.tag==='a'&&node.textContent==='다시 연결'),'the reconnect link stays');

 // Opening shows a modal, focuses the safe action and asks for the preview; nothing can be confirmed before it answers.
 let release;answers['/api/connections/google/disconnect/preview']=()=>new Promise(resolve=>{release=()=>resolve({connector_id:'google-gmail-read',label:'Gmail',state:'connected',confirmation:'c'+(++previews),expires_at:1,effects,message:'server preview text'});});
 opener.onclick({currentTarget:opener});
 assert(dialog.open,'a modal <dialog>');assert.equal(focused,$('google-disconnect-cancel'),'focus starts on 취소');
 assert($('google-disconnect-confirm').disabled,'confirm is disabled while the preview loads');assert(text('google-disconnect-summary').includes('확인하는 중'));
 same(calls.at(-1),{path:'/api/connections/google/disconnect/preview',body:{connector_id:'google-gmail-read'}});
 answers['/api/connections/google/disconnect/preview']=()=>({connector_id:'google-gmail-read',label:'Gmail',state:'connected',confirmation:'c'+(++previews),expires_at:1,effects,message:'server preview text'});
 release();await new Promise(resolve=>setTimeout(resolve,0));
 assert(!$('google-disconnect-confirm').disabled);assert.equal(text('google-disconnect-title'),'Google Gmail 연결 해제');
 const effectsText=text('google-disconnect-effects');
 for(const phrase of ['멈추는 것','바로 쓰지 않습니다','인증 정보를 삭제합니다','Google(oauth2.googleapis.com)에 권한 취소를 요청합니다','남는 것','결과물과 작업 기록은 지우지 않습니다','Google에 있는 메일, 일정, 파일은 삭제하지 않습니다'])assert(effectsText.includes(phrase),'preview names: '+phrase);
 assert(!effectsText.includes('Picker'),'the Drive-only effect is not claimed for Gmail');

 // Confirm sends exactly the preview's confirmation once and shows the receipt's own words.
 answers['/api/connections/google/disconnect']=receipt();refreshes=0;
 await ctx.confirmGoogleDisconnect($('google-disconnect-confirm'));
 same(calls.at(-2),{path:'/api/connections/google/disconnect',body:{connector_id:'google-gmail-read',confirmation:'c1'}});
 assert.equal(calls.at(-1).path,'/api/connections/google/revocations','pending revocations are reloaded after the receipt');
 assert.equal(refreshes,1);assert.equal(text('google-disconnect-title'),'Google Gmail 연결을 해제했습니다');assert.equal(focused,$('google-disconnect-title'),'focus moves to the result');
 assert(text('google-disconnect-effects').includes('Google에서도 권한 취소를 확인했습니다'));assert($('google-disconnect-confirm').hidden&&$('google-disconnect-retry').hidden);
 assert.equal(text('google-disconnect-cancel'),'닫기');

 // Closing returns focus to the row: the reconnect link once the disconnect button is gone.
 ctx.renderConnectors([{...gmail,state:'disconnected'}]);dialog.close();assert.equal(focused?.textContent,'연결','focus returns to the row, not the page top');

 // Unconfirmed at Google: never presented as revoked; retry is offered and only the provider line changes.
 for(const [outcome,expected] of [['unconfirmed','요청이 도착했는지는 알 수 없습니다'],['failed','거절해'],['not_attempted','취소 요청을 보내지 않았습니다']]){
  ctx.renderConnectors([gmail]);const again=button('연결 해제');again.onclick({currentTarget:again});await new Promise(resolve=>setTimeout(resolve,0));
  answers['/api/connections/google/disconnect']=receipt({provider_revocation:outcome,retry_available:outcome!=='not_attempted',local_credentials:outcome==='not_attempted'?'none_stored':'deleted'});
  await ctx.confirmGoogleDisconnect($('google-disconnect-confirm'));
  assert(text('google-disconnect-title').includes('Google 쪽 취소는 확인되지 않음'),outcome+': heading says unconfirmed');
  assert(!text('google-disconnect-effects').includes('권한 취소를 확인했습니다'),outcome+': no revoked claim');
  assert(text('google-disconnect-effects').includes(expected));
  assert.equal($('google-disconnect-retry').hidden,outcome==='not_attempted',outcome+': retry only when the receipt offers it');
  dialog.close();
 }

 // local_access incomplete stays the headline even after a successful retry at Google.
 ctx.renderConnectors([gmail]);button('연결 해제').onclick({currentTarget:button('연결 해제')});await new Promise(resolve=>setTimeout(resolve,0));
 answers['/api/connections/google/disconnect']=receipt({local_access:'incomplete',provider_revocation:'unconfirmed',provider_request:'unknown',retry_available:true});
 await ctx.confirmGoogleDisconnect($('google-disconnect-confirm'));
 assert.equal(text('google-disconnect-title'),'Google Gmail 연결을 모두 해제하지 못했습니다');assert(text('google-disconnect-effects').includes('아직 사용될 수 있습니다'));
 answers['/api/connections/google/revocation/retry']={local_access:'stopped',local_credentials:'deleted',provider_revocation:'revoked',provider_request:'observed',retry_available:false};
 await ctx.retryGoogleDisconnect($('google-disconnect-retry'));
 same(calls.at(-2),{path:'/api/connections/google/revocation/retry',body:{connector_id:'google-gmail-read'}});
 assert.equal(text('google-disconnect-title'),'Google Gmail 연결을 모두 해제하지 못했습니다','a retry never upgrades the local result');
 assert(text('google-disconnect-effects').includes('Google에서도 권한 취소를 확인했습니다')&&$('google-disconnect-retry').hidden);
 dialog.close();

 // A refused confirmation (expired/replayed/changed) is shown as refused; the next attempt asks for a fresh preview.
 ctx.renderConnectors([gmail]);button('연결 해제').onclick({currentTarget:button('연결 해제')});await new Promise(resolve=>setTimeout(resolve,0));
 answers['/api/connections/google/disconnect']=new Error('확인 시간이 지났습니다. 연결 해제를 다시 확인해 주세요.');
 await ctx.confirmGoogleDisconnect($('google-disconnect-confirm'));
 assert(text('google-disconnect-feedback').includes('확인 시간이 지났습니다'));assert.equal(text('google-disconnect-confirm'),'다시 확인');assert.equal(text('google-disconnect-effects'),'','no stale effects after a refusal');
 const before=previews;await ctx.confirmGoogleDisconnect($('google-disconnect-confirm'));
 assert.equal(previews,before+1,'다시 확인 requests a new preview');assert.equal(calls.at(-1).path,'/api/connections/google/disconnect/preview');
 // An unreachable server during the disconnect is not reported as done or as nothing happened.
 const offline=new Error('오프라인');offline.offline=true;answers['/api/connections/google/disconnect']=offline;
 await ctx.confirmGoogleDisconnect($('google-disconnect-confirm'));assert(text('google-disconnect-feedback').includes('처리됐는지 확인하지 못했습니다'));
 dialog.close();

 // Unexpected effects are not paraphrased: the server's own statement is shown.
 answers['/api/connections/google/disconnect/preview']={connector_id:'google-drive-read',confirmation:'x',effects:{...effects,remote_data_deletion:'request'},message:'server preview text'};
 ctx.renderConnectors([{...gmail,connector_id:'google-drive-read'}]);button('연결 해제').onclick({currentTarget:button('연결 해제')});await new Promise(resolve=>setTimeout(resolve,0));
 assert.equal(text('google-disconnect-effects'),'server preview text');dialog.close();
 answers['/api/connections/google/disconnect/preview']={connector_id:'google-drive-read',confirmation:'y',effects,message:''};
 ctx.renderConnectors([{...gmail,connector_id:'google-drive-read'}]);button('연결 해제').onclick({currentTarget:button('연결 해제')});await new Promise(resolve=>setTimeout(resolve,0));
 assert(text('google-disconnect-effects').includes('Google Picker에서 골라 둔 파일 선택도 지웁니다'),'Drive preview names the file selection');dialog.close();

 // A still-unconfirmed revocation stays on the row; retry is offered only while not reconnected.
 answers['/api/connections/google/revocations']={pending_provider_revocations:[{connector_id:'google-gmail-read',label:'Gmail',since:1}]};
 ctx.lastState={settings:{connectors:[{...gmail,state:'disconnected'}]}};await ctx.loadGoogleRevocations();
 assert($('connector-controls').textContent.includes('Google 쪽 권한 취소가 아직 확인되지 않았습니다'));const retry=button('Google에 다시 요청');assert(retry,'retry on the row');
 answers['/api/connections/google/revocation/retry']={provider_revocation:'revoked',retry_available:false};answers['/api/connections/google/revocations']={pending_provider_revocations:[]};
 await retry.onclick({currentTarget:retry});await new Promise(resolve=>setTimeout(resolve,0));
 assert(text('connector-feedback').includes('Google에서도 권한 취소를 확인했습니다'));assert(!button('Google에 다시 요청'),'the row clears once Google confirmed');
 answers['/api/connections/google/revocations']={pending_provider_revocations:[{connector_id:'google-gmail-read',label:'Gmail',since:1}]};
 ctx.lastState={settings:{connectors:[gmail]}};await ctx.loadGoogleRevocations();
 assert($('connector-controls').textContent.includes('아직 확인되지 않았습니다')&&!button('Google에 다시 요청'),'a reconnected row keeps the note but offers no retry that would end the new grant');
 console.log('google disconnect DOM checks passed');
})().catch(error=>{console.error(error);process.exit(1);});
"""


def test_google_disconnect_flow_is_previewed_confirmed_and_truthful():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for the DOM checks")
    result = subprocess.run([node, "-e", DOM_CHECKS, str(ROOT / "app.js")], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "google disconnect DOM checks passed" in result.stdout


def test_disconnect_dialog_markup_is_accessible():
    dialog = HTML[HTML.index('<dialog id="google-disconnect"'):]
    dialog = dialog[:dialog.index("</dialog>")]
    assert 'aria-labelledby="google-disconnect-title"' in dialog
    assert 'id="google-disconnect-title" tabindex="-1"' in dialog  # focus target for the result
    assert 'role="status" aria-live="polite"' in dialog
    assert 'id="google-disconnect-confirm" class="destructive" type="button" disabled' in dialog
    assert '<div id="connector-controls" class="settings-list"></div><p id="connector-feedback"' in HTML
    # The settings view reloads still-unconfirmed revocations; rendering itself calls nothing.
    assert "activeSettings==='external')void loadGoogleRevocations();" in APP

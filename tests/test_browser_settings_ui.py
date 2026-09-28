"""SEC-BROWSER-02 #680: Settings › 외부 연결 › 브라우저 로그인 세션 rendering.

Evidence class: static markup checks plus a node-driven render of the
section's own functions with a fake DOM and a recording ``api``.  No browser
worker, Keychain or site is contacted.
"""
from html.parser import HTMLParser
from pathlib import Path
import json
import shutil
import subprocess
import unittest

WEB = Path(__file__).parents[1] / "src" / "personal_agent" / "web"
HTML = (WEB / "index.html").read_text(encoding="utf-8")
APP = (WEB / "app.js").read_text(encoding="utf-8")


class Elements(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.items = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.items.append((tag, dict(attrs)))


DOM_CHECKS = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const app=fs.readFileSync(process.argv[1],'utf8'),ids=new Map();
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.className='';this.hidden=false;this._text='';this.value='';this.disabled=false;}
 set id(value){this._id=value;ids.set(value,this);} get id(){return this._id;}
 set textContent(value){this._text=String(value);this.children=[];} get textContent(){return this._text+this.children.map(node=>typeof node==='string'?node:node.textContent).join('');}
 append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}
 setAttribute(key,value){this.attrs[key]=value;} focus(){if(!this.disabled)document.activeElement=this;} get isConnected(){return true;}
 contains(node){return node===this||descendants(this).includes(node);}
 get classList(){const node=this;return {toggle(name,on){node._cls=Boolean(on);},add(){},remove(){},contains:()=>Boolean(node._cls)};}
 querySelector(selector){return descendants(this).find(node=>selector[0]==='.'?node.className.split(' ').includes(selector.slice(1)):node.tag===selector.replace(/\[.*$/,''))||null;}
 querySelectorAll(selector){return descendants(this).filter(node=>selector==='[data-focus-key]'?Boolean(node.dataset.focusKey):node.tag===selector);}
}
function descendants(node){return node.children.flatMap(child=>typeof child==='string'?[]:[child,...descendants(child)]);}
for(const id of ['browser-status','browser-feedback','browser-login-form','browser-login-url','browser-login-open','browser-login-cancel'])new Element('div').id=id;
const $=id=>ids.get(id),document={getElementById:$,createElement:tag=>new Element(tag),activeElement:null,body:null};
const part=(start,end)=>app.slice(app.indexOf(start),app.indexOf(end));
const source='var lastState=null;'+part('const LANGUAGES=','function normalizeEndpoint(')+part('function formatTimeParts(','// Formatted result text.')+
 part('function element(','function setError(')+part('function setError(','async function busy(')+part('function focusKey(','function mainAiRoutes(')+
 part('let browserDeletePending=null;','async function refresh(');
const calls=[];let refreshes=0;
const ctx={document,$,console,Date,api:async(path,body)=>{calls.push({path,body});return {};},refresh:async()=>{refreshes++;},busy:async(button,fn)=>fn()};
vm.createContext(ctx);vm.runInContext(source,ctx);vm.runInContext("setLanguage('ko')",ctx);
const text=()=>$('browser-status').textContent,buttons=()=>descendants($('browser-status')).filter(node=>node.tag==='button');
const render=status=>{$('browser-status').dataset.state='';ctx.renderBrowser(status);ctx.lastState={settings:{browser:status}};};
const storage={what:'site-sign-in-cookies',path:'/data/private/browser-profile/session-jar.enc',key:'macos-keychain',key_service:'personal-agentos.browser-jar',sent_to_ai:false,state:'stored'};
const available=(overrides={})=>({available:true,unavailable_reason:null,storage,sessions:[],pending_steps:[],login_window_open:false,in_use:false,...overrides});
const checks=[];
(async()=>{
 render({available:false,unavailable_reason:'platform',message:'x',sessions:[],pending_steps:[]});
 assert(text().includes('macOS에서만 제공됩니다'));assert(text().includes('사용할 수 없음'));assert(!/Playwright|설치 명령|playwright install/.test(text()));
 assert.equal($('browser-login-form').hidden,true);assert.equal($('browser-login-open').hidden,true);assert.equal(buttons().length,0);
 render({available:false,unavailable_reason:'dependency',sessions:[],pending_steps:[]});
 assert(text().includes('pyobjc-framework-WebKit'));
 checks.push('unavailable off macOS or without PyObjC, with no install hint and no login form');

 render(available());
 assert.equal($('browser-login-form').hidden,true,'a supported browser starts with current status, not a login form');
 assert.equal($('browser-login-open').hidden,false,'an explicit login entry is available');
 $('browser-login-open').onclick();
 assert.equal($('browser-login-form').hidden,false,'the explicit action opens the login form');
 assert.equal(document.activeElement,$('browser-login-url'),'opening focuses the site address');
 const draftInput=$('browser-login-url');draftInput.value='https://shop.test/login';
 render(available({login_window_open:true}));
 assert.equal($('browser-login-form').hidden,false,'observed status does not close an active editor');
 assert.equal($('browser-login-url'),draftInput,'the input node survives status refresh');
 assert.equal(draftInput.value,'https://shop.test/login','the address draft survives status refresh');
 $('browser-login-cancel').onclick();
 assert.equal($('browser-login-form').hidden,true,'closing hides the editor');
 assert.equal(document.activeElement,$('browser-login-open'),'closing returns focus to the login action');
 assert.equal(draftInput.value,'https://shop.test/login','closing keeps the address for reopening');
 $('browser-login-open').onclick();assert.equal($('browser-login-url').value,'https://shop.test/login');
 assert.equal(calls.length,0,'opening and closing do not contact the browser');
 checks.push('site login is explicit, with draft preservation and focus return');
 render(available());
 assert(text().includes('사이트별 로그인 쿠키를 이 컴퓨터에 암호화해 저장하고, 암호화 키는 macOS 키체인에 둡니다. 이 정보는 AI에 전달하지 않습니다.'));
 assert(text().includes('저장 위치: /data/private/browser-profile/session-jar.enc'));
 assert(text().includes('암호화 키: macOS 키체인 (서비스 personal-agentos.browser-jar)'));
 assert(text().includes('Google 로그인은 내장 브라우저에서 지원되지 않습니다.'));
 assert(text().includes('저장된 로그인 세션이 없습니다.'));assert(!buttons().some(node=>node.textContent==='모두 삭제'));
 checks.push('storage explained: what, where, key in the Keychain, never sent to the AI, Google note; empty state');

 render(available({sessions:[{site:'shop.test',cookies:3,last_used:Date.now()/1000-120},{site:'news.test',cookies:1,last_used:null}]}));
 assert(text().includes('shop.test'));assert(text().includes('쿠키 3개'));assert(text().includes('마지막 사용:'));
 const rows=descendants($('browser-status')).filter(node=>node.className==='settings-row-title'&&node.attrs.translate==='no');
 assert.deepEqual(rows.map(node=>node.textContent),['shop.test','news.test'],'site names are not machine-translated');
 const del=()=>buttons().filter(node=>node.dataset.focusKey==='browser-delete:shop.test')[0];
 await del().onclick({currentTarget:del()});
 assert.equal(calls.length,0,'the first press only arms the delete');assert($('browser-feedback').textContent.includes('다시 누르면 shop.test'));
 assert.equal(del().textContent,'삭제 확인');
 await del().onclick({currentTarget:del()});
 assert.equal(JSON.stringify(calls.at(-1)),JSON.stringify({path:'/api/browser/sessions/delete',body:{site:'shop.test'}}));assert.equal(refreshes,1);
 assert($('browser-feedback').textContent.includes('shop.test 로그인 세션을 삭제했습니다.'));
 checks.push('per-site list with last use and count; delete asks once more, then deletes that site only');

 const all=()=>buttons().find(node=>node.dataset.focusKey==='browser-delete-all');
 await all().onclick({currentTarget:all()});assert.equal(calls.length,1);assert.equal(all().textContent,'모두 삭제 확인');
 await all().onclick({currentTarget:all()});
 assert.equal(JSON.stringify(calls.at(-1)),JSON.stringify({path:'/api/browser/sessions/delete',body:{all:true}}));
 checks.push('delete all asks once more, then deletes every session and the key');

 ctx.api=async(path,body)=>{calls.push({path,body});return {all:true,deleted:false,jar_deleted:true,key_deleted:false,key_error:'keychain_delete_failed'};};
 render(available({sessions:[{site:'shop.test',cookies:1,last_used:null}]}));
 await all().onclick({currentTarget:all()});await all().onclick({currentTarget:all()});
 assert($('browser-feedback').textContent.includes('암호화 키는 지우지 못했습니다 (keychain_delete_failed)'),'a key that stayed is reported');
 assert(!$('browser-feedback').textContent.includes('모두 삭제했습니다'));
 ctx.api=async(path,body)=>{calls.push({path,body});return {deleted:false,site:'shop.test',removed_from_jar:true,running_browser:'failed'};};
 render(available({sessions:[{site:'shop.test',cookies:1,last_used:null}]}));
 await del().onclick({currentTarget:del()});await del().onclick({currentTarget:del()});
 assert($('browser-feedback').textContent.includes('실행 중인 브라우저에서 지우지 못했습니다'));
 checks.push('a partial delete (key kept, running browser failed) is reported, never acknowledged');
 render(available({storage:{...storage,state:'unreadable'}}));
 assert(text().includes('읽지 못했습니다'));assert(all(),'an unreadable jar can still be reset');
 render(available({login_window_open:true}));assert(text().includes('로그인 창이 열려 있습니다'));
 render(available({storage:{...storage,state:'checking'}}));assert(text().includes('확인하고 있습니다'));assert(!text().includes('저장된 로그인 세션이 없습니다'));
 // #749: the request answers 'opening'; the observed outcome replaces the pending line, never a guessed success.
 for(const [outcome,expected] of [['failed','열지 못했습니다'],['opened','로그인 창을 열었습니다']]){
  ctx.api=async(path,body)=>{calls.push({path,body});return {state:'opening'};};
  $('browser-login-url').value='https://shop.test/login';
  await $('browser-login-form').onsubmit({preventDefault(){},submitter:null});
  assert($('browser-feedback').textContent.includes('여는 중'),'opening is shown as pending');
  render(available({settings_login:{state:'opening',at:1}}));assert($('browser-feedback').textContent.includes('여는 중'));
  render(available({settings_login:{state:outcome,at:2}}));assert($('browser-feedback').textContent.includes(expected),outcome);
 }
 checks.push('an opening Settings login window reports its observed outcome');
 render(available({storage:{...storage,save_error:'key_missing'}}));assert(text().includes('키체인이 잠겨 있지 않은지'));
 render(available({legacy_profile_removed_at:Date.now()/1000}));assert(text().includes('이전 브라우저 프로필을 삭제했습니다'));
 assert(text().includes('/usr/bin/security'),'the Keychain limit is stated');
 checks.push('an unreadable jar is shown and can be reset; an open login window is shown');
 console.log(JSON.stringify({passed:checks.length,checks}));
})().catch(error=>{console.error(error);process.exit(1);});
"""


class BrowserSettingsUiTests(unittest.TestCase):
    def test_markup_says_no_install_and_names_the_login_window(self):
        pane = HTML[HTML.index('id="settings-external"'):HTML.index('id="settings-privacy"')]
        section = pane[pane.index('id="browser-profile"'):]
        self.assertIn('브라우저 로그인 세션', section)
        self.assertIn('별도 브라우저 설치는 필요 없습니다', section)
        self.assertIn('로그인 창 열기', section)
        self.assertIn('Google 로그인은 내장 브라우저에서 지원되지 않습니다.', section)
        self.assertNotIn('Playwright', HTML + APP)
        by_id = {attrs["id"]: (tag, attrs) for tag, attrs in Elements(section).items if "id" in attrs}
        self.assertEqual(by_id['browser-feedback'][1].get('role'), 'status')
        self.assertEqual(by_id['browser-login-url'][1].get('type'), 'url')

    def test_rendering_and_actions_with_a_fake_dom(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required for the DOM checks")
        result = subprocess.run([node, "-e", DOM_CHECKS, str(WEB / "app.js")], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(report["passed"], 8, report)


if __name__ == "__main__":
    unittest.main()

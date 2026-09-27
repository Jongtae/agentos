"""SEC-SEARCH-01 #655 / SEC-SEARCH-02 #678: Settings › 외부 연결 › 웹 검색 제공자 rendering.

Evidence class: static markup checks plus a node-driven render of the
section's own functions with a fake DOM and a recording ``api``.  No
provider, key or service is contacted.
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
 setAttribute(key,value){this.attrs[key]=value;} focus(){} get isConnected(){return true;}
 get classList(){const node=this;return {toggle(name,on){node._cls=Boolean(on);},add(){},remove(){},contains:()=>Boolean(node._cls)};}
 querySelector(selector){return descendants(this).find(node=>selector[0]==='.'?node.className.split(' ').includes(selector.slice(1)):node.tag===selector.replace(/\[.*$/,''))||null;}
 querySelectorAll(selector){return descendants(this).filter(node=>selector==='[data-focus-key]'?Boolean(node.dataset.focusKey):node.tag===selector);}
}
function descendants(node){return node.children.flatMap(child=>typeof child==='string'?[]:[child,...descendants(child)]);}
for(const id of ['search-providers','search-providers-feedback'])new Element('div').id=id;
const $=id=>ids.get(id),document={getElementById:$,createElement:tag=>new Element(tag),activeElement:null,body:null};
const part=(start,end)=>app.slice(app.indexOf(start),app.indexOf(end));
const source='var aiSettings=null;'+part('const LANGUAGES=','function normalizeEndpoint(')+part('function element(','function setError(')+
 part('function aiDate(','function mainAiRoutes(')+part('// #655: web search providers','function renderConnectors(');
const calls=[];let refreshes=0,fail=false;
const ctx={document,$,console,api:async(path,body)=>{calls.push({path,body});if(fail)throw new Error('synthetic refusal');return {};},refresh:async()=>{refreshes++;},busy:async(button,fn)=>fn()};
vm.createContext(ctx);vm.runInContext(source,ctx);vm.runInContext("setLanguage('ko')",ctx);
const text=id=>$(id).textContent,buttons=()=>descendants($('search-providers')).filter(node=>node.tag==='button'),inputs=()=>descendants($('search-providers')).filter(node=>node.tag==='input');
const provider=(id,name,fields,saved)=>({id,name,destination:'api.search.brave.com',setup:'setup '+id,fields,key:{saved,saved_at:saved?1700000000:null}});
const braveFields=[{id:'key',label:'API key'}];
const bingRow=(enabled=false)=>({id:'bing',name:'Bing RSS (개인 용도·비상업 전용 — Microsoft 서비스 약관)',destination:'www.bing.com',note:'personal use note',enabled});
const native=(overrides={})=>({route:'openai',route_name:'OpenAI API',state:'unknown',reason:'',reason_text:'',cost:'per-call cost note',where:'sub-call',...overrides});
const view=(overrides={})=>({native:native(),default:'ai-native',configured_default:'',bing:bingRow(),
 options:[{id:'ai-native',provider:'ai-native',kind:'web',label:"The connected AI's own web search"}],
 providers:[provider('brave','Brave Search API',braveFields,false)],...overrides});
const checks=[];
(async()=>{
 ctx.renderSearchProviders(view());
 const first=descendants($('search-providers')).find(node=>node.className==='settings-row');
 assert(first.textContent.startsWith('연결된 AI의 웹 검색 (기본)'),'the connected AI row comes first');
 assert(text('search-providers').includes('첫 사용 때 확인'));assert(text('search-providers').includes('경로: OpenAI API'));
 assert(text('search-providers').includes('per-call cost note'));
 assert(text('search-providers').includes('Brave Search API'));assert.equal(text('search-providers').split('키 없음').length-1,1);
 assert(text('search-providers').includes('개인 용도·비상업 전용 — Microsoft 서비스 약관'));assert(text('search-providers').includes('꺼짐'));
 assert(!text('search-providers').includes('Naver'));
 assert.equal(inputs().length,0);assert.equal(calls.length,0);
 checks.push('native search first with route and cost, Brave unkeyed, Bing off with its terms; no provider call');

 $('search-providers').dataset.state='';ctx.renderSearchProviders(view({native:native({route:'',route_name:'',state:'unavailable',reason:'no_native_search',reason_text:'no native search here',cost:''})}));
 assert(text('search-providers').includes('사용할 수 없음'));assert(text('search-providers').includes('no native search here'));
 $('search-providers').dataset.state='';ctx.renderSearchProviders(view({native:native({route:'codex',route_name:'Codex CLI',state:'available',where:'work-turn'})}));
 assert(text('search-providers').includes('사용 가능'));assert(text('search-providers').includes('CLI 작업 턴 안에서 CLI가 직접 검색합니다.'));
 checks.push('unavailable shows the reason; a CLI route says it searches inside its own turn');

 $('search-providers').dataset.state='';ctx.renderSearchProviders(view({native:native({state:'unavailable',reason:'rejected',reason_text:'provider said unsupported',recheckable:true})}));
 const recheckAt=calls.length;await buttons().find(node=>node.textContent==='다시 확인').onclick({currentTarget:new Element('button')});
 assert.equal(calls.length,recheckAt+1);assert.equal(calls[recheckAt].path,'/api/search-providers/native/recheck');
 $('search-providers').dataset.state='';ctx.renderSearchProviders(view({native:native({state:'unavailable',reason:'no_api_key',reason_text:'API 키가 없어 사용할 수 없음'})}));
 assert(text('search-providers').includes('API 키가 없어 사용할 수 없음'));assert(!buttons().some(node=>node.textContent==='다시 확인'));
 calls.length=0;refreshes=0;
 checks.push('a remembered unavailable offers 다시 확인; a missing key is stated and has no recheck');

 $('search-providers').dataset.state='';ctx.renderSearchProviders(view());
 buttons().find(node=>node.textContent==='키 입력').onclick();
 const form=descendants($('search-providers')).find(node=>node.tag==='form');
 assert(form);assert.equal(inputs().length,1);assert(inputs().every(node=>node.type==='password'));
 assert(form.textContent.includes('setup brave'));
 await form.onsubmit({preventDefault(){}});
 assert.equal(calls.length,0);assert(text('search-providers-feedback').includes('모든 키 값'));
 inputs()[0].value='brave-token-fixture-0001';
 await form.onsubmit({preventDefault(){}});
 assert.equal(calls.length,1);assert.equal(calls[0].path,'/api/search-providers/key');
 assert.equal(JSON.stringify(calls[0].body),JSON.stringify({provider:'brave',key:'brave-token-fixture-0001'}));
 assert.equal(refreshes,1);assert(text('search-providers-feedback').includes('Brave Search API 키를 저장했습니다.'));
 assert(!text('search-providers').includes('brave-token-fixture-0001'));assert(!text('search-providers-feedback').includes('brave-token-fixture-0001'));
 checks.push('the key form sends the Brave key once, as a password field, and never echoes it');

 $('search-providers').dataset.state='';ctx.renderSearchProviders(view());
 await buttons().find(node=>node.textContent==='켜기').onclick({currentTarget:new Element('button')});
 assert.equal(calls[1].path,'/api/search-providers/bing');assert.equal(JSON.stringify(calls[1].body),JSON.stringify({enabled:true}));
 $('search-providers').dataset.state='';ctx.renderSearchProviders(view({bing:bingRow(true)}));
 assert(text('search-providers').includes('켜짐'));
 await buttons().find(node=>node.textContent==='끄기').onclick({currentTarget:new Element('button')});
 assert.equal(JSON.stringify(calls[2].body),JSON.stringify({enabled:false}));
 checks.push('Bing RSS is switched on and off only by an explicit press');

 const keyed=view({options:[{id:'ai-native',label:'native'},{id:'brave',label:'Brave'},{id:'bing',label:'Bing'}],bing:bingRow(true),
  providers:[provider('brave','Brave Search API',braveFields,true)]});
 $('search-providers').dataset.state='';ctx.renderSearchProviders(keyed);
 assert(text('search-providers').includes('키 저장됨'));
 const select=descendants($('search-providers')).find(node=>node.tag==='select');
 assert(select);assert.equal(JSON.stringify(select.children.map(node=>node.value)),JSON.stringify(['ai-native','brave','bing']));
 assert.equal(select.children.find(node=>node.selected).value,'ai-native');
 select.value='brave';await select.onchange();
 assert.equal(calls[3].path,'/api/search-providers/default');assert.equal(JSON.stringify(calls[3].body),JSON.stringify({provider:'brave'}));
 checks.push('the default selector lists exactly the configured options and sends one explicit choice');

 $('search-providers').dataset.state='';ctx.renderSearchProviders(keyed);
 buttons().find(node=>node.textContent==='지우기').onclick();
 assert(text('search-providers-feedback').includes('다시 누르면'));
 const before=calls.length;await buttons().find(node=>node.textContent==='지우기 확인').onclick({currentTarget:new Element('button')});
 assert.equal(calls.length,before+1);assert.equal(JSON.stringify(calls[before].body),JSON.stringify({provider:'brave',key:''}));
 checks.push('removal needs a second explicit press and clears the Brave slot');

 fail=true;$('search-providers').dataset.state='';ctx.renderSearchProviders(view());
 buttons().find(node=>node.textContent==='키 입력').onclick();
 const braveForm=descendants($('search-providers')).find(node=>node.tag==='form');
 inputs().forEach(node=>{node.value='x';});refreshes=0;
 await braveForm.onsubmit({preventDefault(){}});
 assert.equal(refreshes,0);assert.equal(text('search-providers-feedback'),'synthetic refusal');
 checks.push('a refused save stays inline and does not claim a saved key');
 console.log(JSON.stringify({passed:checks.length,checks}));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


class SearchProviderUiTests(unittest.TestCase):
    def test_markup_has_the_section_in_external_connections_with_a_live_feedback_line(self):
        pane = HTML[HTML.index('id="settings-external"'):HTML.index('id="settings-privacy"')]
        self.assertIn('id="search-providers-heading"', pane)
        self.assertIn('웹 검색 제공자', pane)
        by_id = {attrs["id"]: (tag, attrs) for tag, attrs in Elements(pane).items if "id" in attrs}
        self.assertEqual(by_id['search-providers'][0], 'div')
        self.assertEqual(by_id['search-providers-feedback'][1].get('role'), 'status')
        self.assertEqual(by_id['search-providers-feedback'][1].get('aria-live'), 'polite')
        # No static key input: the values are entered only in the per-provider form.
        self.assertNotIn('name="search-', pane)
        self.assertIn("renderSearchProviders(settings.search_providers)", APP)

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

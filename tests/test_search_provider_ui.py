"""SEC-SEARCH-01 #655: Settings › 외부 연결 › 웹 검색 제공자 rendering.

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
const provider=(id,name,fields,saved)=>({id,name,destination:id==='naver'?'openapi.naver.com':'api.search.brave.com',setup:'setup '+id,fields,key:{saved,saved_at:saved?1700000000:null}});
const naverFields=[{id:'client_id',label:'Client ID'},{id:'client_secret',label:'Client Secret'}],braveFields=[{id:'key',label:'API key'}];
const view=(overrides={})=>({default:'bing',configured_default:'bing',keyless:[{id:'bing',name:'Bing (RSS)',destination:'www.bing.com'}],
 options:[{id:'bing',provider:'bing',kind:'web',label:'Bing web search (RSS, no key)'}],
 providers:[provider('naver','Naver Open API',naverFields,false),provider('brave','Brave Search API',braveFields,false)],...overrides});
const checks=[];
(async()=>{
 ctx.renderSearchProviders(view());
 assert(text('search-providers').includes('Bing (RSS)'));assert(text('search-providers').includes('사용 가능'));
 assert(text('search-providers').includes('Naver Open API'));assert(text('search-providers').includes('Brave Search API'));
 assert.equal(text('search-providers').split('키 없음').length-1,2);
 assert.equal(inputs().length,0);assert.equal(calls.length,0);
 checks.push('unkeyed providers render as 키 없음 with no inputs and no provider call');

 buttons().find(node=>node.textContent==='키 입력').onclick();
 const form=descendants($('search-providers')).find(node=>node.tag==='form');
 assert(form);assert.equal(inputs().length,2);assert(inputs().every(node=>node.type==='password'));
 assert(form.textContent.includes('setup naver'));
 inputs()[0].value='naver-id-fixture-0001';
 await form.onsubmit({preventDefault(){}});
 assert.equal(calls.length,0);assert(text('search-providers-feedback').includes('모든 키 값'));
 inputs()[1].value='naver-secret-fixture-0001';
 await form.onsubmit({preventDefault(){}});
 assert.equal(calls.length,1);assert.equal(calls[0].path,'/api/search-providers/key');
 assert.equal(JSON.stringify(calls[0].body),JSON.stringify({provider:'naver',client_id:'naver-id-fixture-0001',client_secret:'naver-secret-fixture-0001'}));
 assert.equal(refreshes,1);assert(text('search-providers-feedback').includes('Naver Open API 키를 저장했습니다.'));
 assert(!text('search-providers').includes('naver-secret-fixture-0001'));assert(!text('search-providers-feedback').includes('naver-secret-fixture-0001'));
 checks.push('the key form sends both Naver values once, as password fields, and never echoes them');

 const keyed=view({options:[{id:'bing',label:'Bing web search (RSS, no key)'},{id:'naver',label:'Naver web'},{id:'naver-book',label:'Naver book'}],
  providers:[provider('naver','Naver Open API',naverFields,true),provider('brave','Brave Search API',braveFields,false)]});
 $('search-providers').dataset.state='';ctx.renderSearchProviders(keyed);
 assert(text('search-providers').includes('키 저장됨'));
 const select=descendants($('search-providers')).find(node=>node.tag==='select');
 assert(select);assert.equal(JSON.stringify(select.children.map(node=>node.value)),JSON.stringify(['bing','naver','naver-book']));
 assert.equal(select.children.find(node=>node.selected).value,'bing');
 select.value='naver-book';await select.onchange();
 assert.equal(calls[1].path,'/api/search-providers/default');assert.equal(JSON.stringify(calls[1].body),JSON.stringify({provider:'naver-book'}));
 checks.push('the default selector lists exactly the configured options and sends one explicit choice');

 $('search-providers').dataset.state='';ctx.renderSearchProviders(keyed);
 buttons().find(node=>node.textContent==='지우기').onclick();
 assert(text('search-providers-feedback').includes('다시 누르면'));
 const before=calls.length;await buttons().find(node=>node.textContent==='지우기 확인').onclick({currentTarget:new Element('button')});
 assert.equal(calls.length,before+1);assert.equal(JSON.stringify(calls[before].body),JSON.stringify({provider:'naver',client_id:'',client_secret:''}));
 checks.push('removal needs a second explicit press and clears both Naver slots');

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
        self.assertEqual(report["passed"], 5, report)


if __name__ == "__main__":
    unittest.main()

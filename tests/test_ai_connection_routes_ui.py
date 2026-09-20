"""Connection presentation regressions; no provider, credentials or service writes."""
from html.parser import HTMLParser
from pathlib import Path
import json
import shutil
import subprocess
import unittest

WEB = Path(__file__).parents[1] / "src" / "personal_agent" / "web"


class Elements(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.items = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.items.append((tag, dict(attrs)))


NODE_CHECKS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const app = fs.readFileSync(process.argv[1], 'utf8');
const ids = new Map();
class Element {
 constructor(tag) { this.tag=tag; this.children=[]; this.dataset={}; this.attrs={}; this.value=''; this.disabled=false; this._text=''; }
 set id(value) { this._id=value; ids.set(value,this); }
 get id() { return this._id; }
 set textContent(value) { this._text=String(value); this.children=[]; }
 get textContent() { return this._text+this.children.map(item=>typeof item==='string'?item:item.textContent).join(''); }
 append(...items) { this.children.push(...items); }
 replaceChildren(...items) { this._text=''; this.children=[]; this.append(...items); }
 setAttribute(key,value) { this.attrs[key]=value; }
}
for(const id of ['active-ai','subscription-engines','settings-panel','model-name','api-key']) {
 const node=new Element('div');node.id=id;
}
const calls=[];let refreshes=0,fail=false;
const ctx={document:{getElementById:id=>ids.get(id),createElement:tag=>new Element(tag)},
 $:id=>ids.get(id),
 api:async(path,body)=>{calls.push({path,body});if(fail)throw new Error('synthetic failure');return {};},
 refresh:async()=>{refreshes++;}};
const line=prefix=>app.split('\n').find(value=>value.startsWith(prefix));
const source=[line('function error('),line('async function busy('),line('function element('),
 line('const providerNames='),line('function displayProvider('),
 app.slice(app.indexOf('function showExecutionConnection('),app.indexOf('function showOnboarding('))].join('\n');
assert(!source.includes('undefined\n'));
vm.runInNewContext(source,ctx);
const selected=id=>({selected:id,engines:[
 {id:'codex',name:'Codex',installed:true,connected:id==='codex',login_command:'codex login',login_url:'https://example.invalid/codex'},
 {id:'claude-code',name:'Claude Code',installed:true,connected:id==='claude-code',login_command:'claude',login_url:'https://example.invalid/claude'}]});
const model={provider:'openai',endpoint:'https://api.openai.com/v1',model:'synthetic-api-model'};
const settings={model,model_ready:true,model_test:{time:1700000000},subscription_engines:selected('codex')};
const text=id=>ids.get(id).textContent;
const descendants=node=>node.children.flatMap(item=>typeof item==='string'?[]:[item,...descendants(item)]);
const buttons=()=>descendants(ids.get('subscription-engines')).filter(item=>item.tag==='button');
const checks=[];
(async()=>{
 ctx.showExecutionConnection(settings);ctx.showSubscriptionEngines(settings.subscription_engines);
 assert(text('active-ai').includes('Codex · 구독 CLI 우선'));
 assert(text('active-ai').includes('웹·Telegram'));
 assert(text('active-ai').includes('직접 API를 설정하거나 테스트해도 이 선택은 바뀌지 않습니다.'));
 assert(text('active-ai').includes('파일 작업공간 요약은 현재 구독 CLI에서 지원하지 않습니다.'));
 assert(text('active-ai').includes('모델 정보 미제공'));
 assert(!text('active-ai').includes('직접 API 테스트 통과'));
 assert(text('subscription-engines').includes('현재 선택됨'));
 assert.equal(calls.length,0);
 checks.push('global CLI precedence without invented readiness or provider calls');

 ids.get('api-key').value='synthetic-unsaved-key';ids.get('model-name').value='synthetic-draft';
 const firstButton=buttons()[0];
 assert.equal(buttons().length,1);
 assert.equal(firstButton.textContent,'Claude Code 로그인 완료 · 전환');
 ctx.showSubscriptionEngines(JSON.parse(JSON.stringify(settings.subscription_engines)));
 assert.equal(buttons()[0],firstButton);
 assert.equal(ids.get('model-name').value,'synthetic-draft');
 assert.equal(ids.get('api-key').value,'synthetic-unsaved-key');
 checks.push('unchanged polling preserves control identity and unrelated drafts');

 await firstButton.onclick();
 assert.equal(calls.length,1);assert.equal(calls[0].path,'/api/subscription-engines/connect');
 assert.equal(JSON.stringify(calls[0].body),JSON.stringify({engine:'claude-code',officially_authenticated:true}));
 assert.equal(refreshes,1);assert.equal(firstButton.disabled,false);
 assert.equal(ids.get('api-key').value,'synthetic-unsaved-key');
 checks.push('explicit owner confirmation sends only engine and login attestation');

 fail=true;refreshes=0;await firstButton.onclick();
 assert.equal(refreshes,0);assert.equal(text('subscription-feedback'),'synthetic failure');
 assert(text('active-ai').includes('Codex · 구독 CLI 우선'));
 assert.equal(firstButton.disabled,false);
 checks.push('failed switch is inline and does not advertise a changed selection');

 const missing=selected('codex');missing.engines[0].installed=false;
 ctx.showExecutionConnection({...settings,subscription_engines:missing});ctx.showSubscriptionEngines(missing);
 assert(text('active-ai').includes('선택한 CLI를 찾지 못했습니다.'));
 assert(text('active-ai').includes('직접 API로 자동 전환하지 않습니다.'));
 assert(!text('active-ai').includes('직접 API 테스트 통과'));
 assert.equal(buttons().length,1);
 checks.push('missing selected CLI cannot inherit successful API readiness');

 ctx.showExecutionConnection({...settings,model:{},model_ready:false,subscription_engines:selected('claude-code')});
 assert(text('active-ai').includes('Claude Code · 구독 CLI 우선'));
 assert(text('active-ai').includes('직접 API 미설정 · 구독 CLI 선택과 별개입니다.'));
 ctx.showExecutionConnection({...settings,subscription_engines:selected('')});
 assert(text('active-ai').includes('synthetic-api-model · 직접 API'));
 assert(text('active-ai').includes('직접 API 테스트 통과'));
 ctx.showSubscriptionEngines(selected(''));
 assert.equal(buttons().length,2);
 assert(buttons().every(button=>button.textContent.includes('로그인 완료 · 선택')));
 checks.push('CLI-only and API-only configurations remain distinct');

 ctx.showExecutionConnection({});ctx.showSubscriptionEngines();
 assert(text('active-ai').includes('직접 API 미설정 · 구독 CLI도 선택되지 않았습니다.'));
 ctx.showExecutionConnection({...settings,subscription_engines:{selected:'unrecognized',engines:[]}});
 assert(text('active-ai').includes('선택된 구독 CLI · 구독 CLI 우선'));
 assert(!text('active-ai').includes('직접 API 테스트 통과'));
 checks.push('missing discovery data never fabricates a ready direct-API route');
 console.log(JSON.stringify({passed:checks.length,checks}));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


class ConnectionRouteUiTests(unittest.TestCase):
    def test_direct_api_is_visible_and_shortcuts_are_secondary(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        items = Elements(html).items
        by_id = {attrs["id"]: (tag, attrs) for tag, attrs in items if "id" in attrs}
        all_ids = [attrs["id"] for _, attrs in items if "id" in attrs]
        self.assertEqual(len(all_ids), len(set(all_ids)))
        self.assertEqual(by_id["advanced-model"][0], "details")
        self.assertIn("open", by_id["advanced-model"][1])
        self.assertNotIn("open", by_id["optional-providers"][1])
        self.assertIn("OpenAI Developer API", html)
        self.assertLess(html.index('id="model-form"'), html.index('id="optional-providers"'))
        self.assertLess(html.index('id="optional-providers"'), html.index('id="connect-openrouter"'))
        self.assertIn("disabled", by_id["apply-model"][1])
        self.assertNotIn("required", by_id["api-key"][1])

    def test_existing_draft_and_primary_route_wiring_are_preserved(self):
        app = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn("showExecutionConnection(settings);", app)
        self.assertIn("showSubscriptionEngines(settings.subscription_engines);", app)
        self.assertIn("api('/api/model/test',draft)", app)
        self.assertIn("modelDraftVerified!==modelDraftFingerprint(draft)", app)
        self.assertIn("contextDraftDirty", app)
        self.assertIn("if(settingsFingerprint!==conversationSettingsFingerprint)", app)
        self.assertNotIn("Telegram용 구독 엔진", app)
        self.assertNotIn("테스트한 설정을 현재 사용 모델로 적용했습니다.", app)

    def test_javascript_parses(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node is needed for JavaScript syntax validation")
        subprocess.run([node, "--check", str(WEB / "app.js")], check=True, capture_output=True, text=True, timeout=20)

    def test_actual_connection_renderers_and_explicit_switch_callback(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node is needed for isolated DOM rendering checks")
        result = subprocess.run([node, "-e", NODE_CHECKS, str(WEB / "app.js")],
                                check=True, capture_output=True, text=True, timeout=20)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt["passed"], 7)


if __name__ == "__main__":
    unittest.main()

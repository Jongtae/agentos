"""PRESENCE-WEB-01 (#845): the web chat's wait state is a transient typing bubble.

The bubble is ephemeral UI state derived from the live task status on every
render. Nothing about it is stored: the read model carries an observed step
line only while the Work is active, and a finished Work never carries one.
"""
import json
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'src/personal_agent/web'


DOM_CHECKS = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const app=fs.readFileSync(process.argv[1],'utf8');
class Element{constructor(tag){this.tag=tag;this.children=[];this.attrs={};this.className='';this._text='';}
 set textContent(v){this._text=String(v);this.children=[];} get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}
 append(...nodes){this.children.push(...nodes);} setAttribute(k,v){this.attrs[k]=v;} get classList(){const n=this;return {add(c){n.className=(n.className+' '+c).trim();}};}}
const all=n=>n.children.flatMap(c=>[c,...all(c)]);
const part=(a,b)=>app.slice(app.indexOf(a),app.indexOf(b));
const source=part('function element(','function renderInlines(')+part('function typingContent(','function renderTasks(');
const ctx={document:{createElement:tag=>new Element(tag)},t:x=>x,renderRichText:text=>{const n=new Element('div');n.className='rich';n.textContent=text;return n;}};
vm.createContext(ctx);vm.runInContext(source,ctx);
const render=task=>{const body=new Element('div');ctx.typingContent(body,task);return body;};
let body=render({status_kind:'active',step_line:''});
assert.equal(body.children.length,1);assert.equal(body.children[0].className,'typing-dots');
assert.equal(body.children[0].attrs.role,'status');assert.equal(body.children[0].children.length,3);
assert.equal(body.textContent,'');
body=render({status_kind:'active',step_line:'웹 검색 중: 경주 휴게소'});
assert.deepEqual(body.children.map(n=>n.className),['typing-step','typing-dots']);
assert.equal(body.textContent,'웹 검색 중: 경주 휴게소');
body=render({status_kind:'active',step_line:'날씨 보고 있어요',draft_text:'부분 답변',attention_line:'참, 준비해 둔 게 있어요'});
assert.deepEqual(body.children.map(n=>n.className),['rich','typing-step','typing-attention','typing-dots']);
console.log(JSON.stringify({passed:3}));
"""


class TypingBubbleRenderTests(unittest.TestCase):
    def setUp(self):
        self.js = (WEB / 'app.js').read_text()
        self.css = (WEB / 'style.css').read_text()

    def test_bubble_is_derived_from_live_status_not_a_stored_message(self):
        # Derived per render from the polled task; only an active Work that asks nothing of the owner.
        self.assertIn("function typingBubble(task){return task.status_kind==='active'&&!task.waits?.length;}", self.js)
        # Rendered as the agent half of the same .turn-pair, in the same .turn-body container.
        self.assertIn("if(typing)body.classList.add('typing')", self.js)
        # Never pushed into the task list / history.
        self.assertNotRegex(self.js, r"tasks\.push\([^)]*typing")
        self.assertNotRegex(self.js, r"typing[^;]*\.push\(")
        # No status word in the head badge or the bubble while typing.
        self.assertIn("plainSuccess||typing?'':statusText(task)", self.js)
        self.assertIn("if(typing)typingContent(body,task);else{", self.js)

    def test_live_content_replaces_in_place_and_keeps_the_dots(self):
        content = re.search(r"function typingContent\(body,task\)\{(.*?)\}\n", self.js).group(1)
        self.assertIn("task.step_line", content)
        self.assertIn("task.draft_text", content)       # extension point: partial answer
        self.assertIn("task.attention_line", content)   # extension point: #839 attention line
        self.assertTrue(content.rstrip(';').endswith("body.append(typingDots())"), content)
        # The dots are three empty elements with an accessible name only.
        self.assertIn("for(let i=0;i<3;i++)dots.append(element('i'))", self.js)
        self.assertIn("dots.setAttribute('role','status')", self.js)

    def test_dots_animate_and_respect_reduced_motion(self):
        self.assertIn('.turn-body.typing{', self.css)
        self.assertIn('@keyframes typing-bob', self.css)
        self.assertIn('@keyframes typing-pulse', self.css)
        self.assertRegex(self.css, r"@media\(prefers-reduced-motion:reduce\)\{\.typing-dots i\{animation:typing-pulse")
        self.assertIn('.typing-dots i:nth-child(3){animation-delay:', self.css)
        # Same bubble surface as a normal assistant turn: no tone background on the typing body.
        self.assertNotIn('.turn-body.typing{background', self.css)


class TypingBubbleFakeDomTests(unittest.TestCase):
    def test_dots_only_then_live_content_above_the_dots(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node is required for the DOM checks')
        result = subprocess.run([node, '-e', DOM_CHECKS, str(WEB / 'app.js')], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout.strip().splitlines()[-1])['passed'], 3)


class TypingBubbleReadModelTests(unittest.TestCase):
    def _service(self, folder):
        store = QuickStore(folder)
        return store, AgentService(store)

    def _job(self, store, status, message='경주 휴게소 맛집 알려줘'):
        job_id = store.enqueue(message, 'key-' + status, channel='telegram:1')
        with store.db() as db:
            db.execute('UPDATE jobs SET status=? WHERE id=?', (status, job_id))
        return job_id

    def test_active_work_carries_dots_only_until_a_step_is_observed(self):
        with tempfile.TemporaryDirectory() as folder:
            store, service = self._service(folder)
            job_id = self._job(store, 'running')
            task = next(t for t in service.task_progress()['tasks'] if t['id'] == job_id)
            self.assertEqual(task['status_kind'], 'active')
            self.assertEqual(task['step_line'], '')
            with store.db() as db:
                db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                           (job_id, 'bridge_tool', 'running',
                            json.dumps({'step': {'action': 'web_search', 'query': '경주 휴게소'}}, ensure_ascii=False),
                            time.time()))
            task = next(t for t in service.task_progress()['tasks'] if t['id'] == job_id)
            self.assertEqual(task['step_line'], "웹에서 '경주 휴게소' 찾아보고 있어요")
            self.assertNotIn(task['step_line'], ('running', 'queued', '진행 중'))

    def test_a_pending_browser_approval_is_an_owner_wait_not_typing(self):
        with tempfile.TemporaryDirectory() as folder:
            store, service = self._service(folder)
            job_id = self._job(store, 'running')
            store.queue_notification(job_id, 42, 1, 'browser_approval_needed', fingerprint='d1')
            task = next(t for t in service.task_progress()['tasks'] if t['id'] == job_id)
            self.assertEqual(task['waits'], ['승인 대기'])
            self.assertEqual(task['step_line'], '')

    def test_finished_and_failed_work_carry_no_typing_state_and_nothing_is_stored(self):
        with tempfile.TemporaryDirectory() as folder:
            store, service = self._service(folder)
            done = self._job(store, 'succeeded')
            failed = self._job(store, 'failed')
            cancelled = self._job(store, 'cancelled')
            with store.db() as db:
                db.execute('UPDATE jobs SET response=? WHERE id=?', ('답변입니다.', done))
                for job_id in (done, failed):
                    db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                               (job_id, 'bridge_tool', 'running',
                                json.dumps({'step': {'action': 'web_search', 'query': '경주'}}), time.time()))
            tasks = {t['id']: t for t in service.task_progress()['tasks']}
            for job_id in (done, failed, cancelled):
                self.assertNotEqual(tasks[job_id]['status_kind'], 'active')
                self.assertNotIn('step_line', tasks[job_id])
            # Reload path: the durable rows hold no typing text or step line.
            with store.db() as db:
                rows = db.execute('SELECT message,response,error FROM jobs').fetchall()
            for row in rows:
                for value in row:
                    self.assertNotIn('typing', str(value or ''))
                    self.assertNotIn('웹에서 찾아보고 있어요', str(value or ''))


if __name__ == '__main__':
    unittest.main()

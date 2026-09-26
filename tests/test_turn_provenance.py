"""#570 PRESENCE-DEVMODE-01: per-Work provenance for developer mode.

Records what AgentOS sent and what the worker reported, redacted before it is
stored, and links DecisionEngine calls to the Work that made them.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from personal_agent.bounded_execution import (AgentOSMcpTools, BoundedExecutionAdapter, ExecutionError, ExecutionResult,
                                              cli_metadata, display_argv)
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines

WEB = Path(__file__).parents[1] / 'src' / 'personal_agent' / 'web'


class _Caps:
    job_id = 'job'
    private_provenance = set()

    class store:
        root = '/tmp/agentos-provenance-test'

    def execute(self, name, arguments):
        return {'ok': True}


class _Done:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class AdapterMetadata(unittest.TestCase):
    def test_claude_json_reports_model_usage_and_cost(self):
        raw = json.dumps({'result': 'ok', 'num_turns': 2, 'total_cost_usd': 0.01,
                          'usage': {'input_tokens': 10, 'output_tokens': 5, 'service_tier': 'standard'},
                          'modelUsage': {'claude-sonnet-x': {}}})
        meta = cli_metadata('claude-code', raw)
        self.assertEqual(meta['reported_model'], 'claude-sonnet-x')
        self.assertEqual(meta['usage'], {'input_tokens': 10, 'output_tokens': 5})
        self.assertEqual((meta['num_turns'], meta['cost_usd']), (2, 0.01))

    def test_codex_stream_reports_tool_calls_and_no_guessed_model(self):
        raw = '\n'.join(json.dumps(line) for line in (
            {'type': 'thread.started'},
            {'item': {'type': 'mcp_tool_call', 'tool': 'web_search', 'status': 'completed'}},
            {'item': {'type': 'agent_message', 'text': 'answer'}},
            {'type': 'turn.completed', 'usage': {'input_tokens': 3}}))
        meta = cli_metadata('codex', raw)
        self.assertIsNone(meta['reported_model'], 'an unreported model stays unreported')
        self.assertEqual(meta['tool_calls'], [{'type': 'mcp_tool_call', 'name': 'web_search', 'status': 'completed'}])
        self.assertEqual(meta['usage'], {'input_tokens': 3})

    def test_argv_shows_sizes_instead_of_prompt_and_instructions(self):
        shown = display_argv(['claude', '-p', 'secret question', '--append-system-prompt', 'rules'], 'secret question', 'rules')
        self.assertNotIn('secret question', ' '.join(shown))
        self.assertIn('<prompt: 15 bytes>', shown)
        self.assertIn('<AgentOS instructions: 5 bytes>', shown)

    def test_claude_stream_reports_session_model_tool_use_and_denials(self):
        # Record shapes follow `claude -p --output-format stream-json --verbose`
        # (init, assistant, result), observed locally without a model call.
        stream = '\n'.join(json.dumps(line) for line in (
            {'type': 'system', 'subtype': 'init', 'model': 'claude-x', 'tools': ['Bash']},
            {'type': 'assistant', 'message': {'model': 'claude-x', 'content': [{'type': 'tool_use', 'name': 'mcp__agentos__web_search'}]}},
            {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'content': 'x' * 200_000}]}},
            {'type': 'result', 'is_error': False, 'result': 'final answer', 'modelUsage': {}, 'num_turns': 2,
             'permission_denials': [{'tool_name': 'Bash'}], 'usage': {'input_tokens': 9}}))
        meta = cli_metadata('claude-code', stream)
        self.assertEqual(meta['reported_model'], 'claude-x', 'the init record names the session model')
        self.assertEqual(meta['tool_calls'], [{'type': 'tool_use', 'name': 'mcp__agentos__web_search', 'status': 'requested'},
                                              {'type': 'tool_use', 'name': 'Bash', 'status': 'denied'}])
        self.assertEqual(BoundedExecutionAdapter._content('claude-code', stream), 'final answer',
                         'a large tool result earlier in the stream does not reject a small answer')
        synthetic = json.dumps({'type': 'assistant', 'message': {'model': '<synthetic>'}})
        self.assertIsNone(cli_metadata('claude-code', synthetic)['reported_model'])

    def test_claude_runs_with_stream_json(self):
        adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name)
        argv = adapter.command('claude-code', '/runtime/claude', 'hi', '/tmp/c.json')
        self.assertEqual(argv[argv.index('--output-format') + 1], 'stream-json')
        self.assertIn('--verbose', argv, 'stream-json with -p requires --verbose')

    def test_execute_attaches_metadata_on_success_and_failure(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        outputs = [_Done(stdout=json.dumps({'result': 'ok', 'modelUsage': {'m1': {}}})),
                   _Done(returncode=1, stdout=json.dumps({'is_error': True, 'result': 'boom', 'modelUsage': {'m1': {}}}))]
        adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=lambda argv, **kw: outputs.pop(0),
                                          runtime_root=Path(tmp.name) / 'turns')
        result = adapter.execute('claude-code', 'hello', AgentOSMcpTools(_Caps()))
        self.assertEqual(result.meta['reported_model'], 'm1')
        self.assertIn('<prompt: 5 bytes>', result.meta['argv'])
        self.assertIsNone(result.meta['requested_model'])
        with self.assertRaises(ExecutionError) as caught:
            adapter.execute('claude-code', 'hello', AgentOSMcpTools(_Caps()))
        self.assertEqual(caught.exception.meta['reported_model'], 'm1')
        self.assertIn('duration_ms', caught.exception.meta)


class _Engine:
    def __init__(self, meta=None, fail=None):
        self.meta, self.fail, self.prompts = meta or {}, fail, []

    def login_status(self, engine_id, binary=None):
        return {'state': 'signed-in'}

    def execute(self, engine, prompt, tools, **kwargs):
        self.prompts.append(prompt)
        if self.fail:
            raise self.fail
        return ExecutionResult('answer', engine, 0, dict(self.meta))


class ServiceProvenance(unittest.TestCase):
    def _service(self, engine):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        service = AgentService(self.store, subscription_engines=SubscriptionEngines(finder=lambda c: '/runtime/' + c, clock=lambda: 1),
                               execution_adapter=engine)
        service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        return service

    def _selected(self, service):
        job_id = service.task_progress()['tasks'][0]['id']
        return service.task_progress(job_id)['selected']

    def test_records_what_was_sent_redacted_and_what_was_reported(self):
        engine = _Engine(meta={'argv': ['codex', 'exec', '<prompt: 9 bytes>', '/Users/owner/.codex/x'], 'reported_model': None,
                               'usage': {'input_tokens': 7}, 'tool_calls': [], 'duration_ms': 1200})
        service = self._service(engine)
        self.store.secret('telegram_token', 'opaque-telegram-value-123')
        self.store.enqueue('my key is sk-live' + 'a' * 20 + ' and ghp_' + 'b' * 20 + ' and opaque-telegram-value-123'
                           ' and file /Users/owner/private/plan.md', 'k1')
        self.assertTrue(service.run_one())
        record = self._selected(service)['provenance']
        self.assertEqual((record['route'], record['engine'], record['status']), ('subscription', 'codex', 'answered'))
        self.assertIn('sk-live', engine.prompts[0], 'the engine itself still received the real request')
        stored = json.dumps(record, ensure_ascii=False)
        self.assertNotIn('sk-live' + 'a' * 20, stored)
        self.assertNotIn('/Users/owner', stored)
        self.assertNotIn('ghp_' + 'b' * 20, stored)
        self.assertNotIn('opaque-telegram-value-123', stored, 'stored secrets are removed by value, whatever their format')
        self.assertIn('[redacted]', record['prompt_envelope'])
        self.assertIn('[경로 가림]', record['prompt_envelope'])
        self.assertTrue(record['instructions_version'])
        self.assertEqual(len(record['instructions_digest']), 16)
        self.assertNotIn('reported_model', record, 'an unreported model is absent, not guessed')
        self.assertEqual(record['usage'], {'input_tokens': 7})

    def test_private_source_content_is_never_stored(self):
        engine = _Engine()
        service = self._service(engine)
        self.store.enqueue('/note private-plan-XYZ for the merger', 'n1')
        service.run_one()
        self.store.enqueue('/summarize', 'k1')
        service.run_one()
        self.assertIn('private-plan-XYZ', engine.prompts[-1], 'the engine still receives the notes')
        records = [service.task_progress(job['id'])['selected'].get('provenance') for job in self.store.jobs()]
        stored = json.dumps([r for r in records if r], ensure_ascii=False)
        self.assertNotIn('private-plan-XYZ', stored)
        summary = [r for r in records if r and r.get('prompt_withheld')][0]
        self.assertEqual(summary['prompt_withheld'], ['personal-space'])
        self.assertTrue(summary['prompt_envelope'].startswith('[not stored: this turn included personal-space;'))
        self.assertGreater(summary['prompt_bytes'], 0)

    def test_provenance_is_not_exported(self):
        from personal_agent.portable_state import _portable_db
        import sqlite3
        service = self._service(_Engine())
        self.store.enqueue('hello', 'k1')
        service.run_one()
        target = Path(self.store.root) / 'export.db'
        _portable_db(self.store.path, target)
        with sqlite3.connect(target) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM turn_provenance').fetchone()[0], 0)

    def test_bare_request_fallback_records_no_instructions(self):
        service = self._service(_Engine())
        service.record_turn_sent('job-bare', sent='just the request', instructions='', instructions_channel='not sent (bare request)',
                                 route='subscription', instructions_version='v1')
        record = self.store.turn_provenance('job-bare')
        self.assertEqual(record['instructions_channel'], 'not sent (bare request)')
        self.assertNotIn('instructions', record)
        self.assertNotIn('instructions_version', record, 'no version is claimed for instructions that were not sent')
        self.assertEqual(record['prompt_envelope'], 'just the request')

    def test_custom_data_and_turn_folders_are_masked(self):
        service = self._service(_Engine())
        root = str(self.store.root)
        service.record_turn_provenance('job-paths', argv=['codex', '--data', root + '/state.db', '/srv/runs/turn-1'])
        service.execution_adapter.runtime_root = Path('/srv/runs')
        service.record_turn_provenance('job-paths2', argv=['--data', root, '/srv/runs/turn-1'])
        self.assertNotIn(root, json.dumps(self.store.turn_provenance('job-paths')))
        self.assertEqual(self.store.turn_provenance('job-paths2')['argv'], ['--data', '[AgentOS data]', '[turn folder]/turn-1'])

    def test_failure_is_recorded_with_its_class(self):
        service = self._service(_Engine(fail=ExecutionError('x', failure_class='rate-limit', exit_code=1,
                                                            meta={'argv': ['codex'], 'duration_ms': 5})))
        self.store.enqueue('hello', 'k1')
        service.run_one()
        record = self._selected(service)['provenance']
        self.assertEqual((record['status'], record['failure_class'], record['exit_code']), ('failed', 'rate-limit', 1))

    def test_decisions_are_linked_to_their_work_only(self):
        service = self._service(_Engine())
        service.record_decision({'kind': 'decision', 'purpose': 'outside', 'outcome': 'ok'})
        self.store.enqueue('hello', 'k1')
        real_run = service.execution_adapter.execute

        def execute(engine, prompt, tools, **kwargs):
            service.record_decision({'kind': 'decision', 'purpose': 'presence', 'outcome': 'accepted', 'model': 'gpt-x', 'raw': 'hidden', 'answer': 'retry', 'confidence': 0.9})
            return real_run(engine, prompt, tools, **kwargs)
        service.execution_adapter.execute = execute
        service.run_one()
        selected = self._selected(service)
        # #597: the turn's own capability-need judgment is linked to it as well.
        self.assertEqual([row['purpose'] for row in selected['decisions']], ['capability-need', 'presence'])
        self.assertNotIn('raw', selected['decisions'][-1], 'only the summary fields are exposed')
        # #559: the content-free declared answer is shown; the probability is not.
        self.assertEqual(selected['decisions'][-1]['answer'], 'retry')
        self.assertNotIn('confidence', selected['decisions'][-1])
        self.assertIsNone(service.current_work_id, 'the link ends with the Work')

    def test_direct_api_records_requested_and_reported_model(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'state')
        config = {'provider': 'compatible', 'endpoint': 'http://127.0.0.1:9999', 'model': 'fixture-model'}
        service = AgentService(store, adapter=ModelAdapter(lambda url, body, headers: {'model': 'fixture-model-2026', 'choices': [{'message': {'content': 'api answer'}}]}),
                               subscription_engines=SubscriptionEngines(finder=lambda _: None, clock=lambda: 1))
        store.put('model', config)
        store.put('model_test', {'ok': True, 'tools_ok': True, 'time': 9999999999, 'fingerprint': service.model_fingerprint(config)})
        store.enqueue('what is on today', 'k1')
        self.assertTrue(service.run_one())
        job_id = service.task_progress()['tasks'][0]['id']
        record = service.task_progress(job_id)['selected']['provenance']
        self.assertEqual((record['route'], record['requested_model'], record['instructions_channel']), ('direct-api', 'fixture-model', 'system-message'))
        self.assertIn('what is on today', record['prompt_envelope'])
        self.assertEqual(record['status'], 'answered')
        self.assertEqual(record['reported_model'], 'fixture-model-2026', 'a different name in the response is evidence')
        self.assertIn('weather', record['exposed_tools'], 'the tools the model was actually offered')
        self.assertEqual(record['build']['digest_scheme'], 'agentos-package-sha256-v1')

    def test_turn_records_the_offered_tools_and_the_loaded_build(self):
        """AX-11 (#603): route exposure and running build identity, no paths."""
        from personal_agent.bounded_execution import profile_mcp_tools
        from personal_agent.service_control import PACKAGE_DIR, build_identity, package_digest
        service = self._service(_Engine())
        self.store.enqueue('hello', 'k1')
        self.assertTrue(service.run_one())
        record = self._selected(service)['provenance']
        # #627: current context is off here, so its gated action is not offered.
        from personal_agent.bounded_execution import CONTEXT_GATED_ACTIONS
        self.assertEqual(record['exposed_tools'], [tool['name'] for tool in profile_mcp_tools('trusted-local')
                                                   if tool['name'] not in CONTEXT_GATED_ACTIONS])
        self.assertEqual(record['capability_profile'], 'trusted-local')
        self.assertEqual(record['capability_trust'], 'trusted-local')
        self.assertIn('outside AgentOS provenance', record['capability_limitation'])
        self.assertEqual(record['unavailable_tools']['public_page_read'], 'owner-page-approval-bound-to-direct-api-model')
        self.assertEqual(record['build'], build_identity())
        self.assertEqual(record['build']['package_digest'], package_digest(PACKAGE_DIR))
        self.assertEqual(record['build']['origin'], 'source-checkout')
        self.assertNotIn(str(PACKAGE_DIR), json.dumps(record), 'the package path is never recorded')

    def test_isolated_turn_records_the_read_only_facade(self):
        from personal_agent.isolated_mcp_proxy import TaskCapabilityRegistry

        class Isolated:
            def issue_task_token(self, **kwargs):
                return 'isolated-token-value'

            def execute(self, **kwargs):
                return 'isolated answer'
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        service = AgentService(self.store, subscription_engines=SubscriptionEngines(finder=lambda c: '/runtime/' + c, clock=lambda: 1),
                               isolated_engine_adapter=Isolated(), isolated_mcp_registry=TaskCapabilityRegistry())
        service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        self.store.enqueue('hello', 'k1')
        self.assertTrue(service.run_one())
        record = self._selected(service)['provenance']
        self.assertEqual((record['mode'], record['exposed_tools']), ('isolated-agentos-mcp', ['list_notes']))

    def test_direct_api_failure_is_not_left_as_sent(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'state')
        config = {'provider': 'compatible', 'endpoint': 'http://127.0.0.1:9999', 'model': 'fixture-model'}

        def transport(url, body, headers):
            raise OSError('connection refused')
        service = AgentService(store, adapter=ModelAdapter(transport), subscription_engines=SubscriptionEngines(finder=lambda _: None, clock=lambda: 1))
        store.put('model', config)
        store.put('model_test', {'ok': True, 'tools_ok': True, 'time': 9999999999, 'fingerprint': service.model_fingerprint(config)})
        store.enqueue('hello', 'k1')
        service.run_one()
        job_id = store.jobs()[0]['id']
        self.assertEqual(store.turn_provenance(job_id)['status'], 'failed')

    def test_store_keeps_only_the_newest_records(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'state')
        for index in range(store.TURN_PROVENANCE_KEEP + 5):
            store.put_turn_provenance(f'job-{index}', {'n': index})
        self.assertIsNone(store.turn_provenance('job-0'))
        self.assertEqual(store.turn_provenance(f'job-{store.TURN_PROVENANCE_KEEP + 4}'), {'n': store.TURN_PROVENANCE_KEEP + 4})


def node_run(script):
    node = shutil.which('node')
    if node is None:
        raise unittest.SkipTest('Node is needed for JavaScript behaviour checks')
    return subprocess.run([node, '-e', script, str(WEB / 'app.js')], check=True, capture_output=True, text=True, timeout=20).stdout


DOM = r"""
const texts=[];class Node{constructor(tag){this.tag=tag;this.children=[];this._t='';}append(...n){this.children.push(...n);}set textContent(v){this._t=String(v);}get textContent(){return this._t+this.children.map(c=>c.textContent).join(' ');}}
const ui=require(process.argv[1]);ui.setLanguage('en');
global.document={createElement:tag=>new Node(tag)};
const store={};global.window={localStorage:{getItem:k=>store[k]??null,setItem:(k,v)=>{store[k]=String(v);}}};
"""


class DeveloperModeUi(unittest.TestCase):
    def test_off_by_default_and_view_reports_absent_fields_honestly(self):
        out = node_run(DOM + r"""
const assert=require('node:assert/strict');
assert.equal(ui.developerMode(),false);
window.localStorage.setItem('agentos-developer-mode','1');assert.equal(ui.developerMode(),true);
const view=ui.provenanceView({id:'w1',decisions:[],provenance:{route:'subscription',engine:'codex',status:'answered',instructions_version:'v1',instructions_digest:'abcd',prompt_envelope:'PROMPT BODY',argv:['codex','exec']}}).textContent;
assert.match(view,/not specified \(CLI default\)/);assert.match(view,/Reported model not reported/);assert.doesNotMatch(view,/Auxiliary judgment/,'#559: DecisionEngine calls live in 기술 정보, not in the raw developer block');assert.match(view,/PROMPT BODY/);
assert.match(ui.provenanceView({id:'w2'}).textContent,/No run record/);
console.log('ok');""")
        self.assertIn('ok', out)

    def test_technical_info_adds_provenance_only_in_developer_mode(self):
        app = (WEB / 'app.js').read_text(encoding='utf-8')
        self.assertIn("if(developerMode())box.append(provenanceView(task));", app)
        html = (WEB / 'index.html').read_text(encoding='utf-8')
        self.assertIn('id="developer-mode"', html)
        self.assertIn("'agentos-developer-mode'", app)


if __name__ == '__main__':
    unittest.main()

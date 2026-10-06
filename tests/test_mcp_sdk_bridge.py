"""#1025 host stdio integration with the real optional MCP SDK.

Evidence is disposable, model-free process integration. Only the underlying
network/document targets are synthetic; serve, facade, broker, shared Work
ledger, installed SDK transport and dispatcher execute normally. The separate
isolated-engine bridge is outside this migration's supported profiles.
"""
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

from personal_agent.agent_runtime import WORK_LEDGER_KEY, WORK_STOP_KEY
from personal_agent.bounded_execution import HOST_CLI_PROFILES
from personal_agent.quickstart_store import QuickStore


# A subprocess fixture: replace only effect targets, never the upstream API or
# AgentOS facade/broker. Profiling observes actual SDK entry execution without
# wrapping/replacing it or changing its scheduling.
PEER_SERVER = textwrap.dedent('''\
    import json, logging, sys, time
    from pathlib import Path
    from mcp.server.stdio import stdio_server
    from mcp.shared.jsonrpc_dispatcher import JSONRPCDispatcher
    from personal_agent import agent_runtime, mcp_bridge
    from personal_agent.agent_runtime import ToolError
    from personal_agent.local_tools import LocalTools
    from personal_agent.providers import ProviderError

    logging.basicConfig(level=logging.DEBUG)
    data, job, profile, trace, mode = sys.argv[1:]
    trace = Path(trace)
    def record(kind, **fields):
        with trace.open('a') as output:
            output.write(json.dumps({'kind':kind, **fields}) + '\\n')

    watched = {stdio_server.__wrapped__.__code__:'stdio_server',
               JSONRPCDispatcher.run.__code__:'JSONRPCDispatcher.run'}
    seen = set()
    def observe(frame, event, arg):
        name = watched.get(frame.f_code) if event == 'call' else None
        if name and name not in seen:
            seen.add(name)
            record('sdk', api=name)
    sys.setprofile(observe)

    def execute(self, plan, **kwargs):
        record('enter', plan=plan)
        if mode == 'slow':
            time.sleep(0.03)
        if mode == 'noisy':
            print('synthetic helper output', flush=True)
        if mode == 'transient':
            raise ProviderError('synthetic token=abcdefgh12345678')
        if mode == 'unknown_exception':
            raise EOFError('synthetic token=abcdefgh12345678')
        if mode == 'unknown_effect':
            error = ToolError('The synthetic effect needs reconciliation.', 'effect_unknown')
            error.effect = 'unknown'
            raise error
        record('exit', plan=plan)
        return {'tool':plan['tool'], 'location':{'name':plan.get('city')},
                'sources':['https://synthetic.example/'], 'retrieved_at':1}
    LocalTools.execute = execute
    original_read = agent_runtime.read_document
    def read_document(path):
        record('document', path=str(path))
        return original_read(path)
    agent_runtime.read_document = read_document
    mcp_bridge.serve(data, job, profile=profile)
    sys.setprofile(None)
''')


def request(ident, method, params=None, **fields):
    value = {'jsonrpc':'2.0', 'id':ident, 'method':method, **fields}
    if params is not None:
        value['params'] = params
    return value


def call(ident, name='weather', arguments=None):
    return request(ident, 'tools/call', {'name':name, 'arguments':arguments if arguments is not None else {'city':'Synthetic City'}})


@unittest.skipUnless(importlib.util.find_spec('mcp'), 'host SDK extra is not installed')
class InstalledHostBridge(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = QuickStore(self.root / 'state')
        self.job = self.store.enqueue('synthetic SDK boundary', 'sdk-boundary')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (self.job,))
        self.counter = 0

    def _start(self, profile='trusted-local', mode='ok', job=None):
        self.counter += 1
        trace = self.root / f'trace-{self.counter}.jsonl'
        env = dict(os.environ)
        env['PYTHONPATH'] = str(Path(__file__).parents[1] / 'src')
        process = subprocess.Popen(
            [sys.executable, '-c', PEER_SERVER, str(self.store.root), job or self.job, profile, str(trace), mode],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', env=env)
        self.addCleanup(self._cleanup, process)
        return process, trace

    @staticmethod
    def _cleanup(process):
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)

    def _exchange(self, requests, **options):
        process, trace = self._start(**options)
        wire = ''.join(json.dumps(row, ensure_ascii=False) + '\n' if not isinstance(row, str) else row + '\n'
                       for row in requests)
        output, error = process.communicate(wire, timeout=15)
        self.assertEqual(process.returncode, 0, error[-1500:])
        self.last_stderr = error
        replies = [json.loads(line) for line in output.splitlines()]
        events = self._trace(trace)
        self._assert_sdk(events)
        return replies, events

    @staticmethod
    def _trace(trace):
        return [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []

    def _assert_sdk(self, events):
        self.assertEqual({row['api'] for row in events if row['kind']=='sdk'},
                         {'stdio_server', 'JSONRPCDispatcher.run'},
                         'the production entry must actually execute both upstream mechanics')

    def _read(self, process):
        ready, _, _ = select.select([process.stdout], [], [], 10)
        self.assertTrue(ready, 'stdio response deadline exceeded')
        line = process.stdout.readline()
        self.assertTrue(line, 'bridge closed before replying')
        return json.loads(line)

    def _send(self, process, row):
        process.stdin.write(json.dumps(row) + '\n')
        process.stdin.flush()
        return self._read(process)

    def _finish(self, process):
        process.stdin.close()
        process.stdin = None
        output, error = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 0, error[-1500:])
        self.assertEqual(output, '', 'shutdown must not invent an extra response')

    def _events(self):
        with self.store.db() as db:
            return [(row['tool'], row['status'], json.loads(row['detail'])) for row in db.execute(
                'SELECT tool,status,detail FROM tool_events WHERE job_id=? ORDER BY id', (self.job,))]

    def test_installed_sdk_contract_is_the_exact_reviewed_release(self):
        self.assertEqual(importlib.metadata.version('mcp'), '2.3.0')
        self.assertEqual(importlib.metadata.version('mcp-types'), '2.3.0')

    def test_discovery_and_call_use_upstream_and_existing_broker_for_both_host_profiles(self):
        for profile in HOST_CLI_PROFILES:
            with self.subTest(profile=profile):
                replies, effects = self._exchange([
                    request('init', 'initialize', {}),
                    {'jsonrpc':'2.0', 'method':'notifications/initialized'},
                    request('list', 'tools/list'), call('call')], profile=profile)
                self.assertEqual([row['id'] for row in replies], ['init', 'list', 'call'])
                self.assertEqual(replies[0]['result']['capabilities'], {'tools':{}})
                names = {row['name'] for row in replies[1]['result']['tools']}
                self.assertIn('weather', names)
                self.assertNotIn('run_shell', names)
                self.assertNotIn('save_memory', names, 'without its service relay owner-state writes stay unoffered')
                value = json.loads(replies[2]['result']['content'][0]['text'])
                self.assertEqual(value['location']['name'], 'Synthetic City')
                self.assertEqual([row['plan'] for row in effects if row['kind']=='enter'],
                                 [{'tool':'weather', 'city':'Synthetic City'}])
        finals = [row for row in self._events() if row[1]=='succeeded']
        self.assertEqual(len(finals), 2)
        self.assertTrue(all(row[2]['host_action']=='weather' for row in finals))

    def test_denied_and_invalid_calls_never_reach_underlying_target(self):
        for profile in HOST_CLI_PROFILES:
            with self.subTest(profile=profile):
                replies, effects = self._exchange([
                    call(1, 'run_shell', {'command':'denied'}),
                    call(2, arguments={'city':'Synthetic', 'approved':True}),
                    call(3, arguments={'city':7}),
                    call(4, arguments={'city':'token=abcdefgh12345678'})], profile=profile)
                self.assertEqual([row['error']['code'] for row in replies[:3]], [-32602]*3)
                self.assertTrue(replies[3]['result']['isError'])
                self.assertEqual([row for row in effects if row['kind']=='enter'], [])
        self.assertTrue(any(row[0]=='unlisted' and row[2].get('code')=='unknown_tool' for row in self._events()))

    def test_work_stop_deadline_stale_and_foreign_bindings_deny_before_target(self):
        controls = ('stop', 'deadline', 'stale', 'foreign')
        for profile in HOST_CLI_PROFILES:
            for control in controls:
                with self.subTest(profile=profile, control=control):
                    with self.store.db() as db:
                        db.execute("UPDATE jobs SET status='running' WHERE id=?", (self.job,))
                        db.execute('DELETE FROM config WHERE key IN (?,?)', (WORK_STOP_KEY, f'{WORK_LEDGER_KEY}:{self.job}'))
                    if control == 'stop':
                        self.store.put(WORK_STOP_KEY, [self.job])
                    if control == 'deadline':
                        self.store.put(f'{WORK_LEDGER_KEY}:{self.job}', {'attempts':0, 'deadline':time.time()-1})
                    if control == 'stale':
                        with self.store.db() as db:
                            db.execute("UPDATE jobs SET status='succeeded' WHERE id=?", (self.job,))
                    replies, effects = self._exchange([request(1, 'tools/list'), call(2)], profile=profile,
                                                      job='foreign-work' if control=='foreign' else self.job)
                    self.assertIn('tools', replies[0]['result'], 'discovery never grants authority')
                    typed = replies[1]['result']['structuredContent']
                    self.assertEqual(typed['code'], 'deadline_exceeded' if control=='deadline' else 'stopped')
                    self.assertEqual(typed['effect'], 'none')
                    self.assertEqual([row for row in effects if row['kind']=='enter'], [])

    def test_folder_revocation_after_discovery_prevents_another_document_read(self):
        folder = self.root / 'granted'
        folder.mkdir()
        folder = folder.resolve()  # macOS temp directory may have /var symlinks.
        (folder / 'sample.txt').write_text('synthetic original')
        self.store.put('file_roots', [{'id':'synthetic-root', 'path':str(folder), 'name':'Fixture'}])
        process, trace = self._start(profile='trusted-local')
        listed = self._send(process, request(1, 'tools/list'))['result']['tools']
        self.assertIn('read_file', {tool['name'] for tool in listed})
        args = {'root_id':'synthetic-root', 'path':'sample.txt'}
        first = self._send(process, call(2, 'read_file', args))
        self.assertIn('synthetic original', first['result']['content'][0]['text'])
        self.store.put('file_roots', [])
        denied = self._send(process, call(3, 'read_file', args))
        self.assertTrue(denied['result']['isError'])
        self._finish(process)
        events = self._trace(trace)
        self._assert_sdk(events)
        documents = [row for row in events if row['kind']=='document']
        self.assertEqual([Path(row['path']).resolve() for row in documents], [(folder / 'sample.txt').resolve()])
        self.assertEqual((folder / 'sample.txt').read_text(), 'synthetic original')
        # Strict host profile has never offered folder reads, even with a grant.
        self.store.put('file_roots', [{'id':'synthetic-root', 'path':str(folder), 'name':'Fixture'}])
        replies, effects = self._exchange([request(1, 'tools/list'), call(2, 'read_file', args)], profile='strict-isolated')
        self.assertNotIn('read_file', {tool['name'] for tool in replies[0]['result']['tools']})
        self.assertEqual(replies[1]['error']['code'], -32602)
        self.assertEqual([row for row in effects if row['kind']=='document'], [])

    def test_typed_unknown_effect_and_unexpected_failures_are_redacted_and_session_survives(self):
        expected = {'transient':('transient_failure', 'transient', 'none', 2),
                    'unknown_effect':('effect_unknown', 'never', 'unknown', 1),
                    'unknown_exception':('tool_failed', 'permanent', 'none', 1)}
        for profile in HOST_CLI_PROFILES:
            for mode, (code, retry, effect, count) in expected.items():
                with self.subTest(profile=profile, mode=mode):
                    replies, events = self._exchange([call('failed'), request('later', 'tools/list')], profile=profile, mode=mode)
                    self.assertEqual([row['id'] for row in replies], ['failed', 'later'])
                    self.assertTrue(replies[0]['result']['isError'])
                    typed = replies[0]['result']['structuredContent']
                    self.assertEqual((typed['code'], typed['retry'], typed['effect']), (code, retry, effect))
                    self.assertIn('tools', replies[1]['result'])
                    self.assertEqual(len([row for row in events if row['kind']=='enter']), count)
                    self.assertNotIn('abcdefgh12345678', json.dumps(replies))
        self.assertNotIn('abcdefgh12345678', json.dumps(self._events()))

    def test_repeated_request_ids_and_unknown_envelope_fields_preserve_host_characterization(self):
        # Host has never enforced the isolated bridge's exact envelope shape.
        # Duplicate correlation IDs are echoed; no deduplication/replay claim.
        replies, _ = self._exchange([
            request(0, 'initialize', {}, extension='ignored'),
            request('same', 'tools/list', extension='ignored'),
            request('same', 'tools/list'), request(7, 'resources/list')])
        self.assertEqual([row['id'] for row in replies], [0, 'same', 'same', 7])
        self.assertIn('result', replies[0])
        self.assertIn('result', replies[1])
        self.assertEqual(replies[-1]['error'], {'code':-32601, 'message':'Method not found.'})

    def test_malformed_wire_is_dropped_without_parser_payload_logging_or_effects(self):
        # The SDK now owns shape/version/id parsing. The former host did not
        # enforce these checks; this pins the migration difference explicitly.
        bad = [
            'not-json token=abcdefgh12345678',
            [],
            request(1, 'tools/call', {'name':'weather', 'arguments':{'city':'token=abcdefgh12345678'}}, jsonrpc='1.0'),
            request({'secret':'token=abcdefgh12345678'}, 'tools/list'),
            request(2, 'tools/call', ['token=abcdefgh12345678']),
        ]
        replies, effects = self._exchange([*bad, request('valid', 'tools/list'),
                                          request('wrong-notification', 'notifications/initialized')])
        self.assertEqual([row['id'] for row in replies], ['valid', 'wrong-notification'])
        self.assertIn('tools', replies[0]['result'])
        self.assertEqual(replies[1]['error'], {'code':-32601, 'message':'Method not found.'})
        self.assertEqual([row for row in effects if row['kind']=='enter'], [])
        self.assertNotIn('abcdefgh12345678', self.last_stderr)
        self.assertNotIn('ValidationError', self.last_stderr)
        self.assertEqual(self._events(), [])

    def test_invalid_ids_normalize_to_notifications_without_adding_effect_authority(self):
        # mcp-types' union parser falls back to JSONRPCNotification when an id
        # does not validate as int/string. Host notifications already execute
        # mediated calls. Pin that normalization rather than silently claiming
        # isolated bridge rejection semantics for the host.
        ids = [True, 1.5, None, {'invalid':'id'}, ['invalid-id']]
        requests = [call(ident, arguments={'city':str(index)}) for index, ident in enumerate(ids)]
        denied = [call(ident, arguments={'city':'Synthetic', 'approved':True}) for ident in ids]
        replies, effects = self._exchange([*requests, *denied, request('later', 'tools/list')])
        self.assertEqual([row['id'] for row in replies], ['later'])
        self.assertEqual([row['plan']['city'] for row in effects if row['kind']=='enter'],
                         [str(index) for index in range(len(ids))])
        self.assertEqual(len([row for row in self._events() if row[1]=='succeeded']), len(ids))
        self.assertEqual(len([row for row in self._events() if row[2].get('code')=='invalid_arguments']), len(ids))

    def test_call_notifications_execute_without_response_and_late_cancel_does_not_replay(self):
        notification = call(1)
        del notification['id']
        replies, effects = self._exchange([
            notification, call('finished'),
            {'jsonrpc':'2.0', 'method':'notifications/cancelled', 'params':{'requestId':'finished'}},
            request('later', 'tools/list')])
        self.assertEqual([row['id'] for row in replies], ['finished', 'later'])
        self.assertEqual(len([row for row in effects if row['kind']=='enter']), 2)

    def test_batched_same_tool_calls_stay_serialized_and_eof_flushes_all_responses(self):
        replies, effects = self._exchange([
            call('first', arguments={'city':'First'}), call('second', arguments={'city':'Second'})], mode='slow')
        self.assertEqual([row['id'] for row in replies], ['first', 'second'])
        self.assertEqual([(row['kind'], row['plan']['city']) for row in effects if row['kind'] in {'enter','exit'}],
                         [('enter','First'), ('exit','First'), ('enter','Second'), ('exit','Second')])
        self.assertEqual([row[1] for row in self._events()], ['running','succeeded','running','succeeded'])

    def test_unsupported_method_as_only_request_before_eof_is_answered(self):
        replies, effects = self._exchange([request('unknown', 'unknown/synthetic-method')])
        self.assertEqual(replies, [{'jsonrpc':'2.0', 'id':'unknown',
                                   'error':{'code':-32601, 'message':'Method not found.'}}])
        self.assertEqual([row for row in effects if row['kind']=='enter'], [])

    def test_sdk_stdio_claim_keeps_stray_target_output_off_the_wire(self):
        replies, effects = self._exchange([call('noisy')], mode='noisy')
        self.assertEqual([row['id'] for row in replies], ['noisy'])
        self.assertIn('result', replies[0])
        self.assertIn('synthetic helper output', self.last_stderr)
        self.assertEqual(len([row for row in effects if row['kind']=='exit']), 1)

    def test_empty_input_eof_closes_cleanly_without_effects(self):
        replies, effects = self._exchange([])
        self.assertEqual(replies, [])
        self.assertEqual([row for row in effects if row['kind']=='enter'], [])


if __name__ == '__main__':
    unittest.main()

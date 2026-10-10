"""CONNECT-DECIDE-01 (#1296): one AgentOS decision point for every AI-side tool call.

Model-free: scripted CLIs, the real service relay and the real hook process;
nothing reaches a model or an external service.
"""
import io
import json
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from personal_agent import codex_permission_hook, owner_mcp
from personal_agent.bounded_execution import BoundedExecutionAdapter, cli_metadata
from personal_agent.quickstart_store import QuickStore

SAVE = 'mcp__notes__save_note'
LIST = 'mcp__notes__list_notes'


class ToolNameTests(unittest.TestCase):
    def test_names_split_into_kind_service_and_operation(self):
        self.assertEqual(owner_mcp.tool_server('mcp__claude_ai_Google_Drive__search_files'),
                         ('ai-connection', 'Google Drive', 'search_files'))
        self.assertEqual(owner_mcp.tool_server(SAVE), ('owner-mcp', 'notes', 'save_note'))
        self.assertEqual(owner_mcp.tool_server('mcp__notes__get__nested'), ('owner-mcp', 'notes', 'get__nested'))
        for name in ('mcp__agentos__file_read', 'Bash', 'mcp__', 'mcp__notes', 'mcp____x', 'mcp__claude_ai_', None, 'x' * 300):
            self.assertIsNone(owner_mcp.tool_server(name), name)

    def test_confirmed_servers_are_validated_and_bounded(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = QuickStore(Path(temp.name) / 'state')
        self.assertEqual(owner_mcp.confirmed(store, 'codex'), [], 'nothing is confirmed by default')
        self.assertEqual(owner_mcp.set_confirmed(store, 'codex', ['notes', 'notes', 'files']), ['notes', 'files'])
        for bad in (['agentos'], ['has space'], ['a' * 65]):
            with self.assertRaises(ValueError):
                owner_mcp.set_confirmed(store, 'codex', bad)
        with self.assertRaises(ValueError):
            owner_mcp.set_confirmed(store, 'other', ['notes'])
        store.put(owner_mcp.CONFIRMED_KEY, {'codex': ['notes', 'agentos', 7, 'bad name']})
        self.assertEqual(owner_mcp.confirmed(store, 'codex'), ['notes'], 'a stored value is re-validated')


class CodexLaunchTests(unittest.TestCase):
    def test_secret_values_travel_only_in_the_environment(self):
        args, env, secret = owner_mcp.codex_launch({
            'notes': {'type': 'stdio', 'command': '/usr/bin/notes', 'args': ['serve'], 'env': {'NOTES_KEY': 'sk-secret-1'}},
            'web': {'type': 'streamable_http', 'url': 'https://mcp.example.test/mcp',
                    'http_headers': {'Authorization': 'Bearer sk-secret-2'}, 'bearer_token_env_var': None}})
        flat = ' '.join(args)
        self.assertNotIn('sk-secret', flat, 'no value may appear in an argument')
        self.assertEqual(env['NOTES_KEY'], 'sk-secret-1')
        self.assertIn('Bearer sk-secret-2', env.values())
        self.assertIn('mcp_servers.notes.env_vars=["NOTES_KEY"]', args)
        self.assertTrue(any(a.startswith('mcp_servers.web.env_http_headers={"Authorization": "AGENTOS_MCP_') for a in args))
        self.assertIn('mcp_servers.notes.default_tools_approval_mode="approve"', args)
        self.assertIn(f'shell_environment_policy.exclude={json.dumps(secret)}', args,
                      "the model's shell never inherits the values")
        self.assertEqual(set(secret), set(env))

    def test_unexpressible_or_reserved_definitions_are_skipped_whole(self):
        args, env, _secret = owner_mcp.codex_launch({
            'agentos': {'type': 'stdio', 'command': '/x'},
            'path': {'type': 'stdio', 'command': '/x', 'env': {'PATH': '/evil'}},
            'plain': {'type': 'streamable_http', 'url': 'http://insecure.test/mcp'},
            'odd': {'type': 'sse', 'url': 'https://x.test'},
            'bad name': {'type': 'stdio', 'command': '/x'}})
        self.assertEqual((args, env), ([], {}))

    def test_two_servers_cannot_share_a_name_with_different_values(self):
        args, env, _secret = owner_mcp.codex_launch({
            'a': {'type': 'stdio', 'command': '/a', 'env': {'KEY': 'one'}},
            'b': {'type': 'stdio', 'command': '/b', 'env': {'KEY': 'two'}}})
        self.assertEqual(env, {'KEY': 'one'})
        self.assertFalse(any('mcp_servers.b.' in a for a in args))

    def test_definition_comes_from_the_cli_and_disabled_servers_are_absent(self):
        calls = []

        def runner(argv, **kwargs):
            calls.append(argv)
            enabled = argv[3] == 'notes'
            return subprocess.CompletedProcess(argv, 0, json.dumps({'name': argv[3], 'enabled': enabled,
                                                                    'transport': {'type': 'stdio', 'command': '/n'}}), '')
        self.assertEqual(owner_mcp.codex_definition('/runtime/codex', 'notes', {}, runner=runner),
                         {'type': 'stdio', 'command': '/n'})
        self.assertIsNone(owner_mcp.codex_definition('/runtime/codex', 'off', {}, runner=runner))
        self.assertEqual(calls[0], ['/runtime/codex', 'mcp', 'get', 'notes', '--json'])
        self.assertIsNone(owner_mcp.codex_definition('/runtime/codex', 'x', {}, runner=lambda *a, **k: (_ for _ in ()).throw(OSError())))

    def test_the_hook_needs_the_trust_flag_and_the_command_carries_only_the_relay(self):
        args = owner_mcp.codex_hook_arguments('/relay/dir')
        self.assertEqual(args[0], '--dangerously-bypass-hook-trust',
                         'without it codex-cli 0.153.4 skips a session-flag hook and the call runs')
        self.assertIn('matcher="^mcp__"', args[2])
        self.assertIn('personal_agent.codex_permission_hook', args[2])
        self.assertIn('/relay/dir', args[2])

    def test_the_command_places_owner_arguments_before_the_prompt(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        config = Path(temp.name) / 'agentos-mcp.json'
        config.write_text(json.dumps({'mcpServers': {'agentos': {'command': 'python3', 'args': ['-m', 'bridge']}}}))
        adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name)
        argv = adapter.command('codex', '/runtime/codex', 'the prompt', config,
                               owner_mcp_args=('-c', 'mcp_servers.notes.command="/n"'))
        self.assertLess(argv.index('mcp_servers.notes.command="/n"'), argv.index('the prompt'))
        self.assertNotIn('--dangerously-bypass-hook-trust', adapter.command('codex', '/runtime/codex', 'p', config),
                         'without confirmed servers nothing changes')


class HookTests(unittest.TestCase):
    def run_hook(self, call, decision=None, error=None):
        class Relay:
            def __init__(self, directory):
                pass

            def call(self, name, arguments):
                if error:
                    raise error
                self.seen = (name, arguments)
                return decision
        out = io.StringIO()
        with mock.patch.object(codex_permission_hook, 'RelayClient', Relay):
            codex_permission_hook.main(['--relay', '/r'], stdin=io.StringIO(call if isinstance(call, str) else json.dumps(call)), stdout=out)
        return out.getvalue()

    def test_allow_prints_nothing_and_deny_prints_a_reasoned_deny(self):
        call = {'tool_name': SAVE, 'tool_input': {'text': 'x'}}
        self.assertEqual(self.run_hook(call, {'behavior': 'allow', 'updatedInput': {}}), '')
        denied = json.loads(self.run_hook(call, {'behavior': 'deny', 'message': '막았습니다.'}))
        self.assertEqual(denied['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual(denied['hookSpecificOutput']['permissionDecisionReason'], '막았습니다.')

    def test_anything_unexpected_denies(self):
        for call, kwargs in ((('not json'), {}), ({'tool_input': {}}, {}),
                             ({'tool_name': SAVE}, {'error': OSError('gone')}),
                             ({'tool_name': SAVE}, {'decision': {'behavior': 'maybe'}}),
                             ({'tool_name': SAVE}, {'decision': None})):
            output = json.loads(self.run_hook(call, **kwargs))
            self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny', call)
            self.assertTrue(output['hookSpecificOutput']['permissionDecisionReason'], 'Codex requires a non-empty reason')

    def test_the_bridge_decides_its_own_tools(self):
        self.assertEqual(self.run_hook({'tool_name': 'mcp__agentos__file_read'}, error=AssertionError('not asked')), '')


class ServiceDecisionTests(unittest.TestCase):
    def setUp(self):
        from personal_agent.quickstart_service import AgentService
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = QuickStore(Path(temp.name) / 'state')
        self.service = AgentService(self.store)
        self.job = {'id': self.store.enqueue('notes', 'k1')}
        self.service.set_ai_connections({'enabled': True})
        reviewed = {'Google Drive': frozenset({'search_files'}), 'notes': frozenset({'list_notes'})}
        patcher = mock.patch.object(type(self.service), 'reviewed_connector_reads', staticmethod(lambda: reviewed))
        patcher.start()
        self.addCleanup(patcher.stop)

    def decide(self, tool):
        return self.service.connector_permission(self.job, {'tool_name': tool, 'input': {'text': 'private'}})['behavior']

    def events(self, tool):
        with self.store.db() as db:
            return [dict(row) for row in db.execute('SELECT status,detail FROM tool_events WHERE tool=?', (tool,))]

    def test_an_owner_server_is_decided_only_once_confirmed(self):
        self.assertEqual(self.decide(LIST), 'deny', 'an unconfirmed server is refused even for a reviewed read')
        owner_mcp.set_confirmed(self.store, 'codex', ['notes'])
        self.assertEqual(self.decide(LIST), 'allow')
        self.assertEqual(self.decide(SAVE), 'deny', 'an unreviewed operation is not a read')
        self.assertEqual(self.decide('mcp__claude_ai_Google_Drive__search_files'), 'allow', 'claude.ai connectors unchanged')
        self.assertNotIn('private', json.dumps(self.events('connector_permission')), 'the input is never recorded')
        self.assertEqual(json.loads(self.events('connector_permission')[0]['detail'])['evidence']['kind'], 'owner-mcp')

    def test_ai_connections_off_refuses_owner_servers_too(self):
        owner_mcp.set_confirmed(self.store, 'codex', ['notes'])
        self.service.set_ai_connections({'enabled': False})
        self.assertEqual(self.decide(LIST), 'deny')

    def test_a_call_that_ran_without_a_decision_switches_owner_servers_off(self):
        owner_mcp.set_confirmed(self.store, 'codex', ['notes'])
        owner_mcp.set_confirmed(self.store, 'claude-code', ['notes'])
        self.assertEqual(self.decide(LIST), 'allow')
        self.service.record_turn_provenance(self.job['id'], connector_reads=[{'tool': LIST, 'status': 'succeeded'}])
        self.assertEqual(self.events('connector_undecided'), [], 'a decided call is fine')
        self.service.record_turn_provenance(self.job['id'], connector_reads=[{'tool': SAVE, 'status': 'succeeded'},
                                                                             {'tool': SAVE, 'status': 'failed'}])
        undecided = self.events('connector_undecided')
        self.assertEqual(len(undecided), 1, 'only a call that ran counts')
        self.assertEqual(json.loads(undecided[0]['detail'])['evidence'], {'service': 'notes', 'operation': 'save_note', 'kind': 'owner-mcp'})
        self.assertEqual((owner_mcp.confirmed(self.store, 'codex'), owner_mcp.confirmed(self.store, 'claude-code')), ([], []),
                         'fail closed: the owner confirms again')


class StreamTests(unittest.TestCase):
    def test_codex_owner_server_calls_are_recorded_and_the_bridge_is_not(self):
        stream = '\n'.join(json.dumps(record) for record in (
            {'type': 'item.completed', 'item': {'id': 'i1', 'type': 'mcp_tool_call', 'server': 'notes', 'tool': 'list_notes',
                                                'arguments': {'q': 'private'}, 'status': 'completed', 'error': None}},
            {'type': 'item.completed', 'item': {'id': 'i2', 'type': 'mcp_tool_call', 'server': 'notes', 'tool': 'save_note',
                                                'status': 'failed', 'error': {'message': 'x'}}},
            {'type': 'item.completed', 'item': {'id': 'i3', 'type': 'mcp_tool_call', 'server': 'agentos', 'tool': 'file_read',
                                                'status': 'completed'}},
            {'type': 'turn.completed', 'usage': {}}))
        meta = cli_metadata('codex', stream)
        self.assertEqual(meta['connector_reads'], [{'tool': LIST, 'status': 'succeeded'}, {'tool': SAVE, 'status': 'failed'}])
        self.assertNotIn('private', json.dumps(meta['connector_reads']))

    def test_claude_owner_server_calls_are_matched_like_connectors(self):
        stream = '\n'.join(json.dumps(record) for record in (
            {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': 't1', 'name': LIST, 'input': {}}]}},
            {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 't1', 'content': 'x'}]}},
            {'type': 'result', 'subtype': 'success', 'result': 'ok'}))
        self.assertEqual(cli_metadata('claude-code', stream)['connector_reads'], [{'tool': LIST, 'status': 'succeeded'}])


class CodexWireTests(unittest.TestCase):
    """A Codex turn with a confirmed owner server: the real hook process asks the service through the turn's relay."""

    def setUp(self):
        from personal_agent.browser_session import BrowserProfile
        from personal_agent.providers import ModelAdapter
        from personal_agent.quickstart_service import AgentService
        from personal_agent.subscription_engines import SubscriptionEngines
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / 'codex-home').mkdir()
        self.store = QuickStore(root / 'state')
        self.argv, self.env, self.hook_outputs = None, None, {}

        class Done:
            returncode = 0
            stdout = json.dumps({'type': 'item.completed', 'item': {'id': 'm', 'type': 'agent_message', 'text': 'engine answer'}})

        def runner(argv, **kwargs):
            if argv[1:3] == ['mcp', 'get']:
                return subprocess.CompletedProcess(argv, 0, json.dumps({'name': argv[3], 'enabled': True, 'transport': {
                    'type': 'stdio', 'command': '/usr/bin/notes', 'args': [], 'env': {'NOTES_KEY': 'sk-owner-secret'}}}), '')
            if argv[1:2] != ['exec']:
                return subprocess.CompletedProcess(argv, 0, 'codex-cli 0.153.4\n', '')
            self.argv, self.env = argv, kwargs['env']
            hook = next((a for a in argv if a.startswith('hooks.PreToolUse=')), None)
            if hook:
                command = hook.split('command=', 1)[1].rsplit('}]}]', 1)[0]
                command = json.loads(command)
                for tool in (LIST, SAVE, 'mcp__agentos__file_read'):
                    done = subprocess.run(shlex.split(command), input=json.dumps({'tool_name': tool, 'tool_input': {'q': 1}}),
                                          capture_output=True, text=True, timeout=30, env=kwargs['env'])
                    self.hook_outputs[tool] = done.stdout
            return Done()

        adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=runner,
                                          runtime_root=root / 'turns', codex_home=root / 'codex-home')
        self.service = AgentService(self.store, adapter=ModelAdapter(lambda *a: {'choices': [{'message': {'content': 'x'}}]}),
                                    subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/codex', clock=lambda: 1),
                                    execution_adapter=adapter,
                                    browser_profile=BrowserProfile(root / 'browser', available=lambda: False))
        self.service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        self.service.cli_native_search = lambda *args: (False, 'refused')
        reviewed = {'notes': frozenset({'list_notes'})}
        patcher = mock.patch.object(type(self.service), 'reviewed_connector_reads', staticmethod(lambda: reviewed))
        patcher.start()
        self.addCleanup(patcher.stop)

    def turn(self):
        self.store.enqueue('notes please', f'wire-{id(self)}')
        self.assertTrue(self.service.run_one())

    def test_without_confirmed_servers_the_launch_is_unchanged(self):
        self.service.set_ai_connections({'enabled': True})
        self.turn()
        self.assertNotIn('--dangerously-bypass-hook-trust', self.argv)
        self.assertFalse(any(a.startswith('hooks.') for a in self.argv))

    def test_the_hook_asks_the_service_and_the_secret_stays_out_of_arguments(self):
        self.service.set_ai_connections({'enabled': True})
        owner_mcp.set_confirmed(self.store, 'codex', ['notes'])
        self.turn()
        self.assertIn('--dangerously-bypass-hook-trust', self.argv)
        self.assertNotIn('sk-owner-secret', ' '.join(self.argv))
        self.assertEqual(self.env['NOTES_KEY'], 'sk-owner-secret')
        self.assertEqual(self.hook_outputs[LIST], '', 'a reviewed read runs')
        self.assertEqual(json.loads(self.hook_outputs[SAVE])['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual(self.hook_outputs['mcp__agentos__file_read'], '')
        with self.store.db() as db:
            decided = [row['status'] for row in db.execute("SELECT status FROM tool_events WHERE tool='connector_permission'")]
        self.assertEqual(decided, ['allowed', 'denied'])


if __name__ == '__main__':
    unittest.main()

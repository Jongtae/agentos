"""AI-GOOGLE-01 (#1197): Works use the owner's AI-side connections, read-only, by owner opt-in.

Model-free: a scripted CLI speaks to the exact bridge command AgentOS writes,
through the real service relay; nothing reaches a model or Google.
"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from personal_agent.bounded_execution import CONNECTOR_PERMISSION_TOOL, BoundedExecutionAdapter, cli_metadata
from personal_agent.quickstart_store import QuickStore

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
READ = 'mcp__claude_ai_Google_Drive__list_recent_files'
WRITE = 'mcp__claude_ai_Google_Drive__update_file'


class LaunchTests(unittest.TestCase):
    def adapter(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runtime_root=Path(temp.name),
                                       credentials=lambda engine_id: 'long-lived-token'), Path(temp.name)

    def test_on_uses_the_regular_login_and_asks_agentos_for_every_connector_call(self):
        adapter, root = self.adapter()
        argv = adapter.command('claude-code', '/runtime/claude', 'hi', root / 'mcp.json', ai_connections=True)
        self.assertNotIn('--strict-mcp-config', argv)
        self.assertEqual(argv[argv.index('--setting-sources') + 1], 'project')
        self.assertEqual(argv[argv.index('--permission-prompt-tool') + 1], CONNECTOR_PERMISSION_TOOL)
        allowed = argv[argv.index('--allowedTools') + 1]
        self.assertEqual(argv.index('--allowedTools'), len(argv) - 2, '--allowedTools stays last (variadic)')
        self.assertNotIn('claude_ai', allowed, 'no connector tool is pre-approved')
        self.assertNotIn('connector_permission', allowed, 'the model cannot call the permission tool unprompted')
        env = adapter.environment('claude-code', '/runtime/claude', root, ai_connections=True)
        self.assertEqual(env['HOME'], str(Path.home()))
        self.assertNotIn('CLAUDE_CODE_OAUTH_TOKEN', env)
        self.assertIn('--no-session-persistence', argv, 'no turn transcript is left under ~/.claude')

    def test_off_keeps_todays_isolation(self):
        adapter, root = self.adapter()
        argv = adapter.command('claude-code', '/runtime/claude', 'hi', root / 'mcp.json')
        self.assertIn('--strict-mcp-config', argv)
        self.assertNotIn('--permission-prompt-tool', argv)
        env = adapter.environment('claude-code', '/runtime/claude', root)
        self.assertEqual(env['HOME'], str(root))
        self.assertEqual(env['CLAUDE_CODE_OAUTH_TOKEN'], 'long-lived-token')


class ServiceDecisionTests(unittest.TestCase):
    def setUp(self):
        from personal_agent.quickstart_service import AgentService
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = QuickStore(Path(temp.name) / 'state')
        self.service = AgentService(self.store)
        self.job = {'id': self.store.enqueue('drive', 'k1')}

    def events(self, tool='connector_permission'):
        with self.store.db() as db:
            return [dict(row) for row in db.execute('SELECT tool,status,detail FROM tool_events WHERE tool=?', (tool,))]

    def test_off_refuses_everything(self):
        decision = self.service.connector_permission(self.job, {'tool_name': READ, 'input': {}})
        self.assertEqual(decision['behavior'], 'deny')

    def test_on_allows_reads_refuses_writes_and_records_only_names(self):
        self.service.set_ai_connections({'enabled': True})
        allowed = self.service.connector_permission(self.job, {'tool_name': READ, 'input': {'pageSize': 2}})
        self.assertEqual(allowed, {'behavior': 'allow', 'updatedInput': {'pageSize': 2}})
        denied = self.service.connector_permission(self.job, {'tool_name': WRITE, 'input': {'fileId': 'secret-id', 'name': 'x'}})
        self.assertEqual(denied['behavior'], 'deny')
        self.assertIn('실행하지 않았습니다', denied['message'])
        rows = self.events()
        self.assertEqual([row['status'] for row in rows], ['allowed', 'denied'], 'a permission is not a read')
        self.assertNotIn('secret-id', json.dumps(rows))
        self.assertEqual(json.loads(rows[0]['detail'])['evidence'], {'service': 'Google Drive', 'operation': 'list_recent_files',
                                                                      'decision': 'allow'})

    def test_only_reviewed_read_operations_run(self):
        self.service.set_ai_connections({'enabled': True})
        drive = 'mcp__claude_ai_Google_Drive__'
        # Read-sounding names are not reviewed reads: a name never grants authority.
        for tool in (drive + 'get_or_place_order', drive + 'query_database', drive + 'update_file', drive + 'create_file',
                     drive + 'get_and_delete', drive + 'search_files_and_share', 'mcp__claude_ai_Gmail__search_threads',
                     'mcp__claude_ai_X__search_files'):
            self.assertEqual(self.service.connector_permission(self.job, {'tool_name': tool, 'input': {}})['behavior'], 'deny', tool)
        for operation in ('search_files', 'read_file_content', 'get_file_metadata', 'list_recent_files', 'download_file_content'):
            decision = self.service.connector_permission(self.job, {'tool_name': drive + operation, 'input': {}})
            self.assertEqual(decision['behavior'], 'allow', operation)

    def test_an_unreadable_review_list_refuses_everything(self):
        from unittest import mock
        self.service.set_ai_connections({'enabled': True})
        with mock.patch.object(type(self.service), 'reviewed_connector_reads', staticmethod(lambda: {})):
            self.assertEqual(self.service.connector_permission(self.job, {'tool_name': READ, 'input': {}})['behavior'], 'deny')

    def test_a_named_instance_is_treated_as_a_family_instance(self):
        from unittest import mock
        from personal_agent import quickstart_service
        from personal_agent.service_control import DEFAULT_INSTANCES_RELATIVE
        fake_home = Path(self.store.root).parent / 'home'
        instance_root = fake_home / DEFAULT_INSTANCES_RELATIVE / 'family-9'
        instance_root.mkdir(parents=True)
        store = QuickStore(instance_root)
        service = quickstart_service.AgentService(store)
        with mock.patch.object(quickstart_service.Path, 'home', lambda: fake_home):
            self.assertFalse(service.ai_connections_status()['available'])

    def test_only_connector_tools_are_ever_decided(self):
        self.service.set_ai_connections({'enabled': True})
        for tool in ('mcp__agentos__connector_permission', 'Bash', 'mcp__other__read_file', 'mcp__claude_ai_'):
            self.assertEqual(self.service.connector_permission(self.job, {'tool_name': tool, 'input': {}})['behavior'], 'deny', tool)

    def test_the_audit_shows_only_reads_the_stream_saw_complete(self):
        from personal_agent.information_use import work_information_use
        self.service.set_ai_connections({'enabled': True})
        self.service.connector_permission(self.job, {'tool_name': READ, 'input': {}})
        self.assertNotIn('AI에 연결된 서비스', json.dumps(work_information_use(self.store, self.job['id']), ensure_ascii=False),
                         'an allowed call that never ran is not a read')
        self.service.record_turn_provenance(self.job['id'], connector_reads=[
            {'tool': READ, 'status': 'succeeded'}, {'tool': 'mcp__claude_ai_Google_Drive__read_file_content', 'status': 'failed'}])
        self.assertEqual([row['status'] for row in self.events('connector_read')], ['succeeded', 'failed'])
        flat = json.dumps(work_information_use(self.store, self.job['id']), ensure_ascii=False)
        self.assertIn('AI에 연결된 서비스', flat)
        self.assertIn('Google Drive · list_recent_files', flat)
        self.assertNotIn('read_file_content', flat)

    def test_a_family_instance_can_never_turn_it_on(self):
        from unittest import mock
        from personal_agent import family_setup
        with mock.patch.object(family_setup, 'setup_recorded', lambda store: True):
            with self.assertRaises(ValueError):
                self.service.set_ai_connections({'enabled': True})
            self.store.put('ai_connections', {'enabled': True})  # even a stored value is ignored
            self.assertFalse(self.service.ai_connections_enabled())
            read = self.service.conversation_settings_request({'operation': 'read', 'category': 'ai_connections'})
            self.assertIn('unavailable', read['settings']['ai_connections'])

    def test_the_conversation_switches_it_through_a_confirmed_draft(self):
        orchestrator = self.service.settings_orchestrator
        draft = orchestrator.propose('local-owner', 'web', 'ai_connections', 'enabled', 'on')
        self.assertFalse(self.service.ai_connections_enabled(), 'a draft changes nothing')
        orchestrator.confirm('local-owner', 'web', draft['draft_id'], draft['digest'])
        self.assertTrue(self.service.ai_connections_enabled())


class StreamReadTests(unittest.TestCase):
    def test_connector_reads_come_from_matched_tool_results(self):
        stream = '\n'.join(json.dumps(record) for record in (
            {'type': 'assistant', 'message': {'content': [
                {'type': 'tool_use', 'id': 't1', 'name': READ, 'input': {'q': 'private'}},
                {'type': 'tool_use', 'id': 't2', 'name': 'mcp__claude_ai_Google_Drive__read_file_content', 'input': {}},
                {'type': 'tool_use', 'id': 't3', 'name': 'mcp__claude_ai_Google_Drive__search_files', 'input': {}},
                {'type': 'tool_use', 'id': 't4', 'name': 'mcp__agentos__file_read', 'input': {}}]}},
            {'type': 'user', 'message': {'content': [
                {'type': 'tool_result', 'tool_use_id': 't1', 'content': 'file names'},
                {'type': 'tool_result', 'tool_use_id': 't2', 'is_error': True, 'content': 'denied'},
                {'type': 'tool_result', 'tool_use_id': 't4', 'content': 'x'}]}},
            {'type': 'result', 'subtype': 'success', 'result': 'ok'}))
        meta = cli_metadata('claude-code', stream)
        self.assertEqual(meta['connector_reads'], [{'tool': READ, 'status': 'succeeded'},
                                                   {'tool': 'mcp__claude_ai_Google_Drive__read_file_content', 'status': 'failed'}])
        self.assertNotIn('private', json.dumps(meta['connector_reads']))
        self.assertNotIn('connector_reads', cli_metadata('claude-code', json.dumps({'type': 'result', 'result': 'ok'})))


class BridgeWireTests(unittest.TestCase):
    """The exact bridge command answers Claude Code's permission prompt through the service relay."""

    def setUp(self):
        from personal_agent.browser_session import BrowserProfile
        from personal_agent.providers import ModelAdapter
        from personal_agent.quickstart_service import AgentService
        from personal_agent.subscription_engines import SubscriptionEngines
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = QuickStore(Path(temp.name) / 'state')
        self.pending, self.replies, self.argv = None, None, None

        class Done:
            returncode = 0
            stdout = json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'engine answer'})

        adapter = None

        def runner(argv, **kwargs):
            self.argv = argv
            config = json.loads((Path(kwargs['cwd']) / 'agentos-mcp.json').read_text())
            self.server = config['mcpServers']['agentos']
            if self.pending is not None:
                env = {**kwargs['env'], **self.server.get('env', {})}
                completed = subprocess.run([self.server['command'], *self.server['args']],
                                           input=''.join(json.dumps(request) + '\n' for request in self.pending),
                                           capture_output=True, text=True, timeout=30, env=env)
                self.replies = {reply.get('id'): reply for reply in map(json.loads, completed.stdout.splitlines()) if reply}
            return Done()

        adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=runner,
                                          runtime_root=Path(temp.name) / 'turns')
        self.service = AgentService(self.store, adapter=ModelAdapter(lambda *a: {'choices': [{'message': {'content': 'x'}}]}),
                                    subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/claude', clock=lambda: 1),
                                    execution_adapter=adapter,
                                    browser_profile=BrowserProfile(Path(temp.name) / 'browser', available=lambda: False))
        self.service.connect_subscription_engine({'engine': 'claude-code', 'officially_authenticated': True})
        self.service.cli_native_search = lambda *args: (False, 'refused')

    def turn(self, *requests):
        self.pending = (INIT, *requests)
        self.store.enqueue('drive please', f'wire-{len(requests)}-{id(requests)}')
        self.assertTrue(self.service.run_one())
        return self.replies

    def test_off_lists_no_permission_tool_and_keeps_strict_mcp(self):
        replies = self.turn({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
        self.assertNotIn('connector_permission', [tool['name'] for tool in replies[2]['result']['tools']])
        self.assertIn('--strict-mcp-config', self.argv)

    def test_on_the_bridge_answers_with_exactly_one_text_block(self):
        self.service.set_ai_connections({'enabled': True})
        replies = self.turn(
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
             'params': {'name': 'connector_permission', 'arguments': {'tool_name': READ, 'input': {'pageSize': 2}}}},
            {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call',
             'params': {'name': 'connector_permission', 'arguments': {'tool_name': WRITE, 'input': {'name': 'x'}}}})
        self.assertIn('connector_permission', [tool['name'] for tool in replies[2]['result']['tools']])
        self.assertNotIn('--strict-mcp-config', self.argv)
        for reply_id, behavior in ((3, 'allow'), (4, 'deny')):
            content = replies[reply_id]['result']['content']
            self.assertEqual(len(content), 1)
            self.assertEqual(content[0]['type'], 'text')
            self.assertEqual(json.loads(content[0]['text'])['behavior'], behavior)


if __name__ == '__main__':
    unittest.main()

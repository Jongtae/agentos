"""AGENCY-ISOLATION-01 (#616, AX-15 / AX-S19): the strict-isolated CLI profile.

Two evidence classes, named separately:

* Unit tests (always run): the declaration, the exact argv, the execute-time
  version refusal, the no-model qualification logic and the owner's choice.
  Injected runners; no CLI, model or provider is contacted.
* Process-level qualification (opt-in, ``AGENTOS_CLI_QUALIFICATION=1``): the
  exact argv ``BoundedExecutionAdapter.execute`` builds drives the real
  ``codex exec`` / ``claude -p`` against a scripted local fake model endpoint
  (loopback only; no account, credential or live provider).  The only argv
  additions are the fake provider's endpoint settings.  A fake store and a
  canary file are created and removed; no owner data is read.  The bridge's
  public network is stubbed inside the real bridge process through a
  per-turn ``usercustomize`` (the bridge itself is not replaced), as
  ``BoundedProfileHostInvocation`` does in-process.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from personal_agent.bounded_execution import (
    BOUNDED_PROFILE,
    CLI_PROFILES,
    CODEX_STRICT_PERMISSIONS,
    CODEX_STRICT_TABLE,
    STRICT_PROFILE,
    TRUSTED_LOCAL_LIMITATION,
    AgentOSMcpTools,
    BoundedExecutionAdapter,
    ExecutionError,
    ExecutionResult,
    StrictIsolatedAgentOSMcpTools,
    parse_cli_version,
    profile_actions,
    route_unavailable,
)
from personal_agent.quickstart_store import QuickStore

ROOT = Path(__file__).resolve().parents[1]
CODEX_VERSION = CLI_PROFILES[STRICT_PROFILE]['runtimes']['codex']['tested_versions'][0]
CLAUDE_VERSION = CLI_PROFILES[STRICT_PROFILE]['runtimes']['claude-code']['tested_versions'][0]


class _Done:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class _Caps:
    def __init__(self, root):
        self.store = type('S', (), {'root': Path(root)})()
        self.job_id, self.private_provenance = 'job', set()


def _codex_answer():
    return _Done(stdout=json.dumps({'item': {'type': 'agent_message', 'text': 'answer'}}))


class StrictProfileDeclaration(unittest.TestCase):
    def test_strict_profile_is_separate_and_trusted_local_is_unchanged(self):
        strict, trusted = CLI_PROFILES[STRICT_PROFILE], CLI_PROFILES[BOUNDED_PROFILE]
        self.assertEqual((STRICT_PROFILE, strict['trust']), ('strict-isolated', 'strict-isolated'))
        self.assertEqual(trusted['trust'], 'trusted-local')
        self.assertEqual(trusted['limitation'], TRUSTED_LOCAL_LIMITATION)
        self.assertIn('/tmp', strict['limitation'], 'the residual readable paths are stated')
        self.assertEqual(CLI_PROFILES[STRICT_PROFILE]['runtimes']['codex']['tested_versions'], ('0.153.4',))
        self.assertEqual(CLI_PROFILES[STRICT_PROFILE]['runtimes']['claude-code']['tested_versions'], ('2.1.280',))

    def test_strict_offers_what_the_bridge_serves(self):
        """The bridge serves the bounded action set; strict must equal it."""
        self.assertEqual(profile_actions(STRICT_PROFILE), profile_actions(BOUNDED_PROFILE))
        self.assertEqual(route_unavailable(STRICT_PROFILE), route_unavailable(BOUNDED_PROFILE))
        self.assertEqual(StrictIsolatedAgentOSMcpTools.PROFILE, STRICT_PROFILE)

    def test_cli_versions_are_parsed_exactly(self):
        self.assertEqual(parse_cli_version('codex', 'codex-cli 0.153.4\n'), '0.153.4')
        self.assertEqual(parse_cli_version('claude-code', '2.1.280 (Claude Code)\n'), '2.1.280')
        for engine, text in (('codex', 'codex-cli 0.153.4-beta'), ('codex', ''), ('claude-code', '2.1.280'),
                             ('claude-code', 'error'), ('other', '1.0.0')):
            with self.subTest(engine=engine, text=text):
                self.assertIsNone(parse_cli_version(engine, text))


class StrictLaunchArguments(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        (self.folder / 'codex-home').mkdir()
        self.config = self.folder / 'agentos-mcp.json'
        self.config.write_text(json.dumps({'mcpServers': {'agentos': {'command': 'python3', 'args': ['-m', 'x']}}}))
        self.adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, codex_home=self.folder / 'codex-home')

    def test_codex_strict_replaces_the_read_only_sandbox_with_the_permissions_profile(self):
        trusted = self.adapter.command('codex', '/runtime/codex', 'prompt', self.config)
        strict = self.adapter.command('codex', '/runtime/codex', 'prompt', self.config, profile=STRICT_PROFILE)
        # With both present Codex applies --sandbox read-only, which can read the store.
        self.assertNotIn('--sandbox', strict)
        self.assertEqual(strict[3:13], ['-c', f'default_permissions="{CODEX_STRICT_PERMISSIONS}"', '-c', CODEX_STRICT_TABLE,
                                        '--disable', 'apps', '--disable', 'multi_agent', '-c', 'web_search="disabled"'])
        self.assertEqual(CODEX_STRICT_TABLE, 'permissions.agentos-strict-isolated={filesystem={":minimal"="read", '
                                             '":workspace_roots"={"."="read"}}, network={enabled=false}}')
        self.assertEqual(strict[:3] + strict[13:], trusted[:3] + trusted[5:], 'everything else is the trusted-local argv')
        self.assertEqual(trusted[3:5], ['--sandbox', 'read-only'], 'trusted-local is unchanged')

    def test_claude_strict_has_no_built_in_tools_and_allows_only_the_offered_bridge_tools(self):
        trusted = self.adapter.command('claude-code', '/runtime/claude', 'prompt', self.config, 'instructions')
        strict = self.adapter.command('claude-code', '/runtime/claude', 'prompt', self.config, 'instructions', profile=STRICT_PROFILE)
        self.assertEqual(strict[:len(trusted)], trusted)
        self.assertEqual(strict[len(trusted):], ['--tools', '', '--restricted', '--allowedTools',
                                                 'mcp__agentos__bounded_public_research,mcp__agentos__list_notes,'
                                                 'mcp__agentos__save_note,mcp__agentos__weather,mcp__agentos__web_search'])
        self.assertNotIn('--tools', trusted)

    def test_no_widening_for_parity_and_unknown_profiles_are_refused(self):
        for engine in ('codex', 'claude-code'):
            argv = self.adapter.command(engine, '/runtime/cli', 'prompt', self.config, profile=STRICT_PROFILE)
            joined = ' '.join(argv)
            for forbidden in ('danger-full-access', 'workspace-write', '--full-auto', 'dangerously', '--add-dir',
                              'bypass', '"write"', 'enabled=true', ':root'):
                with self.subTest(engine=engine, forbidden=forbidden):
                    self.assertNotIn(forbidden, joined)
            for profile in ('isolated-agentos-mcp', 'unknown', None):
                with self.subTest(engine=engine, profile=profile), self.assertRaises(ExecutionError):
                    self.adapter.command(engine, '/runtime/cli', 'prompt', self.config, profile=profile)
        env = self.adapter.environment('codex', '/runtime/codex', self.folder)
        self.assertEqual(set(env), {'HOME', 'PATH', 'LANG', 'PYTHONPATH', 'CODEX_HOME'}, 'environment unchanged')


class StrictExecuteRefusesUnqualifiedVersions(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        (self.folder / 'codex-home').mkdir()
        self.calls = []
        from unittest import mock
        patcher = mock.patch.object(sys, 'platform', 'darwin')
        patcher.start()
        self.addCleanup(patcher.stop)

    def _adapter(self, version_output):
        def runner(argv, **kwargs):
            self.calls.append(list(argv))
            return _Done(stdout=version_output) if argv[1:] == ['--version'] else _codex_answer()
        return BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=runner,
                                       runtime_root=self.folder / 'turns', codex_home=self.folder / 'codex-home')

    def test_a_qualified_version_runs_with_the_strict_argv(self):
        result = self._adapter(f'codex-cli {CODEX_VERSION}').execute(
            'codex', 'hello', StrictIsolatedAgentOSMcpTools(_Caps(self.folder), qualified_version=CODEX_VERSION))
        self.assertEqual(result.content, 'answer')
        self.assertEqual(self.calls[0], ['/runtime/codex', '--version'])
        self.assertIn(f'default_permissions="{CODEX_STRICT_PERMISSIONS}"', self.calls[1])
        self.assertNotIn('--sandbox', self.calls[1])

    def test_an_upgraded_unqualified_or_unknown_version_is_refused_without_fallback(self):
        for output, qualified in ((f'codex-cli {CODEX_VERSION}', None), (f'codex-cli {CODEX_VERSION}', '0.1.0'),
                                  ('codex-cli 9.9.9', '9.9.9'), ('garbled', CODEX_VERSION)):
            self.calls.clear()
            with self.subTest(output=output, qualified=qualified), self.assertRaises(ExecutionError) as caught:
                self._adapter(output).execute('codex', 'hello',
                                              StrictIsolatedAgentOSMcpTools(_Caps(self.folder), qualified_version=qualified))
            self.assertEqual(caught.exception.failure_class, 'isolation-unqualified')
            self.assertEqual(self.calls, [['/runtime/codex', '--version']], 'no CLI turn is started at all')

    def test_an_untested_platform_is_refused_even_with_a_matching_record(self):
        """A data folder moved from the qualified Mac to another OS (review P1)."""
        from unittest import mock
        with mock.patch.object(sys, 'platform', 'linux'), self.assertRaises(ExecutionError) as caught:
            self._adapter(f'codex-cli {CODEX_VERSION}').execute(
                'codex', 'hello', StrictIsolatedAgentOSMcpTools(_Caps(self.folder), qualified_version=CODEX_VERSION))
        self.assertEqual(caught.exception.failure_class, 'isolation-unqualified')
        self.assertEqual(self.calls, [], 'no CLI process is started at all')

    def test_trusted_local_does_not_check_versions(self):
        result = self._adapter('garbled').execute('codex', 'hello', AgentOSMcpTools(_Caps(self.folder)))
        self.assertEqual(result.content, 'answer')
        self.assertEqual(len(self.calls), 1)
        self.assertIn('--sandbox', self.calls[0])


class StrictQualificationLogic(unittest.TestCase):
    """``qualify_strict`` with a scripted runner in place of the CLI."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.store = self.folder / 'store'
        self.store.mkdir()
        (self.folder / 'codex-home').mkdir()
        self.calls = []
        # The logic under test is platform-independent; CI runs on Linux.
        from unittest import mock
        patcher = mock.patch.object(sys, 'platform', 'darwin')
        patcher.start()
        self.addCleanup(patcher.stop)

    def _qualify(self, engine='codex', version=None, readable=()):
        version = version or (f'codex-cli {CODEX_VERSION}' if engine == 'codex' else f'{CLAUDE_VERSION} (Claude Code)')

        def runner(argv, **kwargs):
            self.calls.append((list(argv), dict(kwargs['env'])))
            if argv[1:] == ['--version']:
                return _Done(stdout=version)
            target = Path(argv[-1])
            turn = Path(kwargs['cwd'])
            return _Done(returncode=0 if target == turn or target in readable else 1)
        adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=runner,
                                          runtime_root=self.folder / 'turns', codex_home=self.folder / 'codex-home')
        return adapter.qualify_strict(engine, protected=[self.store])

    def test_codex_qualifies_when_its_sandbox_denies_store_home_and_login_profile(self):
        result = self._qualify()
        self.assertTrue(result['qualified'], result)
        self.assertEqual(result['version'], CODEX_VERSION)
        self.assertEqual([check['check'] for check in result['checks']],
                         ['tested-platform', 'tested-version', 'turn-directory-readable', 'protected-directory-denied',
                          'protected-directory-denied', 'protected-directory-denied'])
        targets = [argv[-1] for argv, _ in self.calls if 'sandbox' in argv]
        self.assertEqual(targets[1:], [str(Path.home()), str(self.folder / 'codex-home'), str(self.store)])
        for argv, env in ((argv, env) for argv, env in self.calls if 'sandbox' in argv):
            self.assertEqual(argv[2:9], ['-C', argv[3], '-c', CODEX_STRICT_TABLE, '-P', CODEX_STRICT_PERMISSIONS, '--'])
            self.assertEqual(argv[9], '/bin/ls', 'a listing only; output is discarded')
            self.assertNotEqual(env['CODEX_HOME'], str(self.folder / 'codex-home'), "the owner's Codex config is not loaded")
        self.assertNotIn('content', json.dumps(result))

    def test_any_readable_protected_directory_fails_qualification(self):
        for readable in ((self.store,), (Path.home(),), (self.folder / 'codex-home',)):
            with self.subTest(readable=readable):
                result = self._qualify(readable=readable)
                self.assertFalse(result['qualified'])
                self.assertEqual(result['reason'], 'protected-directory-denied')

    def test_an_untested_version_fails_before_any_sandbox_probe(self):
        self.calls.clear()
        result = self._qualify(version='codex-cli 9.9.9')
        self.assertFalse(result['qualified'])
        self.assertEqual(result['reason'], 'tested-version')
        self.assertFalse([argv for argv, _ in self.calls if 'sandbox' in argv])

    def test_a_broken_runner_is_not_mistaken_for_denial(self):
        """Every probe failing (for example no sandbox) fails the turn-dir control."""
        def runner(argv, **kwargs):
            return _Done(stdout=f'codex-cli {CODEX_VERSION}') if argv[1:] == ['--version'] else _Done(returncode=1)
        adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=runner,
                                          runtime_root=self.folder / 'turns', codex_home=self.folder / 'codex-home')
        result = adapter.qualify_strict('codex', protected=[self.store])
        self.assertFalse(result['qualified'])
        self.assertIn('turn-directory-readable', result['reason'])

    def test_an_untested_platform_fails_closed_before_running_anything(self):
        from unittest import mock
        with mock.patch.object(sys, 'platform', 'linux'):
            result = self._qualify()
        self.assertFalse(result['qualified'])
        self.assertEqual(result['reason'], 'tested-platform')
        self.assertEqual(self.calls, [])

    def test_claude_code_qualification_is_its_version_pin(self):
        self.assertTrue(self._qualify('claude-code')['qualified'])
        self.assertFalse(self._qualify('claude-code', version='2.2.0 (Claude Code)')['qualified'])
        self.assertFalse(BoundedExecutionAdapter(finder=lambda name: None).qualify_strict('codex')['qualified'])
        self.assertFalse(BoundedExecutionAdapter().qualify_strict('other')['qualified'])


class _Engine:
    """A scripted subscription adapter recording what the service asks of it."""

    def __init__(self, qualification):
        self.qualification, self.facades, self.qualified = qualification, [], []

    def login_status(self, engine_id, binary=None):
        return {'state': 'signed-in'}

    def qualify_strict(self, engine_id, binary=None, protected=()):
        self.qualified.append((engine_id, [str(path) for path in protected]))
        return dict(self.qualification)

    def execute(self, engine, prompt, tools, **kwargs):
        self.facades.append(tools)
        if getattr(tools, 'PROFILE', None) == STRICT_PROFILE and tools.qualified_version != CODEX_VERSION:
            raise ExecutionError('refused', failure_class='isolation-unqualified')
        return ExecutionResult('answer', engine, 0, {})


PASS = {'qualified': True, 'version': CODEX_VERSION, 'reason': '', 'profile': STRICT_PROFILE,
        'checks': [{'check': 'tested-version', 'passed': True}]}
FAIL = {'qualified': False, 'version': CODEX_VERSION, 'reason': 'protected-directory-denied', 'checks': []}


class OwnerChoosesTheProfile(unittest.TestCase):
    def _service(self, qualification):
        from personal_agent.quickstart_service import AgentService
        from personal_agent.subscription_engines import SubscriptionEngines
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.engine = _Engine(qualification)
        service = AgentService(self.store, subscription_engines=SubscriptionEngines(finder=lambda c: '/runtime/' + c, clock=lambda: 1),
                               execution_adapter=self.engine)
        service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        return service

    def _turn(self, service):
        self.store.enqueue('hello', f'k{len(self.store.jobs())}')
        self.assertTrue(service.run_one())
        job_id = service.task_progress()['tasks'][0]['id']
        return self.store.turn_provenance(job_id)

    def test_default_is_trusted_local_and_labelled(self):
        service = self._service(PASS)
        status = service.settings()['subscription_execution']
        self.assertEqual((status['profile'], status['trust'], status['limitation']),
                         ('trusted-local', 'trusted-local', TRUSTED_LOCAL_LIMITATION))
        record = self._turn(service)
        self.assertEqual((record['capability_profile'], record['capability_trust']), ('trusted-local', 'trusted-local'))
        self.assertIs(type(self.engine.facades[-1]), AgentOSMcpTools)
        self.assertEqual(self.engine.qualified, [], 'nothing is qualified or switched automatically')

    def test_a_passing_qualification_selects_strict_and_every_surface_says_so(self):
        service = self._service(PASS)
        result = service.select_subscription_isolation({'profile': 'strict-isolated'})
        self.assertEqual(result['profile'], 'strict-isolated')
        self.assertEqual(self.engine.qualified, [('codex', [str(self.store.root)])], 'the real store path is probed')
        status = service.settings()['subscription_execution']
        self.assertEqual((status['profile'], status['trust']), ('strict-isolated', 'strict-isolated'))
        self.assertEqual(status['qualified']['codex']['version'], CODEX_VERSION)
        record = self._turn(service)
        self.assertEqual((record['capability_profile'], record['capability_trust'], record['status']),
                         ('strict-isolated', 'strict-isolated', 'answered'))
        self.assertEqual(record['capability_limitation'], CLI_PROFILES[STRICT_PROFILE]['limitation'])
        facade = self.engine.facades[-1]
        self.assertIsInstance(facade, StrictIsolatedAgentOSMcpTools)
        self.assertEqual(facade.qualified_version, CODEX_VERSION)

    def test_a_failed_qualification_keeps_the_previous_profile(self):
        service = self._service(FAIL)
        with self.assertRaisesRegex(ValueError, 'trusted-local'):
            service.select_subscription_isolation({'profile': 'strict-isolated'})
        self.assertEqual(service.settings()['subscription_execution']['trust'], 'trusted-local')
        # Previously strict: a failed requalification keeps strict and its record.
        self.engine.qualification = PASS
        service.select_subscription_isolation({'profile': 'strict-isolated'})
        self.engine.qualification = FAIL
        with self.assertRaisesRegex(ValueError, 'strict-isolated'):
            service.select_subscription_isolation({'profile': 'strict-isolated'})
        status = service.settings()['subscription_execution']
        self.assertEqual((status['trust'], status['qualified']['codex']['version']), ('strict-isolated', CODEX_VERSION))

    def test_no_silent_downgrade_when_the_cli_no_longer_qualifies(self):
        service = self._service(PASS)
        service.select_subscription_isolation({'profile': 'strict-isolated'})
        # The owner switches to another CLI that was never qualified.
        service.connect_subscription_engine({'engine': 'claude-code', 'officially_authenticated': True})
        record = self._turn(service)
        self.assertEqual((record['capability_trust'], record['status'], record['failure_class']),
                         ('strict-isolated', 'failed', 'isolation-unqualified'))
        self.assertTrue(all(isinstance(facade, StrictIsolatedAgentOSMcpTools) for facade in self.engine.facades),
                        'no trusted-local facade was ever used instead')

    def test_a_record_from_another_platform_qualifies_nothing(self):
        service = self._service(PASS)
        service.select_subscription_isolation({'profile': 'strict-isolated'})
        row = self.store.config('subscription_isolation')
        self.assertEqual(row['qualified']['codex']['platform'], sys.platform)
        row['qualified']['codex']['platform'] = 'another-os'
        self.store.put('subscription_isolation', row)
        record = self._turn(service)
        self.assertEqual((record['capability_trust'], record['status'], record['failure_class']),
                         ('strict-isolated', 'failed', 'isolation-unqualified'))
        self.assertIsNone(self.engine.facades[-1].qualified_version)

    def test_trusted_local_is_an_explicit_owner_choice_and_input_is_checked(self):
        service = self._service(PASS)
        service.select_subscription_isolation({'profile': 'strict-isolated'})
        service.select_subscription_isolation({'profile': 'trusted-local'})
        self.assertEqual(service.settings()['subscription_execution']['trust'], 'trusted-local')
        for body in (None, {}, {'profile': 'isolated-agentos-mcp'}, {'profile': 'full-access'}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                service.select_subscription_isolation(body)


class DoctorReportsTheSelectedProfile(unittest.TestCase):
    def test_selected_profile_and_recorded_trust_are_read_only(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        self.addCleanup(sys.path.remove, str(ROOT / 'scripts'))
        import agentos_doctor
        with tempfile.TemporaryDirectory() as folder:
            store = QuickStore(Path(folder) / 'data')
            self.assertEqual(agentos_doctor._selected_host_profile(store.root),
                             {'profile': 'trusted-local', 'qualified_versions': {}})
            store.put('subscription_isolation', {'profile': 'strict-isolated', 'qualified': {'codex': {'version': CODEX_VERSION}}})
            with store.db() as db:
                db.execute('INSERT INTO turn_provenance VALUES (?,?,?)',
                           ('j', json.dumps({'route': 'subscription', 'capability_profile': 'strict-isolated',
                                             'capability_trust': 'strict-isolated'}), 1))
            self.assertEqual(agentos_doctor._selected_host_profile(store.root),
                             {'profile': 'strict-isolated', 'qualified_versions': {'codex': CODEX_VERSION}})
            turn = agentos_doctor._recent_turns(store.root)[0]
            self.assertEqual((turn['capability_profile'], turn['capability_trust']), ('strict-isolated', 'strict-isolated'))


# -- Process-level qualification (opt-in) ------------------------------------

class _ScriptedModel:
    """A loopback fake model endpoint that plays a fixed tool-call script.

    ``responses`` speaks the OpenAI Responses SSE shape Codex reads;
    ``anthropic`` speaks the Messages SSE shape Claude Code reads.  It records
    every request so a test can read the tool results the CLI sent back.
    """

    def __init__(self, dialect, script):
        self.dialect, self.script, self.requests, self.turn = dialect, list(script), [], 0
        model = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(404)
                self.end_headers()

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get('content-length') or 0)) or b'{}')
                model.requests.append({'path': self.path, 'body': body,
                                       'authorization': 'authorization' in {k.lower() for k in self.headers.keys()}})
                events = model.events(self.path, body)
                if events is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header('content-type', 'text/event-stream')
                self.end_headers()
                for name, data in events:
                    self.wfile.write(f'event: {name}\ndata: {json.dumps(data)}\n\n'.encode())
                self.wfile.flush()

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def _next(self):
        step = self.script[self.turn] if self.turn < len(self.script) else {'message': 'done'}
        self.turn += 1
        return step

    def events(self, path, body):
        if self.dialect == 'responses':
            if not path.endswith('/responses'):
                return None
            step = self._next()
            if 'message' in step:
                item = {'type': 'message', 'role': 'assistant', 'id': f'm{self.turn}',
                        'content': [{'type': 'output_text', 'text': step['message']}]}
            else:
                item = {'type': 'function_call', 'id': f'f{self.turn}', 'call_id': f'c{self.turn}',
                        'name': step['name'], 'arguments': json.dumps(step['arguments'])}
                if step.get('namespace'):
                    item['namespace'] = step['namespace']
            usage = {'input_tokens': 1, 'input_tokens_details': None, 'output_tokens': 1,
                     'output_tokens_details': None, 'total_tokens': 2}
            return [('response.created', {'type': 'response.created', 'response': {'id': f'r{self.turn}'}}),
                    ('response.output_item.done', {'type': 'response.output_item.done', 'output_index': 0, 'item': item}),
                    ('response.completed', {'type': 'response.completed', 'response': {'id': f'r{self.turn}', 'usage': usage}})]
        if '/v1/messages' not in path or 'count_tokens' in path:
            return None
        # Side requests (for example a title) carry no tools: answer plainly.
        step = self._next() if body.get('tools') else {'message': 'ok'}
        if 'message' in step:
            block, delta, stop = {'type': 'text', 'text': ''}, {'type': 'text_delta', 'text': step['message']}, 'end_turn'
        else:
            block = {'type': 'tool_use', 'id': f'toolu_{self.turn}', 'name': step['tool'], 'input': {}}
            delta, stop = {'type': 'input_json_delta', 'partial_json': json.dumps(step['input'])}, 'tool_use'
        usage = {'input_tokens': 1, 'output_tokens': 1}
        return [('message_start', {'type': 'message_start', 'message': {
                    'id': f'msg_{self.turn}', 'type': 'message', 'role': 'assistant', 'model': body.get('model', 'fake'),
                    'content': [], 'stop_reason': None, 'stop_sequence': None, 'usage': usage}}),
                ('content_block_start', {'type': 'content_block_start', 'index': 0, 'content_block': block}),
                ('content_block_delta', {'type': 'content_block_delta', 'index': 0, 'delta': delta}),
                ('content_block_stop', {'type': 'content_block_stop', 'index': 0}),
                ('message_delta', {'type': 'message_delta', 'delta': {'stop_reason': stop, 'stop_sequence': None},
                                   'usage': {'output_tokens': 1}}),
                ('message_stop', {'type': 'message_stop'})]

    def tool_results(self):
        """Tool results the CLI returned to the model, in call order."""
        last = self.requests[-1]['body'] if self.requests else {}
        if self.dialect == 'responses':
            results = []
            for request in self.requests:
                for item in request['body'].get('input', []):
                    if item.get('type') == 'function_call_output':
                        results.append(json.dumps(item.get('output')))
            return list(dict.fromkeys(results))
        return [json.dumps(part.get('content')) for message in last.get('messages', [])
                for part in (message.get('content') if isinstance(message.get('content'), list) else [])
                if part.get('type') == 'tool_result']

    def offered_tools(self):
        for request in self.requests:
            if request['body'].get('tools'):
                return request['body']['tools']
        return []


_BRIDGE_STUB = '''
# Test-only (#616): stub the public network of the real AgentOS bridge process.
import sys
sys.path.insert(0, {src!r})
try:
    from personal_agent import local_tools as _lt
    _lt.LocalTools.search = lambda self, query: {{"tool": "web_search", "query": query, "retrieved_at": 1,
        "results": [{{"url": "https://example.com/stub", "title": "stub-search-616", "snippet": "s"}}],
        "sources": ["https://example.com/stub"]}}
    _lt.LocalTools.weather = lambda self, city, country="": {{"tool": "weather", "location": {{"name": "stub-weather-616"}},
        "retrieved_at": 1, "forecast": {{}}, "sources": ["https://open-meteo.com/"]}}
except Exception:
    pass
'''


def _installed(engine):
    binary = shutil.which({'codex': 'codex', 'claude-code': 'claude'}[engine])
    if not binary:
        return None, None
    done = subprocess.run([binary, '--version'], capture_output=True, text=True, timeout=30)
    return binary, parse_cli_version(engine, done.stdout)


@unittest.skipUnless(os.environ.get('AGENTOS_CLI_QUALIFICATION') == '1',
                     'opt-in process-level CLI qualification (set AGENTOS_CLI_QUALIFICATION=1)')
class ProcessLevelQualification(unittest.TestCase):
    """AX-S19 under the exact argv AgentOS uses; no live model or account."""

    def setUp(self):
        # Fake owner layout under the real home, like a default install
        # (store and engine turns under ~/), never inside the owner's data.
        tmp = tempfile.TemporaryDirectory(dir=Path.home(), prefix='.agentos-616-qualification-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = QuickStore(self.root / 'data')
        (self.store.root / 'FAKE-STORE-CANARY.txt').write_text('fake-store-canary-616\n')
        with self.store.db() as db:
            db.execute("INSERT INTO notes VALUES ('n1','fake-note-616',1)")
        self.job = self.store.enqueue('qualification', 'q-' + uuid.uuid4().hex)
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (self.job,))
        self.home_canary = Path.home() / f'.agentos-616-home-canary-{uuid.uuid4().hex}.txt'
        self.home_canary.write_text('fake-home-canary-616\n')
        self.addCleanup(self.home_canary.unlink)
        (self.root / 'codex-home').mkdir()

    def _stub_bridge_network(self, run_dir):
        site = subprocess.run([sys.executable, '-c', 'import site; print(site.getusersitepackages())'],
                              env={'HOME': str(run_dir), 'PATH': '/usr/bin:/bin'}, capture_output=True, text=True,
                              check=True).stdout.strip()
        Path(site).mkdir(parents=True, exist_ok=True)
        (Path(site) / 'usercustomize.py').write_text(_BRIDGE_STUB.format(src=str(ROOT / 'src')))

    def _run(self, engine, binary, model, profile, qualified_version=None):
        def runner(argv, **kwargs):
            argv, env = list(argv), dict(kwargs['env'])
            if argv[1:] == ['--version']:
                return subprocess.run(argv, **kwargs)
            self._stub_bridge_network(Path(kwargs['cwd']))
            if engine == 'codex':
                # Only the fake model endpoint is added; the AgentOS argv is untouched.
                at = argv.index('exec') + 1
                argv[at:at] = ['-c', 'model_provider="fake"', '-c', 'model="fake-model"', '-c',
                               f'model_providers.fake={{name="fake", base_url="http://127.0.0.1:{model.port}/v1", '
                               'wire_api="responses", env_key="AGENTOS_FAKE_MODEL_KEY", request_max_retries=0, stream_max_retries=0}']
                env['AGENTOS_FAKE_MODEL_KEY'] = 'fake'
            else:
                env.update(ANTHROPIC_BASE_URL=f'http://127.0.0.1:{model.port}', ANTHROPIC_API_KEY='fake-key',
                           CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1')
            self.argv = argv
            kwargs['env'] = env
            return subprocess.run(argv, **kwargs)
        adapter = BoundedExecutionAdapter(finder=lambda name: binary, runner=runner, runtime_root=self.root / 'engine-runs',
                                          codex_home=self.root / 'codex-home')
        caps = type('Caps', (), {'store': self.store, 'job_id': self.job, 'private_provenance': set()})()
        facade = StrictIsolatedAgentOSMcpTools.__new__(StrictIsolatedAgentOSMcpTools) if profile == STRICT_PROFILE \
            else AgentOSMcpTools.__new__(AgentOSMcpTools)
        facade.capabilities, facade.qualified_version = caps, qualified_version
        try:
            adapter.execute(engine, 'AgentOS isolation qualification probe', facade)
        finally:
            model.close()
        with self.store.db() as db:
            events = db.execute('SELECT tool, status FROM tool_events WHERE job_id=?', (self.job,)).fetchall()
        return adapter, model.tool_results(), [tuple(row) for row in events]

    def _codex_script(self):
        store_file, canary = self.store.root / 'FAKE-STORE-CANARY.txt', self.home_canary
        shell = lambda cmd: {'name': 'exec_command', 'arguments': {'cmd': cmd, 'login': False}}
        return [shell(f'cat {store_file}; ls {self.store.root / "private"}'),
                shell(f'cat {canary}'),
                shell('cat agentos-mcp.json'),
                {'name': 'web_search', 'namespace': 'mcp__agentos', 'arguments': {'query': 'public query'}},
                {'name': 'weather', 'namespace': 'mcp__agentos', 'arguments': {'city': 'Daejeon'}},
                {'name': 'list_notes', 'namespace': 'mcp__agentos', 'arguments': {}},
                {'message': 'qualification finished'}]

    def test_codex_strict_denies_store_and_home_and_keeps_the_bridge(self):
        binary, version = _installed('codex')
        if version not in CLI_PROFILES[STRICT_PROFILE]['runtimes']['codex']['tested_versions']:
            self.skipTest(f'codex {version} is not a tested version')
        model = _ScriptedModel('responses', self._codex_script())
        _, results, events = self._run('codex', binary, model, STRICT_PROFILE, version)
        store_read, home_read, turn_read, search, weather, notes = results[:6]
        self.assertNotIn('fake-store-canary-616', store_read)
        self.assertIn('Operation not permitted', store_read)
        self.assertNotIn('fake-home-canary-616', home_read)
        self.assertIn('Operation not permitted', home_read)
        self.assertIn('personal_agent.mcp_bridge', turn_read, 'the turn directory is readable')
        self.assertIn('stub-search-616', search)
        self.assertIn('stub-weather-616', weather)
        self.assertIn('fake-note-616', notes)
        self.assertEqual(events, [('web_search', 'succeeded'), ('weather', 'succeeded'), ('list_notes', 'succeeded')])
        names = {tool.get('name') for tool in model.offered_tools()}
        self.assertFalse(names & {'multi_agent_v1', 'web_search'}, 'sub-agents and hosted search are off')
        self.assertNotIn('--sandbox', self.argv)

    def test_codex_trusted_local_reads_the_store_as_its_label_says(self):
        binary, version = _installed('codex')
        if version != '0.153.4':
            self.skipTest(f'codex {version} is not the version the limitation was recorded on')
        model = _ScriptedModel('responses', self._codex_script())
        _, results, _ = self._run('codex', binary, model, BOUNDED_PROFILE)
        self.assertIn('--sandbox', self.argv)
        self.assertIn('fake-store-canary-616', results[0])
        self.assertIn('fake-home-canary-616', results[1])
        self.assertIn('outside AgentOS provenance', CLI_PROFILES[BOUNDED_PROFILE]['limitation'])

    def test_codex_in_product_qualification_uses_the_real_sandbox_runner(self):
        binary, version = _installed('codex')
        if version not in CLI_PROFILES[STRICT_PROFILE]['runtimes']['codex']['tested_versions']:
            self.skipTest(f'codex {version} is not a tested version')
        adapter = BoundedExecutionAdapter(finder=lambda name: binary, runtime_root=self.root / 'engine-runs',
                                          codex_home=self.root / 'codex-home')
        result = adapter.qualify_strict('codex', protected=[self.store.root])
        self.assertTrue(result['qualified'], result)
        # A store the platform baseline keeps readable (/tmp) fails closed.
        with tempfile.TemporaryDirectory(dir='/tmp', prefix='agentos-616-') as readable:
            self.assertFalse(adapter.qualify_strict('codex', protected=[Path(readable)])['qualified'])

    def _claude_script(self):
        return [{'tool': 'Read', 'input': {'file_path': str(self.store.root / 'FAKE-STORE-CANARY.txt')}},
                {'tool': 'Bash', 'input': {'command': f'cat {self.home_canary}'}},
                {'tool': 'mcp__agentos__web_search', 'input': {'query': 'public query'}},
                {'tool': 'mcp__agentos__weather', 'input': {'city': 'Daejeon'}},
                {'tool': 'mcp__agentos__list_notes', 'input': {}},
                {'message': 'qualification finished'}]

    def test_claude_strict_has_no_file_tools_and_keeps_the_bridge(self):
        binary, version = _installed('claude-code')
        if version not in CLI_PROFILES[STRICT_PROFILE]['runtimes']['claude-code']['tested_versions']:
            self.skipTest(f'claude {version} is not a tested version')
        model = _ScriptedModel('anthropic', self._claude_script())
        _, results, events = self._run('claude-code', binary, model, STRICT_PROFILE, version)
        read, shell, search, weather, notes = results[:5]
        for denied in (read, shell):
            self.assertIn('No such tool available', denied)
            self.assertNotIn('canary-616', denied)
        self.assertIn('stub-search-616', search)
        self.assertIn('stub-weather-616', weather)
        self.assertIn('fake-note-616', notes)
        self.assertEqual(events, [('web_search', 'succeeded'), ('weather', 'succeeded'), ('list_notes', 'succeeded')])
        self.assertEqual(sorted(tool['name'] for tool in model.offered_tools()),
                         sorted(f'mcp__agentos__{action}' for action in profile_actions(STRICT_PROFILE)),
                         'no built-in tool is offered at all')
        self.assertFalse(any(request['authorization'] for request in model.requests), 'no owner credential was sent')

    def test_claude_trusted_local_documents_its_permission_layer(self):
        """Observed, not endorsed: under -p the trusted-local argv denies the
        out-of-directory read by permission, and also every bridge call."""
        binary, version = _installed('claude-code')
        if version != '2.1.280':
            self.skipTest(f'claude {version} is not the version this was observed on')
        model = _ScriptedModel('anthropic', self._claude_script())
        _, results, events = self._run('claude-code', binary, model, BOUNDED_PROFILE)
        self.assertNotIn('canary-616', results[0] + results[1])
        self.assertIn("haven't granted", results[2], 'bridge tools are not pre-approved on trusted-local')
        self.assertEqual(events, [])


if __name__ == '__main__':
    unittest.main()

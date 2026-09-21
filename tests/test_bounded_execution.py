import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from personal_agent import bounded_execution
from personal_agent.bounded_execution import (
    AgentOSMcpTools,
    BoundedExecutionAdapter,
    ExecutionError,
    ReadOnlyAgentOSMcpTools,
)
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines


class _Capabilities:
    def __init__(self):
        self.calls=[]; self.store=type('Store',(),{'root':Path('/safe-owner-runtime')})(); self.job_id='fixture-job'
    def execute(self, name, arguments): self.calls.append((name, arguments)); return {'ok': True}


class BoundedExecutionTests(unittest.TestCase):
    def test_mcp_facade_exposes_only_agentos_allowlist(self):
        caps=_Capabilities(); tools=AgentOSMcpTools(caps)
        self.assertEqual([tool['name'] for tool in tools.definitions()], ['list_notes','save_note','web_search'])
        self.assertEqual(tools.call('web_search', {'query':'public weather'}), {'ok':True})
        with self.assertRaises(ExecutionError): tools.call('read_file', {'path':'/etc/passwd'})
        with self.assertRaises(ExecutionError): tools.call('save_note', {'content':''})
        self.assertEqual(caps.calls, [('web_search', {'query':'public weather'})])

    def test_adapter_uses_empty_turn_dir_fixed_env_and_no_shell(self):
        seen={}
        class Done:
            returncode=0
            stdout=json.dumps({'result':'bounded result'})
        def runner(argv, **kwargs):
            seen['argv'],seen['kwargs']=argv,kwargs
            return Done()
        with tempfile.TemporaryDirectory() as folder:
            adapter=BoundedExecutionAdapter(finder=lambda name:'/runtime/'+name, runner=runner, runtime_root=folder)
            result=adapter.execute('claude-code','hello',AgentOSMcpTools(_Capabilities()))
        self.assertEqual(result.content,'bounded result')
        self.assertEqual(seen['argv'][:2], ['/runtime/claude','-p'])
        self.assertTrue(seen['kwargs']['shell'] is False)
        self.assertEqual(set(seen['kwargs']['env']), {'HOME','PATH','LANG','PYTHONPATH'})
        self.assertNotIn('private', str(seen))

    def test_codex_uses_only_its_existing_profile_and_cli_directory(self):
        seen={}
        class Done:
            returncode=0
            stdout=json.dumps({'item':{'type':'agent_message','text':'bounded result'}})
        def runner(argv, **kwargs):
            seen['kwargs']=kwargs
            return Done()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);profile=root/'official-codex-profile';profile.mkdir()
            adapter=BoundedExecutionAdapter(finder=lambda _: '/opt/homebrew/bin/codex', runner=runner,
                                            runtime_root=root/'turns', codex_home=profile)
            result=adapter.execute('codex','hello',AgentOSMcpTools(_Capabilities()))
        self.assertEqual(result.content,'bounded result')
        env=seen['kwargs']['env']
        self.assertEqual(env['CODEX_HOME'],str(profile))
        self.assertTrue(Path(env['HOME']).name.startswith('turn-'))
        self.assertEqual(env['PATH'],'/opt/homebrew/bin:/usr/bin:/bin')
        self.assertNotIn('GITHUB_TOKEN',env)
        self.assertNotIn('OPENAI_API_KEY',env)
        self.assertIn('PYTHONPATH',env)

    def test_codex_command_references_the_generated_agentos_mcp_bridge(self):
        seen={}
        class Done:
            returncode=0
            stdout=json.dumps({'item':{'type':'agent_message','text':'bounded result'}})
        def runner(argv, **kwargs): seen['argv'],seen['kwargs']=argv,kwargs; return Done()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); profile=root/'profile'; profile.mkdir()
            adapter=BoundedExecutionAdapter(finder=lambda _: '/bin/codex', runner=runner, runtime_root=root/'turns', codex_home=profile)
            adapter.execute('codex','hello',AgentOSMcpTools(_Capabilities()))
        args=seen['argv']; self.assertIn('mcp_servers.agentos.command="'+os.sys.executable+'"',args)
        bridge=next(value for value in args if 'mcp_servers.agentos.args=' in value)
        self.assertIn('personal_agent.mcp_bridge',bridge)

    def test_stdio_mcp_bridge_executes_declared_tool_and_records_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            store=QuickStore(Path(folder)/'data')
            with store.db() as db: db.execute('INSERT INTO notes VALUES (?,?,?)',('n1','Bridge note',1))
            process=subprocess.Popen([os.sys.executable,'-m','personal_agent.mcp_bridge','--data',str(store.root),'--job','bridge-job'],
                                     stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
            try:
                process.stdin.write(json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize'})+'\n')
                process.stdin.write(json.dumps({'jsonrpc':'2.0','id':2,'method':'tools/list'})+'\n')
                process.stdin.write(json.dumps({'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'list_notes','arguments':{}}})+'\n'); process.stdin.flush()
                replies=[json.loads(process.stdout.readline()) for _ in range(3)]
            finally:
                process.terminate(); process.wait(timeout=3); process.stdin.close(); process.stdout.close()
            self.assertEqual(replies[-1]['result']['content'][0]['type'],'text')
            self.assertIn('Bridge note',replies[-1]['result']['content'][0]['text'])
            with store.db() as db: self.assertEqual(db.execute("SELECT status FROM tool_events WHERE job_id='bridge-job' AND tool='list_notes'").fetchone()[0],'succeeded')

    def test_default_engine_run_directory_is_owner_local_and_private(self):
        adapter=BoundedExecutionAdapter()
        self.assertEqual(adapter.runtime_root, Path.home()/'.local/share/agentos/engine-runs')

    def test_codex_uses_last_agent_message_not_terminal_usage_event(self):
        raw='\n'.join([json.dumps({'type':'thread.started'}),json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'final answer'}}),json.dumps({'type':'turn.completed','usage':{'input_tokens':1}})])
        self.assertEqual(BoundedExecutionAdapter._content('codex',raw),'final answer')

    def test_rejects_unstructured_or_failed_engine_output(self):
        class Failed: returncode=1; stdout='{}'
        with tempfile.TemporaryDirectory() as folder:
            adapter=BoundedExecutionAdapter(finder=lambda _: '/runtime/codex', runner=lambda *a,**k:Failed(), runtime_root=folder)
            with self.assertRaises(ExecutionError): adapter.execute('codex','hello',AgentOSMcpTools(_Capabilities()))


class SubscriptionServiceTests(unittest.TestCase):
    def test_selected_subscription_engine_runs_through_bounded_adapter(self):
        class Adapter:
            def __init__(self): self.call=None
            def execute(self, engine, prompt, tools):
                self.call=(engine,prompt,[t['name'] for t in tools.definitions()])
                from personal_agent.bounded_execution import ExecutionResult
                return ExecutionResult('engine answer',engine,0)
        with tempfile.TemporaryDirectory() as folder:
            store=QuickStore(Path(folder)/'data')
            engines=SubscriptionEngines(finder=lambda _: '/runtime/codex', clock=lambda:1)
            adapter=Adapter(); service=AgentService(store, subscription_engines=engines, execution_adapter=adapter)
            service.connect_subscription_engine({'engine':'codex','officially_authenticated':True})
            job=store.enqueue('do work','subscription-test')
            self.assertTrue(service.run_one())
            self.assertEqual(adapter.call[0], 'codex')
            self.assertEqual(adapter.call[2], ['list_notes','save_note','web_search'])
            self.assertEqual(store.job(job)['response'], 'engine answer')

    def test_summary_regression_sends_approved_notes_to_subscription_engine(self):
        class Adapter:
            def __init__(self): self.prompt=''; self.tool_result=None
            def execute(self, engine, prompt, tools):
                self.prompt=prompt
                self.tool_result=tools.call('list_notes',{})
                from personal_agent.bounded_execution import ExecutionResult
                return ExecutionResult('summary from declared tool',engine,0)
        with tempfile.TemporaryDirectory() as folder:
            store=QuickStore(Path(folder)/'data')
            with store.db() as db: db.execute('INSERT INTO notes VALUES (?,?,?)',('note-1','Approved Aurora decision',1))
            engines=SubscriptionEngines(finder=lambda _: '/runtime/codex', clock=lambda:1); adapter=Adapter()
            service=AgentService(store, subscription_engines=engines, execution_adapter=adapter)
            service.connect_subscription_engine({'engine':'codex','officially_authenticated':True})
            job=store.enqueue('/summarize','summary-regression',channel='telegram:fixture',chat_id=7)
            self.assertTrue(service.run_one())
            self.assertIn('Approved Aurora decision',adapter.prompt)
            self.assertNotEqual(adapter.prompt,'/summarize')
            self.assertEqual(adapter.tool_result['notes'][0]['content'],'Approved Aurora decision')
            self.assertEqual(store.job(job)['response'],'summary from declared tool')
            with store.db() as db: events=[dict(row) for row in db.execute('SELECT tool,status FROM tool_events WHERE job_id=?',(job,))]
            self.assertIn({'tool':'subscription_engine','status':'succeeded'},events)

    def test_subscription_summary_rejection_timeout_and_malformed_output_are_failed_once(self):
        class Adapter:
            def __init__(self, error): self.error,self.calls=error,0
            def execute(self, *args): self.calls+=1; raise self.error
        for error in (ExecutionError('engine rejected request'), ExecutionError('engine timed out'), ExecutionError('engine returned malformed output')):
            with self.subTest(error=str(error)), tempfile.TemporaryDirectory() as folder:
                store=QuickStore(Path(folder)/'data')
                with store.db() as db: db.execute('INSERT INTO notes VALUES (?,?,?)',('note-1','Approved note',1))
                engines=SubscriptionEngines(finder=lambda _: '/runtime/codex', clock=lambda:1); adapter=Adapter(error)
                service=AgentService(store, subscription_engines=engines, execution_adapter=adapter)
                service.connect_subscription_engine({'engine':'codex','officially_authenticated':True})
                ident=store.enqueue('/summarize','failure-'+str(error),channel='telegram:fixture',chat_id=7)
                self.assertTrue(service.run_one()); self.assertEqual(store.job(ident)['status'],'failed'); self.assertEqual(adapter.calls,1)
                self.assertFalse(service.run_one())
                with store.db() as db: events=[dict(row) for row in db.execute('SELECT tool,status FROM tool_events WHERE job_id=?',(ident,))]
                self.assertIn({'tool':'subscription_engine','status':'failed'},events)

    def test_duplicate_summary_request_key_reuses_one_terminal_job_after_restart(self):
        class Adapter:
            def __init__(self): self.calls=0
            def execute(self, engine, prompt, tools):
                self.calls+=1
                from personal_agent.bounded_execution import ExecutionResult
                return ExecutionResult('one result',engine,0)
        with tempfile.TemporaryDirectory() as folder:
            store=QuickStore(Path(folder)/'data')
            with store.db() as db: db.execute('INSERT INTO notes VALUES (?,?,?)',('note-1','Approved note',1))
            engines=SubscriptionEngines(finder=lambda _: '/runtime/codex', clock=lambda:1); adapter=Adapter()
            service=AgentService(store, subscription_engines=engines, execution_adapter=adapter)
            service.connect_subscription_engine({'engine':'codex','officially_authenticated':True})
            first=store.enqueue('/summarize','same-update',channel='telegram:fixture',chat_id=7)
            self.assertEqual(first,store.enqueue('/summarize','same-update',channel='telegram:fixture',chat_id=7))
            self.assertTrue(service.run_one())
            restarted=AgentService(QuickStore(store.root), subscription_engines=engines, execution_adapter=adapter)
            self.assertFalse(restarted.run_one()); self.assertEqual(adapter.calls,1)


    def test_subscription_preflights_explicit_public_lookup_and_records_sources(self):
        class Network:
            def __init__(self): self.calls=[]
            def execute(self, plan):
                self.calls.append(plan)
                return {'tool':'web_search','query':plan['query'],'retrieved_at':1,
                        'results':[{'title':'Public result','url':'https://example.test/result','snippet':'public snippet'}],
                        'sources':['https://example.test/result']}
        class Adapter:
            def __init__(self): self.prompt=''
            def execute(self, engine, prompt, tools):
                self.prompt=prompt
                from personal_agent.bounded_execution import ExecutionResult
                return ExecutionResult('source-backed answer',engine,0)
        with tempfile.TemporaryDirectory() as folder:
            store=QuickStore(Path(folder)/'data')
            engines=SubscriptionEngines(finder=lambda _: '/runtime/codex', clock=lambda:1)
            adapter=Adapter(); service=AgentService(store, subscription_engines=engines, execution_adapter=adapter)
            network=Network(); service.local_tools=network
            service.connect_subscription_engine({'engine':'codex','officially_authenticated':True})
            job=store.enqueue('성남시 날씨를 찾아줘','subscription-preflight')
            self.assertTrue(service.run_one())
            self.assertEqual(network.calls,[{'tool':'web_search','query':'성남시 날씨'}])
            self.assertIn('https://example.test/result',adapter.prompt)
            with store.db() as db:
                events=[dict(row) for row in db.execute('SELECT tool,status,detail FROM tool_events WHERE job_id=?',(job,))]
            event=next(row for row in events if row['tool']=='web_search' and row['status']=='succeeded')
            self.assertIn('https://example.test/result',event['detail'])

    def test_subscription_lookup_never_derives_private_or_ordinary_prose(self):
        from personal_agent.quickstart_service import subscription_public_lookup_query
        self.assertEqual(subscription_public_lookup_query('/search AgentOS release'), 'AgentOS release')
        self.assertIsNone(subscription_public_lookup_query('/search my api token is abc'))
        self.assertIsNone(subscription_public_lookup_query('내 메모를 정리해줘'))


class BoundedExecutionPreservedBoundaryTests(unittest.TestCase):
    """Execution evidence for each boundary REUSE-R4 must preserve.

    Recorded during the R4 adapter-reuse review (#433).  Neither
    `openai-codex` nor `claude-agent-sdk` can express these controls: both
    spawn the engine with `os.environ.copy()` and allow callers only to *add*
    variables, neither enforces a per-turn wall-clock kill, and the Codex SDK
    speaks the persistent `app-server` protocol rather than the one-shot
    `exec` this adapter depends on.  These tests pin the behaviour the
    adapters keep instead.
    """

    @staticmethod
    def _adapter(folder, runner, finder=None):
        return BoundedExecutionAdapter(
            finder=finder if finder is not None else (lambda name: '/runtime/' + name),
            runner=runner,
            runtime_root=folder,
        )

    @staticmethod
    def _ok(stdout):
        class Done:
            returncode = 0
        Done.stdout = stdout
        return lambda *args, **kwargs: Done()

    # --- bounded environment -------------------------------------------------
    def test_engine_environment_is_a_closed_allowlist_not_the_host_environment(self):
        seen = {}

        def runner(argv, **kwargs):
            seen['env'] = kwargs['env']
            class Done:
                returncode = 0
                stdout = json.dumps({'result': 'ok'})
            return Done()

        os.environ['AGENTOS_R4_FAKE_SECRET'] = 'must-not-be-inherited'
        try:
            with tempfile.TemporaryDirectory() as folder:
                self._adapter(folder, runner).execute(
                    'claude-code', 'hello', AgentOSMcpTools(_Capabilities()))
        finally:
            os.environ.pop('AGENTOS_R4_FAKE_SECRET', None)
        # A closed allowlist, not an inherited-and-extended environment.
        self.assertEqual(set(seen['env']), {'HOME', 'PATH', 'LANG', 'PYTHONPATH'})
        self.assertNotIn('AGENTOS_R4_FAKE_SECRET', seen['env'])
        self.assertEqual(seen['env']['PATH'], '/usr/bin:/bin')

    # --- empty per-request workspace ----------------------------------------
    def test_each_turn_gets_a_fresh_workspace_holding_only_the_bridge_config(self):
        observed = []

        def runner(argv, **kwargs):
            run_dir = Path(kwargs['cwd'])
            observed.append((run_dir, sorted(entry.name for entry in run_dir.iterdir())))
            class Done:
                returncode = 0
                stdout = json.dumps({'result': 'ok'})
            return Done()

        with tempfile.TemporaryDirectory() as folder:
            adapter = self._adapter(folder, runner)
            adapter.execute('claude-code', 'first', AgentOSMcpTools(_Capabilities()))
            adapter.execute('claude-code', 'second', AgentOSMcpTools(_Capabilities()))
            first, second = observed
            self.assertEqual(first[1], ['agentos-mcp.json'])
            self.assertEqual(second[1], ['agentos-mcp.json'])
            self.assertNotEqual(first[0], second[0], 'each turn needs its own workspace')
            # The workspace is removed when the turn ends; nothing survives it.
            self.assertFalse(first[0].exists())
            self.assertFalse(second[0].exists())
            self.assertEqual(sorted(Path(folder).iterdir()), [])

    def test_runtime_root_is_created_private_to_the_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'engine-runs'
            adapter = self._adapter(root, self._ok(json.dumps({'result': 'ok'})))
            adapter.execute('claude-code', 'hello', AgentOSMcpTools(_Capabilities()))
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)

    # --- sandbox flag stays an AgentOS decision ------------------------------
    def test_agentos_always_sets_the_sandbox_and_strict_mcp_flags_itself(self):
        seen = {}

        def runner(argv, **kwargs):
            seen['argv'] = argv
            class Done:
                returncode = 0
                stdout = json.dumps({'item': {'type': 'agent_message', 'text': 'ok'}})
            return Done()

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            profile = root / 'profile'
            profile.mkdir()
            BoundedExecutionAdapter(finder=lambda _: '/bin/codex', runner=runner,
                                    runtime_root=root / 'turns',
                                    codex_home=profile).execute(
                'codex', 'hello', AgentOSMcpTools(_Capabilities()))
        argv = seen['argv']
        self.assertEqual(argv[1:6], ['exec', '--json', '--sandbox', 'read-only',
                                     '--skip-git-repo-check'])
        # No generic argv/approval hook: the caller cannot relax these.
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', argv)
        self.assertNotIn('workspace-write', argv)
        self.assertNotIn('full-access', argv)

    def test_claude_code_invocation_pins_strict_mcp_config(self):
        seen = {}

        def runner(argv, **kwargs):
            seen['argv'] = argv
            class Done:
                returncode = 0
                stdout = json.dumps({'result': 'ok'})
            return Done()

        with tempfile.TemporaryDirectory() as folder:
            self._adapter(folder, runner).execute(
                'claude-code', 'hello', AgentOSMcpTools(_Capabilities()))
        self.assertIn('--strict-mcp-config', seen['argv'])
        self.assertIn('--output-format', seen['argv'])

    # --- timeout and output limits ------------------------------------------
    def test_every_invocation_carries_the_declared_timeout_and_no_shell(self):
        seen = {}

        def runner(argv, **kwargs):
            seen['kwargs'] = kwargs
            class Done:
                returncode = 0
                stdout = json.dumps({'result': 'ok'})
            return Done()

        with tempfile.TemporaryDirectory() as folder:
            self._adapter(folder, runner).execute(
                'claude-code', 'hello', AgentOSMcpTools(_Capabilities()))
        self.assertEqual(seen['kwargs']['timeout'], bounded_execution.MAX_TIMEOUT_SECONDS)
        self.assertIs(seen['kwargs']['shell'], False)
        self.assertEqual(seen['kwargs']['stdin'], subprocess.DEVNULL)
        self.assertIs(seen['kwargs']['capture_output'], True)

    def test_engine_timeout_fails_closed(self):
        def runner(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, bounded_execution.MAX_TIMEOUT_SECONDS)

        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ExecutionError):
                self._adapter(folder, runner).execute(
                    'codex', 'hello', AgentOSMcpTools(_Capabilities()))

    def test_oversized_engine_output_is_refused(self):
        # Well-formed JSONL carrying a valid final message: only the size
        # ceiling can reject it, so the assertion cannot pass by accident.
        oversized = json.dumps({'item': {'type': 'agent_message',
                                         'text': 'x' * bounded_execution.MAX_OUTPUT_BYTES}})
        self.assertGreater(len(oversized.encode()), bounded_execution.MAX_OUTPUT_BYTES)
        self.assertEqual(
            BoundedExecutionAdapter._content(
                'codex', json.dumps({'item': {'type': 'agent_message', 'text': 'small'}})),
            'small', 'the same shape must succeed below the ceiling')
        with self.assertRaises(ExecutionError):
            BoundedExecutionAdapter._content('codex', oversized)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ExecutionError):
                self._adapter(folder, self._ok(oversized)).execute(
                    'codex', 'hello', AgentOSMcpTools(_Capabilities()))

    def test_accepted_result_is_truncated_to_the_declared_ceiling(self):
        long_answer = 'y' * 40_000
        raw = json.dumps({'item': {'type': 'agent_message', 'text': long_answer}})
        self.assertEqual(len(BoundedExecutionAdapter._content('codex', raw)), 24_000)

    def test_oversized_or_empty_prompt_is_refused_before_any_spawn(self):
        calls = []

        def runner(argv, **kwargs):
            calls.append(argv)
            raise AssertionError('must not spawn')

        with tempfile.TemporaryDirectory() as folder:
            adapter = self._adapter(folder, runner)
            for prompt in ('', '   ', 'z' * (bounded_execution.MAX_PROMPT_BYTES + 1), None):
                with self.subTest(prompt=type(prompt).__name__):
                    with self.assertRaises(ExecutionError):
                        adapter.execute('codex', prompt, AgentOSMcpTools(_Capabilities()))
        self.assertEqual(calls, [])

    # --- malformed stream / non-zero exit / missing binary -------------------
    def test_malformed_event_stream_is_refused_even_on_a_zero_exit(self):
        for raw in ('not json at all', '{"item": ', '', '   \n  \n'):
            with self.subTest(raw=raw[:12]):
                with tempfile.TemporaryDirectory() as folder:
                    with self.assertRaises(ExecutionError):
                        self._adapter(folder, self._ok(raw)).execute(
                            'codex', 'hello', AgentOSMcpTools(_Capabilities()))

    def test_event_stream_without_a_final_agent_message_is_refused(self):
        raw = '\n'.join([
            json.dumps({'type': 'thread.started'}),
            json.dumps({'type': 'item.completed',
                        'item': {'type': 'reasoning', 'text': 'hidden thinking'}}),
            json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 1}}),
        ])
        with self.assertRaises(ExecutionError):
            BoundedExecutionAdapter._content('codex', raw)

    def test_non_zero_exit_is_refused_even_with_a_well_formed_answer(self):
        class Failed:
            returncode = 3
            stdout = json.dumps({'item': {'type': 'agent_message', 'text': 'looks fine'}})

        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ExecutionError):
                self._adapter(folder, lambda *a, **k: Failed()).execute(
                    'codex', 'hello', AgentOSMcpTools(_Capabilities()))

    def test_missing_engine_binary_is_refused_before_any_spawn(self):
        calls = []

        def runner(argv, **kwargs):
            calls.append(argv)
            raise AssertionError('must not spawn')

        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ExecutionError):
                self._adapter(folder, runner, finder=lambda _: None).execute(
                    'codex', 'hello', AgentOSMcpTools(_Capabilities()))
        self.assertEqual(calls, [])

    def test_unsupported_engine_is_refused_before_any_spawn(self):
        calls = []

        def runner(argv, **kwargs):
            calls.append(argv)
            raise AssertionError('must not spawn')

        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ExecutionError):
                self._adapter(folder, runner).execute(
                    'gemini-cli', 'hello', AgentOSMcpTools(_Capabilities()))
        self.assertEqual(calls, [])

    def test_os_error_while_starting_the_engine_fails_closed(self):
        def runner(argv, **kwargs):
            raise OSError('exec format error')

        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ExecutionError):
                self._adapter(folder, runner).execute(
                    'codex', 'hello', AgentOSMcpTools(_Capabilities()))

    # --- Grant mediation -----------------------------------------------------
    def test_read_only_facade_exposes_only_the_approved_read_tool(self):
        caps = _Capabilities()
        tools = ReadOnlyAgentOSMcpTools(caps)
        self.assertEqual([tool['name'] for tool in tools.definitions()], ['list_notes'])
        self.assertEqual(tools.call('list_notes', {}), {'ok': True})
        for name, arguments in (('save_note', {'content': 'x'}),
                                ('web_search', {'query': 'x'}),
                                ('list_notes', {'unexpected': 1}),
                                ('read_file', {'path': '/etc/passwd'})):
            with self.subTest(tool=name):
                with self.assertRaises(ExecutionError):
                    tools.call(name, arguments)
        # Exactly one mediated call reached AgentOS capabilities.
        self.assertEqual(caps.calls, [('list_notes', {})])

    def test_tool_definitions_cannot_be_mutated_by_the_engine_facade(self):
        caps = _Capabilities()
        tools = AgentOSMcpTools(caps)
        definitions = tools.definitions()
        definitions.append({'name': 'run_shell'})
        definitions[0]['name'] = 'tampered'
        self.assertEqual([tool['name'] for tool in tools.definitions()],
                         ['list_notes', 'save_note', 'web_search'])

    def test_non_object_tool_arguments_are_refused(self):
        tools = AgentOSMcpTools(_Capabilities())
        for arguments in ('content', ['content'], None, 7):
            with self.subTest(arguments=type(arguments).__name__):
                with self.assertRaises(ExecutionError):
                    tools.call('save_note', arguments)

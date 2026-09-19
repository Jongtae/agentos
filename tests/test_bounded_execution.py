import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from personal_agent.bounded_execution import AgentOSMcpTools, BoundedExecutionAdapter, ExecutionError
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
            adapter=BoundedExecutionAdapter(finder=lambda name:'/runtime/'+name, runner=runner, runtime_root=folder,
                                            claude_config_dir=Path(folder)/'claude-profile')
            (Path(folder)/'claude-profile').mkdir()
            result=adapter.execute('claude-code','hello',AgentOSMcpTools(_Capabilities()))
        self.assertEqual(result.content,'bounded result')
        self.assertEqual(seen['argv'][:2], ['/runtime/claude','-p'])
        self.assertTrue(seen['kwargs']['shell'] is False)
        self.assertEqual(set(seen['kwargs']['env']), {'HOME','PATH','LANG','PYTHONPATH','CLAUDE_CONFIG_DIR'})
        self.assertEqual(seen['kwargs']['env']['CLAUDE_CONFIG_DIR'], str(Path(folder)/'claude-profile'))
        self.assertNotIn('API_KEY', str(seen))
        self.assertNotIn('TOKEN', str(seen))

    def test_claude_requires_an_existing_owner_profile_without_copying_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            adapter=BoundedExecutionAdapter(finder=lambda _: '/runtime/claude', runtime_root=folder,
                                            claude_config_dir=Path(folder)/'missing-profile')
            with self.assertRaisesRegex(ExecutionError, '공식 로그인 프로필'):
                adapter.environment('claude-code','/runtime/claude',Path(folder)/'turn')

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

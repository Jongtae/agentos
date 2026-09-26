"""AGENCY-RECOVERY-01 (#607): typed failures, bounded read retry, shared budget, real Stop.

Evidence class: model-free.  A scripted model transport and a fake public
network replace only the provider and the wire; `run_agent`, `Capabilities`,
`AgentService.run_one` (web and Telegram channels), the real MCP bridge
process and a real CLI process group (a harmless local Python child) run
unchanged.
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import test_agency_loop as loop
from personal_agent import mcp_bridge
from personal_agent.agent_runtime import (WORK_STOP_KEEP, WORK_STOP_KEY, WORK_LEDGER_KEY, Capabilities, ToolError,
                                          WorkBudget, WorkLedger, classify_failure, goal_summary)
from personal_agent.bounded_execution import BoundedExecutionAdapter, EngineInterrupted, ExecutionError, bounded_run
from personal_agent.calendar import CalendarError
from personal_agent.google_calendar import GoogleCalendar, GoogleCalendarError, GoogleCalendarHTTPError
from personal_agent.providers import ModelAdapter, ProviderError
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines

OFFLINE = ProviderError('연결할 수 없거나 응답 시간이 초과되었습니다.', status='timeout')


def _store(case):
    tmp = tempfile.TemporaryDirectory()
    case.addCleanup(tmp.cleanup)
    return QuickStore(Path(tmp.name) / 'data'), Path(tmp.name)


def _running(store, text='turn'):
    job = store.enqueue(text, f'k-{time.time_ns()}')
    with store.db() as db:
        db.execute("UPDATE jobs SET status='running' WHERE id=?", (job,))
    return job


def _gone(pid):
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    os.kill(pid, 9)
    return False


class FailureClassificationTests(unittest.TestCase):
    """AX-06: execution/effect, retryability and needed authority stay distinct."""

    def test_table(self):
        cases = [
            (ProviderError('x', status='timeout'), 'weather', ('transient_failure', 'transient', 'none')),
            (ProviderError('x', status=503), 'web_search', ('transient_failure', 'transient', 'none')),
            (ProviderError('x', status=429), 'web_search', ('transient_failure', 'transient', 'none')),
            (ProviderError('x', status=404), 'web_search', ('provider_error', 'permanent', 'none')),
            (TimeoutError(), 'weather', ('transient_failure', 'transient', 'none')),
            # A write is never retry-eligible, whatever the transport said.
            (ProviderError('x', status='timeout'), 'save_note', ('transient_failure', 'permanent', 'none')),
            (ValueError(loop.NOT_FOUND), 'weather', ('tool_failed', 'permanent', 'none')),
            (ToolError('denied', 'policy_denied'), 'web_search', ('policy_denied', 'permanent', 'none')),
            (ToolError('connect', 'needs_setup', requires='google-calendar'), 'calendar_query',
             ('needs_setup', 'needs_setup', 'none')),
            (ToolError('stop', 'stopped'), 'weather', ('stopped', 'budget', 'none')),
            (ToolError('late', 'deadline_exceeded'), 'weather', ('deadline_exceeded', 'budget', 'none')),
            (CalendarError('provider-timeout', effect='unknown'), 'calendar_draft_create', ('effect_unknown', 'never', 'unknown')),
            (CalendarError('rejected', effect='none'), 'calendar_query', ('tool_failed', 'permanent', 'none')),
        ]
        for exc, action, expected in cases:
            with self.subTest(exc=type(exc).__name__, action=action, expected=expected):
                self.assertEqual(classify_failure(exc, action), expected)

    def test_ambiguous_calendar_mutations_are_unknown_not_no_effect(self):
        """#594 item 6: 408/429 mutations and 404/410 PATCH/DELETE may follow an earlier effect."""
        def raising(status):
            def transport(method, url, body, headers):
                raise GoogleCalendarHTTPError(status)
            return GoogleCalendar(transport, 'token')
        for method, status in (('DELETE', 410), ('DELETE', 404), ('PATCH', 404), ('POST', 408), ('PATCH', 429)):
            with self.subTest(method=method, status=status), self.assertRaises(GoogleCalendarError) as caught:
                raising(status)._call(method, 'https://example.invalid', None, {}, mutation=True)
            self.assertEqual(caught.exception.effect, 'unknown')
        # Control: a read's 404 is still a plain no-effect rejection.
        with self.assertRaises(GoogleCalendarError) as caught:
            raising(404)._call('GET', 'https://example.invalid', None, {}, mutation=False)
        self.assertEqual(caught.exception.effect, 'none')


class TransientReadRetryTests(unittest.TestCase):
    def caps(self, network, **kwargs):
        store, _ = _store(self)
        self.events = []
        return Capabilities(store, None, {}, '', 'job', lambda *event: self.events.append(event),
                            network=network, **kwargs)

    def test_a_transient_read_recovers_once_within_the_budget_and_keeps_the_failure(self):
        network = loop.Network(weather=loop.FORECAST)
        seen = []
        def flaky(plan, original=network.execute):
            seen.append(plan['tool'])
            if len(seen) == 1:raise OFFLINE
            return original(plan)
        network.execute = flaky
        budget = WorkBudget()
        caps = self.caps(network, budget=budget)
        result = caps.execute('weather', {'city': 'Seongnam', 'country': 'KR'})
        self.assertEqual(result['location']['name'], 'Seongnam-si')
        self.assertEqual(seen, ['weather', 'weather'])
        self.assertEqual(budget.attempts_used, 2, 'the retry spends one attempt of the shared budget')
        (tool, status, detail), = self.events
        self.assertEqual((tool, status), ('weather', 'failed'))
        self.assertEqual({k: json.loads(detail)[k] for k in ('code', 'retry', 'effect')},
                         {'code': 'transient_failure', 'retry': 'transient', 'effect': 'none'})
        self.assertNotIn('연결할 수 없거나', detail, 'the event carries AgentOS text, not the exception')

    def test_only_one_retry_and_none_for_a_permanent_failure_or_an_exhausted_budget(self):
        calls = []
        def offline(plan):
            calls.append(plan)
            raise OFFLINE
        with self.assertRaises(ProviderError):
            self.caps(SimpleNamespace(execute=offline)).execute('web_search', {'query': 'today news'})
        self.assertEqual(len(calls), 2, 'retried once, never more')
        calls.clear()
        def missing(plan):
            calls.append(plan)
            raise ValueError(loop.NOT_FOUND)
        with self.assertRaises(ValueError):
            self.caps(SimpleNamespace(execute=missing)).execute('weather', {'city': 'Nowhere'})
        self.assertEqual(len(calls), 1, 'a permanent failure is not retried')
        calls.clear()
        with self.assertRaises(ToolError) as caught:
            self.caps(SimpleNamespace(execute=offline), budget=WorkBudget(attempts=1)).execute('web_search', {'query': 'q'})
        self.assertEqual((caught.exception.code, len(calls)), ('attempt_budget', 1))

    def test_a_private_context_keeps_605s_single_attempt(self):
        calls = []
        def offline(plan):
            calls.append(plan)
            raise OFFLINE
        caps = self.caps(SimpleNamespace(execute=offline))
        caps.lookup_private = lambda: True
        with self.assertRaises(ProviderError):
            caps._read_network({'tool': 'weather', 'city': 'Seongnam'})
        self.assertEqual(len(calls), 1, '#605: one network attempt per destination from a private context')
        self.assertEqual(self.events, [])


class SharedBudgetTests(unittest.TestCase):
    """AX-10: one attempt budget and deadline for the host and its CLI bridge."""

    def test_two_budgets_on_one_ledger_share_the_attempts(self):
        store, _ = _store(self)
        job = _running(store)
        host = WorkBudget(attempts=3, ledger=WorkLedger(store, job))
        bridge = WorkBudget(attempts=3, ledger=WorkLedger(store, job))
        host.spend_attempt(); bridge.spend_attempt(); host.spend_attempt()
        with self.assertRaises(ToolError) as caught:bridge.spend_attempt()
        self.assertEqual(caught.exception.code, 'attempt_budget')
        self.assertEqual(WorkLedger(store, job).used(), 3)

    def test_the_first_opener_fixes_the_deadline_and_a_later_one_inherits_it(self):
        store, _ = _store(self)
        job = _running(store)
        now = [1000.0]
        first = WorkLedger(store, job, seconds=5, wall=lambda: now[0])
        now[0] += 4
        later = WorkLedger(store, job, seconds=600, wall=lambda: now[0])
        self.assertEqual(later.deadline, first.deadline)
        now[0] += 2
        self.assertEqual(WorkBudget(ledger=later).interrupted(), 'deadline_exceeded')

    def test_a_resumed_work_starts_a_fresh_budget_and_the_bridge_inherits_it(self):
        """Park/resume boundary: a later host run never inherits an expired deadline or spent attempts."""
        store, _ = _store(self)
        job = _running(store)
        now = [1000.0]
        parked = WorkBudget(attempts=2, ledger=WorkLedger(store, job, seconds=5, wall=lambda: now[0], fresh=True))
        parked.spend_attempt(); parked.spend_attempt()
        with store.db() as db:  # parked, then requeued hours later with no other Work in between
            db.execute("UPDATE jobs SET status='awaiting_connection' WHERE id=?", (job,))
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job,))
        now[0] += 3600
        resumed = WorkBudget(attempts=2, ledger=WorkLedger(store, job, seconds=5, wall=lambda: now[0], fresh=True))
        bridge = WorkBudget(attempts=2, ledger=WorkLedger(store, job, seconds=600, wall=lambda: now[0]))
        self.assertIsNone(resumed.interrupted())
        resumed.spend_attempt(); bridge.spend_attempt()
        with self.assertRaises(ToolError):bridge.spend_attempt()
        self.assertEqual(bridge.ledger.deadline, resumed.ledger.deadline)
        # The service's own budget is the fresh opener.
        self.assertEqual(AgentService(store).work_budget(job).ledger.used(), 0)

    def test_the_real_bridge_process_spends_the_hosts_budget(self):
        """Through the service's CLI broker: 10 host attempts leave the bridge 2."""
        store, _ = _store(self)

        class HostThenBridge(loop.BridgeCli):
            def execute(self, engine, prompt, tools, **kwargs):
                for _ in range(10):
                    tools.capabilities.budget.spend_attempt()
                return super().execute(engine, prompt, tools, **kwargs)

        cli = HostThenBridge([('list_notes', {}), ('list_notes', {}), ('list_notes', {})], '메모를 확인했습니다.')
        service = AgentService(store, subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/codex', clock=lambda: 1),
                               execution_adapter=cli)
        service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        job = store.enqueue('메모 확인해줘', 'budget-cli', channel='telegram:g', chat_id=77)
        self.assertTrue(service.run_one())
        self.assertNotIn('isError', cli.replies[0]['result'])
        self.assertNotIn('isError', cli.replies[1]['result'])
        self.assertEqual(cli.replies[2]['result']['structuredContent']['code'], 'attempt_budget')
        row = store.job(job)
        self.assertEqual(row['status'], 'partial', 'cut off by the shared budget, not succeeded')
        goal = store.turn_provenance(job)['goal']
        self.assertEqual((goal['attempts'], goal['failed_attempts'], goal['unresolved']), (3, 1, ['list_notes']))
        # The ledger row belongs to the running Work only.
        with store.db() as db:
            self.assertEqual(db.execute('SELECT value FROM config WHERE key=?', (f'{WORK_LEDGER_KEY}:{job}',)).fetchone() is not None, True)


FAKE_CLI = '''#!{python}
import subprocess, sys, time
if "exec" not in sys.argv:  # version/login probes answer at once
    print("codex-cli 0.0.0"); sys.exit(0)
child = subprocess.Popen([{python!r}, "-c", "import time; time.sleep(60)"])
open({marker!r}, "w").write(str(child.pid))
time.sleep(60)
'''


class CliProcessStopTests(unittest.TestCase):
    """Stop / deadline end the real CLI process group, not only the next call."""

    def fake_cli(self, root):
        marker = root / 'grandchild.pid'
        script = root / 'fake-codex'
        script.write_text(FAKE_CLI.format(python=sys.executable, marker=str(marker)))
        script.chmod(0o755)
        return script, marker

    def test_bounded_run_kills_the_group_when_interrupted(self):
        _, root = _store(self)
        script, marker = self.fake_cli(root)
        flag = []
        threading.Timer(1.0, lambda: flag.append('stopped')).start()
        started = time.monotonic()
        with self.assertRaises(EngineInterrupted) as caught:
            bounded_run(subprocess.run, [str(script), "exec"], cwd=root, env=dict(os.environ), timeout=30,
                        interrupted=lambda: flag[0] if flag else None)
        self.assertEqual(caught.exception.reason, 'stopped')
        self.assertLess(time.monotonic() - started, 10)
        self.assertTrue(_gone(int(marker.read_text())), 'the grandchild (MCP bridge / native CLI) is killed too')

    def service(self, root, script):
        store = QuickStore(root / 'data')
        (root / 'codex-home').mkdir()
        adapter = BoundedExecutionAdapter(finder=lambda _: str(script), runtime_root=root / 'turns',
                                          codex_home=root / 'codex-home')
        service = AgentService(store, subscription_engines=SubscriptionEngines(finder=lambda _: str(script), clock=lambda: 1),
                               execution_adapter=adapter)
        service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        return service, store

    def engine_failure(self, store, job):
        return [event['trace'] for event in store.task_events(job) if event['tool'] == 'subscription_engine'
                and event['status'] == 'failed'][0]

    def test_owner_stop_kills_the_running_cli_and_records_a_typed_outcome(self):
        _, root = _store(self)
        script, marker = self.fake_cli(root)
        service, store = self.service(root, script)
        job = store.enqueue('긴 작업 해줘', 'stop-cli', channel='telegram:g', chat_id=77)
        # What `ingest_stop` records for a running Work (the durable Stop).
        def stop():
            while not marker.exists():time.sleep(0.05)
            store.append_config_list(WORK_STOP_KEY, job, WORK_STOP_KEEP)
        threading.Thread(target=stop, daemon=True).start()
        started = time.monotonic()
        self.assertTrue(service.run_one())
        self.assertLess(time.monotonic() - started, 20)
        self.assertEqual(self.engine_failure(store, job)['failure_class'], 'stopped')
        self.assertEqual(store.job(job)['status'], 'failed')
        self.assertTrue(_gone(int(marker.read_text())))

    def test_the_shared_deadline_kills_the_cli_as_deadline_exceeded(self):
        _, root = _store(self)
        script, marker = self.fake_cli(root)
        service, store = self.service(root, script)
        job = store.enqueue('긴 작업 해줘', 'deadline-cli', channel='http')
        # A Work whose shared deadline is two seconds away (the host's fresh ledger).
        service.work_budget = lambda job_id: WorkBudget(ledger=WorkLedger(store, job_id, seconds=2, fresh=True))
        started = time.monotonic()
        self.assertTrue(service.run_one())
        self.assertLess(time.monotonic() - started, 20)
        self.assertEqual(self.engine_failure(store, job)['failure_class'], 'deadline_exceeded')
        self.assertTrue(_gone(int(marker.read_text())))


class RecoveryEntryPointTests(unittest.TestCase):
    """Through AgentService.run_one on the web and Telegram channels."""

    CHANNELS = loop.OwnerEntryPointTests.CHANNELS
    service = loop.OwnerEntryPointTests.service
    run_turn = loop.OwnerEntryPointTests.run_turn

    def test_a_transient_read_failure_recovers_and_the_work_succeeds(self):
        for route in self.CHANNELS:
            with self.subTest(route=route[0]):
                script = loop.Script({'tool_calls': [loop.call('1', 'weather', city='Seongnam', country='KR')]},
                                     {'content': '내일(2026-09-27) 성남은 최저 14°C, 최고 22°C입니다.'})
                network = loop.Network(weather=loop.FORECAST)
                calls = []
                def flaky(plan, original=network.execute):
                    calls.append(plan['tool'])
                    if len(calls) == 1:raise OFFLINE
                    return original(plan)
                network.execute = flaky
                row, failed = self.run_turn('내일 성남 날씨 알려줘', script, network, route)
                self.assertEqual(row['status'], 'succeeded')
                self.assertEqual(calls, ['weather', 'weather'])
                self.assertEqual([event['trace']['code'] for event in failed], ['transient_failure'])
                goal = self._store.turn_provenance(row['id'])['goal']
                self.assertEqual((goal['failed_attempts'], goal['recovered'], goal['outcome']), (1, True, 'succeeded'))

    def test_a_permanent_failure_is_not_retried_and_the_work_fails_truthfully(self):
        for route in self.CHANNELS:
            with self.subTest(route=route[0]):
                script = loop.Script({'tool_calls': [loop.call('1', 'weather', city='Nowhere', country='KR')]},
                                     {'content': '그 지역을 찾지 못했습니다. 어느 도시인지 알려 주시겠어요?'})
                network = loop.Network()
                row, failed = self.run_turn('내일 Nowhere 날씨 알려줘', script, network, route)
                self.assertEqual(row['status'], 'failed')
                self.assertEqual([plan['tool'] for plan in network.plans], ['weather'], 'no blind retry')
                self.assertEqual([(event['trace']['code'], event['trace']['retry']) for event in failed],
                                 [('tool_failed', 'permanent')])
                self.assertEqual(self._store.turn_provenance(row['id'])['goal']['unresolved'], ['weather'])


class UnknownEffectTests(unittest.TestCase):
    """An uncertain write survives restart and is never replayed without reconciliation."""

    def test_a_bridge_crash_mid_write_is_refused_on_retry_after_restart(self):
        store, _ = _store(self)
        job = _running(store, '메모 저장해줘')
        crash = KeyboardInterrupt()
        request = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                              'params': {'name': 'save_note', 'arguments': {'content': 'x'}}}) + '\n'
        with mock.patch.object(Capabilities, 'execute', side_effect=crash), \
             mock.patch.object(sys, 'stdin', io.StringIO(request)), mock.patch.object(sys, 'stdout', io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                mcp_bridge.serve(str(store.root), job)
        self.assertEqual([(e['tool'], e['status']) for e in store.task_events(job)], [('save_note', 'running')],
                         'the attempted write is durable before it runs')
        store.recover()  # the host restarts
        service = AgentService(store)
        interrupted = store.job(job)
        self.assertEqual(interrupted['status'], 'interrupted')
        allowed, reason = service.safe_retry(interrupted)
        self.assertFalse(allowed)
        self.assertIn('상태를 바꾸는', reason)
        self.assertEqual(service.retry_from_control(interrupted, 'g', 77), (None, reason))

    def test_a_failed_run_after_an_unknown_effect_stays_unknown(self):
        store, _ = _store(self)

        class UnknownThenStopped:
            def execute(self, engine, prompt, tools, **_kwargs):
                tools.capabilities.record('calendar_draft_create', 'failed', json.dumps(
                    {'host_action': 'calendar_draft_create', 'code': 'effect_unknown', 'retry': 'never', 'effect': 'unknown'}))
                raise ExecutionError('멈춤', failure_class='stopped')

        service = AgentService(store, subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/codex', clock=lambda: 1),
                               execution_adapter=UnknownThenStopped())
        service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        job = store.enqueue('일정 바꿔줘', 'unknown-cli', channel='http')
        self.assertTrue(service.run_one())
        row = store.job(job)
        self.assertEqual(row['status'], 'unknown')
        self.assertEqual(store.turn_provenance(job)['goal']['effect'], 'unknown')
        allowed, _reason = service.safe_retry({**row, 'status': 'failed'})
        self.assertFalse(allowed, 'even a failed status cannot unlock replay of an unknown effect')

    def test_settings_or_unmediated_cli_work_is_not_replayed(self):
        """#594 item 1: effects without a tool event still refuse replay."""
        store, _ = _store(self)
        service = AgentService(store)
        for label in ('owner-settings', 'engine-unmediated-read'):
            with self.subTest(label=label):
                job = store.enqueue('바꿔줘', f'settings-{label}')
                with store.db() as db:
                    db.execute("UPDATE jobs SET status='failed' WHERE id=?", (job,))
                service.record_work_sources(job, {label})
                allowed, reason = service.safe_retry(store.job(job))
                self.assertFalse(allowed)
                self.assertIn('설정 변경', reason)


class BridgeSavedItemEvidenceTests(unittest.TestCase):
    def test_a_bridged_saved_note_records_its_exact_item_id(self):
        """#594 item 9: the CLI route's saved-note Evidence links the exact item."""
        store, _ = _store(self)
        job = _running(store, '메모 저장해줘')
        request = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                              'params': {'name': 'save_note', 'arguments': {'content': '우유 사기'}}}) + '\n'
        out = io.StringIO()
        with mock.patch.object(sys, 'stdin', io.StringIO(request)), mock.patch.object(sys, 'stdout', out):
            mcp_bridge.serve(str(store.root), job)
        saved = json.loads(json.loads(out.getvalue())['result']['content'][0]['text'])
        events = [(e['tool'], e['status'], e['trace']) for e in store.task_events(job)]
        self.assertEqual([event[:2] for event in events], [('save_note', 'running'), ('save_note', 'succeeded')])
        self.assertEqual(events[1][2]['evidence'], {'saved': True, 'id': saved['id']})
        self.assertNotIn('우유', json.dumps(events, ensure_ascii=False), 'no note content in the event')


class RetryAtomicityTests(unittest.TestCase):
    def test_retry_enqueue_and_relation_commit_together(self):
        """#594 item 2: a failure while linking leaves no orphan retry Work."""
        store, _ = _store(self)
        service = AgentService(store)
        job = store.enqueue('날씨', 'orig', channel='telegram:g', chat_id=77)
        with store.db() as db:
            db.execute("UPDATE jobs SET status='failed' WHERE id=?", (job,))
        with mock.patch.object(QuickStore, 'link_work_relation', side_effect=ValueError('crash')):
            with self.assertRaises(ValueError):
                service.retry_from_control(store.job(job), 'g', 77)
        with store.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0], 1, 'the retry rolled back')
        task_id, reason = service.retry_from_control(store.job(job), 'g', 77)
        self.assertIsNone(reason)
        self.assertEqual(store.job(task_id)['related_job_id'], job)
        self.assertTrue(service._already_retried(job))


class GoalSummaryTests(unittest.TestCase):
    def test_attempts_and_obligations_are_separate(self):
        rows = [('weather', 'failed', json.dumps({'host_action': 'weather', 'code': 'transient_failure'})),
                ('weather', 'succeeded', json.dumps({'host_action': 'weather', 'evidence': {}})),
                ('web_search', 'succeeded', json.dumps({'host_action': 'web_search', 'evidence': {'qualifiers': ['truncated']}}))]
        summary = goal_summary(rows)
        # Two attempts did not fully succeed; the recovered weather read does
        # not make the truncated search a satisfied obligation.
        self.assertEqual((summary['attempts'], summary['failed_attempts'], summary['recovered'], summary['unresolved']),
                         (3, 2, False, ['web_search']))
        recovered = goal_summary(rows[:2])
        self.assertEqual((recovered['recovered'], recovered['unresolved']), (True, []))


if __name__ == '__main__':
    unittest.main()

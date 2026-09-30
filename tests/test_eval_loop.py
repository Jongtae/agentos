"""EVAL-LOOP-01 (#821): model-free unit tests of the evaluation loop in ``evals/agentos_eval``.

The HTTP layer, sandboxes, clock and Keychain are faked; Inspect AI is not
needed (only ``evals/agentos_eval/task.py`` imports it).  Evidence class:
unit tests of the harness logic, not a live evaluation result.
"""
import json
import math
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'evals'))

from agentos_eval import budget as budget_module  # noqa: E402
from agentos_eval import cli, report, runner, sandbox, scenarios, scoring  # noqa: E402
from agentos_eval.client import AgentOSClient, ClientError, state_diff  # noqa: E402
from agentos_eval.paths import LIVE_PORTS, SANDBOX_SITE  # noqa: E402


def scenario(**overrides):
    raw = {'id': 'demo-scenario', 'title': 'Demo', 'turns': ['첫 번째', {'say': '두 번째', 'note': 'Saturday 07:00'}],
           'rubric': ['context_carry', 'follow_through']}
    raw.update(overrides)
    return scenarios.validate(raw)


def turn(**overrides):
    row = {'say': 'x', 'note': '', 'task_id': 't1', 'status': 'succeeded', 'answer': '답변', 'answer_withheld': False,
           'timed_out': False, 'failure_class': None, 'error': None, 'events': [], 'elapsed': 1.0}
    row.update(overrides)
    return row


class ScenarioLoaderTest(unittest.TestCase):
    def test_bundled_scenarios_are_valid_synthetic_and_cover_both_splits(self):
        loaded = scenarios.load(include_local=False)
        self.assertGreaterEqual(len(loaded), 20)
        self.assertEqual({item['source'] for item in loaded}, {'bundled'})
        self.assertEqual({item['split'] for item in loaded}, {'dev', 'heldout'})
        used = {dim for item in loaded for dim in item['rubric']}
        self.assertEqual(used, set(scenarios.RUBRIC))
        self.assertTrue(any(len(item['turns']) > 1 for item in loaded))

    def test_validation_rejects_malformed_scenarios(self):
        for bad in ({'id': 'Bad Id'}, {'unknown': 1}, {'turns': []}, {'turns': [{'say': ' '}]},
                    {'rubric': ['nope']}, {'expect': {'memory_any': [[]]}}, {'expect': {'other': 1}},
                    {'split': 'train'}, {'turns': [{'say': 'a', 'extra': 1}]}):
            with self.subTest(bad=bad), self.assertRaises(scenarios.ScenarioError):
                scenario(**bad)

    def test_normalizes_turns_and_expectations(self):
        item = scenario(expect={'memory_any': [[' 을지로 ', '한빛']], 'preparation': True})
        self.assertEqual(item['turns'][0], {'say': '첫 번째', 'note': '', 'note_in_message': False})
        self.assertEqual(item['expect']['memory_any'], [['을지로', '한빛']])
        self.assertTrue(item['expect']['preparation'])
        self.assertEqual(scenarios.owner_message(item['turns'][1]), '두 번째')
        self.assertEqual(scenarios.owner_message({**item['turns'][1], 'note_in_message': True}), '(Saturday 07:00) 두 번째')

    def test_local_folder_adds_owner_scenarios_and_duplicates_fail(self):
        with tempfile.TemporaryDirectory() as home:
            local = Path(home) / 'scenarios'
            local.mkdir()
            (local / 'mine.json').write_text(json.dumps([{'id': 'owner-case-1', 'turns': ['hi'], 'split': 'heldout'}]))
            loaded = scenarios.load(environ={'AGENTOS_EVAL_HOME': home})
            mine = [item for item in loaded if item['id'] == 'owner-case-1']
            self.assertEqual(mine[0]['source'], 'local')
            self.assertEqual([item['id'] for item in scenarios.load(environ={'AGENTOS_EVAL_HOME': home},
                                                                    split='heldout', ids=['owner-case-1'])],
                             ['owner-case-1'])
            with self.assertRaises(scenarios.ScenarioError):
                scenarios.load(environ={'AGENTOS_EVAL_HOME': home}, ids=['missing-id'])
            (local / 'dup.json').write_text(json.dumps({'id': 'tee-time-reminder', 'turns': ['x']}))
            with self.assertRaises(scenarios.ScenarioError):
                scenarios.load(environ={'AGENTOS_EVAL_HOME': home})


class FakeServer:
    """In-memory stand-in for the AgentOS HTTP routes the client uses."""

    def __init__(self, claimed=True, statuses=('running', 'succeeded'), judgment=None, owner_model=None):
        self.claimed = claimed
        # ``/api/owner-model`` views served in order (the last one repeats); None answers 403.
        self.owner_model = list(owner_model or [])
        self.statuses = list(statuses)
        self.calls = []
        self.memories = []
        # The decision route as ``settings.decision_route`` reports it.
        self.judgment = judgment or {'mode': 'follow_main', 'main': 'claude-code', 'qualification': None,
                                     'active': {'available': True, 'engine': 'claude-code', 'transport': 'subscription_cli'}}

    def __call__(self, method, url, body, headers):
        path = url.split('127.0.0.1:1', 1)[-1]
        path = path[path.index('/'):]
        self.calls.append((method, path, json.loads(body) if body else None, headers.get('Cookie')))
        cookie = {'Set-Cookie': 'agentos_session=tok123; HttpOnly; Path=/'}
        if path == '/api/status':
            return 200, {}, json.dumps({'claimed': self.claimed}).encode()
        if path in ('/api/claim', '/api/local-login'):
            return 200, cookie, b'{"ok": true}'
        if path == '/api/chat':
            return 202, {}, b'{"id": "task-1"}'
        if path == '/api/tasks/task-1':
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return 200, {}, json.dumps({'selected': {'status': status, 'events': [{'tool': 'web_search', 'status': 'succeeded', 'trace': {'x': 1}}]}}).encode()
        if path == '/api/state':
            return 200, {}, json.dumps({'jobs': [{'id': 'task-1', 'status': 'succeeded', 'response': '두 시간'}],
                                        'settings': {'decision_route': self.judgment}}).encode()
        if path == '/api/main-ai/activate':
            main = json.loads(body)['route']
            self.judgment = {'mode': 'follow_main', 'main': main, 'qualification': {'state': 'passed'},
                             'active': {'available': True, 'engine': main, 'requested_model': 'small'}}
            return 200, {}, b'{}'
        if path == '/api/personal-space':
            return 200, {}, json.dumps({'memories': self.memories, 'memory_candidates': []}).encode()
        if path == '/api/owner-model':
            if not self.owner_model:
                return 403, {}, b'{"error": "nope"}'
            view = self.owner_model.pop(0) if len(self.owner_model) > 1 else self.owner_model[0]
            return 200, {}, json.dumps(view).encode()
        return 200, {}, b'{}'


class ClientTest(unittest.TestCase):
    def test_fresh_folder_is_claimed_and_existing_one_uses_local_login(self):
        for claimed, route in ((False, '/api/claim'), (True, '/api/local-login')):
            server = FakeServer(claimed=claimed)
            client = AgentOSClient('http://127.0.0.1:18900', transport=server)
            client.login()
            self.assertEqual(server.calls[-1][:3], ('POST', route, {}))
            self.assertEqual(client.cookie, 'tok123')

    def test_turn_polls_until_the_work_stops_moving(self):
        server = FakeServer(statuses=['queued', 'running', 'succeeded'])
        client = AgentOSClient('http://127.0.0.1:18900', transport=server, sleep=lambda _: None)
        client.cookie = 'tok123'
        task_id = client.send('안녕', 'key-1')
        self.assertEqual(server.calls[-1][2], {'message': '안녕', 'request_key': 'key-1'})
        self.assertEqual(server.calls[-1][3], 'agentos_session=tok123')
        self.assertEqual(client.wait(task_id)['status'], 'succeeded')
        self.assertEqual(client.answer(task_id)['response'], '두 시간')

    def test_wait_times_out_on_the_injected_clock(self):
        now = [0.0]
        server = FakeServer(statuses=['running'])
        client = AgentOSClient('http://127.0.0.1:18900', transport=server, clock=lambda: now[0],
                               sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
        detail = client.wait('task-1', timeout=10, interval=4)
        self.assertTrue(detail['timed_out'])
        self.assertEqual(detail['status'], 'running')

    def test_error_status_raises_and_snapshot_records_unavailable_routes(self):
        client = AgentOSClient('http://127.0.0.1:18900', transport=FakeServer())
        with self.assertRaises(ClientError) as caught:
            client.get('/api/owner-model')
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(client.snapshot()['owner_model'], {'unavailable': 403})

    def test_state_diff_reports_only_new_rows(self):
        before = {'personal_space': {'memories': [{'id': 'm1', 'content': 'old'}], 'memory_candidates': []},
                  'candidates': {'candidates': []}, 'preparations': {'preparations': []}, 'settings': {'a': 1}}
        after = {'personal_space': {'memories': [{'id': 'm1', 'content': 'old'}, {'id': 'm2', 'content': '을지로 한빛타워'}],
                                    'memory_candidates': [{'id': 'c1', 'content': '김치찌개'}]},
                 'candidates': {'candidates': [{'id': 'c1', 'content': '김치찌개'}]},
                 'preparations': {'preparations': [{'id': 'p1', 'goal': '티타임'}]}, 'settings': {'a': 2}}
        diff = state_diff(before, after)
        self.assertEqual([row['id'] for row in diff['memories']], ['m2'])
        self.assertEqual([row['id'] for row in diff['candidates']], ['c1'])
        self.assertEqual([row['id'] for row in diff['preparations']], ['p1'])
        self.assertTrue(diff['settings_changed'])


class UpkeepWaitTest(unittest.TestCase):
    """#832: the state diff waits, bounded, for the asynchronous owner-model upkeep (#805)."""

    @staticmethod
    def view(pending=0, running=0, enabled=True, used=0, cap=12):
        return {'enabled': enabled, 'daily_calls': cap, 'pending': pending, 'running': running, 'calls_last_24h': used}

    def clocked(self, server):
        now = [0.0]
        client = AgentOSClient('http://127.0.0.1:18900', transport=server, clock=lambda: now[0],
                               sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
        return client, now

    def test_waits_until_pending_and_running_upkeep_is_done(self):
        server = FakeServer(owner_model=[self.view(pending=1), self.view(running=1), self.view()])
        client, _ = self.clocked(server)
        self.assertEqual(client.wait_upkeep_idle(timeout=90, interval=2), {'idle': True, 'busy': 0, 'waited': 4.0})
        self.assertEqual(sum(1 for call in server.calls if call[1] == '/api/owner-model'), 3)

    def test_wait_is_bounded(self):
        client, _ = self.clocked(FakeServer(owner_model=[self.view(running=1)]))
        self.assertEqual(client.wait_upkeep_idle(timeout=10, interval=4), {'idle': False, 'busy': 1, 'waited': 12.0})

    def test_paused_capped_or_unreadable_upkeep_does_not_wait(self):
        for server in (FakeServer(owner_model=[self.view(pending=2, enabled=False)]),
                       FakeServer(owner_model=[self.view(pending=2, used=12, cap=12)]),
                       FakeServer()):
            client, now = self.clocked(server)
            result = client.wait_upkeep_idle(timeout=90, interval=2)
            self.assertEqual(now[0], 0.0)
            self.assertEqual(result['busy'], None if not server.owner_model else 0)

    def test_runner_waits_for_upkeep_before_the_after_snapshot(self):
        # Before-snapshot, then the wait's reads (pending, idle), then the after-snapshot.
        server = FakeServer(statuses=['succeeded'], owner_model=[self.view(), self.view(pending=1), self.view()])
        record = runner.run_scenario(scenario(), 'claude-code', FakePool(),
                                     client_factory=lambda url: AgentOSClient(url, transport=server, sleep=lambda _: None))
        self.assertIsNone(record['error'])
        self.assertTrue(record['upkeep']['idle'])
        paths = [call[1] for call in server.calls]
        last_chat = max(index for index, path in enumerate(paths) if path == '/api/chat')
        waits = [index for index, path in enumerate(paths) if path == '/api/owner-model' and index > last_chat]
        # Two reads by the wait (pending, then idle), then the after-snapshot's own read.
        self.assertEqual(len(waits), 3)
        self.assertLess(waits[1], paths.index('/api/personal-space', last_chat))


class FakeBox:
    url = 'http://127.0.0.1:18900'
    slot = 0

    def __init__(self, cached=None):
        self.cached = cached

    def wait_healthy(self, client):
        return True

    def read_config(self, keys):
        return {key: f'row-{key}' for key in keys}


class FakePool:
    def __init__(self, error=None, cached=None):
        self.error = error
        self.cached = cached
        self.used = 0
        self.stored = {}
        self.forgotten = []

    @contextmanager
    def sandbox(self, worker=None):
        self.used += 1
        if self.error:
            raise self.error
        yield FakeBox(self.cached)

    def store_judgment(self, slot, worker, rows):
        self.stored[(slot, worker)] = rows

    def forget_judgment(self, slot, worker):
        self.forgotten.append((slot, worker))


class RunnerTest(unittest.TestCase):
    def test_runs_every_turn_on_a_fresh_sandbox_and_diffs_owner_state(self):
        server = FakeServer(statuses=['succeeded'])
        pool = FakePool()
        record = runner.run_scenario(scenario(), 'claude-code', pool,
                                     client_factory=lambda url: AgentOSClient(url, transport=server, sleep=lambda _: None))
        self.assertIsNone(record['error'])
        self.assertEqual(pool.used, 1)
        self.assertEqual([row['answer'] for row in record['turns']], ['두 시간', '두 시간'])
        self.assertEqual(record['turns'][0]['events'], [{'tool': 'web_search', 'status': 'succeeded'}])
        self.assertIn(('POST', '/api/subscription-engines/connect',
                       {'engine': 'claude-code', 'officially_authenticated': True}),
                      [call[:3] for call in server.calls])
        self.assertEqual(sum(1 for call in server.calls if call[1] == '/api/chat'), 2)

    def test_judgment_ai_is_requalified_for_the_worker_once_and_cached(self):
        server = FakeServer(statuses=['succeeded'], judgment={
            'mode': 'follow_main', 'main': 'codex', 'qualification': None,
            'active': {'available': False, 'engine': 'codex', 'transport': 'subscription_cli'}})
        pool = FakePool(cached={'decision_route': 'stale'})
        record = runner.run_scenario(scenario(), 'claude-code', pool,
                                     client_factory=lambda url: AgentOSClient(url, transport=server, sleep=lambda _: None))
        self.assertIn(('POST', '/api/main-ai/activate', {'route': 'claude-code'}), [call[:3] for call in server.calls])
        self.assertEqual(record['judgment']['ready'], True)
        self.assertTrue(record['judgment']['requalified'])
        self.assertEqual(pool.forgotten, [(0, 'claude-code')])
        self.assertEqual(sorted(pool.stored[(0, 'claude-code')]), sorted(sandbox.JUDGMENT_KEYS))
        # Already qualified for this worker (a cache hit): nothing is re-run or stored.
        server, pool = FakeServer(statuses=['succeeded']), FakePool(cached={'decision_route': 'ok'})
        record = runner.run_scenario(scenario(), 'claude-code', pool,
                                     client_factory=lambda url: AgentOSClient(url, transport=server, sleep=lambda _: None))
        self.assertNotIn('/api/main-ai/activate', [call[1] for call in server.calls])
        self.assertEqual((record['judgment']['cached'], pool.stored), (True, {}))

    def test_explicit_judgment_route_is_requalified_with_its_own_settings(self):
        client = AgentOSClient('http://127.0.0.1:18900', transport=FakeServer())
        posted = []
        client.post = lambda path, body: posted.append((path, body)) or {}
        status = {'mode': 'explicit', 'active': {'transport': 'subscription_cli', 'engine': 'codex',
                                                 'model_policy': 'explicit', 'requested_model': 'm1', 'effort': 'low'}}
        client.requalify_judgment('codex', status)
        self.assertEqual(posted, [('/api/decision-route/activate', {'transport': 'subscription_cli', 'engine': 'codex',
                                                                     'model_policy': 'explicit', 'effort': 'low',
                                                                     'model': 'm1'})])
        self.assertIsNone(client.requalify_judgment('codex', {'mode': 'explicit', 'active': {'transport': 'off'}}))

    def test_infrastructure_failure_is_recorded_not_raised(self):
        record = runner.run_scenario(scenario(), 'codex', FakePool(error=sandbox.SandboxError('port busy')))
        self.assertIn('port busy', record['error'])
        with self.assertRaises(ValueError):
            runner.run_scenario(scenario(), 'gemini', FakePool())


class ScoringTest(unittest.TestCase):
    def test_delivered_and_not_failed_checks(self):
        item = scenario(expect={'allow_status': ['awaiting_context']})
        run = {'worker': 'codex', 'turns': [turn(), turn(status='awaiting_context', answer='어디서 출발하세요?')], 'diff': {}}
        checks, failures = scoring.deterministic_checks(item, run)
        self.assertEqual(checks, {'delivered': True, 'not_failed': True})
        self.assertEqual(failures, [])
        run = {'worker': 'codex', 'turns': [turn(status='failed', failure_class='auth', answer=''),
                                            turn(answer_withheld=True), turn(timed_out=True, status='running')]}
        checks, failures = scoring.deterministic_checks(scenario(), run)
        self.assertEqual(checks, {'delivered': False, 'not_failed': False})
        reasons = {(row['name'], row['reason']) for row in failures}
        self.assertIn(('delivered', 'turn 1: empty'), reasons)
        self.assertIn(('delivered', 'turn 2: withheld'), reasons)
        self.assertIn(('not_failed', 'turn 1: failed/auth'), reasons)
        self.assertIn(('not_failed', 'turn 3: timeout'), reasons)

    def test_memory_and_preparation_expectations_read_the_state_diff(self):
        item = scenario(expect={'memory_any': [['한빛타워', '을지로'], ['김치찌개']], 'preparation': True})
        run = {'turns': [turn()], 'diff': {'memories': [{'content': '평일 출근: 을지로입구 한빛타워'}],
                                          'candidates': [{'content': '점심에 김치찌개를 먹음'}], 'preparations': []}}
        checks, failures = scoring.deterministic_checks(item, run)
        self.assertTrue(checks['memory'])
        self.assertFalse(checks['preparation'])
        self.assertEqual([row['name'] for row in failures], ['preparation'])
        run['diff']['candidates'] = []
        checks, failures = scoring.deterministic_checks(item, run)
        self.assertFalse(checks['memory'])

    def test_no_memory_of_request_rejects_the_owner_sentence_as_a_value(self):
        """#846: a standing wish is a watch; the request sentence must not become a memory."""
        item = scenario(turns=[{'say': '가격이 내려가면 알려줘.'}], expect={'no_memory_of_request': True})
        run = {'turns': [turn(say='가격이 내려가면 알려줘.')],
               'diff': {'memories': [], 'candidates': [{'content': '가격이  내려가면 알려줘.'}], 'preparations': [{'id': 'p1'}]}}
        checks, failures = scoring.deterministic_checks(item, run)
        self.assertFalse(checks['no_memory_of_request'])
        self.assertEqual([row['name'] for row in failures], ['no_memory_of_request'])
        run['diff']['candidates'] = [{'content': '무선 청소기'}]
        checks, failures = scoring.deterministic_checks(item, run)
        self.assertTrue(checks['no_memory_of_request'])
        self.assertEqual(failures, [])
        self.assertNotIn('no_memory_of_request', scoring.deterministic_checks(scenario(), run)[0])
        self.assertIn('check_no_memory_of_request', scoring.combine(item, run, checks, failures)[0])

    def test_unqualified_judgment_ai_is_an_infra_failure(self):
        run = {'turns': [turn()], 'judgment': {'requalified': True, 'ready': False, 'waited': 300.0}}
        checks, failures = scoring.deterministic_checks(scenario(), run)
        self.assertTrue(checks['delivered'])
        self.assertEqual([(row['kind'], row['name']) for row in failures], [('infra', 'judgment_ai')])
        run['judgment'] = {'requalified': False, 'ready': False}   # the owner turned it off: nothing to flag
        self.assertEqual(scoring.deterministic_checks(scenario(), run)[1], [])

    def test_harness_error_is_an_infra_failure_only(self):
        checks, failures = scoring.deterministic_checks(scenario(), {'error': 'SandboxError: boom'})
        self.assertEqual(checks, {'harness': False})
        self.assertEqual(failures[0]['kind'], 'infra')

    def test_judge_prompt_carries_context_notes_and_state(self):
        run = {'turns': [turn(say='첫 번째'), turn(say='두 번째', note='Saturday 07:00', answer='A' * 7000)],
               'diff': {'candidates': [{'content': '김치찌개'}]}}
        prompt = scoring.judge_prompt(scenario(good_secretary='Carry the place.'), run)
        self.assertIn('[situation before turn 2: Saturday 07:00]', prompt)
        self.assertIn('new memory candidate (awaiting owner confirmation): 김치찌개', prompt)
        self.assertIn('- context_carry:', prompt)
        self.assertNotIn('- owner_model:', prompt)
        self.assertIn('[...]', prompt)

    def test_parse_judgment_normalizes_scores_and_rejects_bad_replies(self):
        text = 'Here: {"dimensions": {"context_carry": {"score": 2, "reason": "ok"}, "follow_through": {"score": null}}, "summary": "s"}'
        parsed = scoring.parse_judgment(text, ['context_carry', 'follow_through'])
        self.assertEqual(parsed['dimensions']['context_carry']['score'], 1.0)
        self.assertIsNone(parsed['dimensions']['follow_through']['score'])
        for bad in ('no json', '{"dimensions": {}}', '{"dimensions": {"context_carry": {"score": 3}, "follow_through": {"score": 1}}}',
                    '{"dimensions": {"context_carry": {"score": true}, "follow_through": {"score": 1}}}'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                scoring.parse_judgment(bad, ['context_carry', 'follow_through'])

    def test_combine_counts_zero_rubric_scores_as_failures(self):
        judgment = {'dimensions': {'context_carry': {'score': 0.0, 'reason': 'lost the place'},
                                   'follow_through': {'score': 0.5, 'reason': 'partly'}}, 'summary': 's'}
        value, meta = scoring.combine(scenario(), {'worker': 'codex', 'turns': [turn()]}, {'delivered': True}, [],
                                      judgment, 'judged')
        self.assertEqual(value['rubric_context_carry'], 0.0)
        self.assertEqual(value['rubric_mean'], 0.25)
        self.assertEqual(value['passed'], 0.0)
        self.assertEqual(meta['failures'], [{'kind': 'rubric', 'name': 'context_carry', 'reason': 'lost the place'}])
        value, _ = scoring.combine(scenario(), {'turns': [turn()]}, {'delivered': True}, [])
        self.assertEqual(value['passed'], 1.0)

    def test_every_score_carries_every_key_so_inspect_metrics_do_not_abort(self):
        judged, _ = scoring.combine(scenario(), {'turns': [turn()]}, {'delivered': True, 'memory': True}, [],
                                    {'dimensions': {'context_carry': {'score': 1.0, 'reason': 'ok'}}, 'summary': 's'},
                                    'judged')
        unjudged, _ = scoring.combine(scenario(), {'turns': [turn()]}, {'delivered': True}, [])
        errored, _ = scoring.combine(scenario(), {'error': 'sandbox failed'}, *scoring.deterministic_checks(
            scenario(), {'error': 'sandbox failed'}))
        self.assertEqual(set(judged), set(unjudged))
        self.assertEqual(set(judged), set(errored))
        self.assertTrue(math.isnan(unjudged['rubric_context_carry']))
        self.assertTrue(math.isnan(unjudged['rubric_mean']))
        self.assertTrue(math.isnan(judged['check_preparation']))
        summary = report._group([{'value': judged, 'checks': {}}, {'value': unjudged, 'checks': {}}])
        self.assertEqual(summary['rubric']['context_carry'], {'n': 1, 'mean': 1.0, 'zero_rate': 0.0})
        self.assertNotIn('follow_through', summary['rubric'])


class UsageLimitStopTest(unittest.TestCase):
    """#887: a sweep stops starting runs once a subscription usage limit is hit."""

    @staticmethod
    def scores(*classes):
        run = {'worker': 'codex', 'turns': [turn(status='failed', failure_class=c) if c else turn() for c in classes]}
        _, metadata = scoring.combine(scenario(), run, *scoring.deterministic_checks(scenario(), run))
        score = type('Score', (), {'metadata': metadata})()
        return {'secretary': type('SampleScore', (), {'score': score})()}

    def test_usage_limit_turn_skips_every_later_sample(self):
        import asyncio
        stop = runner.StopOnUsageLimit(lambda **kw: kw)

        async def sweep():
            self.assertEqual(await stop.start_task(None, [], 1), 'stop-on-usage-limit')
            self.assertIsNone(await stop.schedule_sample('a@codex', 1))
            await stop.complete_sample('a@codex', 1, self.scores(None, 'engine-failed'))
            self.assertIsNone(await stop.schedule_sample('b@codex', 1))
            await stop.complete_sample('b@codex', 1, self.scores(None, 'usage-limit'))
            skipped = await stop.schedule_sample('c@codex', 2)
            await stop.complete_sample('d@codex', 1, self.scores('usage-limit'))
            return skipped, await stop.complete_task()

        skipped, summary = asyncio.run(sweep())
        self.assertEqual(skipped, {'id': 'c@codex', 'epoch': 2, 'reason': 'usage limit hit in b@codex (epoch 1)'})
        self.assertEqual(summary, {'tripped_by': 'b@codex (epoch 1)'})
        asyncio.run(stop.start_task(None, [], 1))
        self.assertIsNone(asyncio.run(stop.schedule_sample('a@codex', 1)))

    def test_sweep_reports_the_stop_and_exits_2_only_when_tripped(self):
        def log(metadata, stops=()):
            summary = type('Summary', (), {'metadata': metadata, 'early_stops': list(stops)})()
            return type('Log', (), {'results': type('Results', (), {'early_stopping': summary})()})()

        self.assertIsNone(cli.usage_limit_stops(type('Log', (), {'results': None})()))
        self.assertIsNone(cli.usage_limit_stops(log({'tripped_by': None})))
        self.assertEqual(cli.usage_limit_stops(log({'tripped_by': 'b@codex (epoch 1)'}, ['c', 'd'])),
                         {'tripped_by': 'b@codex (epoch 1)', 'skipped': 2})


class BudgetTest(unittest.TestCase):
    def test_cap_refuses_and_settle_uses_observed_usage(self):
        with tempfile.TemporaryDirectory() as folder:
            now = [1_790_000_000.0]
            ledger = budget_module.JudgeBudget(Path(folder) / 'b.json', cap_usd=0.05, price_in=1.0, price_out=10.0,
                                               clock=lambda: now[0])
            reserved = ledger.reserve(10_000, 2_000)          # 0.01 + 0.02
            self.assertAlmostEqual(reserved, 0.03)
            self.assertIsNone(ledger.reserve(10_000, 2_000))  # 0.06 > 0.05
            ledger.settle(reserved, 5_000, 100)               # 0.005 + 0.001
            status = ledger.status()
            self.assertAlmostEqual(status['usd'], 0.006)
            self.assertEqual((status['calls'], status['refused'], status['input_tokens']), (1, 1, 5_000))
            self.assertIsNotNone(ledger.reserve(10_000, 2_000))
            unknown = ledger.reserve(1_000, 100)
            self.assertEqual(ledger.settle(unknown, None, None), unknown)   # unknown usage keeps the charge
            now[0] += 86_400
            self.assertEqual(ledger.status()['usd'], 0.0)                   # a new day starts fresh

    def test_environment_configures_the_cap(self):
        ledger = budget_module.JudgeBudget.from_environ('/nonexistent/b.json', {'AGENTOS_EVAL_JUDGE_CAP_USD': '2.5'})
        self.assertEqual((ledger.cap, ledger.price_in), (2.5, budget_module.DEFAULT_PRICE_IN))
        self.assertEqual(budget_module.JudgeBudget.from_environ('/x', {}).cap, 10.0)
        with self.assertRaises(ValueError):
            budget_module.JudgeBudget('/x', cap_usd=-1)


def record(scenario_id, worker, passed, failures=(), checks=None, rubric=None, source='bundled'):
    value = {'passed': 1.0 if passed else 0.0}
    value.update({f'rubric_{dim}': score for dim, score in (rubric or {}).items()})
    return {'scenario': scenario_id, 'worker': worker, 'source': source, 'split': 'dev', 'judge_status': 'judged',
            'checks': checks or {'delivered': passed}, 'failures': list(failures), 'value': value}


class ReportTest(unittest.TestCase):
    def records(self):
        carry = {'kind': 'rubric', 'name': 'context_carry', 'reason': 'lost the place'}
        return [record('a', 'codex', False, [carry], rubric={'context_carry': 0.0}),
                record('b', 'codex', False, [carry], rubric={'context_carry': 0.0}),
                record('b', 'claude-code', True, rubric={'context_carry': 1.0}),
                record('c', 'claude-code', False, [{'kind': 'check', 'name': 'not_failed', 'reason': 'turn 1: failed/auth'}],
                       checks={'delivered': False})]

    def test_failures_cluster_by_root_cause_not_by_case(self):
        result = report.aggregate(self.records(), {'id': 'r1'})
        self.assertEqual(result['totals']['runs'], 4)
        self.assertEqual(result['totals']['pass_rate'], 0.25)
        top = result['clusters'][0]
        self.assertEqual((top['key'], top['count'], top['scenarios'], top['workers']),
                         ('rubric:context_carry', 2, {'a': 1, 'b': 1}, {'codex': 2}))
        self.assertEqual(result['by_worker']['codex']['rubric']['context_carry']['zero_rate'], 1.0)
        self.assertEqual(result['by_worker']['claude-code']['checks']['delivered']['pass_rate'], 0.5)

    def test_trend_flags_regressions_and_new_clusters(self):
        previous = report.aggregate([record('a', 'codex', True, rubric={'context_carry': 1.0}),
                                     record('b', 'codex', True, rubric={'context_carry': 1.0})], {'id': 'r0'})
        current = report.aggregate(self.records(), {'id': 'r1'})
        trend = report.compare(current, previous)
        self.assertEqual(trend['previous_run'], 'r0')
        self.assertIn('pass_rate', [row['metric'] for row in trend['regressions']])
        self.assertIn('rubric:context_carry', [row['metric'] for row in trend['regressions']])
        self.assertEqual(trend['new_clusters'], ['check:not_failed', 'rubric:context_carry'])
        self.assertEqual(report.compare(previous, current)['resolved_clusters'], ['check:not_failed', 'rubric:context_carry'])

    def test_write_report_compares_with_the_previous_report_of_the_same_cohort(self):
        with tempfile.TemporaryDirectory() as folder:
            same = [record('a', 'codex', True), record('b', 'codex', True), record('b', 'claude-code', True),
                    record('c', 'claude-code', True)]
            report.write_report(same, folder, {'id': '20260928T0700-aaaaaa'})
            # A targeted re-run of one scenario is its own cohort: no false regression against the full sweep.
            _, _, targeted = report.write_report([record('a', 'codex', False)], folder, {'id': '20260928T0800-cccccc'})
            self.assertIsNone(targeted['trend']['previous_run'])
            self.assertEqual(targeted['trend']['regressions'], [])
            json_path, md_path, result = report.write_report(self.records(), folder, {'id': '20260928T1900-bbbbbb'})
            self.assertEqual(result['trend']['previous_run'], '20260928T0700-aaaaaa')
            self.assertEqual(json.loads(json_path.read_text())['run']['id'], '20260928T1900-bbbbbb')
            text = md_path.read_text()
            self.assertIn('**rubric:context_carry** (new): 2 runs across 2 scenarios', text)
            self.assertIn('## Regressions', text)

    def test_records_from_inspect_samples(self):
        class Score:
            value = {'passed': 1.0}
            metadata = {'scenario': 'a', 'worker': 'codex', 'failures': []}

        class Sample:
            id, epoch, scores = 'a@codex', 2, {'secretary': Score()}

        class Unscored:
            id, epoch, scores, error = 'b@claude-code', 1, None, 'RuntimeError: provider down'
            metadata = {'scenario': {'id': 'b', 'source': 'bundled', 'split': 'dev'}, 'worker': 'claude-code'}
        rows = report.records_from_samples([Sample(), Unscored()])
        self.assertEqual(rows[0], {'scenario': 'a', 'worker': 'codex', 'failures': [], 'sample_id': 'a@codex', 'epoch': 2,
                                   'value': {'passed': 1.0}})
        # An unscored sample stays in the denominator as an infra failure.
        self.assertEqual((rows[1]['scenario'], rows[1]['worker'], rows[1]['value'], rows[1]['failures'][0]['name']),
                         ('b', 'claude-code', {'passed': 0.0}, 'sample_error'))
        self.assertEqual(report.aggregate(rows)['totals']['pass_rate'], 0.5)


class SandboxTest(unittest.TestCase):
    def make_data(self, root):
        private = root / 'private'
        (private / 'logs').mkdir(parents=True)
        (private / 'logs' / 'x.log').write_text('log')
        (private / 'setup-link.txt').write_text('http://127.0.0.1:8787/#setup=secret')
        (private / 'browser-profile').mkdir()
        (private / 'connections.json').write_text(json.dumps({
            'telegram_token': 'T', 'encrypted:drive_web_oauth_tokens': 'D', 'claude_code_token': 'C',
            'model_key': 'M', 'api_key:openai': 'O', 'decision_model_key': 'J', 'search_key:brave': 'B'}))
        db = sqlite3.connect(private / 'quickstart.db')
        db.execute('CREATE TABLE config(key TEXT PRIMARY KEY, value TEXT)')
        db.execute('CREATE TABLE jobs(id TEXT, status TEXT)')
        db.execute('CREATE TABLE preparations(id TEXT, state TEXT)')
        db.execute('CREATE TABLE owner_model_upkeep(job_id TEXT, state TEXT)')
        db.executemany('INSERT INTO owner_model_upkeep VALUES (?,?)', [('j3', 'pending'), ('j4', 'done')])
        db.executemany('INSERT INTO config VALUES (?,?)', [
            ('telegram', json.dumps({'enabled': True, 'user_id': 1})), ('file_roots', '[{"path": "/Users/o"}]'),
            ('file_workspace', '{}'), ('local_access', 'true')])
        db.executemany('INSERT INTO jobs VALUES (?,?)', [('j1', 'queued'), ('j2', 'running'), ('j3', 'succeeded')])
        db.executemany('INSERT INTO preparations VALUES (?,?)', [('p1', 'scheduled'), ('p2', 'delivered')])
        db.commit()
        db.close()

    def test_snapshot_keeps_engine_login_and_drops_outside_world_bindings(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / 'live', Path(folder) / 'seeds' / 'owner'
            self.make_data(source)
            summary = sandbox.snapshot_seed(source, target)
            self.assertIn('connections.json (5 of 7 slots kept)', summary['copied'])
            kept = json.loads((target / 'private' / 'connections.json').read_text())
            self.assertEqual(sorted(kept), ['api_key:openai', 'claude_code_token', 'decision_model_key', 'model_key',
                                            'search_key:brave'])
            for skipped in ('logs', 'setup-link.txt', 'browser-profile'):
                self.assertFalse((target / 'private' / skipped).exists(), skipped)
            db = sqlite3.connect(target / 'private' / 'quickstart.db')
            config = dict(db.execute('SELECT key, value FROM config'))
            self.assertEqual(json.loads(config['telegram']), {'enabled': False, 'user_id': 1})
            self.assertNotIn('file_roots', config)
            self.assertNotIn('file_workspace', config)
            self.assertEqual(dict(db.execute('SELECT id, status FROM jobs')),
                             {'j1': 'interrupted', 'j2': 'interrupted', 'j3': 'succeeded'})
            self.assertEqual(dict(db.execute('SELECT id, state FROM preparations')), {'p1': 'cancelled', 'p2': 'delivered'})
            self.assertEqual(dict(db.execute('SELECT job_id, state FROM owner_model_upkeep')), {'j3': 'expired', 'j4': 'done'})
            db.close()
            # The source is untouched.
            source_db = sqlite3.connect(source / 'private' / 'quickstart.db')
            self.assertEqual(source_db.execute("SELECT status FROM jobs WHERE id='j1'").fetchone()[0], 'queued')
            source_db.close()
            with self.assertRaises(sandbox.SandboxError):
                sandbox.snapshot_seed(source, target)                          # exists, no overwrite
            with self.assertRaises(sandbox.SandboxError):
                sandbox.snapshot_seed(source, source / 'seed', overwrite=True)  # inside the source
            with self.assertRaises(sandbox.SandboxError):
                sandbox.snapshot_seed(Path(folder) / 'empty', Path(folder) / 'x')

    def test_sandbox_environment_is_minimal_and_blocks_pyobjc(self):
        env = sandbox.sandbox_environment('/tmp/box', base={'HOME': '/Users/o', 'PATH': '/usr/bin',
                                                            'AGENTOS_DRIVE_LOCAL_ONLY': '1', 'OPENAI_API_KEY': 'k',
                                                            'TELEGRAM': 'x'}, src='/repo/src')
        self.assertEqual(env['PYTHONPATH'], f'{SANDBOX_SITE}{os.pathsep}/repo/src')
        self.assertEqual(env['AGENTOS_ENGINE_RUNS'], '/tmp/box/engine-runs')
        self.assertFalse({'AGENTOS_DRIVE_LOCAL_ONLY', 'OPENAI_API_KEY', 'TELEGRAM'} & set(env))
        self.assertIn('/opt/homebrew/bin', env['PATH'].split(os.pathsep))
        probe = ('import importlib.util\n'
                 'for name in ("WebKit", "AppKit", "objc"):\n'
                 '    try:\n        importlib.util.find_spec(name); print("found", name)\n'
                 '    except ImportError:\n        print("blocked", name)\n')
        done = subprocess.run([sys.executable, '-c', probe], capture_output=True, text=True,
                              env={'PYTHONPATH': str(SANDBOX_SITE), 'PATH': '/usr/bin:/bin'}, timeout=30)
        self.assertEqual(done.stdout.split(), ['blocked', 'WebKit', 'blocked', 'AppKit', 'blocked', 'objc'])

    def test_pool_uses_locked_stable_slots_and_a_seed_bound_judgment_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            seed = Path(folder) / 'seed'
            seed.mkdir()
            (seed / 'SEED.json').write_text(json.dumps({'created': 1.0}))
            started = []

            class Box:
                def __init__(self, root, seed=None, port=None, slot=None, keep=False):
                    self.slot, self.port = slot, port

                def start(self, config=None):
                    started.append((self.slot, config))

                def stop(self):
                    pass
            pool = sandbox.SandboxPool(size=2, seed=seed, root=Path(folder) / 'boxes', sandbox_factory=Box)
            other = sandbox.SandboxPool(size=2, seed=seed, root=Path(folder) / 'boxes', sandbox_factory=Box)
            with pool.sandbox('codex') as first, other.sandbox('codex') as second:
                self.assertNotEqual(first.slot, second.slot)   # a second sweep never shares a slot
                self.assertNotIn(first.port, LIVE_PORTS)
            pool.store_judgment(0, 'codex', {'decision_route': '{}'})
            with pool.sandbox('codex') as box:
                self.assertEqual(box.cached, {'decision_route': '{}'})
            self.assertEqual(started[-1], (0, {'decision_route': '{}'}))
            self.assertIsNone(pool.cached_judgment(0, 'claude-code'))
            (seed / 'SEED.json').write_text(json.dumps({'created': 2.0}))    # a new snapshot invalidates it
            self.assertIsNone(pool.cached_judgment(0, 'codex'))
            pool.forget_judgment(0, 'codex')
            self.assertFalse(pool._cache_path(0, 'codex').exists())

    def test_sandbox_copies_the_seed_into_its_slot_and_applies_cached_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            seed = Path(folder) / 'seed'
            self.make_data(seed)
            box = sandbox.Sandbox(Path(folder) / 'boxes', seed=seed, port=18950, slot=3, python='/usr/bin/true')
            box.start(config={'decision_route': '{"transport": "off"}'})
            box.process.wait(timeout=10)
            self.assertEqual(box.data, Path(folder) / 'boxes' / 'slot-3')
            self.assertEqual(box.read_config(['decision_route', 'local_access']),
                             {'decision_route': '{"transport": "off"}', 'local_access': 'true'})
            box.stop()
            self.assertFalse(box.data.exists())

    def test_ports_never_collide_with_the_live_server(self):
        for _ in range(3):
            port = sandbox.free_port(start=8786, end=8800)
            self.assertNotIn(port, LIVE_PORTS)
            self.assertNotIn(port + 1, LIVE_PORTS)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(sandbox.SandboxError):
                sandbox.Sandbox(folder, port=8787).start()
            with self.assertRaises(ValueError):
                sandbox.SandboxPool(size=0, root=folder)


class RedactionTest(unittest.TestCase):
    def test_judge_prompt_text_loses_stored_secret_values_and_credential_shapes(self):
        from agentos_eval.redaction import Redactor, secret_values
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'private').mkdir()
            (Path(folder) / 'private' / 'connections.json').write_text(json.dumps({'claude_code_token': 'owner-token-12345',
                                                                                  'short': 'abc'}))
            values = secret_values([folder, Path(folder) / 'missing'])
            self.assertEqual(values, {'owner-token-12345'})
            redact = Redactor(values)
            text = redact('내 토큰은 owner-token-12345 이고 키는 sk-abcdefghijklmnop, password: hunter22 야')
            self.assertNotIn('owner-token-12345', text)
            self.assertNotIn('sk-abcdefghijklmnop', text)
            self.assertNotIn('hunter22', text)
            self.assertIn('[redacted]', text)
            self.assertEqual(redact('점심은 김치찌개'), '점심은 김치찌개')


class CliTest(unittest.TestCase):
    def test_judge_key_comes_from_environment_or_keychain_only_for_this_process(self):
        env = {'OPENAI_API_KEY': 'from-env'}
        self.assertEqual(cli.ensure_judge_key('openai/gpt-5.4-mini', env, keychain=lambda _: 'x'), 'environment')
        env = {}
        self.assertEqual(cli.ensure_judge_key('anthropic/claude-x', env, keychain=lambda provider: f'kc-{provider}'),
                         'keychain')
        self.assertEqual(env, {'ANTHROPIC_API_KEY': 'kc-anthropic'})
        self.assertEqual(cli.ensure_judge_key('none', {}), 'none')
        with self.assertRaises(SystemExit):
            cli.ensure_judge_key('openai/gpt-5.4-mini', {}, keychain=lambda _: '')

    def test_keychain_read_uses_security_without_logging(self):
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout='secret\n', stderr='')
        self.assertEqual(cli.keychain_secret('openai', runner=run), 'secret')
        self.assertEqual(calls[0][:2], ['/usr/bin/security', 'find-generic-password'])

    def test_scenario_listing_hides_local_scenario_text(self):
        with tempfile.TemporaryDirectory() as home:
            (Path(home) / 'scenarios').mkdir()
            (Path(home) / 'scenarios' / 'mine.json').write_text(json.dumps({'id': 'owner-private', 'title': '비밀 제목',
                                                                             'turns': ['x']}))
            from io import StringIO
            from unittest import mock
            out = StringIO()
            with mock.patch.dict(os.environ, {'AGENTOS_EVAL_HOME': home}), mock.patch('sys.stdout', out):
                cli.main(['scenarios'])
            self.assertIn('owner-private', out.getvalue())
            self.assertNotIn('비밀 제목', out.getvalue())


class BoundaryTest(unittest.TestCase):
    def test_runtime_never_imports_the_eval_harness(self):
        for path in (ROOT / 'src' / 'personal_agent').rglob('*.py'):
            text = path.read_text(encoding='utf-8')
            self.assertNotIn('inspect_ai', text, path.name)
            self.assertNotIn('agentos_eval', text, path.name)

    def test_inspect_is_an_eval_only_pinned_dependency(self):
        requirements = (ROOT / 'evals' / 'requirements.txt').read_text()
        self.assertIn('inspect-ai==', requirements)
        self.assertNotIn('inspect', (ROOT / 'pyproject.toml').read_text().split('[project.optional-dependencies]')[0])


if __name__ == '__main__':
    unittest.main()

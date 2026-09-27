"""#685: the Judgment AI qualification runs as a background job, not inside the Main AI switch.

Evidence class: deterministic unit tests with a fake clock and the fake
subscription CLIs of tests/test_decision_routes.py (a fake ``subprocess.run``
shaped after Codex 0.153.4 / Claude Code 2.1.280 machine output).  The
claimed job runs synchronously through an injected ``spawn``.  No live
provider, CLI, account or credential is used.
"""
import os
from pathlib import Path

from personal_agent.decision_qualification import CASE_IDS
from personal_agent.decision_routes import (JOB_CANCELLED, JOB_FAILED, JOB_PASSED, JOB_QUEUED, JOB_RUNNING,
                                            MODE_FOLLOW, QUALIFICATION_JOBS, DecisionRouteError)
from test_decision_routes import CliRunner, ServiceFixture, careless, oracle


class FakeClock:
    def __init__(self, now=1_000.0):
        self.now = now

    def __call__(self):
        self.now += 1.0
        return self.now


class QualificationJobTests(ServiceFixture):
    def setUp(self):
        super().setUp()
        self.clock = FakeClock()

    def service(self, runner=None, **kwargs):
        service = super().service(runner=runner, **kwargs)
        service.decision_routes.clock = self.clock
        service.decision_routes.spawn = lambda run: run()
        return service

    def judgments(self, name='claude'):
        return [call for call in self.runner.calls if os.path.basename(call['argv'][0]) == name
                and ('--output-schema' in call['argv'] or '--json-schema' in call['argv'])]

    def job(self, service):
        return service.decision_routes.qualification()

    def follow_claude(self, service):
        service.activate_main_ai({'route': 'claude-code'})
        self.assertTrue(service.run_due_qualification())
        self.assertEqual(self.job(service)['state'], JOB_PASSED)
        return self.store.config('decision_route')

    # -- AC1: the switch returns immediately; Settings shows the job -----------
    def test_the_switch_returns_before_any_judgment_call_and_the_work_loop_runs_it(self):
        service = self.service()
        result = service.activate_main_ai({'route': 'claude-code'})
        self.assertEqual(service.main_ai.current(), 'claude-code')
        self.assertEqual(result['judgment']['state'], 'queued')
        self.assertEqual(self.judgments(), [], 'no qualification call inside the switch request')
        self.assertIsNone(self.store.config('decision_route'), 'nothing is committed before a pass')
        status = result['decision_route']
        self.assertEqual((status['qualification']['state'], status['qualification']['main']), (JOB_QUEUED, 'claude-code'))
        self.assertEqual(status['effective']['state'], 'checking')
        self.assertIn('대기 중', status['effective']['text'])
        # One work-loop tick claims and runs it.
        self.assertTrue(service.run_due_qualification())
        job = self.job(service)
        self.assertEqual(job['state'], JOB_PASSED)
        self.assertLess(job['queued_at'], job['started_at'])
        self.assertLess(job['started_at'], job['finished_at'])
        self.assertEqual(job['step']['model'], 'haiku')
        self.assertEqual(len(self.judgments()), len(CASE_IDS))
        route = self.store.config('decision_route')
        self.assertEqual((route['mode'], route['main'], route['requested_model']), (MODE_FOLLOW, 'claude-code', 'haiku'))
        self.assertEqual(service.decision_routes.status()['effective']['state'], 'active')
        # Nothing queued: the next tick is a config read.
        calls = len(self.runner.calls)
        self.assertFalse(service.run_due_qualification())
        self.assertEqual(len(self.runner.calls), calls)

    def test_running_progress_is_shown_in_settings(self):
        service = self.service()
        service.activate_main_ai({'route': 'claude-code'})
        seen = []
        original = service.decision_routes._job_checkpoint

        def checkpoint(job, model, case_id, index):
            original(job, model, case_id, index)
            if index == 2 and case_id != 'commit':
                seen.append(service.decision_routes.status()['effective'])
        service.decision_routes._job_checkpoint = checkpoint
        service.run_due_qualification()
        self.assertEqual(seen[0]['state'], 'checking')
        self.assertIn(f'haiku 3/{len(CASE_IDS)}', seen[0]['text'])

    # -- AC1: the previous route stays in effect until the qualification passes --
    def test_the_previous_route_keeps_answering_during_and_after_a_failed_qualification(self):
        runner = CliRunner()
        service = self.service(runner=runner)
        before = self.follow_claude(service)
        # The next qualification cannot pass: haiku and sonnet both answer carelessly.
        runner.judges.update({'haiku': careless, 'sonnet': careless})
        service.activate_main_ai({'route': 'claude-code'})
        rows, answers = [], []
        original = service.decision_routes._job_checkpoint

        def checkpoint(job, model, case_id, index):
            rows.append(self.store.config('decision_route'))
            original(job, model, case_id, index)
        service.decision_routes._job_checkpoint = checkpoint
        service.run_due_qualification()
        self.assertTrue(rows and all(row == before for row in rows), 'the row never changed while it ran')
        job = self.job(service)
        self.assertEqual((job['state'], job['failure']), (JOB_FAILED, 'no-qualified-candidate'))
        self.assertIn('현재 대화 해석 경로는 그대로', job['message'])
        self.assertEqual(self.store.config('decision_route'), before)
        # The kept route still answers (the fake CLI's haiku judges well again).
        runner.judges['haiku'] = oracle
        answers.append(self.judge(service).value)
        self.assertEqual(answers, ['retry'])

    # -- AC2: at most one job per route; a newer switch supersedes -------------
    def test_one_open_job_per_route_and_a_newer_main_supersedes_it(self):
        service = self.service()
        first = service.activate_main_ai({'route': 'claude-code'})['judgment']['job']
        again = service.activate_main_ai({'route': 'claude-code'})['judgment']['job']
        self.assertEqual(first['id'], again['id'])
        service.activate_main_ai({'route': 'codex'})
        jobs = self.store.config(QUALIFICATION_JOBS)
        self.assertEqual((jobs['follow_main:claude-code']['state'], jobs['follow_main:claude-code']['failure']),
                         (JOB_CANCELLED, 'superseded'))
        self.assertEqual(jobs['follow_main:codex']['state'], JOB_QUEUED)
        self.assertEqual([row['state'] for row in jobs.values()].count(JOB_QUEUED), 1)

    def test_a_running_job_of_an_older_main_stops_at_its_next_checkpoint(self):
        service = self.service()
        service.activate_main_ai({'route': 'claude-code'})
        original = service.decision_routes._job_checkpoint

        def checkpoint(job, model, case_id, index):
            if index == 1:
                # The owner switches again while this job runs.
                service.activate_main_ai({'route': 'codex'})
            original(job, model, case_id, index)
        service.decision_routes._job_checkpoint = checkpoint
        service.run_due_qualification()
        jobs = self.store.config(QUALIFICATION_JOBS)
        self.assertEqual((jobs['follow_main:claude-code']['state'], jobs['follow_main:claude-code']['failure']),
                         (JOB_CANCELLED, 'superseded'))
        self.assertLess(len(self.judgments()), len(CASE_IDS))
        self.assertIsNone(self.store.config('decision_route'))
        self.assertEqual(jobs['follow_main:codex']['state'], JOB_QUEUED)

    def test_an_explicit_choice_made_while_queued_wins_over_the_job(self):
        service = self.service()
        service.activate_main_ai({'route': 'claude-code'})
        service.activate_decision_route({'transport': 'off'})
        service.run_due_qualification()
        self.assertEqual((self.job(service)['state'], self.job(service)['failure']), (JOB_CANCELLED, 'superseded'))
        self.assertEqual(self.store.config('decision_route')['transport'], 'off')
        self.assertEqual(self.judgments(), [])

    def test_an_explicit_activation_is_refused_while_a_job_runs(self):
        service = self.service()
        service.activate_main_ai({'route': 'claude-code'})
        refused = []
        original = service.decision_routes._job_checkpoint

        def checkpoint(job, model, case_id, index):
            if index == 0 and not refused:
                with self.assertRaisesRegex(DecisionRouteError, '이미'):
                    service.activate_decision_route({'transport': 'off'})
                refused.append(True)
            original(job, model, case_id, index)
        service.decision_routes._job_checkpoint = checkpoint
        service.run_due_qualification()
        self.assertEqual(refused, [True])
        self.assertEqual(self.job(service)['state'], JOB_PASSED)

    # -- AC2: cancellation -------------------------------------------------------
    def test_cancelling_a_queued_job_runs_nothing(self):
        service = self.service()
        service.activate_main_ai({'route': 'claude-code'})
        status = service.cancel_decision_qualification()
        self.assertEqual((status['qualification']['state'], status['qualification']['failure']), (JOB_CANCELLED, 'cancelled'))
        self.assertFalse(service.run_due_qualification())
        self.assertEqual(self.judgments(), [])
        self.assertIsNone(self.store.config('decision_route'))
        self.assertIn('취소됨', status['effective']['text'])
        with self.assertRaises(DecisionRouteError):
            service.cancel_decision_qualification()

    def test_cancelling_a_running_job_stops_it_and_keeps_the_route(self):
        service = self.service()
        service.activate_main_ai({'route': 'claude-code'})
        original = service.decision_routes._job_checkpoint
        shown = []

        def checkpoint(job, model, case_id, index):
            if index == 2:
                shown.append(service.cancel_decision_qualification()['effective']['text'])
            original(job, model, case_id, index)
        service.decision_routes._job_checkpoint = checkpoint
        service.run_due_qualification()
        self.assertIn('취소하는 중', shown[0])
        self.assertEqual((self.job(service)['state'], self.job(service)['failure']), (JOB_CANCELLED, 'cancelled'))
        self.assertEqual(len(self.judgments()), 2, 'stopped before the third case')
        self.assertIsNone(self.store.config('decision_route'))
        # The lock was released: the owner can act again.
        self.assertEqual(service.activate_decision_route({'transport': 'off'})['mode'], 'off')

    def test_a_cancel_during_the_last_case_wins_over_the_commit(self):
        service = self.service()
        service.activate_main_ai({'route': 'claude-code'})
        original = service.decision_routes._job_checkpoint

        def checkpoint(job, model, case_id, index):
            if case_id == 'commit':
                service.cancel_decision_qualification()
            original(job, model, case_id, index)
        service.decision_routes._job_checkpoint = checkpoint
        service.run_due_qualification()
        self.assertEqual(self.job(service)['state'], JOB_CANCELLED)
        self.assertIsNone(self.store.config('decision_route'))

    # -- AC2: restart -------------------------------------------------------------
    def crash_while_running(self, service):
        """Claim the job, but the process 'dies' before the job thread runs."""
        service.decision_routes.spawn = lambda run: None
        self.assertTrue(service.run_due_qualification())
        self.assertEqual(self.job(service)['state'], JOB_RUNNING)

    def test_a_restart_requeues_a_running_job_once_then_fails_it_as_interrupted(self):
        service = self.service()
        service.activate_main_ai({'route': 'claude-code'})
        self.crash_while_running(service)
        restarted = self.service()
        self.assertEqual(restarted.decision_routes.recover_qualification(), [('follow_main:claude-code', JOB_QUEUED)])
        job = self.job(restarted)
        self.assertEqual((job['state'], job['requeued']), (JOB_QUEUED, 1))
        self.crash_while_running(restarted)
        again = self.service()
        self.assertEqual(again.decision_routes.recover_qualification(), [('follow_main:claude-code', JOB_FAILED)])
        job = self.job(again)
        self.assertEqual((job['state'], job['failure']), (JOB_FAILED, 'interrupted'))
        self.assertIn('AgentOS가 다시 시작되어 중단됨', again.decision_routes.status()['effective']['text'])
        self.assertFalse(again.run_due_qualification())
        self.assertEqual(self.judgments(), [])

    def test_a_restart_does_not_requeue_a_job_for_a_main_ai_that_is_no_longer_current(self):
        service = self.service()
        service.activate_main_ai({'route': 'claude-code'})
        self.crash_while_running(service)
        self.store.put('subscription_engine', {'id': 'codex', 'connected_at': 1,
                                               'authentication': 'owner-confirmed-official-login'})
        restarted = self.service()
        restarted.decision_routes.recover_qualification()
        jobs = self.store.config(QUALIFICATION_JOBS)
        self.assertEqual((jobs['follow_main:claude-code']['state'], jobs['follow_main:claude-code']['failure']),
                         (JOB_FAILED, 'interrupted'))

    def test_a_requeued_job_runs_and_passes_after_the_restart(self):
        service = self.service()
        service.activate_main_ai({'route': 'claude-code'})
        self.crash_while_running(service)
        restarted = self.service()
        restarted.decision_routes.recover_qualification()
        self.assertTrue(restarted.run_due_qualification())
        self.assertEqual(self.job(restarted)['state'], JOB_PASSED)
        self.assertEqual(self.store.config('decision_route')['requested_model'], 'haiku')

    # -- the work loop and Settings wiring ---------------------------------------
    def test_a_dispatch_error_never_stops_the_work_loop(self):
        service = self.service()

        def broken():
            raise RuntimeError('fixture')
        service.decision_routes.run_due_qualification = broken
        self.assertFalse(service.run_due_qualification())

    def test_the_work_loop_and_settings_are_wired(self):
        root = Path(__file__).resolve().parents[1] / 'src' / 'personal_agent'
        service_source = (root / 'quickstart_service.py').read_text(encoding='utf-8')
        start = service_source[service_source.index('    def start(self):'):]
        start = start[:start.index('self.threads=')]
        self.assertIn('self.decision_routes.recover_qualification()', start)
        self.assertIn('self.run_due_qualification()', start)
        server = (root / 'quickstart.py').read_text(encoding='utf-8')
        self.assertIn("'/api/decision-route/qualification/cancel'", server)
        app = (root / 'web' / 'app.js').read_text(encoding='utf-8')
        self.assertIn("api('/api/decision-route/qualification/cancel',{})", app)
        self.assertIn("checking:'확인 중'", app)
        self.assertIn("judgment.state==='queued'", app)

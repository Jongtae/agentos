import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

from personal_agent.delivery import DeliveryController, DeliveryError, DeliveryPlan, StateStore
from personal_agent.handoff import Candidate, Issue


class Runner:
    def __init__(self, results=None):
        self.calls=[]; self.results=list(results or [])

    def run(self, args, cwd=None, timeout=900):
        self.calls.append((list(args), Path(cwd) if cwd else None))
        return self.results.pop(0) if self.results else SimpleNamespace(returncode=0, stdout='', stderr='')


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)/'repo'; self.root.mkdir()
        source=Path(__file__).parents[1]/'delivery-plan.yaml'
        (self.root/'delivery-plan.yaml').write_text(source.read_text())
        self.state=self.root/'state.json'; self.clock=[1_700_000_000]

    def tearDown(self):
        self.temp.cleanup()

    def controller(self, runner=None):
        return DeliveryController(self.root, self.state, runner or Runner(), now=lambda: self.clock[0])

    def activate_governance_goal(self):
        plan=json.loads((self.root/'delivery-plan.yaml').read_text())
        plan['history']['documented_completed_iterations'].remove('GOV-01')
        plan['next_goal']={'id':'GOV-01','status':'active'}
        (self.root/'delivery-plan.yaml').write_text(json.dumps(plan))

    def test_packaged_delivery_plan_matches_repository_plan(self):
        root=Path(__file__).parents[1]
        self.assertEqual(json.loads((root/'delivery-plan.yaml').read_text()), json.loads((root/'src/personal_agent/delivery-plan.yaml').read_text()))

    def test_only_explicit_owner_activated_goal_can_be_selected(self):
        altered=json.loads((self.root/'delivery-plan.yaml').read_text())
        altered['history']['documented_completed_iterations'].remove('GOV-01')
        altered['next_goal']={'id':'GOV-01','status':'active'}
        (self.root/'delivery-plan.yaml').write_text(json.dumps(altered))
        plan=DeliveryPlan(self.root/'delivery-plan.yaml')
        self.assertEqual(plan.select({})['id'], 'GOV-01')
        altered['next_goal']['status']='requires-explicit-owner-approval'
        (self.root/'delivery-plan.yaml').write_text(json.dumps(altered))
        self.assertIsNone(DeliveryPlan(self.root/'delivery-plan.yaml').select({}))

    def activate_top_fixture(self):
        plan=json.loads((self.root/'delivery-plan.yaml').read_text())
        plan['next_goal']={'id':'TOP','status':'active'}
        (self.root/'delivery-plan.yaml').write_text(json.dumps(plan))

    def test_completed_foundation_preserves_deferred_site_and_selects_no_successor(self):
        controller=self.controller()
        self.assertEqual(controller.plan.next_goal()['status'], 'no-owner-activated-successor')
        self.assertIsNone(controller.plan.next_goal()['id'])
        # D-AP-01 closeout must fail closed: the heartbeat cannot select a
        # planned successor or revive the owner-deferred site.
        self.assertIsNone(controller.plan.select({}))
        self.assertIsNone(controller.plan.select({'active':'SITE-01'}))
        self.assertEqual(controller.plan.items['D-AP-01']['activation_status'], 'complete-on-merge')
        self.assertEqual(controller.plan.items['D-AP-01']['issue'], 334)
        self.assertEqual(controller.plan.items['D-AP-01']['depends_on'], ['FILE-WS-C-01'])
        self.assertEqual(controller.plan.items['SITE-01']['activation_status'], 'owner-deferred')
        self.assertNotIn('SITE-01', controller.plan.documented_completed())
        self.assertIsNone(controller.plan.data['programs']['FILE-WORKSPACE-01']['active_substep'])
        self.assertEqual(controller.plan.data['programs']['FILE-WORKSPACE-01']['status'], 'complete')
        self.assertEqual(controller.plan.data['programs']['FILE-WORKSPACE-01']['issue'], 314)
        self.assertEqual(controller.plan.items['FILE-WS-A-01']['issue'], 318)
        self.assertEqual(controller.plan.items['FILE-WS-B-01']['depends_on'], ['FILE-WS-A-01'])
        self.assertEqual(controller.plan.items['FILE-WS-C-01']['depends_on'], ['FILE-WS-B-01'])
        self.assertIn('TOP-03', controller.plan.documented_completed())
        self.assertIn('SCN-D-01', controller.plan.documented_completed())
        self.assertIn('DRIVE-TG-01', controller.plan.documented_completed())
        self.assertIn('FILE-WS-C-01', controller.plan.documented_completed())
        self.assertIn('D-AP-01', controller.plan.documented_completed())
        self.assertNotIn('DRIVE-LOCAL-OP-01', controller.plan.documented_completed())
        self.assertNotIn('SCN-I-01', controller.plan.documented_completed())

    def test_deferred_site_waits_without_external_commands(self):
        runner=Runner()
        result=self.controller(runner).run_once(dry_run=True)
        self.assertEqual(result['status'], 'awaiting-owner-activated-goal')
        self.assertEqual(runner.calls, [])
        altered=json.loads((self.root/'delivery-plan.yaml').read_text())
        altered['next_goal']={'id':'SITE-01','status':'active'}
        (self.root/'delivery-plan.yaml').write_text(json.dumps(altered))
        self.assertIsNone(DeliveryPlan(self.root/'delivery-plan.yaml').select({}))

    def test_deferred_site_active_state_is_retired_without_completion(self):
        StateStore(self.state).write({
            'active':'SITE-01', 'status':'running', 'milestone':'Product Information and Policy Site',
            'issue':313, 'issues':{'SITE-01':313}, 'last_error':'stale site work',
            'next_retry_at':self.clock[0] + 60,
        })
        result=self.controller().status()
        self.assertIsNone(result['active'])
        self.assertEqual(result['status'], 'retired-owner-deferred')
        self.assertNotIn('SITE-01', result.get('completed', []))
        self.assertNotIn('issues', result)
        persisted=StateStore(self.state).read()
        self.assertEqual(persisted['status'], 'retired-owner-deferred')
        self.assertNotIn('active', persisted)
        self.assertNotIn('last_error', persisted)

    def test_deferred_site_blocked_state_is_retired_without_completion(self):
        StateStore(self.state).write({
            'active':'SITE-01', 'blocked':'SITE-01', 'status':'blocked-validation-failed',
            'milestone':'Product Information and Policy Site', 'issue':313,
            'issues':{'SITE-01':313}, 'last_error':'site retry',
            'next_retry_at':self.clock[0] + 60,
        })
        result=self.controller().status()
        self.assertIsNone(result['active'])
        self.assertNotIn('blocked', result)
        self.assertEqual(result['status'], 'retired-owner-deferred')
        self.assertNotIn('issues', result)
        self.assertNotIn('last_error', result)

    def test_deferred_site_retirement_preserves_another_active_goal_metadata(self):
        StateStore(self.state).write({
            'active':'GOV-01', 'status':'running', 'milestone':'Autonomous Goal Governance Alignment',
            'issue':168, 'issues':{'SITE-01':313, 'GOV-01':168}, 'last_error':'governance detail',
        })
        migrated=self.controller()._migrate_stale_state(StateStore(self.state).read())
        self.assertEqual(migrated['active'], 'GOV-01')
        self.assertEqual(migrated['issues'], {'GOV-01':168})
        self.assertEqual(migrated['issue'], 168)
        self.assertEqual(migrated['last_error'], 'governance detail')

    def test_file_workspace_contract_uses_the_canonical_plan_substep_ids(self):
        root=Path(__file__).parents[1]
        contract=(root/'docs'/'file-workspace-first-experience-contract.en.md').read_text()
        self.assertIn('FILE-WS-A-01', contract)
        self.assertIn('FILE-WS-B-01', contract)
        self.assertIn('FILE-WS-C-01', contract)
        self.assertNotIn('FILE-UX-', contract)

    def test_handoff_entrypoint_dispatches_only_injected_bounded_worker(self):
        self.activate_governance_goal()
        active_issue=DeliveryPlan(self.root/'delivery-plan.yaml').select({})['issue']
        class Boundary:
            def __init__(self):
                self.row=Issue(active_issue, {'agent:ready'}, authorized=True, dependencies_satisfied=True)
                self.comments=[]; self.candidate_row=None
            def issues(self): return [self.row]
            def transition(self, number, old, new):
                if self.row.queue_state()!=old:return False
                self.row.labels={new};return True
            def comment_exists(self, number, marker): return any(item[0]==marker for item in self.comments)
            def comment(self, number, marker, text): self.comments.append((marker,text))
            def claim_winner(self, number, marker): return marker==self.comments[0][0]
            def candidate(self, number): return self.candidate_row
            def execution_active(self, number, lease): return False
        seen={}; boundary=Boundary()
        def factory(repository, authorized_goals):
            seen['repository']=repository;seen['goals']=authorized_goals;return boundary
        calls=[]
        def executor(issue, feedback):
            calls.append((issue.number,feedback));boundary.candidate_row=Candidate(active_issue, 77, 'x'*40, 'main', 'success')
            return boundary.candidate_row
        controller=DeliveryController(self.root,self.state,Runner(),now=lambda:self.clock[0],
            handoff_workers={'implementer':executor},handoff_github_factory=factory)
        result=controller.handoff_tick('implementer',self.root/'handoff.json')
        self.assertEqual(result['state'],'agent:review')
        self.assertEqual(calls,[(active_issue,None)])
        self.assertTrue(seen['goals'][active_issue]['authorized'])

    def test_handoff_worker_factory_is_restricted_and_invoked(self):
        calls=[]
        class Module:
            @staticmethod
            def build(*, role, root):
                calls.append((role,root))
                return lambda issue, feedback: self.fail('no eligible issue should execute')
        class Empty:
            def issues(self): return []
        controller=DeliveryController(self.root,self.state,Runner(),now=lambda:self.clock[0],
            handoff_github_factory=lambda *_args,**_kwargs: Empty())
        with patch('personal_agent.delivery.importlib.import_module',return_value=Module):
            self.assertEqual(controller.handoff_tick('implementer',self.root/'factory.json','personal_agent.worker:build')['action'],'idle')
        self.assertEqual(calls,[('implementer',self.root.resolve())])
        with self.assertRaisesRegex(DeliveryError,'personal_agent'):
            controller.handoff_tick('implementer',self.root/'bad.json','os:system')

    def test_top_goal_stays_selectable_after_its_inventory_substep_closes(self):
        self.activate_top_fixture()
        plan=DeliveryPlan(self.root/'delivery-plan.yaml')
        self.assertIn('TOP-00', plan.documented_completed())
        self.assertEqual(plan.next_goal()['id'], 'TOP')
        self.assertEqual(plan.select({})['id'], 'TOP')

    def test_top_goal_migrates_a_documented_legacy_block_before_resuming(self):
        self.activate_top_fixture()
        StateStore(self.state).write({
            'active':'UX-05', 'blocked':'UX-05', 'status':'blocked-validation-failed',
            'issues':{'UX-05':154},
        })
        runner=Runner([SimpleNamespace(returncode=0, stdout='OPEN\n', stderr='')])
        result=self.controller(runner).run_once()
        self.assertEqual(result['status'], 'manual-governance-execution-required')
        self.assertEqual(result['active'], 'TOP')
        self.assertNotIn('blocked', result)
        self.assertIn('TOP-00', result['completed'])

    def test_no_active_goal_refuses_automatic_selection_or_issue_creation(self):
        plan={'repository':'Jongtae/personal-agentos','iterations':[{'id':'NEW','issue':99,'milestone':'test','summary':'new work'}], 'next_goal':{}}
        (self.root/'delivery-plan.yaml').write_text(json.dumps(plan))
        controller=self.controller()
        self.assertIsNone(controller.plan.select({}))
        self.assertEqual(controller.run_once(dry_run=True)['status'], 'awaiting-owner-activated-goal')
        with self.assertRaisesRegex(DeliveryError, 'cannot create an issue'):
            controller._ensure_issue({'id':'NEW','milestone':'test','summary':'new work'}, {}, False)

    def test_closed_issue_does_not_complete_or_select_successor(self):
        self.activate_governance_goal()
        runner=Runner([SimpleNamespace(returncode=0, stdout='CLOSED\n', stderr='')])
        StateStore(self.state).write({'active':'GOV-01','issues':{'GOV-01':168}})
        result=self.controller(runner).reconcile()
        self.assertEqual(result['status'], 'completion-evidence-required')
        self.assertNotIn('GOV-01', result.get('completed', []))
        self.assertEqual(result['active'], 'GOV-01')

    def test_completion_requires_current_evidence_matrix(self):
        controller=self.controller()
        item=controller.plan.items['GOV-01']
        with self.assertRaisesRegex(DeliveryError, 'Completion rejected'):
            controller._complete(item, {'issues':{'GOV-01':168}})
        with self.assertRaisesRegex(DeliveryError, 'Completion rejected'):
            controller._complete(item, {'issues':{'GOV-01':168}, 'evidence_audit':{
                'merged_pr':'https://example.test/pr/1', 'required_ci':'passed', 'closeout':True, 'requirements':'mapped'}})

    def test_run_never_launches_worker_or_merges(self):
        self.activate_governance_goal()
        runner=Runner([SimpleNamespace(returncode=0, stdout='OPEN\n', stderr='')])
        result=self.controller(runner).run_once(dry_run=False)
        self.assertEqual(result['status'], 'manual-governance-execution-required')
        self.assertFalse(any(call[0][0] in {'codex','git'} for call in runner.calls))

    def test_blocked_goal_does_not_retry_or_contact_github_without_changed_condition(self):
        self.activate_governance_goal()
        runner=Runner()
        StateStore(self.state).write({'active':'GOV-01','blocked':'GOV-01','status':'blocked-blocked-approval','issues':{'GOV-01':168}})
        result=self.controller(runner).run_once()
        self.assertEqual(result['status'], 'blocked-awaiting-changed-condition')
        self.assertEqual(runner.calls, [])

    def test_release_helper_fails_closed_without_mutation(self):
        runner=Runner()
        item={'id':'REL','milestone':'test','summary':'release'}
        result=self.controller(runner)._run_release(item,{})
        self.assertEqual(result['status'], 'blocked-manual-governance-execution-required')
        self.assertEqual(runner.calls, [])

    def test_schedule_cannot_create_a_second_delivery_loop(self):
        with self.assertRaisesRegex(DeliveryError, 'one existing goal-resume heartbeat'):
            self.controller().install_schedule()

    def test_state_does_not_persist_sensitive_or_unreviewed_evidence(self):
        saved=StateStore(self.state).write({'active':'GOV-01','status':'blocked','api_key':'secret','evidence_audit':{'requirements':'private'}})
        self.assertEqual(saved, {'active':'GOV-01','status':'blocked'})


if __name__ == '__main__':
    unittest.main()

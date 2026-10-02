"""OWNER-MODEL-03 (#805 phase 1): asynchronous, minimised post-Work owner-model upkeep.

#918 slice (a) (owner decision 2026-09-30): a kept proposal is saved at once
as current Memory attributed to the Work, and the owner is told with an undo
(``test_memory_save_undo``); the per-fact #597 judgment and the candidate
ask are no longer on this path.

Evidence class: model-free unit and service tests.  A scripted
``FixtureDecisionEngine`` plays the Judgment AI (the proposal ``structured``
call); the real ``AgentService`` tick, ``QuickStore`` Memory paths and the
Work loop of ``tests/test_orchestrator.Harness`` run unchanged.  No live model.
"""
import json
import threading
import time
import unittest

from personal_agent import owner_model as om
from personal_agent.agent_runtime import MEMORY_OWNER
from personal_agent.decision import (OUTCOME_DECIDED, BinaryDecision, FixtureDecisionEngine, StructuredDecision,
                                     fixture_confidence)
from personal_agent.quickstart_service import AgentService

from test_orchestrator import Harness

SECRET = 'plain-stored-secret-805'


def proposal(key, content, *, kind='stated', category='place', evidence='the owner said so', supersedes=''):
    return {'category': category, 'kind': kind, 'memory_key': key, 'content': content, 'evidence': evidence,
            'supersedes_key': supersedes}


class Upkeep(Harness):
    def setUp(self):
        super().setUp()
        self.answers, self.explicit, self.facts, self.judged = [], [], [], []

        def structured(context, question, schema):
            if context.purpose != om.PURPOSE:
                return None  # no plan: the default worker runs the raw request
            self.facts.append((context, question, schema))
            if not self.answers:
                return None
            return StructuredDecision(OUTCOME_DECIDED, {'proposals': self.answers.pop(0)}, fixture_confidence(0.9))

        def judge(context, proposition):
            if context.purpose == 'goal-reached':
                return BinaryDecision(OUTCOME_DECIDED, True, fixture_confidence())
            if context.purpose == 'explicit-memory-fact':
                self.judged.append(context)
                if self.explicit:
                    return BinaryDecision(OUTCOME_DECIDED, self.explicit.pop(0), fixture_confidence())
            return None
        self.fixture = FixtureDecisionEngine(structured=structured, judge=judge)
        self.service.use_decision_engine(self.fixture)
        # The run is off-thread in production; here it runs in place so each test reads its result.
        self.service.owner_model_spawn = lambda target: target()

    def finished(self, text, answer='an answer', status='succeeded'):
        """A settled Work with one pending upkeep, as the success path leaves it."""
        job = self.store.enqueue(text, f'om-{time.time()}-{text}')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status=?,response=?,provider='subscription',model='codex' WHERE id=?",
                       (status, answer, job))
            self.service.owner_model.enqueue(db, job)
        return job

    def upkeep_rows(self):
        with self.store.db() as db:
            return {row['job_id']: dict(row) for row in db.execute('SELECT * FROM owner_model_upkeep')}

    def evidence(self, job):
        with self.store.db() as db:
            rows = db.execute('SELECT status,detail FROM tool_events WHERE job_id=? AND tool=?',
                              (job, om.EVENT_TOOL)).fetchall()
        return [(row['status'], json.loads(row['detail'])) for row in rows]

    def structured_calls(self):
        return [item for item in self.fixture.asked if item[0] == 'structured' and item[1].purpose == om.PURPOSE]


class Trigger(Upkeep):
    def test_a_finished_work_enqueues_exactly_one_upkeep(self):
        job, row = self.run_work('나는 판교에서 일해')
        self.assertEqual((row['status'], row['provider']), ('succeeded', 'subscription'))
        self.assertEqual(list(self.upkeep_rows()), [job])
        self.assertEqual(self.upkeep_rows()[job]['state'], om.STATE_PENDING)
        with self.store.db() as db:
            self.assertFalse(self.service.owner_model.enqueue(db, job), 'idempotent per Work')
        self.assertEqual(len(self.upkeep_rows()), 1)
        self.assertEqual(self.structured_calls(), [], 'nothing runs on the request path')

    def test_failed_cancelled_unknown_command_preparation_and_continuation_do_not_enqueue(self):
        eligible = AgentService.owner_model_eligible
        job = {'request_key': 'k'}
        self.assertTrue(eligible(job, 'succeeded', 'subscription'))
        self.assertTrue(eligible(job, 'partial', 'openai'))
        for outcome in ('failed', 'cancelled', 'unknown', 'interrupted'):
            self.assertFalse(eligible(job, outcome, 'subscription'), outcome)
        self.assertFalse(eligible(job, 'succeeded', 'builtin'), 'a rule/command reply: no worker AI ran')
        from personal_agent import preparations as prep
        from personal_agent.context_observations import continuation_key
        self.assertFalse(eligible({'request_key': prep.REQUEST_KEY_PREFIX + 'p1:1'}, 'succeeded', 'subscription'))
        self.assertFalse(eligible({'request_key': continuation_key('r1')}, 'succeeded', 'subscription'))

    def test_a_command_and_a_failed_work_leave_no_upkeep(self):
        self.run_work('/note 판교 사무실 주소 메모')
        self.engine.fail = [ValueError('worker failed')] * 3
        _job, row = self.run_work('나는 판교에서 일해')
        self.assertEqual(row['status'], 'failed')
        self.assertEqual(self.upkeep_rows(), {})

    def test_paused_upkeep_enqueues_nothing(self):
        self.service.owner_model_request({'operation': 'set', 'enabled': False})
        self.run_work('나는 판교에서 일해')
        self.assertEqual(self.upkeep_rows(), {})


class Tick(Upkeep):
    def test_nothing_pending_makes_no_call(self):
        self.assertFalse(self.service.run_owner_model_upkeep())
        self.assertEqual(self.structured_calls(), [])

    def test_the_tick_runs_only_when_no_work_is_queued_or_running(self):
        job = self.finished('나는 판교에서 일해')
        other = self.store.enqueue('다른 요청', 'om-other')
        self.assertFalse(self.service.run_owner_model_upkeep())
        self.assertEqual(self.structured_calls(), [])
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (other,))
        self.assertFalse(self.service.run_owner_model_upkeep())
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='succeeded' WHERE id=?", (other,))
        self.answers = [[]]
        self.assertTrue(self.service.run_owner_model_upkeep())
        self.assertEqual(len(self.structured_calls()), 1)
        self.assertEqual(self.upkeep_rows()[job]['state'], om.STATE_DONE)
        self.assertFalse(self.service.run_owner_model_upkeep(), 'a done upkeep never runs again')

    def test_one_upkeep_per_tick_the_newest_first(self):
        """#876: the live conversation's upkeep runs before an older one still pending."""
        first, second = self.finished('나는 판교에서 일해'), self.finished('나는 매주 월요일 회의가 있어')
        with self.store.db() as db:
            db.execute('UPDATE owner_model_upkeep SET created=? WHERE job_id=?', (time.time() - 120, first))
        self.answers = [[], []]
        self.assertTrue(self.service.run_owner_model_upkeep())
        rows = self.upkeep_rows()
        self.assertEqual((rows[first]['state'], rows[second]['state']), (om.STATE_PENDING, om.STATE_DONE))
        self.assertEqual(self.structured_calls()[0][1].work_id, second)

    def test_a_backlog_older_than_the_conversation_expires_instead_of_asking_late(self):
        """#876: a day-old Work never becomes a memory ask after the conversation moved on."""
        self.assertLessEqual(om.MAX_PENDING_SECONDS, 3600)
        stale, fresh = self.finished('괜찮았어'), self.finished('나는 판교에서 일해')
        with self.store.db() as db:
            db.execute('UPDATE owner_model_upkeep SET created=? WHERE job_id=?', (time.time() - 26 * 3600, stale))
        self.answers = [[proposal('profile.place.work', '판교')]]
        self.explicit = [False]
        self.assertTrue(self.service.run_owner_model_upkeep())
        self.assertTrue(self.service.run_owner_model_upkeep())
        rows = self.upkeep_rows()
        self.assertEqual((rows[fresh]['state'], rows[stale]['state']), (om.STATE_DONE, om.STATE_EXPIRED))
        self.assertEqual([call[1].work_id for call in self.structured_calls()], [fresh])
        self.assertEqual(self.evidence(stale), [(om.EVENT_EXPIRED, {'reason': 'expired'})])

    def test_the_facts_are_the_request_answer_profile_and_clock(self):
        self.store.save_memory('profile.place.home', '분당', work_id='w0')
        job = self.finished('나는 판교에서 일해', answer='판교 근처를 찾아봤습니다')
        self.answers = [[]]
        self.service.run_owner_model_upkeep()
        context, question, schema = self.facts[0]
        self.assertEqual(context.work_id, job)
        self.assertEqual(context.facts['owner_request'], '나는 판교에서 일해')
        self.assertEqual(context.facts['final_answer_excerpt'], '판교 근처를 찾아봤습니다')
        self.assertIn('profile.place.home: 분당', context.facts['owner_profile'])
        self.assertIn('local_time', context.facts['clock'])
        self.assertEqual(question, om.QUESTION)
        item = schema['properties']['proposals']['items']['properties']
        self.assertEqual(item['category']['enum'], list(om.CATEGORIES))
        self.assertEqual(item['kind']['enum'], ['stated', 'inferred'])
        self.assertIn('model-stated', question)
        self.assertIn('remembered like a stated fact and the owner is told with an undo', question)

    def test_a_stored_secret_never_reaches_the_judgment_facts(self):
        self.store.secret('telegram_token', SECRET)
        self.store.save_memory('profile.identity.note', f'토큰 {SECRET}', work_id='w0')
        self.finished(f'나는 판교에서 일해 {SECRET}', answer=f'확인했습니다 {SECRET} sk-abcdefghijklmnopqrstuvwx')
        self.answers = [[proposal('profile.place.work', '판교')]]
        self.explicit = [True]
        self.service.run_owner_model_upkeep()
        rendered = self.facts[0][0].render() + ''.join(context.render() for context in self.judged)
        self.assertNotIn(SECRET, rendered)
        self.assertNotIn('sk-abcdefghijklmnopqrstuvwx', rendered)
        self.assertIn('[redacted]', self.facts[0][0].facts['owner_request'])

    def test_an_unavailable_judgment_stores_nothing_and_says_so(self):
        job = self.finished('나는 판교에서 일해')
        self.assertTrue(self.service.run_owner_model_upkeep())
        self.assertEqual(self.upkeep_rows()[job]['state'], om.STATE_UNAVAILABLE)
        [(status, detail)] = self.evidence(job)
        self.assertEqual(status, om.EVENT_UNAVAILABLE)
        self.assertEqual(self.store.memory_candidates(MEMORY_OWNER), [])

    def test_an_old_pending_upkeep_expires_without_a_call(self):
        job = self.finished('나는 판교에서 일해')
        with self.store.db() as db:
            db.execute('UPDATE owner_model_upkeep SET created=? WHERE job_id=?', (time.time() - om.MAX_PENDING_SECONDS - 60, job))
        self.assertTrue(self.service.run_owner_model_upkeep())
        self.assertEqual(self.upkeep_rows()[job]['state'], om.STATE_EXPIRED)
        self.assertEqual(self.structured_calls(), [])
        self.assertEqual(self.evidence(job), [(om.EVENT_EXPIRED, {'reason': 'expired'})])


class Apply(Upkeep):
    def test_a_stated_fact_becomes_memory_linked_to_the_work_without_a_judgment(self):
        job = self.finished('나는 판교에서 일해')
        self.answers = [[proposal('profile.place.work', '판교')]]
        self.service.run_owner_model_upkeep()
        [memory] = self.store.memories(MEMORY_OWNER, key_prefix='profile.')
        self.assertEqual((memory['memory_key'], memory['content']), ('profile.place.work', '판교'))
        with self.store.db() as db:
            row = db.execute('SELECT work_key,candidate_id FROM memories WHERE id=?', (memory['id'],)).fetchone()
        self.assertEqual(row['work_key'], self.store._work_binding(job), 'provenance links back to the Work')
        self.assertIsNone(row['candidate_id'], '#918: no candidate row')
        self.assertEqual(self.store.memory_candidates(MEMORY_OWNER, include_decided=True), [])
        self.assertEqual(self.judged, [], '#918: no per-fact #597 judgment call')
        [(status, detail)] = self.evidence(job)
        self.assertEqual(status, om.EVENT_RECORDED)
        self.assertNotIn('memory_requests', detail)
        self.assertEqual([(item['memory_key'], item['kind'], item['outcome'], item['memory_id'], item['auto_saved'])
                          for item in detail['applied']],
                         [('profile.place.work', 'stated', 'memory', memory['id'], True)])
        # #804: a saved profile fact is not a lookup exclusion.
        from personal_agent.agent_runtime import work_written_values
        self.assertNotIn('판교', work_written_values(self.store, job))

    def test_a_credential_shaped_or_stored_secret_value_is_never_saved(self):
        """#918 review P1: the upkeep write passes the same secret gate as the worker's save."""
        self.store.secret('telegram_token', 'LEAKYSECRET0918VALUE')
        job = self.finished('나는 판교에서 일해')
        self.answers = [[proposal('profile.api', 'sk-proj-abcdefghijklmnopqrstuvwxyz123456', category='preference'),
                         proposal('profile.note', 'token LEAKYSECRET0918VALUE', category='preference'),
                         proposal('profile.place.work', '판교')]]
        self.service.run_owner_model_upkeep()
        self.assertEqual([row['content'] for row in self.store.memories(MEMORY_OWNER)], ['판교'])
        [(_status, detail)] = self.evidence(job)
        self.assertEqual([item['reason'] for item in detail['dropped']], ['secret-shaped-value', 'secret-shaped-value'])
        text = json.dumps(detail, ensure_ascii=False)
        for raw in ('sk-proj', 'LEAKYSECRET0918VALUE', 'profile.api'):
            self.assertNotIn(raw, text)

    def test_a_stated_value_the_owner_did_not_say_is_saved_too(self):
        """#918: the value-coverage gate is off this path; the owner's notice with undo is the correction."""
        job = self.finished('나는 판교에서 일해')
        self.answers = [[proposal('profile.place.work', '서울 강남')]]
        self.service.run_owner_model_upkeep()
        self.assertEqual([row['content'] for row in self.store.memories(MEMORY_OWNER)], ['서울 강남'])
        [(_status, detail)] = self.evidence(job)
        self.assertEqual((detail['applied'][0]['outcome'], detail['applied'][0].get('refused_because')), ('memory', None))

    def test_an_inference_is_saved_with_its_kind_recorded(self):
        job = self.finished('나는 판교에서 일해')
        self.answers = [[proposal('profile.routine.commute', '평일 판교 출근', kind='inferred', category='routine')]]
        self.service.run_owner_model_upkeep()
        [memory] = self.store.memories(MEMORY_OWNER)
        self.assertEqual(memory['memory_key'], 'profile.routine.commute')
        self.assertEqual(self.store.memory_candidates(MEMORY_OWNER, work_id=job), [])
        self.assertEqual(self.judged, [], 'no #597 judgment is asked')
        [(_status, detail)] = self.evidence(job)
        self.assertEqual((detail['applied'][0]['kind'], detail['applied'][0]['outcome']), ('inferred', 'memory'))

    def test_out_of_enum_oversized_and_non_profile_proposals_are_dropped(self):
        job = self.finished('나는 판교에서 일해')
        self.answers = [[proposal('profile.health.condition', '판교', category='health'),
                         proposal('profile.place.work', '판교', kind='guess'),
                         proposal('home', '판교'),
                         proposal('profile.place.office', 'x' * 201),
                         proposal('profile.place.other', '판교', evidence=''),
                         proposal('profile.place.old', '판교', supersedes='home'),
                         'not an object']]
        self.service.run_owner_model_upkeep()
        self.assertEqual(self.store.memories(MEMORY_OWNER), [])
        self.assertEqual(self.store.memory_candidates(MEMORY_OWNER), [])
        [(_status, detail)] = self.evidence(job)
        self.assertEqual(detail['applied'], [])
        self.assertEqual([item['reason'] for item in detail['dropped']],
                         ['category', 'kind', 'key', 'content', 'evidence', 'over-limit', 'over-limit'])
        self.assertNotIn('memory_key', detail['dropped'][2], 'a malformed key is not recorded')

    def test_duplicates_of_current_or_pending_values_are_dropped(self):
        self.store.save_memory('profile.place.work', '판교', work_id='w0')
        earlier = self.finished('earlier')
        self.store.save_memory_candidate(earlier, 'profile.place.home', '분당')
        with self.store.db() as db:
            db.execute('DELETE FROM owner_model_upkeep WHERE job_id=?', (earlier,))
        job = self.finished('나는 판교에서 일하고 분당에 살아')
        self.answers = [[proposal('profile.place.work', ' 판교 '), proposal('profile.place.home', '분당'),
                         proposal('profile.place.gym', '분당'), proposal('profile.place.pool', '분당')]]
        self.explicit = [False]
        self.service.run_owner_model_upkeep()
        [(_status, detail)] = self.evidence(job)
        self.assertEqual([item['memory_key'] for item in detail['applied']], ['profile.place.gym'])
        self.assertEqual([(item['key_digest'], item['reason']) for item in detail['dropped']],
                         [(om.key_digest('profile.place.work'), 'duplicate'),
                          (om.key_digest('profile.place.home'), 'duplicate'),
                          (om.key_digest('profile.place.pool'), 'duplicate')])

    def test_a_current_value_under_another_key_is_a_duplicate(self):
        # #805 review P2-3: the same content under a different key would be a second canonical row.
        self.store.save_memory('profile.place.work', '판교', work_id='w0')
        job = self.finished('나는 판교에서 일해')
        self.answers = [[proposal('profile.place.office', '판교')]]
        self.explicit = [True]
        self.service.run_owner_model_upkeep()
        self.assertEqual([row['memory_key'] for row in self.store.memories(MEMORY_OWNER)], ['profile.place.work'])
        self.assertEqual(self.judged, [], 'a duplicate is dropped before any judgment')
        [(_status, detail)] = self.evidence(job)
        self.assertEqual(detail['dropped'], [{'key_digest': om.key_digest('profile.place.office'), 'reason': 'duplicate'}])

    def test_what_the_work_already_wrote_is_a_duplicate(self):
        # #805 review P2-3: the worker's own save_memory (Memory or candidate, any key) is not written again.
        job = self.finished('나는 판교에서 일하고 분당에 살아')
        self.store.save_memory('home', '분당', work_id=job)
        self.store.save_memory_candidate(job, 'work', '판교')
        self.answers = [[proposal('profile.place.work', '판교'), proposal('profile.place.home', '분당')]]
        self.explicit = [True, True]
        self.service.run_owner_model_upkeep()
        self.assertEqual(self.store.memories(MEMORY_OWNER, key_prefix='profile.'), [])
        [(_status, detail)] = self.evidence(job)
        self.assertEqual([item['reason'] for item in detail['dropped']], ['duplicate', 'duplicate'])

    def test_what_the_work_already_noted_is_asked_once(self):
        """#836: upkeep sees what the same owner message already noted, and adds nothing under a key it covers."""
        job = self.finished('할인 초밥으로 저녁을 먹었어')
        self.store.save_memory_candidate(job, 'profile.preference.sushi', '할인 초밥')
        self.answers = [[proposal('profile.preference.sushi', '할인하는 초밥을 즐겨 먹음', kind='inferred',
                                  category='preference'),
                         proposal('profile.routine.dinner', '저녁은 주로 밖에서', kind='inferred', category='routine')]]
        self.service.run_owner_model_upkeep()
        context = self.facts[0][0]
        self.assertEqual(context.facts['already_noted'], '할인 초밥')
        self.assertIn('already_noted', om.QUESTION)
        [(_status, detail)] = self.evidence(job)
        self.assertEqual(detail['dropped'], [{'key_digest': om.key_digest('profile.preference.sushi'), 'reason': 'duplicate'}])
        self.assertEqual([row['memory_key'] for row in self.store.memory_candidates()], ['profile.preference.sushi'])
        self.assertEqual([row['memory_key'] for row in self.store.memories(MEMORY_OWNER)], ['profile.routine.dinner'],
                         '#918: the kept proposal is saved at once')

    def test_nothing_noted_is_said_as_none(self):
        self.finished('나는 판교에서 일해')
        self.answers = [[]]
        self.service.run_owner_model_upkeep()
        self.assertEqual(self.facts[0][0].facts['already_noted'], 'none')

    def test_a_contradiction_supersedes_and_keeps_the_previous_value_for_undo(self):
        """#918: a replacement is never silent - the notice says 전에는 and the undo restores it."""
        kept = self.store.save_memory('profile.place.work', '서울역', work_id='w0')
        job = self.finished('나는 판교에서 일해')
        self.answers = [[proposal('profile.place.work', '판교', supersedes='profile.place.work')]]
        self.service.run_owner_model_upkeep()
        [memory] = self.store.memories(MEMORY_OWNER)
        self.assertEqual((memory['content'], memory['supersedes']), ('판교', kept['id']))
        [(_status, detail)] = self.evidence(job)
        self.assertEqual((detail['applied'][0]['outcome'], detail['applied'][0]['superseded'],
                          detail['applied'][0]['supersedes_key']), ('memory', True, 'profile.place.work'))
        receipt = self.store.retract_memory(MEMORY_OWNER, memory['id'], memory['content_digest'])
        self.assertEqual(receipt['restored']['id'], kept['id'])
        self.assertEqual([row['content'] for row in self.store.memories(MEMORY_OWNER)], ['서울역'])


class Budget(Upkeep):
    def test_the_daily_cap_stops_calls(self):
        self.service.owner_model_request({'operation': 'set', 'daily_calls': 1})
        # Newest first (#876): the later Work runs, the earlier one waits.
        second, first = self.finished('나는 판교에서 일해'), self.finished('나는 분당에 살아')
        self.answers = [[], []]
        self.assertTrue(self.service.run_owner_model_upkeep())
        self.assertFalse(self.service.run_owner_model_upkeep())
        self.assertEqual(len(self.structured_calls()), 1)
        self.assertEqual(self.upkeep_rows()[second]['state'], om.STATE_PENDING, 'it waits for the window')
        self.assertEqual(self.service.owner_model_request()['calls_last_24h'], 1)
        with self.store.db() as db:
            db.execute('UPDATE owner_model_upkeep SET claimed=? WHERE job_id=?', (time.time() - om.WINDOW_SECONDS - 1, first))
        self.assertTrue(self.service.run_owner_model_upkeep())

    def test_the_pause_switch_stops_calls(self):
        self.finished('나는 판교에서 일해')
        self.service.owner_model_request({'operation': 'set', 'enabled': False})
        self.assertFalse(self.service.run_owner_model_upkeep())
        self.assertEqual(self.structured_calls(), [])
        status = self.service.owner_model_request({'operation': 'set', 'enabled': True})
        self.assertEqual((status['enabled'], status['pending'], status['daily_calls']), (True, 1, om.DEFAULT_DAILY_CALLS))

    def test_only_the_proposal_call_counts_against_the_cap(self):
        job = self.finished('나는 판교에서 일해')
        self.answers = [[proposal('profile.place.work', '판교'), proposal('profile.place.home', '판교 근처')]]
        self.service.run_owner_model_upkeep()
        self.assertEqual(self.judged, [], '#918: no per-fact judgment calls')
        self.assertEqual(self.upkeep_rows()[job]['calls'], 1)
        self.assertEqual(self.service.owner_model_request()['calls_last_24h'], 1)

    def test_a_write_is_not_a_call_so_the_cap_does_not_hold_it(self):
        # #805 review P3a, under #918: with one call left the proposal runs; both facts are saved (writes are free).
        self.service.owner_model_request({'operation': 'set', 'daily_calls': 1})
        job = self.finished('나는 판교에서 일하고 분당에 살아')
        self.answers = [[proposal('profile.place.work', '판교'), proposal('profile.place.home', '분당')]]
        self.service.run_owner_model_upkeep()
        self.assertEqual(self.judged, [])
        [(_status, detail)] = self.evidence(job)
        self.assertEqual([(item['outcome'], item.get('refused_because')) for item in detail['applied']],
                         [('memory', None), ('memory', None)])
        self.assertEqual(self.service.owner_model_request()['calls_last_24h'], 1)

    def test_controls_are_validated(self):
        for body in ({'operation': 'set', 'enabled': 'no'}, {'operation': 'set', 'daily_calls': -1},
                     {'operation': 'set', 'daily_calls': True}, {'operation': 'drop'}):
            with self.assertRaises(ValueError):
                self.service.owner_model_request(body)


class Evidence(Upkeep):
    def test_the_run_is_recorded_on_the_source_work_without_input_text(self):
        job = self.finished('나는 판교에서 일해', answer='판교 근처 답변')
        self.answers = [[proposal('profile.place.work', '판교'), proposal('bad', 'x')]]
        self.explicit = [False]
        self.service.run_owner_model_upkeep()
        [(status, detail)] = self.evidence(job)
        self.assertEqual(status, om.EVENT_RECORDED)
        self.assertEqual((detail['decision'], detail['provider'], detail['model'], detail['confidence']),
                         ('decided', 'fixture', 'fixture', 0.9))
        self.assertEqual(detail['inputs'], {'owner_request_chars': len('나는 판교에서 일해'),
                                            'answer_chars': len('판교 근처 답변'),
                                            'profile_chars': 0, 'clock': True})
        self.assertEqual(detail['proposed'], 2)
        self.assertEqual(detail['applied'][0]['content_chars'], 2)
        text = json.dumps(detail, ensure_ascii=False)
        for raw in ('나는 판교에서 일해', '판교 근처 답변', 'the owner said so'):
            self.assertNotIn(raw, text)
        # The event is not a Work step: task events show it, step trails do not.
        from personal_agent.agent_runtime import event_trail
        with self.store.db() as db:
            rows = db.execute('SELECT tool,status,detail FROM tool_events WHERE job_id=?', (job,)).fetchall()
        self.assertEqual(event_trail([(r['tool'], r['status'], r['detail']) for r in rows])[0], [])
        self.assertIn(om.EVENT_TOOL, AgentService.LOCAL_NON_TOOL_EVENTS)


class Review(Upkeep):
    """#805 independent review findings."""

    def test_a_category_word_does_not_name_a_key(self):
        # P1: "prefer" once named every profile.preference.* key, so another preference was superseded.
        from personal_agent.agent_runtime import memory_write_refusal
        self.store.save_memory('profile.preference.drink', 'oat latte', work_id='w0')
        job = self.finished('Remember I prefer quiet cafes for work')
        approval = self.store.issue_memory_approval(job, 'Remember I prefer quiet cafes for work')
        self.assertEqual(memory_write_refusal(self.store, job, approval, 'profile.preference.drink', 'quiet cafes'),
                         'replaces-a-memory-the-request-did-not-name')
        named = self.finished('Remember my drink is cold brew now')
        approval = self.store.issue_memory_approval(named, 'Remember my drink is cold brew now')
        self.assertIsNone(memory_write_refusal(self.store, named, approval, 'profile.preference.drink', 'cold brew'),
                          'the fact word still names the key')

    def test_a_supersede_under_its_own_key_keeps_the_previous_value_for_undo(self):
        # P1 of #805 made "prefer" unable to name every preference key; under #918 the key-replacement
        # gate is off this path, and the superseded value is kept so the owner's undo restores it.
        kept = self.store.save_memory('profile.preference.drink', 'oat latte', work_id='w0')
        job = self.finished('Remember I prefer quiet cafes for work')
        self.answers = [[proposal('profile.preference.drink', 'quiet cafes', category='preference',
                                  supersedes='profile.preference.drink')]]
        self.service.run_owner_model_upkeep()
        [memory] = self.store.memories(MEMORY_OWNER)
        self.assertEqual((memory['content'], memory['supersedes']), ('quiet cafes', kept['id']))
        [(_status, detail)] = self.evidence(job)
        self.assertTrue(detail['applied'][0]['superseded'])

    def test_no_per_fact_judgment_is_asked_and_every_kept_fact_is_saved(self):
        # P2-2 under #918: nothing per fact is asked; each kept proposal is saved on its own.
        job = self.finished('나는 판교에서 일하고 분당에 살아')
        self.answers = [[proposal('profile.place.work', '판교'), proposal('profile.place.home', '분당')]]
        self.service.run_owner_model_upkeep()
        self.assertEqual(self.judged, [])
        self.assertEqual(sorted(row['memory_key'] for row in self.store.memories(MEMORY_OWNER)),
                         ['profile.place.home', 'profile.place.work'])
        self.assertEqual(self.store.memory_candidates(MEMORY_OWNER, work_id=job), [])
        [(_status, detail)] = self.evidence(job)
        self.assertEqual([item['memory_key'] for item in detail['applied']], ['profile.place.work', 'profile.place.home'])

    def test_supersedes_only_its_own_key(self):
        # P3e.
        job = self.finished('나는 판교에서 일해')
        self.answers = [[proposal('profile.place.work', '판교', supersedes='profile.place.home')]]
        self.service.run_owner_model_upkeep()
        [(_status, detail)] = self.evidence(job)
        self.assertEqual(detail['dropped'], [{'key_digest': om.key_digest('profile.place.work'), 'reason': 'supersedes'}])

    def test_a_claim_a_crash_left_expires_as_interrupted(self):
        # P3b.
        job = self.finished('나는 판교에서 일해')
        with self.store.db() as db:
            db.execute('UPDATE owner_model_upkeep SET state=?,claimed=?,calls=1 WHERE job_id=?',
                       (om.STATE_CLAIMED, time.time() - om.CLAIM_STALE_SECONDS - 5, job))
        self.assertFalse(self.service.run_owner_model_upkeep())
        self.assertEqual(self.upkeep_rows()[job]['state'], om.STATE_EXPIRED)
        self.assertEqual(self.evidence(job), [(om.EVENT_EXPIRED, {'reason': 'interrupted'})])
        self.assertEqual(self.structured_calls(), [])

    def test_the_run_is_off_the_work_thread_and_single_flight(self):
        # P2-4: the tick returns while the judgment is still running; nothing else is claimed meanwhile.
        entered, release, threads = threading.Event(), threading.Event(), []

        def blocking(context, question, schema):
            if context.purpose != om.PURPOSE:
                return None
            entered.set()
            release.wait(5)
            return StructuredDecision(OUTCOME_DECIDED, {'proposals': []}, fixture_confidence(0.9))
        self.service.use_decision_engine(FixtureDecisionEngine(structured=blocking))

        def spawn(target):
            thread = threading.Thread(target=target, daemon=True)
            threads.append(thread)
            thread.start()
        self.service.owner_model_spawn = spawn
        # Newest first (#876): ``first`` is the one claimed first.
        second, first = self.finished('나는 판교에서 일해'), self.finished('나는 분당에 살아')
        self.assertTrue(self.service.run_owner_model_upkeep())
        self.assertTrue(entered.wait(5))
        self.assertIsNot(threads[0], threading.current_thread())
        self.assertFalse(self.service.run_owner_model_upkeep(), 'single-flight: a run is in flight')
        rows = self.upkeep_rows()
        self.assertEqual((rows[first]['state'], rows[second]['state']), (om.STATE_CLAIMED, om.STATE_PENDING))
        release.set()
        threads[0].join(5)
        self.assertEqual(self.upkeep_rows()[first]['state'], om.STATE_DONE)
        self.assertTrue(self.service.run_owner_model_upkeep())
        threads[1].join(5)
        self.assertEqual(self.upkeep_rows()[second]['state'], om.STATE_DONE)

    def test_the_idle_check_and_the_claim_are_one_transaction(self):
        job = self.finished('나는 판교에서 일해')
        self.store.enqueue('다른 요청', 'om-busy')
        self.assertIsNone(self.service.owner_model.claim_due(time.time()))
        self.assertEqual(self.upkeep_rows()[job]['state'], om.STATE_PENDING)

    def test_no_call_starts_after_the_deadline(self):
        self.finished('나는 판교에서 일해')
        clock = [time.time()]
        self.service.owner_model.clock = lambda: clock[0]

        def late(context, question, schema):
            clock[0] += om.RUN_SECONDS + 1
            return StructuredDecision(OUTCOME_DECIDED, {'proposals': [proposal('profile.place.work', '판교')]},
                                      fixture_confidence(0.9))
        seen = []
        self.service.use_decision_engine(FixtureDecisionEngine(structured=late,
                                                               judge=lambda c, p: seen.append(c) or None))
        self.service.run_owner_model_upkeep()
        self.assertEqual(seen, [], 'no further call is started past the deadline')
        self.assertEqual([row['content'] for row in self.store.memories(MEMORY_OWNER)], ['판교'],
                         '#918: the write is not a call, so the kept proposal is still saved')


class PrReview(Upkeep):
    """PR #811 review threads."""

    def test_an_unconfigured_judgment_route_counts_no_call(self):
        # Thread 1: ModelDecisionEngine answers unavailable before its transport; nothing was sent.
        from personal_agent.decision import ModelDecisionEngine

        class Adapter:
            sent = 0

            def tool_turn(self, *args, **kwargs):
                Adapter.sent += 1
                raise AssertionError('no transport call')
        self.service.use_decision_engine(ModelDecisionEngine(Adapter(), lambda: None))
        job = self.finished('나는 판교에서 일해')
        self.assertTrue(self.service.run_owner_model_upkeep())
        self.assertEqual((Adapter.sent, self.upkeep_rows()[job]['calls']), (0, 0))
        self.assertEqual(self.service.owner_model_request()['calls_last_24h'], 0)
        [(status, detail)] = self.evidence(job)
        self.assertEqual((status, detail['sent']), (om.EVENT_UNAVAILABLE, False))

    def test_a_call_that_reached_the_transport_counts_even_when_it_failed(self):
        from personal_agent.decision import ModelDecisionEngine
        from personal_agent.providers import ProviderError

        class Adapter:
            def tool_turn(self, *args, **kwargs):
                raise ProviderError('down', status=500)
        config = ({'provider': 'openai', 'endpoint': 'https://api.openai.com/v1', 'model': 'gpt-4o-mini'}, 'k')
        self.service.use_decision_engine(ModelDecisionEngine(Adapter(), lambda: config))
        job = self.finished('나는 판교에서 일해')
        self.service.run_owner_model_upkeep()
        self.assertEqual(self.upkeep_rows()[job]['calls'], 1)

    def test_adapters_report_whether_they_sent(self):
        from personal_agent.decision import STRUCTURED_UNSUPPORTED, DecisionContext, DecisionEngine
        from personal_agent.decision_adapters import JevDecisionEngine
        self.assertEqual(om.STRUCTURED_UNSUPPORTED_ENGINE, STRUCTURED_UNSUPPORTED)
        context = DecisionContext('p', {'a': 'b'})
        self.assertIs(DecisionEngine().structured(context, 'q', {'properties': {}}).confidence.sent, False)
        self.assertIs(JevDecisionEngine(lambda: '').judge(context, 'q').confidence.sent, False)
        replies = JevDecisionEngine(lambda: 'k', transport=lambda *a: {'answers': {}}).judge(context, 'q')
        self.assertIs(replies.confidence.sent, True)
        self.assertFalse(om.call_sent(DecisionEngine().structured(context, 'q', {'properties': {}})))

    def test_a_pause_during_the_run_stops_it_and_says_so(self):
        # Thread 2: the owner pauses while the proposal call is in flight.
        job = self.finished('나는 판교에서 일하고 분당에 살아')

        def pausing(context, question, schema):
            self.service.owner_model_request({'operation': 'set', 'enabled': False})
            return StructuredDecision(OUTCOME_DECIDED, {'proposals': [proposal('profile.place.work', '판교'),
                                                                      proposal('profile.place.home', '분당')]},
                                      fixture_confidence(0.9))
        judged = []
        self.service.use_decision_engine(FixtureDecisionEngine(structured=pausing,
                                                               judge=lambda c, p: judged.append(c) or None))
        self.service.run_owner_model_upkeep()
        self.assertEqual(judged, [], 'no call after the pause')
        self.assertEqual(self.store.memory_candidates(MEMORY_OWNER), [])
        [(_status, detail)] = self.evidence(job)
        self.assertEqual(detail['stopped'], om.STOPPED_PAUSED)
        self.assertEqual([item['reason'] for item in detail['dropped']], ['paused', 'paused'])

    def test_a_cap_spent_during_the_run_stops_further_calls(self):
        # Thread 2: the rolling allowance is re-read before each judgment, not taken from claim time.
        self.service.owner_model_request({'operation': 'set', 'daily_calls': 3})
        job = self.finished('나는 판교에서 일하고 분당에 살아')

        def spending(context, question, schema):
            with self.store.db() as db:
                db.execute("INSERT INTO owner_model_upkeep(job_id,state,created,claimed,calls) VALUES ('other','done',?,?,2)",
                           (time.time(), time.time()))
            return StructuredDecision(OUTCOME_DECIDED, {'proposals': [proposal('profile.place.work', '판교')]},
                                      fixture_confidence(0.9))
        judged = []
        self.service.use_decision_engine(FixtureDecisionEngine(structured=spending,
                                                               judge=lambda c, p: judged.append(c) or None))
        self.service.run_owner_model_upkeep()
        self.assertEqual(judged, [])
        [(_status, detail)] = self.evidence(job)
        # #918: no further call is made; the write is not a call, so the kept proposal is saved.
        self.assertIsNone(detail['stopped'])
        self.assertEqual(detail['applied'][0]['outcome'], 'memory')
        self.assertEqual([row['content'] for row in self.store.memories(MEMORY_OWNER)], ['판교'])

    def test_judgment_audit_rows_carry_the_source_work(self):
        # Thread 3: record_decision links the background run's judgments to their Work.
        threads = []

        def audited(context, question, schema):
            self.service.record_decision({'purpose': context.purpose, 'kind': 'structured'})
            return StructuredDecision(OUTCOME_DECIDED, {'proposals': []}, fixture_confidence(0.9))
        self.service.use_decision_engine(FixtureDecisionEngine(structured=audited))

        def spawn(target):
            thread = threading.Thread(target=target, daemon=True)
            threads.append(thread)
            thread.start()
        self.service.owner_model_spawn = spawn
        job = self.finished('나는 판교에서 일해')
        self.service.run_owner_model_upkeep()
        threads[0].join(5)
        audit = [row for row in self.store.config('decision_audit', []) if row.get('purpose') == om.PURPOSE]
        self.assertEqual([row.get('work_id') for row in audit], [job])
        self.assertIsNone(self.service.current_work_id, 'the work loop thread is untouched')


class Unit(unittest.TestCase):
    def test_validate_bounds_and_duplicates(self):
        kept, dropped = om.validate([proposal('profile.a', 'v'), proposal('profile.a', 'w'),
                                     proposal('profile.b', ' V ')], set(), set())
        self.assertEqual([item['memory_key'] for item in kept], ['profile.a'])
        self.assertEqual([item['reason'] for item in dropped], ['duplicate', 'duplicate'])
        self.assertNotIn('profile.a', json.dumps(dropped), 'a dropped key is kept only as a digest')
        self.assertEqual(om.validate('nope', set(), set()), ([], []))
        for key in ('profile.', 'profile.a b', 'Profile.a', 'profile.' + 'k' * 160):
            self.assertFalse(om.profile_key(key), key)

    def test_the_request_sentence_is_never_a_value(self):
        """#846: content equal to the owner's request is dropped as 'request'; other values pass."""
        request = ' 가격이 내려가면  알려줘. '
        kept, dropped = om.validate([proposal('profile.a', '가격이 내려가면 알려줘.'), proposal('profile.b', '무선 청소기')],
                                    set(), set(), request=request)
        self.assertEqual([item['content'] for item in kept], ['무선 청소기'])
        self.assertEqual([item['reason'] for item in dropped], ['request'])
        kept, _dropped = om.validate([proposal('profile.a', '가격이 내려가면 알려줘.')], set(), set())
        self.assertEqual(len(kept), 1, 'without a request there is nothing to compare against')
        self.assertIn('never turn the request sentence into content', om.QUESTION)

    def test_a_passing_reaction_is_not_proposed_as_a_lasting_preference(self):
        """#876: the question keeps the strength of what the owner said."""
        self.assertIn('a passing reaction to one occasion', om.QUESTION)
        self.assertIn('not a durable preference, unless the owner says it lasts', om.QUESTION)

    def test_the_question_names_no_task(self):
        from test_no_scenario_code import scenario_tokens
        self.assertEqual(scenario_tokens(om.QUESTION), [])


if __name__ == '__main__':
    unittest.main()

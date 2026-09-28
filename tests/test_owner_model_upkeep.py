"""OWNER-MODEL-03 (#805 phase 1): asynchronous, minimised post-Work owner-model upkeep.

Evidence class: model-free unit and service tests.  A scripted
``FixtureDecisionEngine`` plays the Judgment AI (the proposal ``structured``
call and the #597 ``explicit_memory_request`` judgment); the real
``AgentService`` tick, ``QuickStore`` Memory/candidate paths and the Work
loop of ``tests/test_orchestrator.Harness`` run unchanged.  No live model.
"""
import json
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
            if context.purpose == 'explicit-memory-request':
                self.judged.append(context)
                if self.explicit:
                    return BinaryDecision(OUTCOME_DECIDED, self.explicit.pop(0), fixture_confidence())
            return None
        self.fixture = FixtureDecisionEngine(structured=structured, judge=judge)
        self.service.use_decision_engine(self.fixture)

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

    def test_one_upkeep_per_tick(self):
        first, second = self.finished('나는 판교에서 일해'), self.finished('나는 매주 월요일 회의가 있어')
        self.answers = [[], []]
        self.assertTrue(self.service.run_owner_model_upkeep())
        rows = self.upkeep_rows()
        self.assertEqual((rows[first]['state'], rows[second]['state']), (om.STATE_DONE, om.STATE_PENDING))

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
        self.assertIn('never asserted', question)

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
    def test_a_stated_fact_the_owner_asked_to_keep_becomes_memory_linked_to_the_work(self):
        job = self.finished('나는 판교에서 일해')
        self.answers = [[proposal('profile.place.work', '판교')]]
        self.explicit = [True]
        self.service.run_owner_model_upkeep()
        [memory] = self.store.memories(MEMORY_OWNER, key_prefix='profile.')
        self.assertEqual((memory['memory_key'], memory['content']), ('profile.place.work', '판교'))
        with self.store.db() as db:
            row = db.execute('SELECT work_key,candidate_id FROM memories WHERE id=?', (memory['id'],)).fetchone()
            candidate = db.execute('SELECT state,work_key FROM memory_candidates WHERE id=?',
                                   (row['candidate_id'],)).fetchone()
        self.assertEqual(row['work_key'], self.store._work_binding(job), 'provenance links back to the Work')
        self.assertEqual(dict(candidate), {'state': 'accepted', 'work_key': self.store._work_binding(job)})
        [(status, detail)] = self.evidence(job)
        self.assertEqual(status, om.EVENT_RECORDED)
        self.assertEqual(detail['memory_request'], 'yes')
        self.assertEqual([(item['memory_key'], item['kind'], item['outcome'], item['memory_id'])
                          for item in detail['applied']],
                         [('profile.place.work', 'stated', 'memory', memory['id'])])
        # #804: an accepted, owner-stated profile fact is not a lookup exclusion.
        from personal_agent.agent_runtime import work_written_values
        self.assertNotIn('판교', work_written_values(self.store, job))

    def test_a_stated_fact_without_an_explicit_request_stays_a_candidate(self):
        job = self.finished('나는 판교에서 일해')
        self.answers = [[proposal('profile.place.work', '판교')]]
        self.explicit = [False]
        self.service.run_owner_model_upkeep()
        self.assertEqual(self.store.memories(MEMORY_OWNER), [])
        [candidate] = self.store.memory_candidates(MEMORY_OWNER, work_id=job)
        self.assertEqual((candidate['memory_key'], candidate['state']), ('profile.place.work', 'pending'))
        [(_status, detail)] = self.evidence(job)
        self.assertEqual(detail['applied'][0]['refused_because'], 'no-owner-memory-request')

    def test_a_stated_value_the_owner_did_not_say_stays_a_candidate(self):
        job = self.finished('나는 판교에서 일해')
        self.answers = [[proposal('profile.place.work', '서울 강남')]]
        self.explicit = [True]
        self.service.run_owner_model_upkeep()
        self.assertEqual(self.store.memories(MEMORY_OWNER), [])
        [(_status, detail)] = self.evidence(job)
        self.assertEqual(detail['applied'][0]['refused_because'], 'value-not-in-owner-request')

    def test_an_inference_is_only_ever_a_candidate(self):
        job = self.finished('나는 판교에서 일해')
        self.answers = [[proposal('profile.routine.commute', '평일 판교 출근', kind='inferred', category='routine')]]
        self.explicit = [True]
        self.service.run_owner_model_upkeep()
        self.assertEqual(self.store.memories(MEMORY_OWNER), [])
        [candidate] = self.store.memory_candidates(MEMORY_OWNER, work_id=job)
        self.assertEqual(candidate['memory_key'], 'profile.routine.commute')
        self.assertEqual(self.judged, [], 'no #597 judgment is asked for an inference')
        [(_status, detail)] = self.evidence(job)
        self.assertEqual(detail['applied'][0]['refused_because'], om.REFUSED_INFERRED)
        self.assertIsNone(detail['memory_request'])

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
                         proposal('profile.place.gym', '판교'), proposal('profile.place.gym', '분당')]]
        self.explicit = [False]
        self.service.run_owner_model_upkeep()
        [(_status, detail)] = self.evidence(job)
        self.assertEqual([item['memory_key'] for item in detail['applied']], ['profile.place.gym'])
        self.assertEqual([(item['memory_key'], item['reason']) for item in detail['dropped']],
                         [('profile.place.work', 'duplicate'), ('profile.place.home', 'duplicate'),
                          ('profile.place.gym', 'duplicate')])

    def test_a_contradiction_of_an_unnamed_memory_is_not_silently_superseded(self):
        self.store.save_memory('profile.place.work', '서울역', work_id='w0')
        job = self.finished('나는 판교에서 일해')
        self.answers = [[proposal('profile.place.work', '판교', supersedes='profile.place.work')]]
        self.explicit = [True]
        self.service.run_owner_model_upkeep()
        [memory] = self.store.memories(MEMORY_OWNER)
        self.assertEqual(memory['content'], '서울역')
        [(_status, detail)] = self.evidence(job)
        self.assertEqual(detail['applied'][0]['refused_because'], 'replaces-a-memory-the-request-did-not-name')
        self.assertEqual(detail['applied'][0]['supersedes_key'], 'profile.place.work')


class Budget(Upkeep):
    def test_the_daily_cap_stops_calls(self):
        self.service.owner_model_request({'operation': 'set', 'daily_calls': 1})
        first, second = self.finished('나는 판교에서 일해'), self.finished('나는 분당에 살아')
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

    def test_a_stated_run_counts_its_memory_judgment(self):
        job = self.finished('나는 판교에서 일해')
        self.answers = [[proposal('profile.place.work', '판교'), proposal('profile.place.home', '판교 근처')]]
        self.explicit = [False]
        self.service.run_owner_model_upkeep()
        self.assertEqual(len(self.judged), 1, 'one #597 judgment per run')
        self.assertEqual(self.upkeep_rows()[job]['calls'], 2)

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


class Unit(unittest.TestCase):
    def test_validate_bounds_and_duplicates(self):
        kept, dropped = om.validate([proposal('profile.a', 'v'), proposal('profile.a', 'w')], set(), set())
        self.assertEqual([item['memory_key'] for item in kept], ['profile.a'])
        self.assertEqual(dropped, [{'memory_key': 'profile.a', 'reason': 'duplicate'}])
        self.assertEqual(om.validate('nope', set(), set()), ([], []))
        for key in ('profile.', 'profile.a b', 'Profile.a', 'profile.' + 'k' * 160):
            self.assertFalse(om.profile_key(key), key)

    def test_the_question_names_no_task(self):
        from test_no_scenario_code import scenario_tokens
        self.assertEqual(scenario_tokens(om.QUESTION), [])


if __name__ == '__main__':
    unittest.main()

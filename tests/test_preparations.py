"""SEC-ATTN-01 (#659): owner-accepted preparations - reminders and prepared answers.

Evidence class: model-free, fixture transports.  A scripted compatible-API
model, a counting public network, a recording Telegram transport and a
FixtureDecisionEngine replace only the provider and the wires; the real
QuickStore, ``AgentService`` (Telegram ingress, ``run_one``, ``deliver_one``,
``deliver_notification``, the callback handler, restart recovery),
``run_agent`` and ``Capabilities`` run unchanged.  The preparations clock is
a fake clock.  No live model, Telegram, calendar or search provider is
contacted, and none is claimed.
"""
import json
import logging
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from personal_agent import preparations as prep
from personal_agent.agent_runtime import (PROFILE_HEADING, Capabilities, action_definitions, recorded_arguments,
                                          turn_context, render_turn_prompt)
from personal_agent.conversation_handoff import ConversationJudgments, PREPARATION_REQUEST_PROPOSITION
from personal_agent.decision import OUTCOME_DECIDED, BinaryDecision, FixtureDecisionEngine, fixture_confidence
from personal_agent.memory_service import MemoryService
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore

CHAT, GENERATION = 77, 'gen-1'
SECRET = 'bot-token-value-1234-abcdef'
SEOUL = ZoneInfo('Asia/Seoul')


def call(ident, name, **args):
    return {'id': ident, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}


def finish(ident, *refs, summary='끝났습니다.', status='done'):
    return {'content': None, 'tool_calls': [call(ident, 'finish', status=status, evidence_refs=list(refs), summary=summary)]}


def engine(preparation=True, goal=True):
    """Answers the two judgments this feature relies on; everything else is unavailable."""
    def judge(context, proposition):
        if context.purpose == 'goal-reached':
            return BinaryDecision(OUTCOME_DECIDED, goal, fixture_confidence())
        if context.purpose == 'explicit-preparation-request' and preparation is not None:
            return BinaryDecision(OUTCOME_DECIDED, preparation, fixture_confidence())
        return None
    return FixtureDecisionEngine(judge=judge)


class Network:
    """The public wire; counts every outbound plan."""

    def __init__(self):
        self.plans = []

    def execute(self, plan):
        self.plans.append(dict(plan))
        return {'tool': plan['tool'], 'query': plan.get('query'), 'retrieved_at': 1,
                'sources': ['https://lunch.example/list'],
                'results': [{'title': '합정 식당 목록', 'url': 'https://lunch.example/list', 'snippet': '국수, 덮밥, 샐러드'}]}


class _Case(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / 'data'
        self.store = QuickStore(self.root)
        self.now = float(int(time.time()))
        self.telegram, self.model_calls, self.script = [], [], []
        self.network = Network()
        self.service = self.make_service()
        self.service.save_model({'provider': 'compatible', 'endpoint': 'https://example.test/v1', 'model': 'test-model', 'api_key': 'k'})
        self.assertTrue(self.service.test_model()['ok'])
        self.store.secret('telegram_token', SECRET)
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION, 'cursor': 0})
        self.service.context_observations.set_controls({'timezone': 'Asia/Seoul'})
        self.judge = engine()
        self.service.use_decision_engine(self.judge)
        self.model_calls.clear()
        self.telegram.clear()
        self.update_id, self.message_id = 100, 500

    # --- fakes --------------------------------------------------------------

    def make_service(self):
        """A service over the same store: a second one is a restart."""
        service = AgentService(self.store, ModelAdapter(self._model), self._telegram)
        service.local_tools = self.network
        service.preparations.clock = lambda: self.now
        if hasattr(self, 'judge'):
            service.use_decision_engine(self.judge)
        return service

    def _model(self, url, body, headers=None, timeout=60):
        names = [tool.get('function', {}).get('name') for tool in body.get('tools', [])]
        if 'agentos_connection_probe' in names:
            return {'choices': [{'message': {'tool_calls': [{'id': 'p', 'function': {'name': 'agentos_connection_probe', 'arguments': '{}'}}]}}]}
        self.model_calls.append(json.loads(json.dumps(body)))
        step = self.script.pop(0) if self.script else {'content': '끝났습니다.'}
        message = step(body) if callable(step) else step
        return {'choices': [{'message': message}]}

    def _telegram(self, url, body=None, headers=None, timeout=60):
        method = url.rsplit('/', 1)[-1]
        self.telegram.append((method, body))
        if method == 'sendMessage':
            return {'ok': True, 'result': {'message_id': 9000 + len(self.telegram)}}
        return {'ok': True, 'result': True}

    # --- helpers ------------------------------------------------------------

    def due_iso(self, seconds):
        return datetime.fromtimestamp(self.now + seconds, SEOUL).isoformat(timespec='seconds')

    def receive(self, text):
        """The owner's Telegram message, run through the ordinary worker."""
        self.update_id += 1
        self.message_id += 1
        self.service.ingest_update({'update_id': self.update_id, 'message': {
            'message_id': self.message_id, 'from': {'id': CHAT}, 'chat': {'id': CHAT, 'type': 'private'},
            'text': text, 'date': int(self.now)}}, GENERATION)
        job_id = self.store.jobs()[0]['id']
        self.assertTrue(self.service.run_one())
        return job_id

    def web_turn(self, text):
        self.message_id += 1
        job_id = self.store.enqueue(text, f'web-{self.message_id}')
        self.assertTrue(self.service.run_one())
        return job_id

    def tap(self, data, message_id):
        self.service.ingest_callback({'id': 'cb', 'from': {'id': CHAT}, 'data': data,
                                      'message': {'message_id': message_id, 'chat': {'id': CHAT, 'type': 'private'}}},
                                     GENERATION)

    def sends(self):
        return [body for method, body in self.telegram if method == 'sendMessage']

    def texts(self):
        return [str(body.get('text')) for body in self.sends()]

    def rows(self):
        return self.service.preparations.rows()

    def runs(self, preparation_id):
        with self.store.db() as db:
            return [dict(row) for row in db.execute('SELECT * FROM jobs WHERE request_key LIKE ? ORDER BY created',
                                                    (prep.REQUEST_KEY_PREFIX + preparation_id + ':%',))]

    def scheduled(self, kind='prepare', goal='점심 후보 3곳 준비해 줘', seconds=60, recurrence=None, channel='web'):
        """A row the owner already accepted in Settings."""
        return self.service.preparations.create(kind=kind, goal=goal, due_at=self.now + seconds, timezone='Asia/Seoul',
                                                recurrence=recurrence, channel=channel, created_from='settings',
                                                state=prep.STATE_SCHEDULED, accepted_by=prep.ACCEPTED_OWNER_SETTINGS)

    def tick(self, service=None):
        return (service or self.service).run_due_preparation()


class ReminderTests(_Case):
    def reminder_request(self):
        """The owner asks; the scripted model reads nothing else and schedules one reminder."""
        self.script = [{'content': None, 'tool_calls': [call('1', 'schedule_preparation', kind='reminder', goal='치과 예약 10시',
                                                             due=self.due_iso(3600))]},
                       finish('f', '1', summary='내일 9시에 알려 드릴게요.')]
        work = self.receive('한 시간 뒤에 치과 예약 알려줘')
        [row] = self.rows()
        return work, row

    def test_a_reminder_from_the_request_is_delivered_once_and_survives_restart(self):
        work, row = self.reminder_request()
        self.assertEqual((row['state'], row['accepted_by'], row['kind']), ('scheduled', 'owner-request', 'reminder'))
        self.assertEqual(row['created_from'], work)
        asked = [item[1] for item in self.judge.asked if item[0] == 'judge' and item[1].purpose == 'explicit-preparation-request']
        self.assertEqual(len(asked), 1, 'one judgment, not a text rule')
        self.assertEqual(asked[0].facts['owner_message'], '한 시간 뒤에 치과 예약 알려줘')
        self.assertIn('치과 예약 10시', asked[0].facts['proposed_preparation'])
        self.assertEqual(self.store.job(work)['status'], 'succeeded')
        self.service.deliver_one()
        self.service.deliver_notification()
        self.assertEqual(len(self.sends()), 1, 'the reply only; no proposal message for an accepted reminder')

        # Not due yet: nothing happens.
        self.now += 3500
        self.assertFalse(self.tick())
        self.now += 101
        model_calls = len(self.model_calls)
        self.assertTrue(self.tick())
        [run] = self.runs(row['id'])
        self.assertEqual((run['status'], run['delivery'], run['channel']), ('succeeded', 'pending', f'telegram:{GENERATION}'))
        self.service.deliver_one()
        self.assertEqual(sum('알림: 치과 예약 10시' in text for text in self.texts()), 1)
        self.assertEqual(len(self.model_calls), model_calls, 'a reminder runs no model')
        self.tick()
        self.assertEqual(self.service.preparations.get(row['id'])['state'], 'delivered')

        # Restart, more ticks and deliveries: never a second reminder.
        restarted = self.make_service()
        restarted.recover_interrupted_work()
        for _ in range(3):
            self.now += 3600
            self.tick(restarted)
            restarted.deliver_one()
            restarted.deliver_notification()
        self.assertEqual(sum('치과 예약' in text for text in self.texts()), 1)
        self.assertEqual(len(self.runs(row['id'])), 1)
        # Evidence: preparation id -> Work id -> delivery receipt.
        events = [e['trace'] for e in self.store.task_events(run['id']) if e['tool'] == 'preparation']
        self.assertEqual([e['preparation_id'] for e in events], [row['id'], row['id']])
        self.assertEqual(events[-1]['delivery'], 'sent')
        self.assertEqual(self.service.preparations.get(row['id'])['last_run_job_id'], run['id'])

    def test_a_restart_between_claim_and_send_sends_once(self):
        _work, row = self.reminder_request()
        self.service.deliver_one()
        self.now += 3700
        self.assertTrue(self.tick())
        restarted = self.make_service()
        restarted.recover_interrupted_work()
        self.tick(restarted)
        restarted.deliver_one()
        restarted.deliver_one()
        self.assertEqual(sum('알림: 치과 예약 10시' in text for text in self.texts()), 1)
        self.assertEqual(len(self.runs(row['id'])), 1)

    def test_a_send_interrupted_mid_flight_is_unknown_and_never_resent(self):
        _work, row = self.reminder_request()
        self.service.deliver_one()
        self.now += 3700
        self.tick()
        [run] = self.runs(row['id'])
        with self.store.db() as db:
            db.execute("UPDATE jobs SET delivery='sending' WHERE id=?", (run['id'],))
        restarted = self.make_service()
        restarted.recover_interrupted_work()
        restarted.deliver_one()
        self.tick(restarted)
        self.assertFalse(any('알림:' in text for text in self.texts()))
        self.assertEqual(self.service.preparations.get(row['id'])['state'], 'unknown')

    def test_a_late_reminder_says_it_is_late(self):
        row = self.scheduled(kind='reminder', goal='약 먹기', seconds=60, channel='telegram')
        self.now += 3 * 3600
        self.tick()
        self.service.deliver_one()
        [text] = [t for t in self.texts() if '약 먹기' in t]
        self.assertIn('늦게 전달했습니다', text)
        self.assertEqual(len(self.runs(row['id'])), 1)


class RecurrenceTests(_Case):
    def test_a_recurring_preparation_advances_and_a_missed_window_runs_once(self):
        row = self.scheduled(recurrence='daily')
        first = row['due_at']
        self.now = first + 3 * 86400 + 60  # three daily slots missed while down
        self.assertTrue(self.tick())
        self.assertFalse(self.tick(), 'the claimed slot is running, not due again')
        self.assertTrue(self.service.run_one())
        self.assertTrue(self.tick())  # settle
        current = self.service.preparations.get(row['id'])
        self.assertEqual(current['state'], 'scheduled')
        self.assertEqual(current['due_at'], first + 4 * 86400, 'next wall-clock slot after now')
        self.assertEqual(len(self.runs(row['id'])), 1, 'three missed slots ran once')
        self.assertFalse(self.tick())
        self.now = current['due_at'] + 1
        self.assertTrue(self.tick())
        self.assertEqual(len(self.runs(row['id'])), 2)

    def test_next_due_keeps_wall_clock_time_and_weekdays(self):
        friday = datetime(2026, 10, 2, 11, 30, tzinfo=SEOUL).timestamp()
        monday = prep.next_due(friday, 'Asia/Seoul', 'weekdays', friday + 60)
        self.assertEqual(datetime.fromtimestamp(monday, SEOUL).strftime('%a %H:%M'), 'Mon 11:30')
        weekly = prep.next_due(friday, 'Asia/Seoul', 'weekly', friday + 60)
        self.assertEqual(weekly - friday, 7 * 86400)
        self.assertIsNone(prep.next_due(friday, 'Asia/Seoul', None, friday + 60))
        # DST (New York leaves daylight time on 2026-11-01): 09:00 stays 09:00.
        new_york = ZoneInfo('America/New_York')
        before = datetime(2026, 10, 31, 9, 0, tzinfo=new_york).timestamp()
        after = prep.next_due(before, 'America/New_York', 'daily', before + 60)
        self.assertEqual(datetime.fromtimestamp(after, new_york).strftime('%m-%d %H:%M'), '11-01 09:00')
        self.assertEqual(after - before, 86400 + 3600)
        later = prep.next_due(after, 'America/New_York', 'daily', after + 60)
        self.assertEqual(datetime.fromtimestamp(later, new_york).strftime('%m-%d %H:%M'), '11-02 09:00')

    def test_due_parsing_refuses_the_past_and_a_missing_zone(self):
        with self.assertRaises(prep.PreparationRefusal) as refused:
            prep.parse_due(self.due_iso(-3600), '', 'Asia/Seoul', self.now)
        self.assertEqual(refused.exception.code, 'due_in_past')
        self.assertIn('지금은', str(refused.exception), 'the loop learns the current time')
        with self.assertRaises(prep.PreparationRefusal) as refused:
            prep.parse_due('2026-12-01T09:00', '', '', self.now)
        self.assertEqual(refused.exception.code, 'timezone_unknown')
        day = datetime.fromtimestamp(self.now + 30 * 86400, SEOUL).date().isoformat()
        due_at, zone = prep.parse_due(day + 'T09:00', '', 'Asia/Seoul', self.now)
        self.assertEqual((zone, datetime.fromtimestamp(due_at, SEOUL).hour), ('Asia/Seoul', 9))
        with self.assertRaises(prep.PreparationRefusal):
            prep.normalize_recurrence('every 5 minutes')


class TickCostTests(_Case):
    def test_a_tick_with_nothing_due_calls_no_model_network_or_telegram(self):
        self.scheduled(seconds=3600)
        proposed = self.service.preparations.create(kind='reminder', goal='제안만 된 알림', due_at=self.now + 1,
                                                    timezone='Asia/Seoul', recurrence=None, channel='telegram',
                                                    created_from='w', state=prep.STATE_PROPOSED)
        cancelled = self.scheduled(kind='reminder', goal='취소된 알림', seconds=1, channel='telegram')
        self.service.preparations.cancel(cancelled['id'])
        self.now += 60
        for _ in range(50):
            self.assertFalse(self.tick())
            self.now += 1
        self.assertEqual((self.model_calls, self.network.plans, self.telegram, self.store.jobs()), ([], [], [], []))
        self.assertEqual(self.service.preparations.get(proposed['id'])['state'], 'proposed')

    def test_the_tick_query_uses_the_state_due_index(self):
        with self.store.db() as db:
            plan = ' '.join(str(tuple(row)) for row in db.execute(
                "EXPLAIN QUERY PLAN SELECT p.* FROM preparations p LEFT JOIN jobs j ON j.id=p.last_run_job_id "
                "WHERE p.state IN ('scheduled','running') AND p.due_at<=? ORDER BY p.due_at LIMIT 8", (self.now,)))
        self.assertIn('preparations_state_due', plan)


class PreparedAnswerTests(_Case):
    def lunch_worker(self, body):
        """The prepared Work's model reads the profile it was given, then searches."""
        system = body['messages'][0]['content']
        self.assertIn(PROFILE_HEADING, system)
        self.assertIn('땅콩', system)
        return {'content': None, 'tool_calls': [call('1', 'web_search', query='합정 점심 땅콩 없는 식당')]}

    def test_a_prepared_lunch_runs_the_loop_and_is_consumed_fresh_but_not_stale(self):
        memory = MemoryService(self.store, private_read_sink=MemoryService.NO_EGRESS_GUARD)
        memory.remember_profile('local-owner', 'settings', 'profile.allergy', '땅콩 알레르기')
        memory.remember_profile('local-owner', 'settings', 'profile.place.home', '합정')
        row = self.scheduled(recurrence='daily')
        self.now += 120
        self.tick()
        self.script = [self.lunch_worker, finish('f', '1', summary='합정 점심 후보: 국수집, 덮밥집, 샐러드집 (땅콩 없음)')]
        self.assertTrue(self.service.run_one())
        [run] = self.runs(row['id'])
        run = self.store.job(run['id'])
        self.assertEqual(run['status'], 'succeeded', run)
        self.assertEqual([plan['query'] for plan in self.network.plans], ['합정 점심 땅콩 없는 식당'])
        self.tick()
        current = self.service.preparations.get(row['id'])
        self.assertEqual((current['prepared_result_ref'], current['last_outcome']), (run['id'], 'delivered'))

        seen = []
        self.script = [lambda body: seen.append(body['messages'][0]['content']) or {'content': '준비해 둔 후보입니다.'}]
        self.now += 30 * 60
        asked = self.web_turn('점심 뭐 먹지?')
        section = seen[0].split(prep.PREPARED_HEADING + '\n', 1)[1]
        payload = json.loads(section.split('\n')[1].split('\n\n')[0])
        [item] = payload['items']
        self.assertEqual((item['ref'], item['goal']), ('prep:' + row['id'], '점심 후보 3곳 준비해 줘'))
        self.assertIn('국수집', item['answer'])
        self.assertEqual(item['age_min'], 30)
        record = self.store.turn_provenance(asked)
        # #701 (pilot posture): the prepared section no longer withholds the local
        # record; the envelope is kept after deterministic redaction.
        self.assertNotIn('prompt_withheld', record)
        self.assertIn('국수집', record['prompt_envelope'])

        self.script = [lambda body: seen.append(body['messages'][0]['content']) or {'content': '다시 찾아볼게요.'}]
        self.now += prep.FRESH_SECONDS
        self.web_turn('점심 뭐 먹지?')
        self.assertNotIn(prep.PREPARED_HEADING, seen[1], 'a stale prepared answer is not offered')

    def test_the_section_is_bounded_and_counted_in_the_turn_budget(self):
        rows = [{'id': f'p{i}', 'goal_text': '목표' * 20, 'timezone': 'Asia/Seoul', 'recurrence': None,
                 'prepared_at': self.now - 60, 'status': 'succeeded', 'response': '가' * 5000} for i in range(3)]
        text = prep.render_prepared(rows, self.now)
        self.assertLessEqual(len(text.encode()), prep.SECTION_MAX_BYTES)
        context = turn_context([{'role': 'user', 'content': '점심'}], 'cli', prepared=text)
        self.assertIn(prep.PREPARED_HEADING, render_turn_prompt(context))
        self.assertEqual(turn_context([{'role': 'user', 'content': '점심'}], 'cli').get('prepared'), None)


class AcceptanceTests(_Case):
    def propose(self, text='점심 메뉴 추천해줘'):
        self.script = [{'content': None, 'tool_calls': [call('1', 'schedule_preparation', kind='prepare', goal='점심 후보 준비',
                                                             due=self.due_iso(1800), recurrence='daily', delivery='send')]},
                       {'content': '매일 점심 후보를 준비해 둘까요? 수락하면 예약합니다.'}]
        work = self.receive(text)
        [row] = self.rows()
        return work, row

    def test_no_message_is_sent_except_from_an_accepted_preparation(self):
        self.service.use_decision_engine(engine(preparation=False))
        work, row = self.propose()
        self.assertEqual((row['state'], row['accepted_by']), ('proposed', None))
        [result] = [json.loads(m['content']) for m in self.model_calls[-1]['messages'] if m['role'] == 'tool']
        self.assertTrue(result['requires_owner_acceptance'])
        self.service.deliver_one()
        self.service.deliver_notification()
        self.assertEqual(len(self.sends()), 2, 'the reply and the one proposal message')
        proposal = self.sends()[-1]
        self.assertIn('점심 후보 준비', proposal['text'])
        buttons = json.dumps(proposal['reply_markup'])
        self.assertIn('p7p:', buttons)

        self.now += 3600
        for _ in range(3):
            self.assertFalse(self.tick(), 'an unaccepted preparation never runs')
            self.service.deliver_one()
            self.service.deliver_notification()
        self.assertEqual(len(self.sends()), 2)
        self.assertEqual(self.runs(row['id']), [])

        with self.store.db() as db:
            notification = dict(db.execute("SELECT * FROM telegram_notifications WHERE job_id=? AND kind='preparation_proposed'",
                                           (work,)).fetchone())
        self.tap(f"p7p:{notification['id']}:accept", notification['message_id'] + 1)
        self.assertEqual(self.service.preparations.get(row['id'])['state'], 'proposed', 'another message is not the proposal')
        self.tap(f"p7p:{notification['id']}:accept", notification['message_id'])
        accepted = self.service.preparations.get(row['id'])
        self.assertEqual((accepted['state'], accepted['accepted_by']), ('scheduled', 'owner-button'))
        self.assertTrue(self.tick())
        self.script = [{'content': '국수집과 덮밥집이 좋아요.'}]
        self.assertTrue(self.service.run_one())
        self.service.deliver_one()
        self.assertEqual(len(self.sends()), 3)
        self.assertTrue(self.sends()[-1]['text'].startswith('미리 준비한 결과입니다 (점심 후보 준비)'))

    def test_declining_the_proposal_cancels_it(self):
        self.service.use_decision_engine(engine(preparation=False))
        work, row = self.propose()
        self.service.deliver_one()
        self.service.deliver_notification()
        with self.store.db() as db:
            notification = dict(db.execute("SELECT * FROM telegram_notifications WHERE job_id=? AND kind='preparation_proposed'",
                                           (work,)).fetchone())
        self.tap(f"p7p:{notification['id']}:deny", notification['message_id'])
        self.assertEqual(self.service.preparations.get(row['id'])['state'], 'cancelled')
        self.assertIn('editMessageText', [method for method, _body in self.telegram])
        self.tap(f"p7p:{notification['id']}:accept", notification['message_id'])
        self.assertEqual(self.service.preparations.get(row['id'])['state'], 'cancelled', 'a used message cannot accept later')
        self.now += 3600
        self.assertFalse(self.tick())

    def test_without_a_decision_engine_the_owner_is_asked(self):
        self.service.use_decision_engine(engine(preparation=None))
        _work, row = self.propose('매일 11시 반에 점심 후보 준비해 둬')
        self.assertEqual(row['state'], 'proposed')

    def test_settings_accept_cancel_and_delete(self):
        self.service.use_decision_engine(engine(preparation=False))
        _work, row = self.propose()
        status = self.service.preparation_request({'operation': 'accept', 'id': row['id']})
        [listed] = status['preparations']
        self.assertEqual((listed['state'], listed['accepted_by'], listed['recurrence']), ('scheduled', 'owner-settings', 'daily'))
        self.assertIn('Asia/Seoul', listed['due_local'])
        with self.assertRaises(ValueError):
            self.service.preparation_request({'operation': 'accept', 'id': row['id']})
        self.service.preparation_request({'operation': 'cancel', 'id': row['id']})
        self.service.preparation_request({'operation': 'delete', 'id': row['id']})
        self.assertEqual(self.service.preparation_request({'operation': 'list'}), {'preparations': []})

    def test_a_preparation_run_cannot_accept_a_new_preparation_itself(self):
        row = self.scheduled(goal='내일도 점심 후보 준비해 둬', channel='web')
        self.now += 120
        self.tick()
        before = len(self.judge.asked)
        self.script = [{'content': None, 'tool_calls': [call('1', 'schedule_preparation', kind='prepare', goal='점심 후보',
                                                             due=self.due_iso(86400))]}, {'content': '제안했습니다.'}]
        self.assertTrue(self.service.run_one())
        created = [r for r in self.rows() if r['id'] != row['id']]
        self.assertEqual([r['state'] for r in created], ['proposed'])
        self.assertFalse(any(item[1].purpose == 'explicit-preparation-request' for item in self.judge.asked[before:]))

    def test_the_judgment_is_a_bounded_proposition_not_a_rule(self):
        engine_ = engine(preparation=True)
        judged = ConversationJudgments(engine_).explicit_preparation_request('내일 9시에 알려줘', '[알림] 2026-09-28 09:00')
        self.assertEqual(judged.outcome, 'yes')
        [(_kind, context, proposition)] = engine_.asked
        self.assertEqual(proposition, PREPARATION_REQUEST_PROPOSITION)
        self.assertEqual(set(context.facts), {'owner_message', 'proposed_preparation'})


class CancelTests(_Case):
    def test_cancel_stops_future_runs(self):
        row = self.scheduled(recurrence='daily')
        self.service.preparation_request({'operation': 'cancel', 'id': row['id']})
        self.now += 2 * 86400
        self.assertFalse(self.tick())
        self.assertEqual(self.runs(row['id']), [])

    def test_cancel_while_running_lets_that_work_finish_and_stops_the_next(self):
        row = self.scheduled(recurrence='daily')
        self.now += 120
        self.tick()
        self.service.preparation_request({'operation': 'cancel', 'id': row['id']})
        self.assertTrue(self.service.run_one())
        self.tick()
        self.now += 3 * 86400
        self.tick()
        self.assertEqual(self.service.preparations.get(row['id'])['state'], 'cancelled')
        self.assertEqual(len(self.runs(row['id'])), 1)
        with self.assertRaises(ValueError):
            self.service.preparations.delete('missing')


class SecretTests(_Case):
    PASSPORT = 'M12345678'

    def capture_logs(self):
        """Every record of the service and runtime loggers, whatever other tests configured."""
        records = []
        handler = logging.Handler(logging.DEBUG)
        handler.emit = records.append
        previous_disable = logging.root.manager.disable
        logging.disable(logging.NOTSET)
        self.addCleanup(logging.disable, previous_disable)
        for name in ('', 'personal_agent', 'personal_agent.service'):
            logger = logging.getLogger(name)
            level = logger.level
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
            self.addCleanup(logger.removeHandler, handler)
            self.addCleanup(logger.setLevel, level)
        return records

    def test_a_secret_in_goal_text_or_result_never_reaches_logs_or_evidence(self):
        records = self.capture_logs()
        self.script = [{'content': None, 'tool_calls': [call('1', 'schedule_preparation', kind='reminder',
                                                             goal=f'토큰 {SECRET} 갱신하기', due=self.due_iso(600))]},
                       finish('f', '1', summary='예약했습니다.')]
        self.web_turn(f'10분 뒤에 토큰 {SECRET} 갱신하라고 알려줘')
        prepared = self.scheduled(goal='점심 후보 준비', seconds=30)
        self.now += 700
        self.tick()
        self.script = [{'content': f'결과에 섞인 {SECRET} 값'}]
        self.service.run_one()
        self.service.deliver_one()
        self.tick()

        [reminder] = [row for row in self.rows() if row['kind'] == 'reminder']
        self.assertEqual(reminder['goal_text'], '토큰 [redacted] 갱신하기')
        self.assertEqual(reminder['state'], 'delivered')
        logged = '\n'.join(record.getMessage() for record in records)
        self.assertIn('preparation', logged)
        self.assertNotIn(SECRET, logged)
        with self.store.db() as db:
            events = ' '.join(row['detail'] or '' for row in db.execute('SELECT detail FROM tool_events'))
            stored = json.dumps([dict(row) for row in db.execute('SELECT * FROM preparations')], ensure_ascii=False)
        self.assertNotIn(SECRET, events)
        self.assertIn('토큰 [redacted] 갱신하기', events, 'the call record keeps the goal with the secret removed')
        self.assertNotIn(SECRET, stored)
        section = self.service.prepared_text({'id': 'next'})
        self.assertIn(prepared['id'], section)
        self.assertNotIn(SECRET, section)

    def test_a_goal_without_a_secret_is_recorded_as_written(self):
        self.script = [{'content': None, 'tool_calls': [call('1', 'schedule_preparation', kind='reminder',
                                                             goal='치과 예약 10시', due=self.due_iso(600))]},
                       finish('f', '1', summary='예약했습니다.')]
        job = self.web_turn('10분 뒤에 치과 예약 알려줘')
        running = [e['trace'] for e in self.store.task_events(job) if e['status'] == 'running']
        self.assertEqual(running[0]['arguments']['goal'], '치과 예약 10시')

    def test_saved_private_values_leave_the_goal_and_the_prepared_answer(self):
        """The Work's own private-store writes (#605 exclusion set) are removed before storage."""
        self.script = [{'content': None, 'tool_calls': [
                           call('1', 'save_note', content='여권번호 ' + self.PASSPORT),
                           call('2', 'schedule_preparation', kind='reminder', goal=f'여권 {self.PASSPORT} 챙기기',
                                due=self.due_iso(600))]},
                       finish('f', '1', '2', summary='저장하고 예약했습니다.')]
        self.web_turn(f'여권번호는 {self.PASSPORT}야. 10분 뒤에 여권 챙기라고 알려줘')
        [reminder] = self.rows()
        self.assertNotIn(self.PASSPORT, reminder['goal_text'])

        row = self.scheduled(goal='여행 준비물 정리', seconds=900)
        self.now += 1000
        self.tick()
        self.script = [{'content': None, 'tool_calls': [call('1', 'save_note', content='비자번호 V7654321')]},
                       finish('f', '1', summary='비자번호 V7654321 을 메모했고 준비물은 여권, 충전기입니다.')]
        self.service.run_one()
        self.tick()
        current = self.service.preparations.get(row['id'])
        self.assertIn('충전기', current['prepared_text'])
        self.assertNotIn('V7654321', current['prepared_text'])
        self.assertNotIn('V7654321', self.service.prepared_text({'id': 'next'}))


class PreparationScopeTests(_Case):
    """PR #671 review: a preparation's Work sees its origin and goal only, and
    persists nothing unscrubbed; a proposal message accepts only what it shows."""

    ORIGIN = '매일 점심 후보 준비해 줘 ORIGIN-MARK'
    UNRELATED = '어제 병원 검사 결과 이야기 UNRELATED-MARK'

    def origin_then_unrelated(self):
        self.script = [{'content': None, 'tool_calls': [call('1', 'schedule_preparation', kind='prepare', goal='점심 후보 3곳 준비',
                                                             due=self.due_iso(600), recurrence='daily')]},
                       finish('f', '1', summary='매일 준비할게요.')]
        origin = self.web_turn(self.ORIGIN)
        [row] = self.rows()
        self.assertEqual((row['state'], row['created_from']), ('scheduled', origin))
        self.script = [{'content': '그랬군요.'}]
        self.web_turn(self.UNRELATED)
        self.now += 700
        self.assertTrue(self.tick())
        return row

    def test_direct_route_preparation_work_sees_only_its_origin_and_goal(self):
        self.origin_then_unrelated()
        seen = []
        self.script = [lambda body: seen.append(json.loads(json.dumps(body['messages']))) or {'content': '후보: 국수집'}]
        self.assertTrue(self.service.run_one())
        sent = json.dumps(seen[0], ensure_ascii=False)
        self.assertIn('ORIGIN-MARK', sent)
        self.assertIn('점심 후보 3곳 준비', sent)
        self.assertNotIn('UNRELATED-MARK', sent)
        self.assertEqual([m['role'] for m in seen[0][1:]], ['user', 'user'])

    def test_cli_route_preparation_work_sees_only_its_origin_and_goal(self):
        from personal_agent.bounded_execution import ExecutionResult
        from personal_agent.subscription_engines import SubscriptionEngines
        prompts = []

        class Engine:
            def execute(self_, engine, prompt, tools, **kwargs):
                prompts.append(prompt)
                return ExecutionResult('준비했습니다.', engine, 0)

        self.service = AgentService(self.store, ModelAdapter(self._model), self._telegram, execution_adapter=Engine(),
                                    subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/cli', clock=lambda: 1))
        self.service.preparations.clock = lambda: self.now
        self.service.use_decision_engine(self.judge)
        self.service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        origin = self.web_turn(self.ORIGIN)
        self.web_turn(self.UNRELATED)
        row = self.service.preparations.create(kind='prepare', goal='점심 후보 3곳 준비', due_at=self.now + 60,
                                               timezone='Asia/Seoul', recurrence=None, channel='web', created_from=origin,
                                               state=prep.STATE_SCHEDULED, accepted_by=prep.ACCEPTED_OWNER_SETTINGS)
        self.now += 120
        self.assertTrue(self.tick())
        prompts.clear()
        self.assertTrue(self.service.run_one())
        [prompt] = prompts
        self.assertIn('ORIGIN-MARK', prompt)
        self.assertIn('점심 후보 3곳 준비', prompt)
        self.assertNotIn('UNRELATED-MARK', prompt)
        self.assertEqual(len(self.runs(row['id'])), 1)

    def test_a_secret_in_a_preparation_answer_is_never_persisted_or_replayed(self):
        self.origin_then_unrelated()
        # The same reply to the loop's one execution check.
        self.script = [{'content': f'후보: 국수집 (키 {SECRET})'}] * 2
        self.assertTrue(self.service.run_one())
        [run] = [job for job in self.store.jobs() if (job['request_key'] or '').startswith(prep.REQUEST_KEY_PREFIX)]
        self.assertIn('국수집', run['response'])
        self.assertNotIn(SECRET, run['response'])
        with self.store.db() as db:
            stored = ' '.join(row['content'] for row in db.execute('SELECT content FROM messages'))
        self.assertIn('국수집', stored)
        self.assertNotIn(SECRET, stored)
        self.tick()
        seen = []
        self.script = [lambda body: seen.append(json.loads(json.dumps(body['messages']))) or {'content': '좋아요.'}]
        self.web_turn('점심 뭐 먹지?')
        replay = json.dumps(seen[0], ensure_ascii=False)
        self.assertIn('국수집', replay, 'the earlier answer is in the next turn')
        self.assertNotIn(SECRET, replay)

    def test_accept_schedules_only_the_proposals_the_message_showed(self):
        self.service.use_decision_engine(engine(preparation=False))
        self.script = [{'content': '알겠습니다.'}]
        work = self.receive('여러 가지 준비해 줘')
        for index in range(12):
            self.service.preparations.create(kind='prepare', goal=f'P{index:02d}Q ' + '긴 준비 목표 ' * 60, due_at=self.now + 3600 + index,
                                             timezone='Asia/Seoul', recurrence=None, channel='web', created_from=work,
                                             state=prep.STATE_PROPOSED)
        self.service.queue_preparation_proposal(self.store.job(work))
        self.service.deliver_one()
        self.service.deliver_notification()
        proposal = self.sends()[-1]
        self.assertLessEqual(len(proposal['text']), prep.PROPOSAL_TEXT_LIMIT)
        self.assertIn('설정 > 준비해 둔 일', proposal['text'])
        shown = [row for row in self.rows() if row['goal_text'][:4] in proposal['text']]
        self.assertTrue(0 < len(shown) < 12)
        with self.store.db() as db:
            notification = dict(db.execute("SELECT * FROM telegram_notifications WHERE job_id=? AND kind='preparation_proposed'",
                                           (work,)).fetchone())
        self.tap(f"p7p:{notification['id']}:accept", notification['message_id'])
        states = {row['goal_text'][:4]: row['state'] for row in self.rows()}
        self.assertEqual({key for key, state in states.items() if state == 'scheduled'}, {row['goal_text'][:4] for row in shown})
        self.assertEqual(sum(state == 'proposed' for state in states.values()), 12 - len(shown))


# --- SEC-ATTN-02 (#719): watching until a deadline, telling only when needed ---

def watch_engine(verdicts, preparation=False):
    """Scripted ``watch-notification`` verdicts (True/False/None=unavailable), in order."""
    verdicts = list(verdicts)

    def judge(context, proposition):
        if context.purpose == 'goal-reached':
            return BinaryDecision(OUTCOME_DECIDED, True, fixture_confidence())
        if context.purpose == 'explicit-preparation-request':
            return BinaryDecision(OUTCOME_DECIDED, preparation, fixture_confidence())
        if context.purpose == 'watch-notification':
            verdict = verdicts.pop(0) if verdicts else None
            return None if verdict is None else BinaryDecision(OUTCOME_DECIDED, verdict, fixture_confidence())
        return None
    return FixtureDecisionEngine(judge=judge)


class _WatchCase(_Case):
    EVERY = 600

    def watch(self, *, runs=None, span=3600, delivery=prep.DELIVERY_WHEN_NEEDED, goal='출발 시각을 앞당겨야 하는지 확인'):
        """An accepted watch: every 10 minutes from one minute from now for ``span`` seconds."""
        due = self.now + 60
        every, end, max_runs = prep.normalize_window(self.EVERY // 60, datetime.fromtimestamp(due + span, SEOUL).isoformat(),
                                                     runs, due, 'Asia/Seoul', self.now)
        return self.service.preparations.create(kind='prepare', goal=goal, due_at=due, timezone='Asia/Seoul', recurrence=None,
                                                channel='telegram', created_from='settings', state=prep.STATE_SCHEDULED,
                                                accepted_by=prep.ACCEPTED_OWNER_SETTINGS, window=(every, end, max_runs),
                                                delivery_mode=delivery)

    def run_slot(self, answer):
        """Advance to the row's slot, start it, let the worker answer, settle, deliver."""
        row = self.service.preparations.get(self.watched['id'])
        self.now = max(self.now, row['due_at']) + 1
        self.assertTrue(self.tick())
        self.script = [{'content': answer}] * 2  # the loop asks once more after a bare answer
        self.assertTrue(self.service.run_one())
        self.service.deliver_one()
        self.assertTrue(self.tick())  # settle: the decision
        self.service.deliver_notification()
        return self.service.preparations.get(self.watched['id'])

    def watch_asks(self):
        return [item[1] for item in self.judge.asked if item[0] == 'judge' and item[1].purpose == 'watch-notification']


class WindowTests(_WatchCase):
    def setUp(self):
        super().setUp()
        self.judge = watch_engine([False] * 50)
        self.service.use_decision_engine(self.judge)

    def test_the_window_is_bounded_by_its_slots_max_runs_and_limits(self):
        due = self.now + 60
        until = lambda seconds: datetime.fromtimestamp(due + seconds, SEOUL).isoformat()
        self.assertEqual(prep.normalize_window(10, until(3600), None, due, 'Asia/Seoul', self.now), (600, due + 3600, 6), 'slots before the deadline')
        self.assertEqual(prep.normalize_window('10', until(3600), 3, due, 'Asia/Seoul', self.now)[2], 3)
        self.assertEqual(prep.normalize_window(5, until(86400), None, due, 'Asia/Seoul', self.now)[2], prep.MAX_WINDOW_RUNS)
        # #846: about three checks a day up to a deadline weeks away fits the window.
        self.assertEqual(prep.normalize_window(480, until(30 * 86400), None, due, 'Asia/Seoul', self.now)[2], 90)
        for every, span, runs in ((4, 3600, None), (721, 3600, None), (10, 0, None), (10, -600, None),
                                  (10, 31 * 86400 + 60, None), (True, 3600, None), (10, 3600, 0), (10, 3600, 97)):
            with self.assertRaises(prep.PreparationRefusal, msg=(every, span, runs)):
                prep.normalize_window(every, until(span), runs, due, 'Asia/Seoul', self.now)
        with self.assertRaises(prep.PreparationRefusal):
            self.service.preparations.create(kind='reminder', goal='x', due_at=due, timezone='Asia/Seoul', recurrence=None,
                                             channel='telegram', created_from='w', state=prep.STATE_SCHEDULED,
                                             delivery_mode=prep.DELIVERY_WHEN_NEEDED)

    def test_a_watch_runs_at_most_max_runs_then_stops(self):
        self.watched = self.watch(runs=3)
        for index in range(3):
            row = self.run_slot(f'확인 {index}: 아직 괜찮습니다.')
        self.assertEqual((row['state'], row['run_count']), ('delivered', 3))
        for _ in range(12):
            self.now += self.EVERY
            self.assertFalse(self.tick(), 'no fourth run inside the window')
        self.assertEqual(len(self.runs(row['id'])), 3)
        events = [e['trace'] for run in self.runs(row['id']) for e in self.store.task_events(run['id'])
                  if e['tool'] == 'preparation' and 'run' in e['trace']]
        self.assertEqual([(e['run'], e['max_runs']) for e in events], [(1, 3), (2, 3), (3, 3)])

    def test_a_watch_stops_at_its_deadline(self):
        self.watched = self.watch(span=1800)  # slots at +0, +10, +20 minutes; none at the deadline
        slots = []
        while self.service.preparations.get(self.watched['id'])['state'] == 'scheduled':
            slots.append(self.service.preparations.get(self.watched['id'])['due_at'])
            row = self.run_slot('아직 괜찮습니다.')
        end = self.watched['window_end']
        self.assertEqual(len(slots), 3)
        self.assertTrue(all(slot < end for slot in slots))
        self.assertEqual(row['state'], 'delivered')
        self.now = end + 7200
        self.assertFalse(self.tick())
        self.assertEqual(len(self.runs(row['id'])), 3)

    def test_a_window_missed_while_down_expires_without_running(self):
        self.watched = self.watch(span=1800)
        self.now = self.watched['window_end'] + prep.PAST_GRACE_SECONDS + 1
        self.assertTrue(self.tick())
        self.assertEqual(self.service.preparations.get(self.watched['id'])['state'], prep.STATE_EXPIRED)
        self.assertEqual((self.runs(self.watched['id']), self.model_calls), ([], []))
        self.assertFalse(self.tick())

    def test_a_tick_just_after_the_deadline_does_not_run(self):
        self.watched = self.watch(span=1800)
        self.now = self.watched['window_end']
        self.assertTrue(self.tick())
        self.assertEqual(self.service.preparations.get(self.watched['id'])['state'], prep.STATE_EXPIRED)
        self.assertEqual((self.runs(self.watched['id']), self.model_calls), ([], []))

    def test_missed_slots_run_once_then_the_next_slot_after_now(self):
        self.watched = self.watch(span=3600)
        first = self.watched['due_at']
        self.now = first + 3 * self.EVERY + 5  # three slots missed while down
        self.assertTrue(self.tick())
        self.script = [{'content': '아직 괜찮습니다.'}] * 2
        self.assertTrue(self.service.run_one())
        self.assertTrue(self.tick())
        row = self.service.preparations.get(self.watched['id'])
        self.assertEqual((row['state'], row['due_at'], row['run_count']), ('scheduled', first + 4 * self.EVERY, 1))

    def test_a_tick_with_nothing_due_makes_no_model_or_judgment_call(self):
        self.watched = self.watch()
        for _ in range(50):
            self.assertFalse(self.tick())
            self.now += 1
        self.assertEqual((self.model_calls, self.telegram, self.store.jobs(), self.watch_asks()), ([], [], [], []))


class SilentDeliveryTests(_WatchCase):
    def use(self, verdicts):
        self.judge = watch_engine(verdicts)
        self.service.use_decision_engine(self.judge)

    def notifications(self):
        return [text for text in self.texts() if text.startswith('지켜보던 일에서 알려 드립니다')]

    def test_quiet_runs_send_nothing_and_notify_sends_once_per_new_decision(self):
        self.use([False, True, True])
        self.watched = self.watch()
        row = self.run_slot('지금은 평소와 같습니다. 예정대로 출발하면 됩니다.')
        self.assertEqual((row['last_decision'], row['last_decision_reason']), ('quiet', prep.REASON_JUDGED_NOT_NEEDED))
        self.assertEqual(self.telegram, [], 'a quiet run sends nothing, not even a typing indicator')
        [run] = self.runs(row['id'])
        self.assertEqual((run['channel'], run['chat_id'], run['delivery'], run['status']), ('web', None, 'none', 'succeeded'))
        self.assertIn(run['id'], [job['id'] for job in self.store.jobs()], 'a quiet run stays in 작업 현황')
        settled = [e['trace'] for e in self.store.task_events(run['id']) if e['tool'] == 'preparation' and 'decision' in e['trace']]
        self.assertEqual([(e['decision'], e['reason'], e['notification_queued']) for e in settled],
                         [('quiet', prep.REASON_JUDGED_NOT_NEEDED, False)])
        self.assertNotIn('평소와', json.dumps(settled, ensure_ascii=False), 'Evidence records the decision, not the answer')

        row = self.run_slot('정체가 시작됐습니다. 20분 일찍 출발하세요.')
        self.assertEqual((row['last_decision'], row['last_decision_reason']), ('notify', prep.REASON_JUDGED_NEEDED))
        [sent] = self.notifications()
        self.assertIn('20분 일찍 출발하세요', sent)
        self.assertIn('p7q:', json.dumps(self.sends()[-1]['reply_markup']))
        self.service.deliver_notification()
        self.service.deliver_one()
        self.assertEqual(len(self.sends()), 1, 'exactly one message for this decision')

        # The same result again: quiet without asking the judgment.
        asked = len(self.watch_asks())
        row = self.run_slot('정체가 시작됐습니다.  20분 일찍 출발하세요.')
        self.assertEqual((row['last_decision'], row['last_decision_reason']), ('quiet', prep.REASON_UNCHANGED))
        self.assertEqual(len(self.watch_asks()), asked)
        self.assertEqual(len(self.notifications()), 1)

        # A new situation the judgment says is new: one more message.
        row = self.run_slot('정체가 더 심해졌습니다. 40분 일찍 출발하세요.')
        self.assertEqual(row['last_decision'], 'notify')
        self.assertEqual(len(self.notifications()), 2)
        last = self.watch_asks()[-1]
        self.assertEqual(set(last.facts), {'watch_goal', 'run_result', 'last_notification'})
        self.assertIn('20분 일찍', last.facts['last_notification'], 'the judgment sees what the owner was last told')
        self.assertEqual(last.facts['watch_goal'], '출발 시각을 앞당겨야 하는지 확인')

    def test_a_notification_survives_a_restart_and_is_sent_once(self):
        self.use([True])
        self.watched = self.watch()
        row = self.service.preparations.get(self.watched['id'])
        self.now = row['due_at'] + 1
        self.tick()
        self.script = [{'content': '지금 출발하세요.'}] * 2
        self.service.run_one()
        self.tick()  # settled and queued in one transaction, not yet sent
        restarted = self.make_service()
        restarted.recover_interrupted_work()
        for _ in range(3):
            restarted.deliver_notification()
            self.tick(restarted)
        self.assertEqual(len(self.notifications()), 1)

    def test_only_a_confirmed_send_is_what_the_owner_was_last_told(self):
        self.use([True, True])
        self.watched = self.watch()
        row = self.service.preparations.get(self.watched['id'])
        self.now = row['due_at'] + 1
        self.tick()
        self.script = [{'content': '지금 출발하세요.'}] * 2
        self.service.run_one()
        self.tick()  # notify decided and queued
        self.assertIsNone(self.service.preparations.get(row['id'])['last_notified_digest'], 'queued is not sent')
        # The pairing changes before the send: the queued message is cancelled, never sent.
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': 'gen-2', 'cursor': 0})
        self.service.deliver_notification()
        self.assertEqual(self.notifications(), [])
        row = self.service.preparations.get(row['id'])
        self.assertEqual((row['last_notified_digest'], row['last_notified_text']), (None, None))
        # The same result on the next slot is judged again and reaches the re-paired owner.
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION, 'cursor': 0})
        asked = len(self.watch_asks())
        row = self.run_slot('지금 출발하세요.')
        self.assertEqual((row['last_decision'], len(self.watch_asks())), ('notify', asked + 1))
        self.assertEqual(len(self.notifications()), 1)
        self.assertEqual(row['last_notified_digest'], prep.text_digest('지금 출발하세요.'))
        self.assertIn('지금 출발하세요', row['last_notified_text'])

    def test_without_a_judgment_the_result_is_sent_once_then_kept_quiet(self):
        self.use([None, None, None])
        self.watched = self.watch()
        self.assertEqual(self.run_slot('상황 A')['last_decision_reason'], prep.REASON_UNJUDGED)
        self.assertEqual(self.run_slot('상황 B')['last_decision_reason'], prep.REASON_UNJUDGED_REPEAT)
        self.assertEqual(self.run_slot('상황 C')['last_decision'], 'quiet')
        self.assertEqual(len(self.notifications()), 1)

    def test_a_run_without_a_result_is_quiet_and_asks_nothing(self):
        self.use([True])
        self.watched = self.watch()
        row = self.service.preparations.get(self.watched['id'])
        self.now = row['due_at'] + 1
        self.tick()
        [run] = self.runs(row['id'])
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='failed',response=NULL,error='x',delivery='none' WHERE id=?", (run['id'],))
        self.tick()
        row = self.service.preparations.get(row['id'])
        self.assertEqual((row['last_decision'], row['last_decision_reason'], row['state']),
                         ('quiet', prep.REASON_RUN_FAILED, 'scheduled'))
        self.assertEqual((self.watch_asks(), self.telegram), ([], []))

    def test_the_owner_stops_a_watch_from_its_notification(self):
        self.use([True])
        self.watched = self.watch()
        self.run_slot('지금 출발하세요.')
        with self.store.db() as db:
            notification = dict(db.execute('SELECT * FROM telegram_notifications WHERE kind=?', (prep.NOTIFY_KIND,)).fetchone())
        self.tap(f"p7q:{notification['id']}:stop", notification['message_id'] + 1)
        self.assertEqual(self.service.preparations.get(self.watched['id'])['state'], 'scheduled', 'another message stops nothing')
        self.tap(f"p7q:{notification['id']}:stop", notification['message_id'])
        self.assertEqual(self.service.preparations.get(self.watched['id'])['state'], 'cancelled')
        self.assertIn('editMessageReplyMarkup', [method for method, _body in self.telegram])
        self.now += 3 * 3600
        self.assertFalse(self.tick())
        self.assertEqual(len(self.runs(self.watched['id'])), 1)

    def test_a_notification_queued_before_a_cancel_is_not_sent(self):
        self.use([True])
        self.watched = self.watch()
        row = self.service.preparations.get(self.watched['id'])
        self.now = row['due_at'] + 1
        self.tick()
        self.script = [{'content': '지금 출발하세요.'}] * 2
        self.service.run_one()
        self.tick()
        self.service.preparation_request({'operation': 'cancel', 'id': row['id']})
        self.service.deliver_notification()
        self.assertEqual(self.notifications(), [])

    def test_the_judgment_is_a_bounded_proposition_not_a_rule(self):
        from personal_agent.conversation_handoff import WATCH_NOTIFY_PROPOSITION
        engine_ = watch_engine([True])
        judged = ConversationJudgments(engine_).watch_notification_needed('목표', '결과', None, work_id='w')
        self.assertEqual(judged.outcome, 'yes')
        [(_kind, context, proposition)] = engine_.asked
        self.assertEqual(proposition, WATCH_NOTIFY_PROPOSITION)
        self.assertEqual(context.facts['last_notification'], 'none')


class WatchAcceptanceTests(_WatchCase):
    def propose_watch(self, preparation):
        self.judge = watch_engine([], preparation=preparation)
        self.service.use_decision_engine(self.judge)
        self.script = [{'content': None, 'tool_calls': [call('1', 'schedule_preparation', kind='prepare',
                                                             goal='출발 시각을 앞당겨야 하는지 확인', due=self.due_iso(600),
                                                             every_minutes='10', until=self.due_iso(600 + 7200), max_runs='6',
                                                             delivery='when_needed')]},
                       {'content': '7시부터 10분마다 확인하고 필요할 때만 알려 드릴게요.'}]
        work = self.receive('9시 전에 출발 시간 당겨야 하면 알려줘')
        [row] = self.rows()
        [result] = [json.loads(m['content']) for m in self.model_calls[-1]['messages'] if m['role'] == 'tool']
        return work, row, result

    def test_a_watch_is_proposed_and_accepted_with_the_existing_flow(self):
        work, row, result = self.propose_watch(preparation=False)
        self.assertEqual((row['state'], row['recurrence'], row['every_seconds'], row['max_runs'], row['delivery_mode']),
                         ('proposed', prep.RECURRENCE_WINDOW, 600, 6, 'when_needed'))
        self.assertEqual((result['every_minutes'], result['max_runs'], result['delivery']), (10, 6, 'when_needed'))
        self.service.deliver_one()
        self.service.deliver_notification()
        proposal = self.sends()[-1]['text']
        self.assertIn('10분마다', proposal)
        self.assertIn('최대 6회', proposal)
        self.assertIn('알려야 할 때만', proposal)
        with self.store.db() as db:
            notification = dict(db.execute("SELECT * FROM telegram_notifications WHERE job_id=? AND kind='preparation_proposed'",
                                           (work,)).fetchone())
        self.tap(f"p7p:{notification['id']}:accept", notification['message_id'])
        self.assertEqual(self.service.preparations.get(row['id'])['state'], 'scheduled')
        listed = self.service.preparations_status()['preparations'][0]
        self.assertEqual((listed['every_minutes'], listed['max_runs'], listed['run_count'], listed['delivery']),
                         (10, 6, 0, 'when_needed'))
        self.assertIn('Asia/Seoul', listed['until_local'])

    def test_a_three_a_day_watch_until_a_deadline_is_accepted_as_a_proposal(self):
        """#846: the guidance's default cadence (every_minutes ~420 with until) is within the validated window."""
        self.judge = watch_engine([], preparation=False)
        self.service.use_decision_engine(self.judge)
        self.script = [{'content': None, 'tool_calls': [call('1', 'schedule_preparation', kind='prepare',
                                                             goal='바뀌었는지 확인', due=self.due_iso(600),
                                                             every_minutes='420', until=self.due_iso(600 + 20 * 3600),
                                                             delivery='when_needed')]},
                       {'content': '하루 세 번 확인하고 필요할 때만 알려 드릴까요?'}]
        self.receive('바뀌면 알려줘')
        [row] = self.rows()
        [result] = [json.loads(m['content']) for m in self.model_calls[-1]['messages'] if m['role'] == 'tool']
        self.assertEqual((row['state'], row['every_seconds'], row['delivery_mode']), ('proposed', 420 * 60, 'when_needed'))
        self.assertEqual((result['every_minutes'], result['delivery']), (420, 'when_needed'))
        self.assertNotIn('refused_because', json.dumps(result))

    def test_the_owners_own_request_schedules_it(self):
        _work, row, _result = self.propose_watch(preparation=True)
        self.assertEqual((row['state'], row['accepted_by']), ('scheduled', 'owner-request'))

    def test_bad_windows_are_refused_to_the_model(self):
        self.judge = watch_engine([], preparation=True)
        self.service.use_decision_engine(self.judge)
        self.script = [{'content': None, 'tool_calls': [
            call('1', 'schedule_preparation', kind='prepare', goal='확인', due=self.due_iso(600), every_minutes='1',
                 until=self.due_iso(1200)),
            call('2', 'schedule_preparation', kind='reminder', goal='확인', due=self.due_iso(600), delivery='when_needed'),
            call('3', 'schedule_preparation', kind='prepare', goal='확인', due=self.due_iso(600), recurrence='daily',
                 every_minutes='10', until=self.due_iso(1200))]}, {'content': '예약하지 못했습니다.'}]
        self.receive('확인해줘')
        results = [m['content'] for m in self.model_calls[-1]['messages'] if m['role'] == 'tool']
        self.assertEqual(len(results), 3)
        self.assertTrue(all('every_minutes' in text or 'when_needed' in text for text in results), results)
        self.assertEqual(self.rows(), [])

    def test_rejected_watch_cannot_fan_out_into_same_goal_daily_preparations(self):
        """#860: correct one rejected watch; never replace it with dated one-shot rows."""
        self.judge = watch_engine([], preparation=False)
        self.service.use_decision_engine(self.judge)
        goal = '같은 목표의 변동을 확인하고 달라질 때 알리기'
        self.script = [{'content': None, 'tool_calls': [
            call('window-bad', 'schedule_preparation', kind='prepare', goal=goal, due=self.due_iso(600),
                 every_minutes='1', until=self.due_iso(600 + 7200), delivery='when_needed')]}]
        for index in range(5):
            self.script.append({'content': None, 'tool_calls': [
                call(f'daily-{index}', 'schedule_preparation', kind='prepare', goal=goal,
                     due=self.due_iso(600 + index * 86400), recurrence='daily', delivery='when_needed')]})
        self.script.extend([
            {'content': None, 'tool_calls': [
                call('window-corrected', 'schedule_preparation', kind='prepare', goal=goal,
                     due=self.due_iso(600), every_minutes='420', until=self.due_iso(600 + 4 * 86400),
                     delivery='when_needed')]},
            finish('finish-watch', 'window-corrected', summary='반복 확인을 제안했습니다.')
        ])

        self.receive('마감 때까지 변동을 매일 확인해줘')

        results = [json.loads(message['content']) for message in self.model_calls[-1]['messages']
                   if message['role'] == 'tool']
        rows = self.rows()
        self.assertEqual(len(rows), 1, ([(row['goal_text'], row['state'], row['recurrence'], row['every_seconds']) for row in rows], results))
        [row] = rows
        self.assertEqual((row['goal_text'], row['state'], row['recurrence'], row['every_seconds'], row['delivery_mode']),
                         (goal, 'proposed', prep.RECURRENCE_WINDOW, 420 * 60, prep.DELIVERY_WHEN_NEEDED))
        self.assertEqual(len(results), 8)  # includes the final finish-tool receipt
        self.assertIn('invalid_window', json.dumps(results[0]))
        self.assertTrue(all('window_retry_required' in json.dumps(result) for result in results[1:6]))
        self.assertEqual(results[6]['preparation_id'], row['id'])
        self.assertTrue(results[6]['requires_owner_acceptance'])

    def test_failed_watch_retry_guard_does_not_block_a_different_explicit_goal(self):
        """#860: the guard is scoped to the rejected watch goal, not the whole Work."""
        self.judge = watch_engine([], preparation=False)
        self.service.use_decision_engine(self.judge)
        self.script = [
            {'content': None, 'tool_calls': [
                call('window-bad', 'schedule_preparation', kind='prepare', goal='가격 변동 확인',
                     due=self.due_iso(600), every_minutes='1', until=self.due_iso(600 + 7200),
                     delivery='when_needed')]},
            {'content': None, 'tool_calls': [
                call('other-goal', 'schedule_preparation', kind='reminder', goal='다른 약속 알림',
                     due=self.due_iso(3600))]},
            finish('finish-other', 'other-goal', summary='두 번째 준비는 제안했습니다.')
        ]

        self.receive('가격 변동을 마감까지 살펴보고 별도로 약속도 알려줘')

        [row] = self.rows()
        self.assertEqual((row['goal_text'], row['kind'], row['state']), ('다른 약속 알림', 'reminder', 'proposed'))
        results = [json.loads(message['content']) for message in self.model_calls[-1]['messages']
                   if message['role'] == 'tool']
        self.assertEqual([result['preparation_id'] for result in results if 'preparation_id' in result], [row['id']])


class SurfaceTests(unittest.TestCase):
    def test_the_tool_is_offered_only_where_the_service_wired_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = QuickStore(Path(tmp) / 'data')
            plain = Capabilities(store, None, {}, '', 'job', lambda *a: None)
            wired = Capabilities(store, None, {}, '', 'job', lambda *a: None, preparations=lambda args: {})
            names = lambda caps: [d['function']['name'] for d in caps.definitions()]
            self.assertNotIn('schedule_preparation', names(plain))
            self.assertIn('schedule_preparation', names(wired))
        schema = next(d for d in action_definitions({'schedule_preparation': {'host_action': 'schedule_preparation'}},
                                                    {'schedule_preparation'}))
        self.assertEqual(schema['function']['parameters']['required'], ['kind', 'goal', 'due'])
        self.assertIn('proposal the owner accepts', schema['function']['description'])
        # Scrubbed with the Work's redactor; without one, only the length.
        scrub = lambda text: text.replace('token-1', '[redacted]')
        self.assertEqual(recorded_arguments('schedule_preparation', {'goal': '갱신 token-1', 'kind': 'reminder'}, scrub)['goal'],
                         '갱신 [redacted]')
        self.assertEqual(recorded_arguments('schedule_preparation', {'goal': 'abc', 'kind': 'reminder'})['goal'], '[가림: 3자]')


UI_CHECK = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const app=fs.readFileSync(process.argv[1],'utf8'),ids=new Map();
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.className='';this.hidden=false;this._text='';}
 set id(value){this._id=value;ids.set(value,this);} get id(){return this._id;}
 set textContent(value){this._text=String(value);this.children=[];} get textContent(){return this._text+this.children.map(node=>typeof node==='string'?node:node.textContent).join('');}
 append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}
 setAttribute(key,value){this.attrs[key]=value;} focus(){} get isConnected(){return true;}
 get classList(){const node=this;return {toggle(name,on){node._cls=Boolean(on);},add(){},remove(){},contains:()=>Boolean(node._cls)};}
 querySelector(){return null;} querySelectorAll(){return [];}
}
function descendants(node){return node.children.flatMap(child=>typeof child==='string'?[]:[child,...descendants(child)]);}
for(const id of ['preparations-list','preparations-feedback'])new Element('div').id=id;
const $=id=>ids.get(id),document={getElementById:$,createElement:tag=>new Element(tag)};
const part=(start,end)=>app.slice(app.indexOf(start),app.indexOf(end));
const source=part('const LANGUAGES=','function normalizeEndpoint(')+part('function element(','function setError(')+part('let preparationRows=','// end of #659 preparations');
const calls=[];
const ctx={document,$,console,calls,
 api:async(path,body)=>{calls.push({path,body});if(body&&body.operation==='accept')ctx.rows=[{...ctx.rows[0],state:'scheduled',accepted_by:'owner-settings'}];if(body&&body.operation==='delete')ctx.rows=[];return {preparations:ctx.rows};},
 busy:async(button,fn)=>fn(),setError:(id,error)=>{$(id).textContent=error?.message||String(error||'');},setFeedback:(id,text)=>{$(id).textContent=text||'';}};
vm.createContext(ctx);vm.runInContext(source,ctx);vm.runInContext("setLanguage('ko')",ctx);
const rows=()=>$('preparations-list').children.filter(node=>node.tag==='div'&&node.className.split(' ')[0]==='settings-row');
const texts=(node,cls)=>descendants(node).filter(n=>n.className===cls).map(n=>n.textContent);
const buttons=node=>descendants(node).filter(n=>n.tag==='button').map(n=>n.textContent);
const press=async(label)=>{const button=descendants(rows()[0]).find(n=>n.tag==='button'&&n.textContent===label);await button.onclick({currentTarget:button});};
(async()=>{
 ctx.rows=[];await ctx.loadPreparations();
 assert.equal($('preparations-list').children[0].className,'settings-empty');
 ctx.rows=[{id:'p1',kind:'prepare',goal:'점심 후보 준비',state:'proposed',due_local:'2026-09-28 11:30 (Mon, Asia/Seoul)',recurrence:'daily',delivery:'keep',last_result:''}];
 await ctx.loadPreparations();
 assert.deepEqual(texts(rows()[0],'settings-row-title'),['점심 후보 준비']);
 assert.equal(texts(rows()[0],'settings-row-description')[0],'미리 준비 · 매일 · 2026-09-28 11:30 (Mon, Asia/Seoul) 예정 · 결과는 보관만 함');
 assert.deepEqual(texts(rows()[0],'settings-state attention'),['수락 대기']);
 assert.deepEqual(buttons(rows()[0]),['수락','취소','삭제']);
 await press('수락');
 assert.equal(JSON.stringify(calls.at(-1)),JSON.stringify({path:'/api/preparations/request',body:{operation:'accept',id:'p1'}}));
 assert.deepEqual(texts(rows()[0],'settings-state active'),['예약됨']);
 assert.deepEqual(buttons(rows()[0]),['취소','삭제']);
 await press('삭제');
 assert.equal(calls.filter(c=>c.body).length,1,'the first press deletes nothing');
 assert(texts(rows()[0],'confirm-text')[0].includes('지난 실행 기록은 남습니다'));
 await press('삭제 확인');
 assert.equal(JSON.stringify(calls.at(-1).body),JSON.stringify({operation:'delete',id:'p1'}));
 assert.equal($('preparations-feedback').textContent,'지웠습니다.');
 ctx.rows=[{id:'p2',kind:'reminder',goal:'치과',state:'running',due_local:'x',recurrence:null,delivery:'send',last_result:''}];
 await ctx.loadPreparations();
 assert.deepEqual(buttons(rows()[0]),['취소'],'a running preparation can be cancelled, not deleted');
 // #719: a watch shows its window, bound, delivery and last typed decision; Settings cancels it.
 ctx.rows=[{id:'p3',kind:'prepare',goal:'출발 확인',state:'scheduled',due_local:'D',recurrence:'window',every_minutes:10,until_local:'U',max_runs:6,run_count:2,delivery:'when_needed',last_decision:'quiet',last_decision_reason:'judged-not-needed',last_result:''}];
 await ctx.loadPreparations();
 assert.equal(texts(rows()[0],'settings-row-description')[0],'미리 준비 · 10분마다 U까지 · 2/6회 실행 · D 예정 · 알려야 할 때만 Telegram으로 알림 · 마지막 실행: 조용히 넘어감 (알릴 일이 없다고 판단)');
 assert.deepEqual(buttons(rows()[0]),['취소','삭제']);
 await press('취소');
 assert.equal(JSON.stringify(calls.at(-1).body),JSON.stringify({operation:'cancel',id:'p3'}));
 vm.runInContext("setLanguage('en')",ctx);ctx.rows=[{...ctx.rows[0],state:'expired',last_decision:'notify',last_decision_reason:'judged-needed'}];
 await ctx.loadPreparations();
 assert.equal(texts(rows()[0],'settings-row-description')[0],'Prepare ahead · Every 10 min until U · 2/6 runs · D · Telegram only when you need to know · Last run: notified (judged you need to know)');
 assert.deepEqual(texts(rows()[0],'settings-state neutral'),['Window closed']);
 console.log('ok');
})().catch(error=>{console.error(error);process.exit(1);});
"""


class PreparationSettingsUi(unittest.TestCase):
    def test_the_settings_group_lists_accepts_cancels_and_deletes(self):
        import shutil
        import subprocess
        node = shutil.which('node')
        if node is None:
            raise unittest.SkipTest('Node is needed for the DOM-stub check')
        app = Path(__file__).resolve().parents[1] / 'src' / 'personal_agent' / 'web' / 'app.js'
        result = subprocess.run([node, '-e', UI_CHECK, str(app)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines()[-1], 'ok')


if __name__ == '__main__':
    unittest.main()

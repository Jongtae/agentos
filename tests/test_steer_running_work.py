"""STEER-01 (#999): a message sent while a Work runs can steer that Work.

Evidence class: model-free, fixture transports.  A scripted compatible-API
model, a recording Telegram transport and a FixtureDecisionEngine replace only
the provider and the wires; the real QuickStore, ``AgentService`` (Telegram
ingress, ``run_one``), ``run_agent`` and the MCP bridge helper run unchanged.
No live model or Telegram is contacted, and none is claimed.
"""
import json
import threading
import unittest

from personal_agent import mcp_bridge
from personal_agent.agent_runtime import STEER_EVENT, STEER_LEAD, claim_owner_steers
from personal_agent.decision import OUTCOME_DECIDED, BinaryDecision, FixtureDecisionEngine, fixture_confidence
from personal_agent.quickstart_service import STEER_FOLDED_TEXT

from test_preparations import CHAT, GENERATION, _Case, call, finish

FIRST = '마음에 드는 벨트 네 개를 장바구니에 한 번에 담아줘'
REMARK = '보니까 내가 로고가 크게 박힌 걸 싫어하네'


def steer_engine(steers):
    """Goal judgments pass; the steer judgment answers ``steers`` (None: unavailable)."""
    def judge(context, proposition):
        if context.purpose == 'goal-reached':
            return BinaryDecision(OUTCOME_DECIDED, True, fixture_confidence())
        if context.purpose == 'running-work-steer' and steers is not None:
            return BinaryDecision(OUTCOME_DECIDED, steers, fixture_confidence())
        return None
    return FixtureDecisionEngine(judge=judge)


class _SteerCase(_Case):
    STEERS = True

    def setUp(self):
        super().setUp()
        self.judge = steer_engine(self.STEERS)
        self.service.use_decision_engine(self.judge)
        # The judgment runs inline here instead of on its own thread.
        self.service.steer_spawn = lambda target: target()
        self.seen = []

    def typed(self, text):
        self.update_id += 1
        self.message_id += 1
        self.service.ingest_update({'update_id': self.update_id, 'message': {
            'message_id': self.message_id, 'from': {'id': CHAT}, 'chat': {'id': CHAT, 'type': 'private'},
            'text': text, 'date': int(self.now)}}, GENERATION)
        return self.message_id

    def jobs(self):
        with self.store.db() as db:
            return {row['message']: dict(row) for row in db.execute('SELECT * FROM jobs ORDER BY created')}

    def events(self, job_id, tool):
        with self.store.db() as db:
            return [dict(row) for row in db.execute('SELECT * FROM tool_events WHERE job_id=? AND tool=? ORDER BY id',
                                                    (job_id, tool))]

    def typed_from_poll_thread(self, text):
        """Ingest on another thread, as the Telegram poll thread does while the work thread runs."""
        sent = []
        thread = threading.Thread(target=lambda: sent.append(self.typed(text)))
        thread.start()
        thread.join()
        return sent[0]

    def remark_mid_run(self, body):
        """The first model call: the owner sends a remark while this Work runs, then a tool is called."""
        self.remark_message = self.typed_from_poll_thread(REMARK)
        return {'content': None, 'tool_calls': [call('1', 'list_notes')]}

    def after_tool(self, body):
        self.seen.append(json.loads(json.dumps(body['messages'])))
        return finish('f', '1', summary='담았어요.')


class SteeringReachesTheRunningWork(_SteerCase):
    def test_a_remark_mid_run_reaches_the_worker_and_is_not_answered_twice(self):
        self.script = [self.remark_mid_run, self.after_tool]
        self.typed(FIRST)
        self.assertTrue(self.service.run_one())

        [messages] = self.seen
        steer = [m for m in messages if m.get('role') == 'user' and str(m.get('content', '')).startswith(STEER_LEAD)]
        self.assertEqual(len(steer), 1)
        self.assertIn(REMARK, steer[0]['content'])
        # The steer follows the tool result it rode on.
        self.assertEqual(messages[-1], steer[0])

        jobs = self.jobs()
        first, remark = jobs[FIRST], jobs[REMARK]
        self.assertEqual((remark['status'], remark['relation_kind'], remark['related_job_id']),
                         ('queued', 'steer', first['id']))
        self.assertEqual([e['status'] for e in self.events(first['id'], STEER_EVENT)], ['received', 'delivered'])
        # Content-free Evidence: the remark text is not in the events.
        self.assertTrue(all(REMARK not in (e['detail'] or '') for e in self.events(first['id'], STEER_EVENT)))

        self.telegram.clear()
        self.assertTrue(self.service.run_one())
        remark = self.jobs()[REMARK]
        self.assertEqual((remark['status'], remark['response'], remark['delivery']),
                         ('succeeded', STEER_FOLDED_TEXT, 'none'))
        self.assertEqual(self.sends(), [], 'a folded remark gets no second answer')
        reactions = [body for method, body in self.telegram if method == 'setMessageReaction']
        self.assertEqual([(r['message_id'], r['reaction']) for r in reactions],
                         [(self.remark_message, [{'type': 'emoji', 'emoji': '👌'}])])
        # The owner's words stay in the conversation.
        with self.store.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM messages WHERE role='user' AND content=?",
                                        (REMARK,)).fetchone()[0], 1)
        self.assertFalse(self.service.run_one())

    def test_a_steer_the_worker_never_received_runs_as_its_own_work(self):
        # The worker answers without another tool call, so nothing carries the remark.
        def remark_then_finish(body):
            self.remark_message = self.typed_from_poll_thread(REMARK)
            return {'content': '담았어요.'}
        self.script = [remark_then_finish]
        self.typed(FIRST)
        self.assertTrue(self.service.run_one())
        self.assertEqual(self.jobs()[REMARK]['relation_kind'], 'steer')
        self.assertFalse(self.store.steer_delivered(self.jobs()[REMARK]['id']))
        calls = len(self.model_calls)
        self.assertTrue(self.service.run_one())
        remark = self.jobs()[REMARK]
        self.assertNotEqual(remark['response'], STEER_FOLDED_TEXT)
        self.assertGreater(len(self.model_calls), calls, 'the remark ran as its own Work')


class SteeredWorkFailed(_SteerCase):
    def test_a_steer_claimed_by_a_work_that_then_failed_runs_as_its_own_work(self):
        self.script = [self.remark_mid_run, self.after_tool]
        self.typed(FIRST)
        self.assertTrue(self.service.run_one())
        first = self.jobs()[FIRST]
        self.assertTrue(self.store.steer_delivered(self.jobs()[REMARK]['id']))
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='failed' WHERE id=?", (first['id'],))
        calls = len(self.model_calls)
        self.assertTrue(self.service.run_one())
        self.assertNotEqual(self.jobs()[REMARK]['response'], STEER_FOLDED_TEXT)
        self.assertGreater(len(self.model_calls), calls)


class NotASteer(_SteerCase):
    STEERS = False

    def test_a_new_request_mid_run_stays_its_own_work(self):
        self.script = [self.remark_mid_run, self.after_tool, {'content': '네, 알겠어요.'}]
        self.typed(FIRST)
        self.assertTrue(self.service.run_one())
        [messages] = self.seen
        self.assertFalse(any(str(m.get('content', '')).startswith(STEER_LEAD) for m in messages))
        remark = self.jobs()[REMARK]
        self.assertEqual((remark['status'], remark['relation_kind']), ('queued', None))
        self.assertEqual(self.events(self.jobs()[FIRST]['id'], STEER_EVENT), [])
        self.assertTrue(self.service.run_one())
        self.assertNotEqual(self.jobs()[REMARK]['response'], STEER_FOLDED_TEXT)


class Unavailable(NotASteer):
    """No answer from the Judgment AI keeps today's behaviour: the message waits its turn."""
    STEERS = None


class StoreAndBridge(_SteerCase):
    def test_a_steer_is_recorded_only_while_the_work_runs_and_its_message_waits(self):
        first = self.store.enqueue(FIRST, 'k-1')
        remark = self.store.enqueue(REMARK, 'k-2')
        self.assertFalse(self.store.add_steer(first, remark, REMARK), 'not running yet')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (first,))
        self.assertTrue(self.store.add_steer(first, remark, REMARK))
        self.assertEqual(self.store.claim_steers(first), [REMARK])
        self.assertEqual(self.store.claim_steers(first), [], 'each steer is handed over once')
        self.assertTrue(self.store.steer_delivered(remark))
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='succeeded' WHERE id=?", (first,))
        other = self.store.enqueue('다른 말', 'k-3')
        self.assertFalse(self.store.add_steer(first, other, '다른 말'), 'a finished Work takes no steer')

    def test_the_bridge_appends_the_steer_to_the_next_tool_result(self):
        first = self.store.enqueue(FIRST, 'k-1')
        remark = self.store.enqueue(REMARK, 'k-2')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (first,))
        self.assertTrue(self.store.add_steer(first, remark, REMARK))
        recorded = []
        result = {'content': [{'type': 'text', 'text': json.dumps({'ok': True})}]}
        mcp_bridge._with_steer(result, self.store, first, lambda *args: recorded.append(args))
        self.assertEqual(len(result['content']), 2)
        self.assertTrue(result['content'][1]['text'].startswith(STEER_LEAD))
        self.assertIn(REMARK, result['content'][1]['text'])
        self.assertEqual([(tool, status) for tool, status, _ in recorded], [(STEER_EVENT, 'delivered')])
        again = {'content': [{'type': 'text', 'text': '{}'}]}
        mcp_bridge._with_steer(again, self.store, first, lambda *args: recorded.append(args))
        self.assertEqual(len(again['content']), 1)
        self.assertIsNone(claim_owner_steers(object(), first))


if __name__ == '__main__':
    unittest.main()

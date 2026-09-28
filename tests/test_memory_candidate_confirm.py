"""OWNER-MODEL-04 (#818): a proposed memory is not a failure; the owner confirms it in one tap.

Observed live 2026-09-28 (Works 18c91ca7, 7767e7da): a ``save_memory`` held as
a pending MemoryCandidate counted as a failed state-changing action, so the
owner saw only "이 요청은 완료하지 못했습니다".  Now the candidate is a recorded
proposal: the answer reaches the owner, then one Telegram message lists the
Work's pending candidates with [기억하기] [아니요], following the #659
preparation-acceptance buttons (exact notification, chat, message and digest;
consume once).  A yes is the existing owner approval path.

Evidence class: unit and model-free service tests with a scripted model and
an injected Telegram transport.
"""
import json
import tempfile
import unittest
from pathlib import Path

from personal_agent.agent_runtime import (CORE_INSTRUCTIONS, DEFINITIONS, event_trail, goal_summary, memory_proposal,
                                          outcome_from_events, state_change_short)
from personal_agent.orchestrator import QUESTION
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import MEMORY_CANDIDATES_KIND, AgentService
from personal_agent.quickstart_store import QuickStore

CHAT = 8181
OTHER = 9191
GENERATION = 'g1'
KEY, VALUE = 'profile.place.work', '판교 카카오뱅크'


def event(action, status='succeeded', **evidence):
    return (action, status, json.dumps({'host_action': action, 'evidence': evidence}))


class TrailTests(unittest.TestCase):
    """The outcome rules read a pending candidate as a proposal, and only for save_memory."""

    PROPOSAL = event('save_memory', saved=False, state='pending', refused_because='value-not-in-owner-request')

    def test_a_memory_proposal_is_settled_not_short(self):
        trail = event_trail([self.PROPOSAL])[0]
        self.assertEqual(trail, [('save_memory', 'proposed')])
        self.assertFalse(state_change_short(trail))
        self.assertEqual(outcome_from_events([self.PROPOSAL])[0], 'succeeded')
        self.assertEqual(goal_summary([self.PROPOSAL])['unresolved'], [])
        read = event('web_search')
        self.assertEqual(outcome_from_events([read, self.PROPOSAL])[0], 'succeeded')

    def test_the_rule_is_scoped_to_save_memory_candidates(self):
        """``refused_because`` on another tool, or a draft awaiting approval, still withholds."""
        other = event('calendar_draft_create', applied=False, requires_owner_approval=True)
        self.assertEqual(event_trail([other])[0], [('calendar_draft_create', 'withheld')])
        self.assertTrue(state_change_short(event_trail([other])[0]))
        refused = event('save_note', refused_because='no-owner-memory-request', state='pending')
        self.assertEqual(event_trail([refused])[0], [('save_note', 'withheld')])
        self.assertFalse(memory_proposal('save_note', {'state': 'pending', 'refused_because': 'x'}))
        self.assertFalse(memory_proposal('save_memory', {'state': 'current', 'id': 'm1'}))

    def test_a_write_that_errored_still_counts(self):
        errored = ('save_memory', 'failed', json.dumps({'host_action': 'save_memory', 'code': 'tool_failed'}))
        trail = event_trail([errored])[0]
        self.assertEqual(trail, [('save_memory', 'failed')])
        self.assertTrue(state_change_short(trail))
        self.assertEqual(outcome_from_events([errored])[0], 'failed')


class TelegramConfirmTests(unittest.TestCase):
    """One Telegram owner, one scripted model, every outbound Telegram call recorded."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parent))
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name) / 'data')
        self.calls = []
        self.plan = []
        self.text = '출근하셨군요. 점심 추천은 판교 기준으로 다시 드릴게요.'

        def transport(url, body=None, headers=None, timeout=60):
            method = url.rsplit('/', 1)[-1]
            self.calls.append((method, body))
            if method == 'sendMessage':
                return {'ok': True, 'result': {'message_id': 700 + len(self.calls)}}
            if method == 'getMe':
                return {'ok': True, 'result': {'username': 'owner_test_bot'}}
            return {'ok': True, 'result': True}

        def model(url, body, headers=None, timeout=60):
            tools = [t.get('function', {}).get('name') or t.get('name') for t in body.get('tools', [])]
            if 'agentos_connection_probe' in tools:
                return {'message': {'content': '', 'tool_calls': [
                    {'id': 'probe', 'function': {'name': 'agentos_connection_probe', 'arguments': {}}}]}}
            if self.plan:
                name, arguments = self.plan.pop(0)
                return {'message': {'content': '', 'tool_calls': [
                    {'id': f'call-{len(self.plan)}', 'function': {'name': name, 'arguments': arguments}}]}}
            return {'message': {'content': self.text}}

        self.service = AgentService(self.store, ModelAdapter(model), transport)
        self.service.save_model({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434',
                                 'model': 'test-model', 'api_key': ''})
        self.assertTrue(self.service.test_model()['ok'])
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION})

    def sends(self):
        return [body for method, body in self.calls if method == 'sendMessage']

    def edits(self):
        return [body for method, body in self.calls if method == 'editMessageText']

    def answers(self):
        return [body.get('text') for method, body in self.calls if method == 'answerCallbackQuery']

    def notification(self, job_id):
        with self.store.db() as db:
            rows = db.execute('SELECT * FROM telegram_notifications WHERE job_id=? AND kind=?',
                              (job_id, MEMORY_CANDIDATES_KIND)).fetchall()
        return [dict(row) for row in rows]

    def turn(self, message='난 오늘 내 직장인 판교 카카오뱅크로 출근했어.', channel=True):
        self.plan = [('save_memory', {'memory_key': KEY, 'content': VALUE})]
        if channel:
            job_id = self.store.enqueue(message, f'ask-{len(self.calls)}', channel=f'telegram:{GENERATION}', chat_id=CHAT)
        else:
            job_id = self.store.enqueue(message, f'web-{len(self.calls)}')
        self.service.run_one()
        return job_id

    def offered(self):
        """Run, deliver the reply, deliver the confirm prompt; return (job, prompt, notification)."""
        job_id = self.turn()
        self.assertEqual(self.notification(job_id), [], 'nothing is offered before the reply')
        self.service.deliver_one()
        self.assertEqual(self.sends()[-1]['text'], self.text, 'the answer is delivered, not withheld')
        self.assertTrue(self.service.deliver_notification())
        [row] = self.notification(job_id)
        return self.store.job(job_id), self.sends()[-1], row

    def tap(self, data, message_id, sender=CHAT, chat=None):
        self.service.ingest_callback({'id': 'cb', 'from': {'id': sender}, 'data': data,
                                      'message': {'message_id': message_id,
                                                  'chat': {'id': chat or sender, 'type': 'private'}}}, GENERATION)

    def test_the_owner_gets_the_answer_then_one_confirm_prompt(self):
        job, prompt, row = self.offered()
        self.assertEqual(job['status'], 'succeeded', job.get('error'))
        self.assertEqual(prompt['text'], f'기억해 둘까요?\n• place.work: {VALUE}')
        buttons = prompt['reply_markup']['inline_keyboard'][0]
        self.assertEqual([button['text'] for button in buttons], ['기억하기', '아니요'])
        self.assertEqual([button['callback_data'] for button in buttons],
                         [f"p7m:{row['id']}:accept", f"p7m:{row['id']}:reject"])
        self.assertEqual(row['state'], 'sent')
        self.assertIsInstance(row['message_id'], int)
        # Queued once: a second delivery pass sends nothing more.
        self.service.queue_memory_candidates(job)
        self.assertFalse(self.service.deliver_notification())
        self.assertEqual(len(self.notification(job['id'])), 1)

    def test_accept_writes_canonical_memory_through_the_approval_path(self):
        job, prompt, row = self.offered()
        self.assertEqual(self.store.memories(), [])
        self.tap(f"p7m:{row['id']}:accept", row['message_id'])
        [memory] = self.store.memories()
        self.assertEqual((memory['memory_key'], memory['content']), (KEY, VALUE))
        [candidate] = self.store.memory_candidates(include_decided=True)
        self.assertEqual((candidate['state'], candidate['resulting_memory_id']), ('accepted', memory['id']))
        [edit] = self.edits()
        self.assertEqual(edit['message_id'], row['message_id'])
        self.assertTrue(edit['text'].startswith('기억해 두었습니다.'), edit['text'])
        self.assertIn(VALUE, edit['text'])
        self.assertEqual(edit['reply_markup'], {'inline_keyboard': []})
        self.assertEqual(self.notification(job['id'])[0]['state'], 'memory_accepted')
        # Consumed once: the same tap again changes nothing.
        self.tap(f"p7m:{row['id']}:reject", row['message_id'])
        self.assertEqual(len(self.store.memories()), 1)
        self.assertEqual(len(self.edits()), 1)
        self.assertEqual(self.answers()[-1], '처리할 수 있는 요청이 아닙니다.')

    def test_reject_leaves_memory_untouched(self):
        job, _prompt, row = self.offered()
        self.tap(f"p7m:{row['id']}:reject", row['message_id'])
        self.assertEqual(self.store.memories(), [])
        [candidate] = self.store.memory_candidates(include_decided=True)
        self.assertEqual(candidate['state'], 'rejected')
        self.assertTrue(self.edits()[-1]['text'].startswith('기억하지 않았습니다.'))
        self.tap(f"p7m:{row['id']}:accept", row['message_id'])
        self.assertEqual(self.store.memories(), [], 'a used message cannot accept later')

    def test_other_chat_other_message_and_stale_taps_are_refused(self):
        job, _prompt, row = self.offered()
        self.tap(f"p7m:{row['id']}:accept", row['message_id'], sender=OTHER)
        self.tap(f"p7m:{row['id']}:accept", row['message_id'] + 1)
        self.tap(f"p7m:{row['id']}:accept", row['message_id'], chat=OTHER)
        self.service.ingest_callback({'id': 'cb', 'from': {'id': CHAT}, 'data': f"p7m:{row['id']}:accept",
                                      'message': {'message_id': row['message_id'], 'chat': {'id': CHAT, 'type': 'private'}}},
                                     'g0')
        self.assertEqual(self.store.memories(), [])
        self.assertEqual(self.edits(), [])
        # Stale: the owner decided the candidate in 내 기록 before tapping.
        [candidate] = self.store.memory_candidates()
        self.service.memory_candidate_request({'operation': 'reject', 'work_ref': candidate['work_ref'],
                                               'id': candidate['id'], 'content_digest': candidate['content_digest']})
        self.tap(f"p7m:{row['id']}:accept", row['message_id'])
        self.assertEqual(self.store.memories(), [])
        self.assertEqual(self.notification(job['id'])[0]['state'], 'sent')
        self.assertEqual(self.answers()[-1], '처리할 수 있는 요청이 아닙니다.')

    def test_a_changed_set_is_not_offered(self):
        job_id = self.turn()
        self.service.deliver_one()
        [candidate] = self.store.memory_candidates()
        self.store.reject_memory_candidate('local-owner', job_id, candidate['id'], candidate['content_digest'])
        before = len(self.sends())
        self.assertTrue(self.service.deliver_notification())
        self.assertEqual(len(self.sends()), before)
        self.assertEqual(self.notification(job_id)[0]['state'], 'cancelled')

    def test_a_web_work_offers_nothing_on_telegram(self):
        job_id = self.turn(channel=False)
        self.service.queue_memory_candidates(self.store.job(job_id))
        self.assertEqual(self.notification(job_id), [])

    def test_the_prompt_is_bounded(self):
        job_id = self.store.enqueue('x', 'bounded', channel=f'telegram:{GENERATION}', chat_id=CHAT)
        for index in range(7):
            self.store.save_memory_candidate(job_id, f'profile.item{index}', '가' * 300)
        shown, remaining = self.service.offered_memory_candidates(job_id)
        self.assertEqual((len(shown), remaining), (5, 2))
        text = self.service.memory_candidates_text(shown, remaining)
        self.assertTrue(all(len(line) <= 200 for line in text.splitlines()), text)
        self.assertIn('그 밖의 후보 2개는 내 기록에서 확인할 수 있습니다.', text)


class GuidanceTests(unittest.TestCase):
    """#818 items 3 and 4: generic guidance texts; the judgment stays the model's."""

    def test_save_memory_content_is_the_value_in_the_owners_words(self):
        [save_memory] = [tool['function'] for tool in DEFINITIONS if tool['function']['name'] == 'save_memory']
        self.assertIn("content is the value itself in the owner's own words", save_memory['description'])
        self.assertIn('not a sentence about it; memory_key names the attribute', save_memory['description'])

    def test_owner_statements_get_a_secretarys_response(self):
        self.assertIn('When the owner tells you something about themselves or their situation rather than asking',
                      CORE_INSTRUCTIONS)
        self.assertIn('earlier advice or plans that no longer fit, timing that has passed, and a brief apology',
                      CORE_INSTRUCTIONS)
        self.assertIn('When the owner tells AgentOS something about themselves or their situation rather than asking',
                      QUESTION)
        self.assertIn('timing that has passed, and a brief apology where AgentOS fell short', QUESTION)


if __name__ == '__main__':
    unittest.main()

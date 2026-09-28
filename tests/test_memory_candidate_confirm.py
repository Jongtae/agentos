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
from personal_agent.providers import ModelAdapter, ProviderError
from personal_agent.quickstart_service import (MEMORY_CANDIDATES_KIND, MEMORY_PENDING_TELEGRAM_NOTE, MEMORY_PENDING_WEB_NOTE,
                                               MEMORY_UPKEEP_KIND, AgentService)
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
        self.lose_reply = False   # the next sendMessage times out (delivery 'unknown')
        self.text = '출근하셨군요. 점심 추천은 판교 기준으로 다시 드릴게요.'

        def transport(url, body=None, headers=None, timeout=60):
            method = url.rsplit('/', 1)[-1]
            self.calls.append((method, body))
            if method == 'sendMessage' and self.lose_reply:
                self.lose_reply = False
                raise ProviderError('Telegram timed out')
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

    def notification(self, job_id, kind=MEMORY_CANDIDATES_KIND):
        with self.store.db() as db:
            rows = db.execute('SELECT * FROM telegram_notifications WHERE job_id=? AND kind=?',
                              (job_id, kind)).fetchall()
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
        self.assertEqual(self.sends()[-1]['text'], self.text + '\n\n' + MEMORY_PENDING_TELEGRAM_NOTE,
                         'the answer is delivered with AgentOS\'s own not-yet-saved line')
        self.assertTrue(self.service.deliver_notification())
        [row] = self.notification(job_id)
        return self.store.job(job_id), self.sends()[-1], row

    def tap(self, data, message_id, sender=CHAT, chat=None):
        self.service.ingest_callback({'id': 'cb', 'from': {'id': sender}, 'data': data,
                                      'message': {'message_id': message_id,
                                                  'chat': {'id': chat or sender, 'type': 'private'}}}, GENERATION)

    def open_candidates(self, job_id):
        return [row for row in self.store.memory_candidates() if row['state'] == 'pending']

    def binding(self, row):
        return json.loads(self.store.notification(row['id'])['fingerprint'])

    def test_the_owner_gets_the_answer_then_one_confirm_prompt(self):
        job, prompt, row = self.offered()
        self.assertEqual(job['status'], 'succeeded', job.get('error'))
        self.assertEqual(prompt['text'], f'기억해 둘까요?\n• place.work: {VALUE}')
        buttons = prompt['reply_markup']['inline_keyboard']
        self.assertEqual([[button['text'] for button in line] for line in buttons], [['기억하기', '아니요']])
        self.assertEqual([button['callback_data'] for button in buttons[0]],
                         [f"p7m:{row['id']}:1:accept", f"p7m:{row['id']}:1:reject"])
        self.assertEqual(row['state'], 'sent')
        self.assertIsInstance(row['message_id'], int)
        # Queued once: a second delivery pass sends nothing more.
        self.service.queue_memory_candidates(job)
        self.assertFalse(self.service.deliver_notification())
        self.assertEqual(len(self.notification(job['id'])), 1)

    def test_accept_writes_canonical_memory_through_the_approval_path(self):
        job, _prompt, row = self.offered()
        self.assertEqual(self.store.memories(), [])
        self.tap(f"p7m:{row['id']}:1:accept", row['message_id'])
        [memory] = self.store.memories()
        self.assertEqual((memory['memory_key'], memory['content']), (KEY, VALUE))
        [candidate] = self.store.memory_candidates(include_decided=True)
        self.assertEqual((candidate['state'], candidate['resulting_memory_id']), ('accepted', memory['id']))
        [edit] = self.edits()
        self.assertEqual(edit['message_id'], row['message_id'])
        self.assertEqual(edit['text'], f'기억해 둘까요?\n• place.work: {VALUE} → 기억함\n'
                                       '기억한 내용은 내 기록에서 고치거나 지울 수 있습니다.')
        self.assertEqual(edit['reply_markup'], {'inline_keyboard': []})
        self.assertEqual(self.notification(job['id'])[0]['state'], 'memory_decided')
        # Consumed once: the same message again changes nothing.
        self.tap(f"p7m:{row['id']}:1:reject", row['message_id'])
        self.assertEqual(len(self.store.memories()), 1)
        self.assertEqual(len(self.edits()), 1)
        self.assertEqual(self.answers()[-1], '처리할 수 있는 요청이 아닙니다.')

    def test_reject_leaves_memory_untouched(self):
        _job, _prompt, row = self.offered()
        self.tap(f"p7m:{row['id']}:1:reject", row['message_id'])
        self.assertEqual(self.store.memories(), [])
        [candidate] = self.store.memory_candidates(include_decided=True)
        self.assertEqual(candidate['state'], 'rejected')
        self.assertTrue(self.edits()[-1]['text'].endswith('→ 기억 안 함'), self.edits()[-1]['text'])
        self.tap(f"p7m:{row['id']}:1:accept", row['message_id'])
        self.assertEqual(self.store.memories(), [], 'a used message cannot accept later')

    def test_other_chat_other_message_and_malformed_taps_are_refused(self):
        _job, _prompt, row = self.offered()
        self.tap(f"p7m:{row['id']}:1:accept", row['message_id'], sender=OTHER)
        self.tap(f"p7m:{row['id']}:1:accept", row['message_id'] + 1)
        self.tap(f"p7m:{row['id']}:1:accept", row['message_id'], chat=OTHER)
        self.tap(f"p7m:{row['id']}:2:accept", row['message_id'])
        self.tap(f"p7m:{row['id']}:accept", row['message_id'])
        self.service.ingest_callback({'id': 'cb', 'from': {'id': CHAT}, 'data': f"p7m:{row['id']}:1:accept",
                                      'message': {'message_id': row['message_id'], 'chat': {'id': CHAT, 'type': 'private'}}},
                                     'g0')
        self.assertEqual(self.store.memories(), [])
        self.assertEqual(self.edits(), [])

    def test_a_candidate_decided_elsewhere_is_reported_outdated(self):
        job, _prompt, row = self.offered()
        [candidate] = self.store.memory_candidates()
        self.service.memory_candidate_request({'operation': 'reject', 'work_ref': candidate['work_ref'],
                                               'id': candidate['id'], 'content_digest': candidate['content_digest']})
        self.tap(f"p7m:{row['id']}:1:accept", row['message_id'])
        self.assertEqual(self.store.memories(), [])
        self.assertIn('→ 그 사이 바뀌어 처리하지 않음', self.edits()[-1]['text'])
        self.assertIn('처리하지 않은 항목이 있습니다', self.answers()[-1])

    def test_a_set_with_nothing_pending_is_not_offered(self):
        job_id = self.turn()
        self.service.deliver_one()
        [candidate] = self.store.memory_candidates()
        self.store.reject_memory_candidate('local-owner', job_id, candidate['id'], candidate['content_digest'])
        before = len(self.sends())
        self.assertTrue(self.service.deliver_notification())
        self.assertEqual(len(self.sends()), before)
        self.assertEqual(self.notification(job_id)[0]['state'], 'cancelled')

    # --- P2-1: #805 upkeep adds candidates to the same Work asynchronously ---------

    def test_an_upkeep_candidate_added_before_the_send_neither_cancels_nor_joins_the_prompt(self):
        job_id = self.turn()
        self.service.deliver_one()
        self.store.save_memory_candidate(job_id, 'profile.routine.commute', '지하철')   # #805 upkeep, same Work
        self.assertTrue(self.service.deliver_notification())
        [row] = self.notification(job_id)
        self.assertEqual(row['state'], 'sent')
        self.assertEqual(self.sends()[-1]['text'], f'기억해 둘까요?\n• place.work: {VALUE}')

    def test_an_upkeep_candidate_added_after_the_send_does_not_break_the_tap(self):
        _job, _prompt, row = self.offered()
        self.store.save_memory_candidate(_job['id'], 'profile.routine.commute', '지하철')
        self.tap(f"p7m:{row['id']}:1:accept", row['message_id'])
        self.assertEqual([(m['memory_key'], m['content']) for m in self.store.memories()], [(KEY, VALUE)])
        self.assertEqual([c['memory_key'] for c in self.open_candidates(_job['id'])], ['profile.routine.commute'],
                         'the later candidate is left to 내 기록, never accepted by this tap')

    # --- P2-2: an old button never overwrites a newer Memory unseen ---------------

    def test_a_memory_changed_after_the_send_refuses_the_tap(self):
        job, _prompt, row = self.offered()
        self.store.save_memory(KEY, '여의도 본사')      # the owner changed it elsewhere
        self.tap(f"p7m:{row['id']}:1:accept", row['message_id'])
        self.assertEqual([m['content'] for m in self.store.memories()], ['여의도 본사'])
        self.assertIn('→ 그 사이 바뀌어 처리하지 않음', self.edits()[-1]['text'])
        self.assertIn('처리하지 않은 항목이 있습니다', self.edits()[-1]['text'])
        self.assertEqual([c['state'] for c in self.store.memory_candidates(include_decided=True)], ['pending'])

    def test_the_prompt_shows_the_value_it_would_replace(self):
        self.store.save_memory(KEY, '서울 역삼 오피스')
        job, prompt, row = self.offered()
        self.assertEqual(prompt['text'], f'기억해 둘까요?\n• place.work: {VALUE} (현재: 서울 역삼 오피스)')
        self.tap(f"p7m:{row['id']}:1:accept", row['message_id'])
        self.assertEqual([m['content'] for m in self.store.memories()], [VALUE], 'the shown value is what it replaced')

    def test_buttons_expire(self):
        job, _prompt, row = self.offered()
        binding = self.binding(row)
        binding['sent'] -= 86401
        self.store.update_notification(row['id'], 'sent', fingerprint=json.dumps(binding))
        self.tap(f"p7m:{row['id']}:1:accept", row['message_id'])
        self.assertEqual(self.store.memories(), [])
        self.assertEqual(self.notification(job['id'])[0]['state'], 'expired')
        self.assertEqual(self.edits()[-1]['reply_markup'], {'inline_keyboard': []})
        self.assertIn('확인 시간이 지나', self.edits()[-1]['text'])

    def test_the_sweep_closes_an_expired_prompt_without_a_tap(self):
        job, _prompt, row = self.offered()
        sent = self.binding(row)['sent']
        self.service.expire_memory_prompts(now=sent + 100)
        self.assertEqual(self.notification(job['id'])[0]['state'], 'sent')
        self.service._memory_prompt_sweep = 0
        self.service.expire_memory_prompts(now=sent + 86401)
        self.assertEqual(self.notification(job['id'])[0]['state'], 'expired')
        self.assertEqual(self.edits()[-1]['reply_markup'], {'inline_keyboard': []})

    def test_each_candidate_is_decided_on_its_own(self):
        job_id = self.store.enqueue('두 가지', 'two', channel=f'telegram:{GENERATION}', chat_id=CHAT)
        self.store.save_memory_candidate(job_id, KEY, VALUE)
        self.store.save_memory_candidate(job_id, 'profile.food_preference', '매운 음식')
        self.service.queue_memory_candidates(self.store.job(job_id))
        self.assertTrue(self.service.deliver_notification())
        [row] = self.notification(job_id)
        prompt = self.sends()[-1]
        self.assertEqual(prompt['text'], f'기억해 둘까요?\n1. place.work: {VALUE}\n2. food_preference: 매운 음식')
        self.assertEqual([[button['text'] for button in line] for line in prompt['reply_markup']['inline_keyboard']],
                         [['1 기억하기', '1 아니요'], ['2 기억하기', '2 아니요'], ['모두 기억하기', '모두 아니요']])
        self.tap(f"p7m:{row['id']}:2:reject", row['message_id'])
        self.assertEqual(self.notification(job_id)[0]['state'], 'sent', 'one is still open')
        self.assertEqual([[button['text'] for button in line] for line in self.edits()[-1]['reply_markup']['inline_keyboard']],
                         [['1 기억하기', '1 아니요']])
        self.tap(f"p7m:{row['id']}:a:accept", row['message_id'])
        self.assertEqual([(m['memory_key'], m['content']) for m in self.store.memories()], [(KEY, VALUE)])
        self.assertEqual(self.notification(job_id)[0]['state'], 'memory_decided')
        self.assertTrue(self.edits()[-1]['text'].endswith('기억한 내용은 내 기록에서 고치거나 지울 수 있습니다.'))

    def test_a_web_work_offers_nothing_on_telegram(self):
        job_id = self.turn(channel=False)
        self.service.queue_memory_candidates(self.store.job(job_id))
        self.assertEqual(self.notification(job_id), [])

    def test_the_prompt_is_bounded(self):
        job_id = self.store.enqueue('x', 'bounded', channel=f'telegram:{GENERATION}', chat_id=CHAT)
        for index in range(7):
            self.store.save_memory_candidate(job_id, f'profile.item{index}', '가' * 300)
        self.service.queue_memory_candidates(self.store.job(job_id))
        self.assertTrue(self.service.deliver_notification())
        text = self.sends()[-1]['text']
        self.assertEqual(len(text.splitlines()), 1 + 5 + 1)
        self.assertTrue(all(len(line) <= 200 for line in text.splitlines()), text)
        self.assertIn('그 밖의 후보 2개는 내 기록에서 확인할 수 있습니다.', text)
        self.assertTrue(all(len(button['callback_data'].encode()) <= 64
                            for line in self.sends()[-1]['reply_markup']['inline_keyboard'] for button in line))

    # --- review round 2 (Codex threads on #819) ------------------------------------

    def test_the_reply_says_nothing_was_saved_yet_on_telegram_and_the_web(self):
        """P1: AgentOS's own line, not a scan of the model's prose; gone once the owner decided."""
        self.text = '기억해 둘게요.'
        job, _prompt, row = self.offered()
        reply = self.sends()[-2]['text']
        self.assertEqual(reply, '기억해 둘게요.\n\n' + MEMORY_PENDING_TELEGRAM_NOTE)
        [served] = [item for item in self.service.owner_jobs(self.store.jobs()) if item['id'] == job['id']]
        self.assertEqual(served['response'], '기억해 둘게요.\n\n' + MEMORY_PENDING_WEB_NOTE)
        [message] = [item for item in self.service.owner_messages(self.store.history())
                     if item.get('role') == 'assistant' and item.get('job_id') == job['id']]
        self.assertTrue(message['content'].endswith(MEMORY_PENDING_WEB_NOTE))
        self.tap(f"p7m:{row['id']}:1:accept", row['message_id'])
        [served] = [item for item in self.service.owner_jobs(self.store.jobs()) if item['id'] == job['id']]
        self.assertEqual(served['response'], '기억해 둘게요.', 'decided: the line is no longer true, so it is gone')

    def test_a_reply_without_candidates_carries_no_line(self):
        job_id = self.store.enqueue('안녕', 'plain', channel=f'telegram:{GENERATION}', chat_id=CHAT)
        self.text = '안녕하세요.'
        self.service.run_one()
        self.service.deliver_one()
        self.assertEqual(self.sends()[-1]['text'], '안녕하세요.')
        self.assertEqual(self.notification(job_id), [])

    def test_only_a_value_shown_complete_and_unchanged_gets_a_button(self):
        """P1: the owner approves exactly what was shown; anything else is left to 내 기록."""
        job_id = self.store.enqueue('세 가지', 'three', channel=f'telegram:{GENERATION}', chat_id=CHAT)
        self.store.save_memory_candidate(job_id, KEY, VALUE)
        self.store.save_memory_candidate(job_id, 'profile.note.long', '가' * 121)
        self.store.save_memory_candidate(job_id, 'profile.note.key', 'sk-proj-abcdefghijklmnopqrstuvwxyz123456')
        self.service.queue_memory_candidates(self.store.job(job_id))
        self.assertTrue(self.service.deliver_notification())
        [row] = self.notification(job_id)
        prompt = self.sends()[-1]
        lines = prompt['text'].splitlines()
        self.assertEqual(lines[1], f'1. place.work: {VALUE}')
        self.assertTrue(lines[2].endswith('… → 내 기록에서 확인해 주세요'), lines[2])
        self.assertEqual(lines[3], '3. note.key: [redacted] → 내 기록에서 확인해 주세요')
        self.assertEqual([[button['callback_data'] for button in line] for line in prompt['reply_markup']['inline_keyboard']],
                         [[f"p7m:{row['id']}:1:accept", f"p7m:{row['id']}:1:reject"]])
        for target in ('2', '3'):
            self.tap(f"p7m:{row['id']}:{target}:accept", row['message_id'])
        self.assertEqual(self.store.memories(), [])
        self.tap(f"p7m:{row['id']}:a:accept", row['message_id'])
        self.assertEqual([(m['memory_key'], m['content']) for m in self.store.memories()], [(KEY, VALUE)],
                         '"all" covers only what the message showed complete')
        self.assertEqual(sorted(c['memory_key'] for c in self.store.memory_candidates()),
                         ['profile.note.key', 'profile.note.long'])

    def test_a_prompt_with_nothing_tappable_is_only_a_list(self):
        job_id = self.store.enqueue('긴 값', 'long', channel=f'telegram:{GENERATION}', chat_id=CHAT)
        self.store.save_memory_candidate(job_id, KEY, '가' * 200)
        self.service.queue_memory_candidates(self.store.job(job_id))
        self.assertTrue(self.service.deliver_notification())
        self.assertEqual(self.sends()[-1]['reply_markup'], {'inline_keyboard': []})
        self.assertEqual(self.notification(job_id)[0]['state'], 'memory_listed')

    def test_no_prompt_after_an_unknown_reply_delivery(self):
        """P2: a reply that may not have arrived is never followed by an approval prompt."""
        job_id = self.turn()
        self.lose_reply = True
        self.service.deliver_one()
        self.assertEqual(self.store.job(job_id)['delivery'], 'unknown')
        self.assertEqual(self.notification(job_id), [])
        self.assertFalse(self.service.deliver_notification())
        self.assertEqual([c['state'] for c in self.store.memory_candidates()], ['pending'], 'still in 내 기록')

    def upkeep_adds(self, job_id, key='profile.routine.commute', content='지하철'):
        """Run the #805 upkeep path with a scripted result that leaves one pending candidate."""
        def run(job, judgments, **_kwargs):
            candidate = self.store.save_memory_candidate(job['id'], key, content)
            return 'done', 1, 'recorded', {'applied': [{'memory_key': key, 'candidate_id': candidate['id'],
                                                         'outcome': 'candidate', 'refused_because': 'inferred'}]}
        self.service.owner_model.run = run
        self.assertTrue(self.service.owner_model_flight.acquire(blocking=False))
        self.service._owner_model_run({'job_id': job_id, 'expired': 0}, 0)

    def test_upkeep_candidates_get_one_later_prompt(self):
        """P2: upkeep runs after the only reply-time queueing point; it queues its own prompt."""
        job, _prompt, first = self.offered()
        self.upkeep_adds(job['id'])
        [later] = self.notification(job['id'], MEMORY_UPKEEP_KIND)
        self.assertTrue(self.service.deliver_notification())
        prompt = self.sends()[-1]
        self.assertEqual(prompt['text'], '기억해 둘까요?\n• routine.commute: 지하철', 'only what no earlier prompt listed')
        later = self.notification(job['id'], MEMORY_UPKEEP_KIND)[0]
        self.tap(f"p7m:{later['id']}:1:accept", later['message_id'])
        self.assertEqual([m['content'] for m in self.store.memories()], ['지하철'])
        # The reply's own prompt still decides its own candidate.
        self.tap(f"p7m:{first['id']}:1:accept", first['message_id'])
        self.assertEqual(sorted(m['content'] for m in self.store.memories()), sorted(['지하철', VALUE]))
        # At most one upkeep prompt per Work.
        self.upkeep_adds(job['id'], 'profile.routine.gym', '헬스장')
        self.assertEqual(len(self.notification(job['id'], MEMORY_UPKEEP_KIND)), 1)
        self.assertFalse(self.service.deliver_notification())

    def test_no_upkeep_prompt_before_the_reply_was_sent(self):
        job_id = self.turn()
        self.upkeep_adds(job_id)
        self.assertEqual(self.notification(job_id, MEMORY_UPKEEP_KIND), [])
        self.service.deliver_one()
        self.assertTrue(self.service.deliver_notification())
        self.assertEqual(self.sends()[-1]['text'].splitlines()[1:],
                         [f'1. place.work: {VALUE}', '2. routine.commute: 지하철'], 'the reply prompt lists both')

    # --- P3: the in-process outcome agrees with the event-derived one --------------

    def test_a_proposal_does_not_lift_a_failed_turn_to_partial(self):
        self.plan = [('calendar_query', {'start': '2026-09-24T00:00:00+09:00', 'end': '2026-09-25T00:00:00+09:00',
                                         'timezone': 'Asia/Seoul'}),
                     ('save_memory', {'memory_key': KEY, 'content': VALUE})]
        job_id = self.store.enqueue('내일 일정 알려줘', 'p3', channel=f'telegram:{GENERATION}', chat_id=CHAT)
        self.service.run_one()
        job = self.store.job(job_id)
        with self.store.db() as db:
            rows = [tuple(row) for row in db.execute('SELECT tool,status,detail FROM tool_events WHERE job_id=? ORDER BY id',
                                                     (job_id,))]
        self.assertEqual(outcome_from_events(rows)[0], 'failed')
        self.assertEqual(job['status'], 'failed', job.get('error'))


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

"""ATTN-WAIT-01 / #839: one already-prepared item on the waiting draft.

Drives the real Telegram ingest -> worker -> presence path with the fake
transport and fake clock of ``test_telegram_native_presence``.  The items
come from existing state only (preparations, memory asks); no model call
picks them.  Evidence class: automated synthetic/fixture only.
"""
import json
import time
import unittest

from personal_agent import preparations as prep
from personal_agent.information_use import work_information_use
from personal_agent.quickstart_service import MEMORY_CANDIDATES_KIND
from personal_agent.telegram_presence import (ATTENTION_ASK, ATTENTION_PREFIX, ATTENTION_PREPARED, ATTENTION_REMINDER,
                                              DOTS_FRAMES, attention_line, draft_frame, pick_attention)
from test_telegram_native_presence import CHAT, GENERATION, NativePresenceTestCase

SECRET = 'sk-live-ATTNSECRET1234567890'


class AttentionWaitTests(NativePresenceTestCase):
    def setUp(self):
        super().setUp()
        self.connect_model()
        # Two draft ticks while the model "thinks": 6 s and 8 s after the Work started.
        self.during_model = lambda job: [self.service.acknowledge_long_work(now=job['created'] + offset) for offset in (6, 8)]

    # --- fixtures --------------------------------------------------------------

    def prepared(self, goal='내일 아침 회의 자료 요약', delivered=False, age=600):
        """A fresh prepared answer whose run reached (or not) the owner as a message."""
        now = time.time()
        row = self.service.preparations.create(kind=prep.KIND_PREPARE, goal=goal, due_at=now - age - 60, timezone='Asia/Seoul',
                                               recurrence=None, channel=prep.CHANNEL_TELEGRAM, created_from='seed-' + goal,
                                               state=prep.STATE_SCHEDULED, accepted_by=prep.ACCEPTED_OWNER_BUTTON)
        run_id = 'run-' + row['id']
        with self.store.db() as db:
            db.execute("INSERT INTO jobs(id,request_key,message,channel,chat_id,status,response,error,delivery,created) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (run_id, prep.request_key(row['id'], row['due_at']), goal, 'web', None, 'succeeded', '답', None,
                        'sent' if delivered else 'none', now - age))
            db.execute("UPDATE preparations SET state=?,prepared_result_ref=?,prepared_at=?,prepared_text=? WHERE id=?",
                       (prep.STATE_DELIVERED, run_id, now - age, '준비한 답 ' + SECRET, row['id']))
        return row

    def reminder(self, hours, goal='공항 출발'):
        return self.service.preparations.create(kind=prep.KIND_REMINDER, goal=goal, due_at=time.time() + hours * 3600,
                                                timezone='Asia/Seoul', recurrence=None, channel=prep.CHANNEL_TELEGRAM,
                                                created_from='seed-' + goal, state=prep.STATE_SCHEDULED,
                                                accepted_by=prep.ACCEPTED_OWNER_BUTTON)

    def memory_ask(self, content='저녁은 매운 음식 선호', work='earlier-work'):
        """An open memory ask of an earlier Work, as #836 binds it at send time."""
        with self.store.db() as db:
            db.execute("INSERT INTO jobs(id,request_key,message,channel,chat_id,status,response,error,delivery,created) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?)", (work, None, '이전 질문', f'telegram:{GENERATION}', CHAT, 'succeeded',
                                                        '답', None, 'sent', time.time() - 300))
        candidate = self.store.save_memory_candidate(work, 'profile.food_preference', content)
        row = self.store.memory_candidate(candidate['id'], work_id=work)
        binding = {'candidates': [self.service.memory_prompt_item(row)], 'more': 0, 'sent': time.time() - 200, 'done': {}}
        with self.store.db() as db:
            db.execute('INSERT INTO telegram_notifications VALUES (?,?,?,?,?,?,?,?,?)',
                       ('n-' + work, work, CHAT, GENERATION, MEMORY_CANDIDATES_KIND, json.dumps(binding), 'sent', 777,
                        time.time() - 200))
        return candidate

    def attention_lines(self):
        return [text.split('\n', 1)[1] for text in self.drafts() if '\n' in text]

    def surfacings(self, job_id):
        return [event for event in self.store.task_events(job_id) if event['tool'] == 'presence']

    # --- (a) a fresh unread prepared answer --------------------------------------

    def test_fresh_unread_prepared_answer_is_surfaced_on_the_draft(self):
        row = self.prepared()
        job, _ = self.turn('오늘 저녁 뭐 먹지?')
        self.assertEqual(job['status'], 'succeeded')
        drafts = self.drafts()
        self.assertEqual(len(drafts), 2)
        # Dots first, the "참, …" line under them; the same line on every frame of this Work, never empty.
        self.assertEqual(drafts[0], draft_frame('', 0, attention_line(ATTENTION_PREPARED, row['goal_text'])))
        self.assertEqual(drafts[1].split('\n')[0], DOTS_FRAMES[1])
        self.assertTrue(all(line.startswith(ATTENTION_PREFIX) and row['goal_text'] in line for line in self.attention_lines()))
        self.assertNotIn(SECRET, '\n'.join(drafts))
        # The durable surfaces are unchanged: one reply, no extra message, the preparation row untouched.
        self.assertEqual(len(self.sends()), 1)
        self.assertEqual(self.service.preparations.get(row['id'])['state'], prep.STATE_DELIVERED)
        self.assertEqual(self.after_answer(), ['setMessageReaction'])

    def test_a_prepared_answer_that_reached_the_owner_is_not_repeated(self):
        self.prepared(delivered=True)
        self.turn('질문')
        self.assertEqual(self.attention_lines(), [])
        self.assertEqual(self.drafts(), [DOTS_FRAMES[0], DOTS_FRAMES[1]])

    # --- (b) reminders ---------------------------------------------------------------

    def test_reminder_due_within_12_hours_is_surfaced_and_a_later_one_is_not(self):
        self.reminder(20, goal='치과 예약')
        soon = self.reminder(3, goal='공항 출발')
        self.turn('질문')
        lines = self.attention_lines()
        self.assertTrue(lines)
        self.assertIn('공항 출발', lines[0])
        self.assertIn('알림 있어요', lines[0])
        self.assertNotIn('치과', '\n'.join(lines))
        self.assertIn(prep.local_text(soon['due_at'], 'Asia/Seoul'), lines[0])
        # The reminder still fires at its own time: the row is untouched.
        self.assertEqual(self.service.preparations.get(soon['id'])['state'], prep.STATE_SCHEDULED)

    def test_reminder_only_due_in_20_hours_surfaces_nothing(self):
        self.reminder(20)
        self.turn('질문')
        self.assertEqual(self.attention_lines(), [])

    # --- (c) a pending ask -----------------------------------------------------------

    def test_pending_memory_ask_is_surfaced(self):
        self.memory_ask()
        self.turn('질문')
        lines = self.attention_lines()
        self.assertTrue(lines)
        self.assertIn('저녁은 매운 음식 선호', lines[0])
        self.assertIn('기억해 둘까요', lines[0])
        self.assertNotIn('food_preference', lines[0], 'the value, never the memory key')

    def test_selection_order_prepared_then_reminder_then_ask(self):
        self.memory_ask()
        self.reminder(2)
        row = self.prepared()
        self.turn('질문')
        self.assertIn(row['goal_text'], self.attention_lines()[0])
        self.assertEqual(len({line for line in self.attention_lines()}), 1, 'at most one item per Work')

    # --- (d) the Work is itself the preparation's run --------------------------------

    def test_nothing_for_the_work_that_is_the_preparations_own_run(self):
        row = self.prepared()
        job_id, _ = self.receive('준비 실행')
        with self.store.db() as db:
            db.execute('UPDATE jobs SET request_key=? WHERE id=?', (prep.request_key(row['id'], time.time()), job_id))
        self.service.run_one()
        self.service.deliver_one()
        self.assertTrue(self.drafts())
        self.assertEqual(self.attention_lines(), [])
        self.assertEqual(self.surfacings(job_id), [])

    def test_nothing_for_the_work_whose_own_ask_is_pending(self):
        job_id, _ = self.receive('질문')
        # The open ask belongs to this Work itself.
        candidate = self.store.save_memory_candidate(job_id, 'profile.food_preference', '매운 음식')
        row = self.store.memory_candidate(candidate['id'], work_id=job_id)
        binding = {'candidates': [self.service.memory_prompt_item(row)], 'more': 0, 'sent': time.time(), 'done': {}}
        with self.store.db() as db:
            db.execute('INSERT INTO telegram_notifications VALUES (?,?,?,?,?,?,?,?,?)',
                       ('n-own', job_id, CHAT, GENERATION, MEMORY_CANDIDATES_KIND, json.dumps(binding), 'sent', 778, time.time()))
        self.service.run_one()
        self.service.deliver_one()
        self.assertEqual(self.attention_lines(), [])

    # --- (e) cooldown ------------------------------------------------------------------

    def test_cooldown_prevents_the_same_item_twice(self):
        self.prepared()
        self.turn('첫 질문')
        self.assertTrue(self.attention_lines())
        self.calls.clear()
        self.during_model = lambda job: [self.service.acknowledge_long_work(now=job['created'] + offset) for offset in (6, 8)]
        self.turn('둘째 질문')
        self.assertTrue(self.drafts())
        self.assertEqual(self.attention_lines(), [], 'the same prepared answer is not surfaced again within the cooldown')

    def test_pick_attention_respects_cooldown_and_rank(self):
        items = [{'ref': 'a', 'kind': ATTENTION_ASK, 'text': 'ask', 'at': 1},
                 {'ref': 'r', 'kind': ATTENTION_REMINDER, 'text': 'rem', 'at': 2},
                 {'ref': 'p', 'kind': ATTENTION_PREPARED, 'text': 'prep', 'at': 3}]
        self.assertEqual(pick_attention(items, 1000, {})['ref'], 'p')
        self.assertEqual(pick_attention(items, 1000, {'p': 999})['ref'], 'r')
        self.assertEqual(pick_attention(items, 1000, {'p': 999, 'r': 998})['ref'], 'a')
        self.assertIsNone(pick_attention(items, 1000, {'p': 999, 'r': 998, 'a': 997}))
        self.assertEqual(pick_attention(items, 1000, {'p': 1000 - 7 * 3600})['ref'], 'p', 'after the cooldown it may return')
        self.assertIsNone(pick_attention([{'ref': 'x', 'kind': 'other', 'text': 't'}], 1000))
        self.assertIsNone(attention_line(ATTENTION_ASK, '   '))

    # --- (f) approval step -------------------------------------------------------------

    def test_nothing_is_surfaced_while_an_approval_prompt_is_pending(self):
        self.prepared()
        job_id, _ = self.receive('질문')
        with self.store.db() as db:
            db.execute('INSERT INTO telegram_notifications VALUES (?,?,?,?,?,?,?,?,?)',
                       ('n-approval', job_id, CHAT, GENERATION, 'approval_needed', None, 'queued', None, time.time()))
        self.service.run_one()
        self.assertNotIn('sendMessageDraft', self.methods())
        self.assertEqual(self.surfacings(job_id), [])

    # --- (g) the audit -------------------------------------------------------------------

    def test_surfacing_is_recorded_in_the_works_information_use_audit(self):
        row = self.prepared()
        job, _ = self.turn('질문')
        [event] = self.surfacings(job['id'])
        self.assertEqual(event['status'], 'succeeded')
        self.assertEqual(event['trace']['ref'], 'prep:' + row['id'])
        self.assertNotIn(SECRET, json.dumps(event, ensure_ascii=False))
        audit = work_information_use(self.store, job['id'], self.service._redact_known_secrets)
        [used] = [section for section in audit['used'] if section['category'] == 'attention']
        self.assertEqual(used['name'], '기다리는 동안 알린 것')
        self.assertIn(row['goal_text'], used['items'][0])
        self.assertIn('prep:' + row['id'], used['items'][0])
        self.assertEqual(self.store.config('attention_surfaced')['prep:' + row['id']], job['created'] + 6)


if __name__ == '__main__':
    unittest.main()

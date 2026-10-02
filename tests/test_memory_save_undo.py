"""GOV-ASK-LESS-01 slice (a) (#918): the owner's own AI saves a fact at once; the owner is told, with undo.

Owner decision 2026-09-30: "기억해 둘게요. • 배우자(아내)가 있음 — 이런건 물어보지 않고
그냥 처리 하는게 좋을 것 같은데, 모든 물어보는 행위는 좋은 사용자 경험이 아니야".

* The owner's worker's ``save_memory`` writes current Memory at once (no
  👍/👎 ask, no #597 judgment call).  After the reply, one quiet notice per
  Work: "기억했어요: <fact> · [되돌리기]".  Several facts of one Work share one
  notice; a fact #805 upkeep saves later joins it by an edit.
* 되돌리기 retracts exactly that Memory row (bound id and content digest),
  restores the value it superseded, and edits the notice to "되돌렸어요".  It
  is exact (this notification, chat, generation, message), consumed once,
  refused after seven days, and refused when the row changed since.
* Third-party writers (package tools, delegated specialists) still leave a
  pending MemoryCandidate with the #818/#836 ask (C5 unchanged for them).
* The web lists the fact as saved, not for review; Evidence and the
  information-use audit record the auto-saved write and the undo.

Evidence class: unit and model-free service tests with a scripted model and
an injected Telegram transport.  No live model, no live Telegram.
"""
import json
import tempfile
import unittest
from pathlib import Path

from personal_agent.agent_runtime import (CORE_INSTRUCTIONS, DEFINITIONS, MEMORY_OWNER, MEMORY_REFUSALS,
                                          SECRET_SHAPED_VALUE, THIRD_PARTY_MEMORY_WRITE, Capabilities, evidence_summary,
                                          work_written_values, worker_result)
from personal_agent.decision import OUTCOME_DECIDED, BinaryDecision, FixtureDecisionEngine, fixture_confidence
from personal_agent.manifests import runtime_packages
from personal_agent.quickstart_service import (MEMORY_CANDIDATES_KIND, MEMORY_PENDING_WEB_NOTE, MEMORY_SAVED_EXPIRED_TEXT,
                                               MEMORY_SAVED_KIND, MEMORY_SAVED_OUTDATED_TEXT, MEMORY_SAVED_TTL_SECONDS,
                                               MEMORY_SAVED_UPKEEP_KIND, MEMORY_UNDO_TOOL)
from personal_agent.quickstart_store import QuickStore

from test_memory_candidate_confirm import CHAT, GENERATION, KEY, OTHER, VALUE, TelegramHarness

SECOND_KEY, SECOND_VALUE = 'profile.routine.commute', '지하철'


class SaveAndTell(TelegramHarness):
    """The owner's own worker saves; the owner is told after the reply, with undo."""

    def saved_turn(self, message='난 오늘 내 직장인 판교 카카오뱅크로 출근했어.', plan=None, channel=True):
        self.plan = plan if plan is not None else [('save_memory', {'memory_key': KEY, 'content': VALUE})]
        if not self.claim:
            self.claim_completion()
        job_id = self.enqueue(message, channel)
        self.service.run_one()
        return job_id

    def told(self, **kwargs):
        """Run, deliver the reply, deliver the notice; return (job, notice, notification row)."""
        job_id = self.saved_turn(**kwargs)
        self.assertEqual([row['state'] for row in self.notification(job_id, MEMORY_SAVED_KIND)], ['held'],
                         'held at save time; nothing is told before the reply')
        self.service.deliver_one()
        self.assertEqual(self.sends()[-1]['text'], self.text, 'the answer as the secretary said it')
        self.assertTrue(self.service.deliver_notification())
        [row] = self.notification(job_id, MEMORY_SAVED_KIND)
        return self.store.job(job_id), self.sends()[-1], row

    def memory_states(self):
        with self.store.db() as db:
            return [(row['content'], row['state']) for row in db.execute('SELECT content,state FROM memories ORDER BY created,id')]

    def upkeep_saves(self, job_id, key=SECOND_KEY, content=SECOND_VALUE):
        """Run the #805 upkeep path with a scripted result that saved one fact at once."""
        def run(job, judgments, **_kwargs):
            memory = self.store.save_memory(key, content, MEMORY_OWNER, work_id=job['id'], notice=True)
            return 'done', 1, 'recorded', {'applied': [{'memory_key': key, 'memory_id': memory['id'],
                                                         'outcome': 'memory', 'auto_saved': True}]}
        self.service.owner_model.run = run
        self.assertTrue(self.service.owner_model_flight.acquire(blocking=False))
        self.service._owner_model_run({'job_id': job_id, 'expired': 0}, 0)

    # --- save directly, tell with undo --------------------------------------------

    def test_the_owner_worker_save_is_current_at_once_and_the_owner_is_told_with_undo(self):
        job, notice, row = self.told()
        self.assertEqual(job['status'], 'succeeded', job.get('error'))
        self.assertEqual([(m['memory_key'], m['content'], m['state']) for m in self.store.memories()],
                         [(KEY, VALUE, 'current')])
        self.assertEqual(self.store.memory_candidates(include_decided=True), [], 'no candidate, pending or decided')
        self.assertEqual(notice['text'], f'기억했어요: {VALUE}')
        [[button]] = notice['reply_markup']['inline_keyboard']
        self.assertEqual((button['text'], button['callback_data']), ('되돌리기', f"p7u:{row['id']}:1"))
        self.assertEqual(row['state'], 'sent')
        self.assertIsInstance(row['message_id'], int)
        self.assertEqual(self.notification(job['id'], MEMORY_CANDIDATES_KIND), [], 'no ask')
        # Told once: a second pass sends nothing more.
        self.service.queue_memory_saved(job)
        self.assertFalse(self.service.deliver_notification())
        self.assertEqual(len(self.notification(job['id'], MEMORY_SAVED_KIND)), 1)

    def test_the_worker_reads_the_save_as_done(self):
        self.saved_turn()
        [tool] = [message['content'] for message in self.bodies[-1]['messages'] if message.get('role') == 'tool']
        result = json.loads(tool)
        self.assertEqual((result['remembered'], result['content'], result['memory_key'], result['replaced_previous']),
                         (True, VALUE, KEY, False))
        self.assertIn('can undo it', result['next'])
        for word in ('Not remembered', 'one tap', 'AgentOS', 'candidate', 'approval', 'refused_because', 'digest', 'stor'):
            self.assertNotIn(word, tool)

    def test_nothing_asks_anymore_for_an_owner_worker_save(self):
        purposes = []

        def judge(context, proposition):
            purposes.append(context.purpose)
            return BinaryDecision(OUTCOME_DECIDED, True, fixture_confidence()) if context.purpose == 'goal-reached' else None
        self.claim_completion(FixtureDecisionEngine(judge=judge))
        job, _notice, _row = self.told()
        self.assertIn('goal-reached', purposes, 'the judgment ran, so its absence below is meaningful')
        self.assertNotIn('explicit-memory-request', purposes, 'no #597 judgment call on the owner-worker path')
        for body in self.sends():
            self.assertNotIn('기억해 둘까요', body['text'])
            for line in (body.get('reply_markup') or {}).get('inline_keyboard') or ():
                for button in line:
                    self.assertNotIn('👍', button['text'])
                    self.assertNotIn('👎', button['text'])
        self.assertEqual(self.notification(job['id'], MEMORY_CANDIDATES_KIND), [])

    # --- review P2: a save is never untold ---------------------------------------------

    def test_the_save_holds_its_notice_in_the_same_transaction(self):
        job_id = self.saved_turn()
        [row] = self.notification(job_id, MEMORY_SAVED_KIND)
        self.assertEqual(row['state'], 'held', 'durable at save time, released after the reply')
        self.assertFalse(self.service.deliver_notification(), 'held is not queued: nothing goes out before the reply')
        self.service._memory_saved_release_sweep = 0
        self.service.release_memory_saved_notices()
        self.assertEqual(self.notification(job_id, MEMORY_SAVED_KIND)[0]['state'], 'held', 'the reply is still pending')

    def test_the_notice_is_told_after_an_unknown_reply_delivery(self):
        job_id = self.saved_turn()
        self.lose_reply = True
        self.service.deliver_one()
        self.assertEqual(self.store.job(job_id)['delivery'], 'unknown')
        self.assertEqual(self.notification(job_id, MEMORY_SAVED_KIND)[0]['state'], 'queued')
        self.assertTrue(self.service.deliver_notification())
        [row] = self.notification(job_id, MEMORY_SAVED_KIND)
        self.assertEqual((row['state'], self.sends()[-1]['text']), ('sent', f'기억했어요: {VALUE}'))
        self.tap(f"p7u:{row['id']}:1", row['message_id'])
        self.assertEqual(self.store.memories(), [], 'the undo works on the notice that followed the unknown reply')

    def test_a_crash_between_the_reply_and_the_release_is_recovered_by_the_sweep(self):
        job_id = self.saved_turn()
        real = self.service.release_memory_saved
        self.service.release_memory_saved = lambda job: (_ for _ in ()).throw(RuntimeError('crash'))
        self.service.deliver_one()
        self.service.release_memory_saved = real
        self.assertEqual(self.store.job(job_id)['delivery'], 'sent')
        self.assertEqual(self.notification(job_id, MEMORY_SAVED_KIND)[0]['state'], 'held')
        self.assertFalse(self.service.deliver_notification())
        self.service._memory_saved_release_sweep = 0
        self.service.release_memory_saved_notices()
        self.assertEqual(self.notification(job_id, MEMORY_SAVED_KIND)[0]['state'], 'queued')
        self.assertTrue(self.service.deliver_notification())
        self.assertEqual(self.sends()[-1]['text'], f'기억했어요: {VALUE}')

    def test_a_notice_lost_in_sending_is_told_again_after_a_restart(self):
        job, _notice, row = self.told()
        # A crash while the notice was being sent leaves 'sending'; recover() marks it 'unknown' (#581).
        self.store.update_notification(row['id'], 'sending')
        self.store.recover()
        self.assertEqual(self.notification(job['id'], MEMORY_SAVED_KIND)[0]['state'], 'unknown')
        sends = len(self.sends())
        self.service._memory_saved_release_sweep = 0
        self.service.release_memory_saved_notices()
        self.assertTrue(self.service.deliver_notification())
        self.assertEqual(len(self.sends()), sends + 1)
        [again] = self.notification(job['id'], MEMORY_SAVED_KIND)
        self.assertEqual((again['state'], self.sends()[-1]['text']), ('sent', f'기억했어요: {VALUE}'))
        self.assertEqual(self.binding(again)['retells'], 1)
        self.tap(f"p7u:{again['id']}:1", again['message_id'])
        self.assertEqual(self.store.memories(), [])
        # Told again at most once: a second loss stays in 내 기록.
        self.store.update_notification(again['id'], 'unknown')
        self.service._memory_saved_release_sweep = 0
        self.service.release_memory_saved_notices()
        self.assertEqual(self.notification(job['id'], MEMORY_SAVED_KIND)[0]['state'], 'unknown')

    def test_a_retried_work_that_saves_again_after_its_notice_tells_the_second_fact(self):
        """Re-review P2: the notice was told, the Work is retried (delivery 'none'), a second save is told too."""
        job, _notice, row = self.told()
        self.assertEqual(self.binding(row)['items'][0]['key'], KEY)
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='queued',delivery='none',response=NULL WHERE id=?", (job['id'],))
        self.plan = [('save_memory', {'memory_key': SECOND_KEY, 'content': SECOND_VALUE})]
        self.service.run_one()
        self.assertEqual(sorted(m['content'] for m in self.store.memories()), sorted([VALUE, SECOND_VALUE]))
        self.assertEqual([r['state'] for r in self.notification(job['id'], MEMORY_SAVED_KIND)], ['sent'], 'one row per Work')
        sends = len(self.sends())
        self.service.deliver_one()
        self.assertEqual(self.store.job(job['id'])['delivery'], 'sent')
        self.assertEqual(self.edits()[-1]['text'], f'기억했어요\n1. {VALUE}\n2. {SECOND_VALUE}', 'joined into the told notice')
        self.assertEqual(len(self.binding(row)['items']), 2)
        self.assertFalse(self.service.deliver_notification(), 'no second message; the edit told it')
        self.assertEqual(len(self.sends()), sends + 1, 'only the retried reply was sent')
        self.tap(f"p7u:{row['id']}:2", row['message_id'])
        self.assertEqual([m['content'] for m in self.store.memories()], [VALUE])

    def test_a_retried_work_after_an_undone_notice_gets_a_separate_notice(self):
        job, _notice, row = self.told()
        self.tap(f"p7u:{row['id']}:1", row['message_id'])
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='queued',delivery='none',response=NULL WHERE id=?", (job['id'],))
        self.plan = [('save_memory', {'memory_key': SECOND_KEY, 'content': SECOND_VALUE})]
        self.service.run_one()
        self.service.deliver_one()
        self.assertTrue(self.service.deliver_notification())
        self.assertEqual(self.sends()[-1]['text'], f'기억했어요: {SECOND_VALUE}')
        [upkeep] = self.notification(job['id'], MEMORY_SAVED_UPKEEP_KIND)
        self.assertEqual(upkeep['state'], 'sent')

    def test_an_upkeep_save_after_an_unknown_reply_is_told_too(self):
        job_id = self.saved_turn()
        self.lose_reply = True
        self.service.deliver_one()
        self.assertTrue(self.service.deliver_notification())
        self.upkeep_saves(job_id)
        self.assertEqual(self.edits()[-1]['text'], f'기억했어요\n1. {VALUE}\n2. {SECOND_VALUE}')

    def test_a_web_work_tells_nothing_on_telegram(self):
        job_id = self.saved_turn(channel=False)
        self.service.queue_memory_saved(self.store.job(job_id))
        self.assertEqual(self.notification(job_id, MEMORY_SAVED_KIND), [])
        self.assertEqual([m['content'] for m in self.store.memories()], [VALUE])

    def test_a_credential_shaped_value_leaves_no_memory_and_no_notice(self):
        secret = 'sk-proj-abcdefghijklmnopqrstuvwxyz123456'
        job_id = self.saved_turn(plan=[('save_memory', {'memory_key': 'profile.api', 'content': secret})])
        self.assertEqual(self.store.memories(), [])
        self.assertEqual(self.store.memory_candidates(include_decided=True), [])
        self.service.deliver_one()
        self.assertFalse(self.service.deliver_notification(), 'nothing was remembered, so nothing is told')
        self.assertEqual(self.notification(job_id, MEMORY_SAVED_KIND), [])
        tool_messages = [body['content'] for body in self.bodies[-1]['messages'] if body.get('role') == 'tool']
        self.assertTrue(any(SECRET_SHAPED_VALUE in content for content in tool_messages), tool_messages)
        for content in tool_messages:
            self.assertNotIn(secret, content, 'the worker\'s refusal never echoes the value')
        [event] = [row for row in self.store.task_events(job_id) if row['tool'] == 'save_memory' and row['status'] != 'running']
        self.assertNotIn(secret, json.dumps(event, ensure_ascii=False))

    # --- undo -----------------------------------------------------------------------

    def test_undo_retracts_exactly_that_item(self):
        job, _notice, row = self.told()
        self.store.save_memory('profile.food_preference', '매운 음식')   # another fact, elsewhere: untouched
        self.tap(f"p7u:{row['id']}:1", row['message_id'])
        self.assertEqual([(m['memory_key'], m['content']) for m in self.store.memories()],
                         [('profile.food_preference', '매운 음식')])
        self.assertEqual(self.memory_states(), [(VALUE, 'retracted'), ('매운 음식', 'current')])
        [edit] = self.edits()
        self.assertEqual(edit['message_id'], row['message_id'])
        self.assertEqual(edit['text'], f'되돌렸어요: {VALUE}')
        self.assertEqual(edit['reply_markup'], {'inline_keyboard': []})
        self.assertEqual(self.notification(job['id'], MEMORY_SAVED_KIND)[0]['state'], 'memory_undone')
        # Consumed once: the same message again changes nothing.
        self.tap(f"p7u:{row['id']}:1", row['message_id'])
        self.assertEqual(len(self.edits()), 1)
        self.assertEqual(self.memory_states(), [(VALUE, 'retracted'), ('매운 음식', 'current')])
        self.assertEqual(self.answers()[-1], '처리할 수 있는 요청이 아닙니다.')

    def test_undo_restores_the_superseded_value(self):
        self.store.save_memory(KEY, '서울 역삼 오피스')
        job, notice, row = self.told()
        self.assertEqual(notice['text'], f'기억했어요: {VALUE} (전에는 서울 역삼 오피스)', 'a replacement is never silent')
        self.assertEqual(self.memory_states(), [('서울 역삼 오피스', 'superseded'), (VALUE, 'current')])
        self.tap(f"p7u:{row['id']}:1", row['message_id'])
        self.assertEqual([(m['memory_key'], m['content']) for m in self.store.memories()], [(KEY, '서울 역삼 오피스')])
        self.assertEqual(self.memory_states(), [('서울 역삼 오피스', 'current'), (VALUE, 'retracted')])
        self.assertEqual(self.edits()[-1]['text'], f'되돌렸어요: {VALUE} (다시 서울 역삼 오피스)')
        self.assertEqual(self.store.current_memory(KEY, MEMORY_OWNER)['content'], '서울 역삼 오피스')

    def test_undo_is_refused_from_another_chat_message_or_generation(self):
        _job, _notice, row = self.told()
        self.tap(f"p7u:{row['id']}:1", row['message_id'], sender=OTHER)
        self.tap(f"p7u:{row['id']}:1", row['message_id'] + 1)
        self.tap(f"p7u:{row['id']}:1", row['message_id'], chat=OTHER)
        self.tap(f"p7u:{row['id']}:2", row['message_id'])
        self.tap(f"p7u:{row['id']}", row['message_id'])
        self.service.ingest_callback({'id': 'cb', 'from': {'id': CHAT}, 'data': f"p7u:{row['id']}:1",
                                      'message': {'message_id': row['message_id'], 'chat': {'id': CHAT, 'type': 'private'}}},
                                     'g0')
        self.assertEqual([m['content'] for m in self.store.memories()], [VALUE])
        self.assertEqual(self.edits(), [])

    def test_undo_is_refused_after_seven_days(self):
        job, _notice, row = self.told()
        binding = self.binding(row)
        binding['sent'] -= MEMORY_SAVED_TTL_SECONDS + 1
        self.store.update_notification(row['id'], 'sent', fingerprint=json.dumps(binding))
        self.tap(f"p7u:{row['id']}:1", row['message_id'])
        self.assertEqual([m['content'] for m in self.store.memories()], [VALUE], 'the save stands')
        self.assertEqual(self.notification(job['id'], MEMORY_SAVED_KIND)[0]['state'], 'expired')
        self.assertEqual(self.edits()[-1]['reply_markup'], {'inline_keyboard': []})
        self.assertIn(MEMORY_SAVED_EXPIRED_TEXT, self.edits()[-1]['text'])
        self.assertEqual(MEMORY_SAVED_TTL_SECONDS, 7 * 86400)

    def test_the_sweep_closes_an_old_notice_without_a_tap(self):
        job, _notice, row = self.told()
        sent = self.binding(row)['sent']
        self.service.expire_memory_prompts(now=sent + 6 * 86400)
        self.assertEqual(self.notification(job['id'], MEMORY_SAVED_KIND)[0]['state'], 'sent', 'still within the week')
        self.service._memory_prompt_sweep = 0
        self.service.expire_memory_prompts(now=sent + MEMORY_SAVED_TTL_SECONDS + 1)
        self.assertEqual(self.notification(job['id'], MEMORY_SAVED_KIND)[0]['state'], 'expired')
        self.assertEqual(self.edits()[-1]['reply_markup'], {'inline_keyboard': []})

    def test_a_memory_changed_after_the_notice_refuses_the_undo(self):
        job, _notice, row = self.told()
        self.store.save_memory(KEY, '여의도 본사')      # the owner changed it elsewhere
        self.tap(f"p7u:{row['id']}:1", row['message_id'])
        self.assertEqual([m['content'] for m in self.store.memories()], ['여의도 본사'], 'nothing retracted')
        self.assertIn('그 사이 바뀌어 그대로 두었어요', self.edits()[-1]['text'])
        self.assertIn(MEMORY_SAVED_OUTDATED_TEXT, self.edits()[-1]['text'])
        self.assertEqual(self.answers()[-1], MEMORY_SAVED_OUTDATED_TEXT)
        self.assertEqual(self.notification(job['id'], MEMORY_SAVED_KIND)[0]['state'], 'memory_undone')

    def test_a_deleted_memory_refuses_the_undo(self):
        _job, _notice, row = self.told()
        [memory] = self.store.memories()
        self.assertTrue(self.store.delete_memory(MEMORY_OWNER, memory['id'])['deleted'])
        self.tap(f"p7u:{row['id']}:1", row['message_id'])
        self.assertEqual(self.store.memories(), [])
        self.assertIn('그 사이 바뀌어 그대로 두었어요', self.edits()[-1]['text'])

    def test_retract_is_bound_to_the_content_digest(self):
        self.saved_turn()
        [memory] = self.store.memories()
        with self.assertRaises(ValueError):
            self.store.retract_memory(MEMORY_OWNER, memory['id'], 'f' * 64)
        with self.assertRaises(ValueError):
            self.store.retract_memory('someone-else', memory['id'], memory['content_digest'])
        self.assertEqual([m['content'] for m in self.store.memories()], [VALUE])
        receipt = self.store.retract_memory(MEMORY_OWNER, memory['id'], memory['content_digest'])
        self.assertEqual((receipt['retracted'], receipt['id'], receipt['restored']), (True, memory['id'], None))
        with self.assertRaises(ValueError):
            self.store.retract_memory(MEMORY_OWNER, memory['id'], memory['content_digest'])

    # --- one notice per Work ----------------------------------------------------------

    def test_several_facts_in_one_work_make_one_notice(self):
        job, notice, row = self.told(plan=[('save_memory', {'memory_key': KEY, 'content': VALUE}),
                                           ('save_memory', {'memory_key': SECOND_KEY, 'content': SECOND_VALUE})])
        self.assertEqual(sorted(m['content'] for m in self.store.memories()), sorted([VALUE, SECOND_VALUE]))
        self.assertEqual(notice['text'], f'기억했어요\n1. {VALUE}\n2. {SECOND_VALUE}')
        self.assertEqual([[button['text'] for button in line] for line in notice['reply_markup']['inline_keyboard']],
                         [['1 되돌리기'], ['2 되돌리기'], ['모두 되돌리기']])
        self.assertEqual(len([body for body in self.sends() if body['text'].startswith('기억했어요')]), 1, 'one notice')
        self.tap(f"p7u:{row['id']}:2", row['message_id'])
        self.assertEqual([m['content'] for m in self.store.memories()], [VALUE])
        self.assertEqual(self.edits()[-1]['text'], f'기억했어요\n1. {VALUE}\n2. {SECOND_VALUE} → 되돌렸어요')
        self.assertEqual([[button['text'] for button in line] for line in self.edits()[-1]['reply_markup']['inline_keyboard']],
                         [['1 되돌리기']])
        self.assertEqual(self.notification(job['id'], MEMORY_SAVED_KIND)[0]['state'], 'sent', 'one is still open')
        self.tap(f"p7u:{row['id']}:a", row['message_id'])
        self.assertEqual(self.store.memories(), [])
        self.assertEqual(self.edits()[-1]['text'], f'되돌렸어요\n1. {VALUE} → 되돌렸어요\n2. {SECOND_VALUE} → 되돌렸어요')
        self.assertEqual(self.edits()[-1]['reply_markup'], {'inline_keyboard': []})
        self.assertEqual(self.notification(job['id'], MEMORY_SAVED_KIND)[0]['state'], 'memory_undone')

    def test_the_notice_is_bounded_and_never_shows_a_key(self):
        job_id = self.store.enqueue('x', 'bounded', channel=f'telegram:{GENERATION}', chat_id=CHAT)
        for index in range(7):
            self.store.save_memory(f'profile.item{index}', '가' * 300, MEMORY_OWNER, work_id=job_id)
        self.store.save_memory('profile.note.key', 'sk-proj-abcdefghijklmnopqrstuvwxyz123456', MEMORY_OWNER, work_id=job_id)
        self.service.queue_memory_saved(self.store.job(job_id))
        self.assertTrue(self.service.deliver_notification())
        text = self.sends()[-1]['text']
        self.assertEqual(len(text.splitlines()), 1 + 5 + 1)
        self.assertTrue(all(len(line) <= 200 for line in text.splitlines()), text)
        self.assertIn('그 밖의 3가지는 내 기록에서 볼 수 있어요.', text)
        for key in ('profile.', 'item0', 'note.key'):
            self.assertNotIn(key, text)
        self.assertNotIn('sk-proj', text)
        self.assertTrue(all(len(button['callback_data'].encode()) <= 64
                            for line in self.sends()[-1]['reply_markup']['inline_keyboard'] for button in line))

    def test_an_upkeep_fact_saved_later_joins_the_notice(self):
        job, _notice, row = self.told()
        sends = len(self.sends())
        self.upkeep_saves(job['id'])
        self.assertEqual(len(self.sends()), sends, 'no second notice')
        self.assertEqual(self.notification(job['id'], MEMORY_SAVED_UPKEEP_KIND), [])
        [edit] = self.edits()
        self.assertEqual(edit['message_id'], row['message_id'])
        self.assertEqual(edit['text'], f'기억했어요\n1. {VALUE}\n2. {SECOND_VALUE}')
        self.assertEqual([[button['text'] for button in line] for line in edit['reply_markup']['inline_keyboard']],
                         [['1 되돌리기'], ['2 되돌리기'], ['모두 되돌리기']])
        self.assertEqual(len(self.binding(row)['items']), 2, 'bound once the edit was confirmed')
        self.tap(f"p7u:{row['id']}:2", row['message_id'])
        self.assertEqual([m['content'] for m in self.store.memories()], [VALUE])

    def test_an_upkeep_fact_is_bound_only_when_the_edit_was_confirmed(self):
        from personal_agent.providers import ProviderError
        job, _notice, row = self.told()
        real = self.service.telegram.edit_message_text

        def refuse(*_args, **_kwargs):
            raise ProviderError('Telegram timed out')
        self.service.telegram.edit_message_text = refuse
        self.upkeep_saves(job['id'])
        self.service.telegram.edit_message_text = real
        self.assertEqual(len(self.binding(row)['items']), 1)
        self.tap(f"p7u:{row['id']}:a", row['message_id'])
        self.assertEqual([m['content'] for m in self.store.memories()], [SECOND_VALUE], 'the unshown fact is never undone')
        # Review P3: the refused edit fell back to a notice of its own, so the fact is still told.
        self.assertTrue(self.service.deliver_notification())
        self.assertEqual(self.sends()[-1]['text'], f'기억했어요: {SECOND_VALUE}')
        [upkeep] = self.notification(job['id'], MEMORY_SAVED_UPKEEP_KIND)
        self.tap(f"p7u:{upkeep['id']}:1", upkeep['message_id'])
        self.assertEqual(self.store.memories(), [])

    def test_a_joined_fact_restarts_the_undo_window(self):
        job, _notice, row = self.told()
        binding = self.binding(row)
        binding['sent'] -= 6 * 86400
        self.store.update_notification(row['id'], 'sent', fingerprint=json.dumps(binding))
        self.upkeep_saves(job['id'])
        self.assertGreater(self.binding(row)['sent'], binding['sent'] + 5 * 86400, 'review P3: the week restarts at the join')
        self.tap(f"p7u:{row['id']}:2", row['message_id'])
        self.assertEqual([m['content'] for m in self.store.memories()], [VALUE])

    def test_a_deleted_previous_value_is_not_shown_as_empty(self):
        kept = self.store.save_memory(KEY, '서울 역삼 오피스')
        job_id = self.saved_turn()
        with self.store.db() as db:
            db.execute('DELETE FROM memories WHERE id=?', (kept['id'],))
        self.service.deliver_one()
        self.assertTrue(self.service.deliver_notification())
        self.assertEqual(self.sends()[-1]['text'], f'기억했어요: {VALUE}', 'review P3: no "(전에는 )"')
        [row] = self.notification(job_id, MEMORY_SAVED_KIND)
        self.tap(f"p7u:{row['id']}:1", row['message_id'])
        self.assertEqual(self.edits()[-1]['text'], f'되돌렸어요: {VALUE}')

    def test_an_upkeep_fact_after_an_undone_notice_gets_its_own_notice(self):
        job, _notice, row = self.told()
        self.tap(f"p7u:{row['id']}:1", row['message_id'])
        self.upkeep_saves(job['id'])
        self.assertTrue(self.service.deliver_notification())
        self.assertEqual(self.sends()[-1]['text'], f'기억했어요: {SECOND_VALUE}')
        [upkeep] = self.notification(job['id'], MEMORY_SAVED_UPKEEP_KIND)
        self.assertEqual(upkeep['state'], 'sent')
        self.tap(f"p7u:{upkeep['id']}:1", upkeep['message_id'])
        self.assertEqual(self.store.memories(), [])

    def test_an_upkeep_fact_before_the_notice_is_sent_is_bound_with_it(self):
        job_id = self.saved_turn()
        self.service.deliver_one()
        self.upkeep_saves(job_id)
        self.assertTrue(self.service.deliver_notification())
        self.assertEqual(self.sends()[-1]['text'], f'기억했어요\n1. {VALUE}\n2. {SECOND_VALUE}')
        self.assertFalse(self.service.deliver_notification(), 'one notice')

    # --- the web and the records -----------------------------------------------------

    def test_the_web_shows_the_fact_as_saved_not_for_review(self):
        job_id = self.saved_turn()
        self.assertEqual(self.service.memory_candidate_request({'operation': 'list'})['candidates'], [])
        saved = self.store.personal_records(record_filter='memory')['items']
        self.assertEqual([(row['memory_key'], row['content']) for row in saved], [(KEY, VALUE)])
        [memory] = self.store.memories()
        self.assertEqual(self.store.memory_sources([memory['id']])[memory['id']]['work_id'], job_id, 'its source as today')
        [served] = [item for item in self.service.owner_jobs(self.store.jobs()) if item['id'] == job_id]
        self.assertNotIn(MEMORY_PENDING_WEB_NOTE, served['response'], 'nothing to choose in 내 기록')
        [link] = self.service._retained_links([(job_id, self.store.task_events(job_id))])[job_id]
        self.assertEqual((link['kind'], link['id'], link['available']), ('memory', memory['id'], True))

    def test_the_records_name_the_auto_saved_write_and_the_undo(self):
        job, _notice, row = self.told()
        [event] = [row for row in self.store.task_events(job['id'])
                   if row['tool'] == 'save_memory' and row['status'] == 'succeeded']
        evidence = event['trace']['evidence']
        self.assertEqual((evidence['saved'], evidence['state'], evidence['auto_saved'], evidence['memory_key']),
                         (True, 'current', True, KEY))
        self.assertNotIn(VALUE, json.dumps(evidence, ensure_ascii=False), 'references, never the value')
        audit = self.service.work_information_use(job['id'])
        [memory] = [row for row in audit['used'] if row['category'] == 'memory']
        self.assertEqual(memory['items'], [f'{KEY} (바로 저장)'])
        self.tap(f"p7u:{row['id']}:1", row['message_id'])
        [undo] = [row for row in self.store.task_events(job['id']) if row['tool'] == MEMORY_UNDO_TOOL]
        self.assertEqual(undo['status'], 'recorded', 'not a Work step')
        self.assertEqual(undo['trace']['evidence']['memory_key'], KEY)
        audit = self.service.work_information_use(job['id'])
        [memory] = [row for row in audit['used'] if row['category'] == 'memory']
        self.assertEqual(memory['items'], [f'{KEY} (바로 저장)', f'{KEY} (되돌림)'])
        self.assertEqual(self.store.job(job['id'])['status'], 'succeeded', 'the settled Work is unchanged')

    def test_evidence_summary_carries_the_auto_saved_state(self):
        summary = evidence_summary('save_memory', {'id': 'm1', 'memory_key': KEY, 'content': VALUE, 'state': 'current',
                                                   'saved': True, 'auto_saved': True})
        self.assertEqual((summary['saved'], summary['auto_saved'], summary['state']), (True, True, 'current'))
        self.assertNotIn('content', summary)
        held = evidence_summary('save_memory', {'id': 'c1', 'state': 'pending', 'refused_because': THIRD_PARTY_MEMORY_WRITE})
        self.assertEqual((held['saved'], held['auto_saved'], held['refused_because']), (False, False, THIRD_PARTY_MEMORY_WRITE))


    # --- review P2: the undo and its record are one transaction; the redaction set keeps every state ---

    def test_the_undo_and_its_record_are_one_transaction(self):
        job, _notice, row = self.told()
        [memory] = self.store.memories()
        [item] = self.binding(row)['items']
        broken = {'job_id': job['id'], 'tool': MEMORY_UNDO_TOOL, 'status': 'recorded',
                  'detail': {'host_action': MEMORY_UNDO_TOOL, 'evidence': {'id': item['id'], 'unserializable': object()}}}
        with self.assertRaises(TypeError):
            self.store.retract_memory(MEMORY_OWNER, item['id'], item['digest'], record=broken)
        self.assertEqual([(m['id'], m['state']) for m in self.store.memories()], [(memory['id'], 'current')],
                         'a record that cannot be written leaves the Memory current')
        self.assertEqual([row for row in self.store.task_events(job['id']) if row['tool'] == MEMORY_UNDO_TOOL], [])
        self.tap(f"p7u:{row['id']}:1", row['message_id'])
        self.assertEqual(self.store.memories(), [])
        [undo] = [row for row in self.store.task_events(job['id']) if row['tool'] == MEMORY_UNDO_TOOL]
        self.assertEqual((undo['status'], undo['trace']['evidence']['id'], undo['trace']['evidence']['restored_id']),
                         ('recorded', memory['id'], None))

    def test_the_undo_record_names_the_restored_row(self):
        kept = self.store.save_memory(KEY, '서울 역삼 오피스')
        job, _notice, row = self.told()
        self.tap(f"p7u:{row['id']}:1", row['message_id'])
        [undo] = [row for row in self.store.task_events(job['id']) if row['tool'] == MEMORY_UNDO_TOOL]
        self.assertEqual(undo['trace']['evidence']['restored_id'], kept['id'])

    def test_the_redaction_set_keeps_superseded_and_retracted_values_of_the_work(self):
        job, _notice, row = self.told(plan=[('save_memory', {'memory_key': 'passport', 'content': 'M1234567'}),
                                            ('save_memory', {'memory_key': 'passport', 'content': 'M7654321'})])
        self.assertEqual(self.memory_states(), [('M1234567', 'superseded'), ('M7654321', 'current')])
        written = work_written_values(self.store, job['id'])
        self.assertIn('M1234567', written, 'the superseded value still stands in the Work\'s tool conversation')
        self.assertIn('M7654321', written)
        self.tap(f"p7u:{row['id']}:1", row['message_id'])
        self.assertEqual(self.memory_states(), [('M1234567', 'current'), ('M7654321', 'retracted')])
        written = work_written_values(self.store, job['id'])
        self.assertIn('M7654321', written, 'a retracted value stays in the redaction set')
        self.assertIn('M1234567', written)


class SecretsNeverEnterMemory(unittest.TestCase):
    """#918 review P1: a stored secret or a credential-shaped value is refused before any Memory write."""

    CREDENTIAL = 'sk-proj-abcdefghijklmnopqrstuvwxyz123456'
    STORED = 'LEAKYSECRET0918VALUE'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name) / 'data')
        self.store.secret('telegram_token', self.STORED)
        self.job = self.store.enqueue('내 토큰 좀 기억해 둬', 'secret-save')

    def caps(self, **kwargs):
        return Capabilities(self.store, None, {}, '', self.job, lambda *a, **k: None, **kwargs)

    def assert_refused(self, result, value):
        self.assertEqual((result['saved'], result['state'], result['refused_because']), (False, 'refused', SECRET_SHAPED_VALUE))
        self.assertNotIn(value, json.dumps(result, ensure_ascii=False), 'the refusal never echoes the value')
        self.assertNotIn('content', result)
        self.assertNotIn(value, json.dumps(worker_result('save_memory', result), ensure_ascii=False))
        self.assertNotIn(value, MEMORY_REFUSALS[SECRET_SHAPED_VALUE])
        self.assertEqual(self.store.memories(), [])
        self.assertEqual(self.store.memory_candidates(include_decided=True), [])

    def test_a_credential_shaped_value_is_refused_by_the_owner_worker(self):
        self.assert_refused(self.caps().execute('save_memory', {'memory_key': 'profile.api', 'content': self.CREDENTIAL}),
                            self.CREDENTIAL)

    def test_a_stored_secret_value_is_refused_wherever_it_stands(self):
        for key, content in (('profile.note', 'my token is ' + self.STORED), ('profile.' + self.STORED, '값')):
            with self.subTest(key=key):
                self.assert_refused(self.caps().execute('save_memory', {'memory_key': key, 'content': content}), self.STORED)

    def test_a_bare_value_under_a_credential_named_key_is_refused(self):
        """Re-review P3: the joined ``key: content`` passes the gate too."""
        self.assert_refused(self.caps().execute('save_memory', {'memory_key': 'profile.account.password', 'content': 'hunter2'}),
                            'hunter2')
        self.assert_refused(self.caps().execute('save_memory', {'memory_key': 'profile.bank.api_key', 'content': 'abc123'}),
                            'abc123')

    def test_a_third_party_write_with_a_secret_makes_no_candidate(self):
        caps = self.caps(delegated=True, allowed_tools=['save_memory'])
        self.assert_refused(caps.execute('save_memory', {'memory_key': 'profile.api', 'content': self.CREDENTIAL}), self.CREDENTIAL)

    def test_an_ordinary_value_still_saves(self):
        result = self.caps().execute('save_memory', {'memory_key': KEY, 'content': VALUE})
        self.assertEqual((result['state'], result['auto_saved']), ('current', True))

    def test_list_memory_passes_the_secret_filter(self):
        # A row that entered the store another way (older data, a direct owner write) still never reaches the model raw.
        self.store.save_memory('profile.note.' + self.STORED, 'token ' + self.STORED + ' and ' + self.CREDENTIAL)
        from personal_agent.current_context import redact_known_secrets
        caps = self.caps(secret_redactor=lambda text: redact_known_secrets(self.store, text))
        result = caps.execute('list_memory', {})
        serialized = json.dumps(result, ensure_ascii=False) + json.dumps(caps.evidence, ensure_ascii=False)
        self.assertNotIn(self.STORED, serialized)
        self.assertNotIn(self.CREDENTIAL, serialized)
        [row] = result['memories']
        self.assertEqual((row['memory_key'], row['content']), ('profile.note.[redacted]', 'token [redacted] and [redacted]'))
        # The credential-shape filter applies even without a stored-secret redactor.
        [row] = self.caps().execute('list_memory', {})['memories']
        self.assertNotIn(self.CREDENTIAL, row['content'])


class ThirdPartyWrites(unittest.TestCase):
    """C5 unchanged: a package tool or a delegated specialist still proposes a MemoryCandidate."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name) / 'data')
        self.job = self.store.enqueue('난 판교에서 일해', 'third-party')

    def caps(self, **kwargs):
        return Capabilities(self.store, None, {}, '', self.job, lambda *a, **k: None, **kwargs)

    def assert_pending(self, result):
        self.assertEqual((result['state'], result['saved'], result['requires_owner_approval'], result['refused_because']),
                         ('pending', False, True, THIRD_PARTY_MEMORY_WRITE))
        self.assertEqual(self.store.memories(), [], 'nothing entered canonical Memory')
        [candidate] = self.store.memory_candidates(MEMORY_OWNER, self.job)
        self.assertEqual((candidate['memory_key'], candidate['content'], candidate['state']), (KEY, VALUE, 'pending'))
        shown = json.dumps(worker_result('save_memory', result), ensure_ascii=False)
        self.assertEqual(json.loads(shown)['remembered'], False, 'the third party is told it is not remembered yet')

    def test_a_delegated_specialist_write_stays_a_pending_candidate(self):
        result = self.caps(delegated=True, allowed_tools=['save_memory']).execute('save_memory', {'memory_key': KEY, 'content': VALUE})
        self.assert_pending(result)

    def test_a_package_tool_write_stays_a_pending_candidate(self):
        package = {'version': 1, 'id': 'notebook', 'enabled': True,
                   'tools': [{'id': 'notebook_remember', 'host_action': 'save_memory', 'mode': 'bounded_write'}], 'roles': []}
        caps = self.caps(packages=runtime_packages([package]), allowed_tools=['notebook_remember', 'save_memory'])
        result = caps.execute('notebook_remember', {'memory_key': KEY, 'content': VALUE})
        self.assert_pending(result)
        self.assertTrue(caps.third_party_memory_write('notebook_remember'))
        self.assertFalse(caps.third_party_memory_write('save_memory'))

    def test_the_owner_worker_itself_saves_directly(self):
        result = self.caps().execute('save_memory', {'memory_key': KEY, 'content': VALUE})
        self.assertEqual((result['state'], result['saved'], result['auto_saved']), ('current', True, True))
        self.assertEqual([m['content'] for m in self.store.memories()], [VALUE])
        self.assertEqual(self.store.memory_candidates(include_decided=True), [])
        shown = worker_result('save_memory', result)
        self.assertEqual((shown['remembered'], shown['content'], shown['replaced_previous']), (True, VALUE, False))
        self.assertNotIn('id', shown)

    def test_the_request_sentence_is_still_never_a_value(self):
        """#846 stays: the owner's own request sentence is the task, not a fact."""
        result = self.caps().execute('save_memory', {'memory_key': KEY, 'content': '난 판교에서 일해'})
        self.assertEqual((result['state'], result['refused_because']), ('refused', 'value-is-the-request'))
        self.assertEqual(self.store.memories(), [])


class Guidance(unittest.TestCase):
    def test_the_worker_is_told_it_is_remembered_at_once(self):
        [save_memory] = [tool['function'] for tool in DEFINITIONS if tool['function']['name'] == 'save_memory']
        self.assertIn('remembered at once and the owner is told afterwards with an undo', save_memory['description'])
        self.assertNotIn('asked with one tap', save_memory['description'])
        self.assertNotIn('candidate', save_memory['description'])
        self.assertIn('may be saved the same way, as what you inferred', save_memory['description'])
        self.assertIn('Never save a credential', save_memory['description'])
        self.assertNotIn('Never save an inference as a fact', save_memory['description'])
        self.assertIn("Speak as the owner's secretary", CORE_INSTRUCTIONS)


if __name__ == '__main__':
    unittest.main()

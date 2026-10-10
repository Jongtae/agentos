"""OWNER-STATE-02 (#774 step 2): ``ask_location`` and the one-time continuation.

Evidence class: model-free, fixture transports.  A scripted compatible-API
model, a recording Telegram transport and a FixtureDecisionEngine replace only
the provider and the wires; the real QuickStore, ``AgentService`` (Telegram
ingress, ``run_one``), ``run_agent``, ``Capabilities`` and the context stores
run unchanged.  No live model, Telegram or device location is contacted, and
none is claimed.
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from personal_agent import mcp_bridge
from personal_agent import preparations as prep
from personal_agent.agent_runtime import (EFFECT_FREE_READS, OWNER_STATE_ACTIONS, READONLY_EXCLUDED, WORK_STOP_KEY,
                                          Capabilities, ToolError, evidence_summary, recorded_arguments)
from personal_agent.bounded_execution import BOUNDED_PROFILE, CLI_PROFILES, STRICT_PROFILE, profile_actions
from personal_agent.cli_browser_relay import RELAYED_LOCATION_REQUEST
from personal_agent.conversation_handoff import FOLLOWUP_CANCEL
from personal_agent.context_observations import LOCATION_REQUEST_TTL_SECONDS, continuation_key, continuation_request
from personal_agent.manifests import HOST_ACTIONS, WRITE_ACTIONS
from personal_agent.quickstart_service import (CONTINUATION_EFFECT_NOTE_HEAD, LOCATION_NOT_CONTINUED_TEXT, LOCATION_RECEIVED_TEXT,
                                              RETRY_EFFECT_TOOLS)
from personal_agent.quickstart_store import QuickStore
from personal_agent.telegram_presence import draft_id_for

from test_preparations import CHAT, GENERATION, SECRET, _Case, call, finish

POINT = {'latitude': 37.5665, 'longitude': 126.978, 'horizontal_accuracy': 12.5}


class ToolDeclaration(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'data')
        self.asked = []

    def caps(self, **kwargs):
        return Capabilities(self.store, None, {}, '', 'job', lambda *a: None, **kwargs)

    def names(self, caps):
        return [d['function']['name'] for d in caps.definitions()]

    def test_offered_only_when_the_service_wired_it(self):
        self.assertNotIn('ask_location', self.names(self.caps()))
        wired = self.caps(location_request=self.asked.append)
        self.assertIn('ask_location', self.names(wired))
        schema = next(d for d in wired.definitions() if d['function']['name'] == 'ask_location')['function']
        self.assertEqual(schema['parameters']['required'], ['reason'])
        with self.assertRaises(ToolError) as refused:
            self.caps().execute('ask_location', {'reason': '출발했는지 확인하려고요.'})
        self.assertEqual(refused.exception.code, 'location_unavailable')

    def test_button_label_is_passed_only_when_valid(self):
        caps = self.caps(location_request=lambda *a: self.asked.append(a))
        caps.execute('ask_location', {'reason': 'where are you?', 'button_label': '  Share location  '})
        caps.execute('ask_location', {'reason': 'where are you?', 'button_label': 'x' * 41})
        caps.execute('ask_location', {'reason': 'where are you?'})
        self.assertEqual(self.asked, [('where are you?', 'Share location'), ('where are you?',), ('where are you?',)])

    def test_a_call_asks_once_with_the_reason_and_reports_the_channel(self):
        caps = self.caps(location_request=self.asked.append)
        self.assertEqual(caps.execute('ask_location', {'reason': '  지금 어디세요?  '}),
                         {'requested': True, 'channel': 'telegram'})
        self.assertEqual(self.asked, ['지금 어디세요?'])
        for bad in ('', '   ', 'x' * 301, None):
            with self.subTest(reason=bad), self.assertRaises(ToolError) as refused:
                caps.execute('ask_location', {'reason': bad})
            self.assertEqual(refused.exception.code, 'invalid_reason')
        self.assertEqual(len(self.asked), 1)
        delegated = self.caps(location_request=self.asked.append, delegated=True)
        with self.assertRaises(ToolError):
            delegated.execute('ask_location', {'reason': '위치'})
        self.assertEqual(evidence_summary('ask_location', {'requested': True, 'channel': 'telegram'}),
                         {'requested': True, 'channel': 'telegram'})

    def test_an_effect_relayed_on_trusted_local_and_unavailable_elsewhere(self):
        self.assertIn('ask_location', HOST_ACTIONS)
        self.assertIn('ask_location', WRITE_ACTIONS)
        self.assertIn('ask_location', READONLY_EXCLUDED)
        self.assertNotIn('ask_location', EFFECT_FREE_READS)
        self.assertIn('ask_location', OWNER_STATE_ACTIONS)
        self.assertIn('ask_location', profile_actions(BOUNDED_PROFILE))
        for profile in (STRICT_PROFILE, 'isolated-agentos-mcp'):
            with self.subTest(profile=profile):
                self.assertNotIn('ask_location', CLI_PROFILES[profile]['actions'])
                self.assertTrue(CLI_PROFILES[profile]['unavailable']['ask_location'])
        # The bridge lists it with a placeholder that never runs in the bridge.
        bridge = self.caps(location_request=RELAYED_LOCATION_REQUEST)
        self.assertIn('ask_location', self.names(bridge))
        with self.assertRaises(ToolError):
            bridge.execute('ask_location', {'reason': '위치'})


class BridgeOffer(unittest.TestCase):
    """P2-4: the trusted-local bridge lists ask_location only for a Work from the paired chat."""

    def listed(self, store, job_id):
        requests = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
                    {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}]
        out = io.StringIO()
        with mock.patch.object(sys, 'stdin', io.StringIO(''.join(json.dumps(r) + '\n' for r in requests))), \
                contextlib.redirect_stdout(out):
            mcp_bridge.serve(str(store.root), job_id, profile=BOUNDED_PROFILE, browser_relay=str(store.root / 'relay'))
        replies = {reply['id']: reply for reply in map(json.loads, out.getvalue().splitlines())}
        return [tool['name'] for tool in replies[2]['result']['tools']]

    def test_only_a_telegram_work_is_offered_the_relayed_tool(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'data')
        web = store.enqueue('지금 어디야', 'web-1')
        telegram = store.enqueue('지금 어디야', 'tg-1', f'telegram:{GENERATION}', CHAT)
        self.assertNotIn('ask_location', self.listed(store, web))
        self.assertIn('schedule_preparation', self.listed(store, web), 'the other relayed tools are unchanged')
        self.assertIn('ask_location', self.listed(store, telegram))


class RecordedReason(unittest.TestCase):
    def test_the_reason_is_scrubbed_where_arguments_are_recorded(self):
        args = {'reason': f'키 {SECRET} 로 위치 확인'}
        scrubbed = recorded_arguments('ask_location', args, redact=lambda text: text.replace(SECRET, '[비밀]'))
        self.assertEqual(scrubbed, {'reason': '키 [비밀] 로 위치 확인'})
        self.assertNotIn(SECRET, json.dumps(recorded_arguments('ask_location', args), ensure_ascii=False))
        self.assertIn('ask_location', RETRY_EFFECT_TOOLS, 'a Work that already prompted the owner is not replayed')

    def test_a_preparation_continuation_key_keeps_its_slot(self):
        slot = prep.request_key('abc123', 1700000000)
        key = continuation_key('req-1', slot)
        self.assertEqual(prep.preparation_of(key), 'abc123')
        self.assertEqual(continuation_request(key), 'req-1')
        # A continuation of a continuation keeps the slot, not a growing chain.
        again = continuation_key('req-2', key)
        self.assertEqual((prep.preparation_of(again), continuation_request(again)), ('abc123', 'req-2'))
        self.assertEqual(again, slot + '/loc:req-2')
        self.assertEqual((continuation_key('req-3', 'tg:1:2'), continuation_request('loc:req-3')), ('loc:req-3', 'req-3'))
        for other in (slot, 'tg:1:2', 'x/loc:req', '', None):
            with self.subTest(key=other):
                self.assertIsNone(continuation_request(other))


class _LocationCase(_Case):
    REQUEST = '티오프 전에 내가 출발했는지 확인해 줘'

    def setUp(self):
        super().setUp()
        self.service.context_observations.clock = lambda: self.now

    def location(self, update_id=None, message_id=None):
        """The owner's Telegram location message (a new one unless ids are given)."""
        if update_id is None:
            self.update_id += 1
            self.message_id += 1
        self.service.ingest_update({'update_id': update_id or self.update_id, 'message': {
            'message_id': message_id or self.message_id, 'from': {'id': CHAT},
            'chat': {'id': CHAT, 'type': 'private'}, 'location': dict(POINT), 'date': int(self.now)}}, GENERATION)
        return self.update_id, self.message_id

    def typed(self, text):
        """The owner's next Telegram text, ingested only (not run)."""
        self.update_id += 1
        self.message_id += 1
        self.service.ingest_update({'update_id': self.update_id, 'message': {
            'message_id': self.message_id, 'from': {'id': CHAT}, 'chat': {'id': CHAT, 'type': 'private'},
            'text': text, 'date': int(self.now)}}, GENERATION)
        return self.message_id

    def jobs(self):
        with self.store.db() as db:
            return [dict(row) for row in db.execute('SELECT * FROM jobs ORDER BY created')]

    def pending(self):
        with self.store.db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM context_location_requests WHERE state='pending'")]

    def ask(self):
        self.script = [{'content': None, 'tool_calls': [call('1', 'ask_location', reason='출발하셨는지 보려고 현재 위치가 필요해요.')]},
                       finish('f', '1', summary='현재 위치를 요청했어요.')]
        return self.receive(self.REQUEST)

    def continued(self):
        return [row for row in self.jobs() if row['relation_kind'] == 'reference']


class Continuation(_LocationCase):
    def test_the_reply_continues_the_asking_work_once_with_the_position(self):
        work = self.ask()
        [prompt] = [body for body in self.sends() if (body.get('reply_markup') or {}).get('keyboard')]
        self.assertEqual(prompt['text'], '출발하셨는지 보려고 현재 위치가 필요해요.')
        self.assertTrue(prompt['reply_markup']['keyboard'][0][0]['request_location'])
        [request] = self.pending()
        self.assertEqual(request['job_id'], work)
        self.assertEqual(len(self.jobs()), 1)

        self.now += 30
        update_id, message_id = self.location()
        continuation = [row for row in self.jobs() if row['id'] != work]
        self.assertEqual(len(continuation), 1)
        [row] = continuation
        self.assertEqual((row['message'], row['channel'], row['chat_id'], row['status']),
                         (self.REQUEST, f'telegram:{GENERATION}', CHAT, 'queued'))
        self.assertEqual((row['related_job_id'], row['relation_kind']), (work, 'reference'))
        self.assertEqual(self.store.job(work)['status'], 'succeeded', 'the asking Work is not re-run')
        self.assertEqual(self.service.telegram_turns.source(row['id']), message_id)
        self.assertEqual(self.pending(), [])

        # A replayed update, or Telegram re-delivering the same message, makes no second Work.
        self.location(update_id=update_id, message_id=message_id)
        self.location(update_id=update_id + 1, message_id=message_id)
        self.assertEqual(len(self.jobs()), 2)

        # The continuation's current context carries the reported position.
        text = self.service.current_state.render(row['id'])
        self.assertIn('current_position_report', text)
        self.assertIn('37.57,126.98', text)
        seen = []
        self.script = [lambda body: seen.append(json.dumps(body, ensure_ascii=False)) or {'content': '출발하셨네요.'}]
        self.assertTrue(self.service.run_one())
        self.assertIn('current_position_report', seen[0])
        self.assertIn(self.REQUEST, seen[0])
        self.assertEqual(self.store.job(row['id'])['status'], 'succeeded')

    def test_the_location_keyboard_is_removed_by_the_first_answer_after_the_request_ended(self):
        """#992 (live 2026-10-03): a keyboard never removed let a tap answer yesterday's prompt."""
        self.ask()
        while self.service.deliver_one():
            pass
        removals = lambda: [body for body in self.sends() if (body.get('reply_markup') or {}).get('remove_keyboard')]
        self.assertEqual(removals(), [], 'the asking Work\'s own reply keeps the button while the request waits')
        self.now += 30
        self.location()
        # #1305 (owner 2026-10-10): the button goes as soon as the location arrives, before the request runs.
        [removal] = removals()
        self.assertEqual((removal['text'], removal['reply_markup']), (LOCATION_RECEIVED_TEXT, {'remove_keyboard': True}))
        self.assertTrue(self.service.run_one())
        while self.service.deliver_one():
            pass
        self.assertEqual(len(removals()), 1, 'the continuation\'s answer carries nothing more')
        self.assertIsNone(self.service.location_keyboard_removal(CHAT), 'removed once; later answers carry nothing')

    def test_an_unrequested_location_or_a_failed_removal_sends_nothing_more(self):
        """#1305: only a location that continued a request withdraws the keyboard; #992 stays the fallback."""
        removals = lambda: [body for body in self.sends() if (body.get('reply_markup') or {}).get('remove_keyboard')]
        self.location()
        self.assertEqual(removals(), [], 'no request was pending')
        self.ask()
        original = self._telegram

        def refusing(url, body=None, headers=None, timeout=60):
            if (body or {}).get('reply_markup', {}).get('remove_keyboard'):
                return {'ok': False, 'error_code': 400, 'description': 'Bad Request'}
            return original(url, body, headers, timeout)
        self.service.telegram_transport = refusing
        self.now += 30
        self.location()
        self.assertEqual(len(self.continued()), 1, 'the request still continues')
        self.assertEqual(self.service.location_keyboard_removal(CHAT), {'remove_keyboard': True},
                         'the next reply still removes it')

    def test_a_keyboard_from_before_the_record_existed_is_removed_once(self):
        """#992 (live 2026-10-03): a keyboard sent before the deploy left no record and stayed."""
        self.assertIsNone(self.service.location_keyboard_removal(CHAT), 'never asked here: nothing to remove')
        self.ask()
        with self.store.db() as db:
            db.execute("DELETE FROM config WHERE key=?", (self.service.LOCATION_KEYBOARD_KEY,))
            db.execute("UPDATE context_location_requests SET state='expired'")
        self.assertEqual(self.service.location_keyboard_removal(CHAT), {'remove_keyboard': True})
        self.assertIsNone(self.service.location_keyboard_removal(CHAT + 1), 'only a chat that was asked')
        self.store.put(self.service.LOCATION_KEYBOARD_KEY, {})
        self.assertIsNone(self.service.location_keyboard_removal(CHAT), 'once removed, never again')

    # --- review: a typed place (the keyboard offers it) continues the request once --

    def test_a_typed_reply_is_an_ordinary_work_and_the_request_still_waits(self):
        work = self.ask()
        [prompt] = [body for body in self.sends() if (body.get('reply_markup') or {}).get('keyboard')]
        self.assertNotIn('input_field_placeholder', prompt['reply_markup'], 'no typed alternative is offered')
        [request] = self.pending()
        self.now += 30
        self.typed('강남역')
        [row] = [job for job in self.jobs() if job['id'] != work]
        self.assertTrue(row['request_key'].startswith('tg:'))
        self.assertIsNone(continuation_request(row['request_key']))
        self.assertEqual((row['relation_kind'], row['related_job_id']), (None, None))
        self.assertEqual([item['id'] for item in self.pending()], [request['id']], 'the request is not consumed')
        # A shared location still continues the asking Work.
        self.location()
        [continued] = self.continued()
        self.assertEqual((continued['related_job_id'], continued['message']), (work, self.REQUEST))

    # --- review: an answer whose continuation cannot be queued is kept -------

    def test_an_unqueued_continuation_keeps_the_request_and_tells_the_owner_once(self):
        work = self.ask()
        [request] = self.pending()
        cursor = self.store.config('telegram')['cursor']
        self.now += 30
        with mock.patch.object(self.store, 'enqueue', side_effect=ValueError('대기 중인 작업이 많습니다.')):
            self.location()
            self.location()
        self.assertEqual([row['id'] for row in self.jobs()], [work], 'nothing continued')
        self.assertEqual([row['id'] for row in self.pending()], [request['id']], 'the request waits again')
        self.assertEqual(self.store.config('telegram')['cursor'], cursor + 2, 'the cursor still advances')
        with self.store.db() as db:
            bound = {row['source_job_id'] for row in db.execute('SELECT source_job_id FROM context_observations')}
            notes = [dict(row) for row in db.execute('SELECT * FROM telegram_notifications')]
        self.assertEqual(bound, {work}, 'the positions stay with the asking Work')
        self.assertEqual([(note['job_id'], note['kind']) for note in notes], [(work, 'location_not_continued')])
        self.assertTrue(self.service.deliver_notification())
        self.assertEqual(self.texts()[-1], LOCATION_NOT_CONTINUED_TEXT)
        self.assertFalse(self.service.deliver_notification(), 'told once')

        # Resending once the queue has room continues the asking Work.
        self.location()
        [row] = self.continued()
        self.assertEqual((row['related_job_id'], row['message']), (work, self.REQUEST))
        self.assertEqual(self.pending(), [])

    def test_an_unrequested_location_makes_no_work(self):
        self.service.set_current_context({'enabled': True})
        self.location()
        self.assertEqual(self.jobs(), [])
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT source_kind FROM context_observations').fetchone()['source_kind'],
                             'place_reference')

    def test_a_web_work_is_not_offered_the_tool_and_nothing_is_sent(self):
        """A Work that did not come from the paired chat could never be answered: no handler, so no tool."""
        work = self.store.enqueue('지금 어디야', 'web-1')
        self.assertIsNone(self.service.location_requester(self.store.job(work)))
        self.assertEqual(self.sends(), [])
        self.assertEqual(self.pending(), [])

    def test_a_continuation_never_accepts_a_preparation_by_itself(self):
        self.ask()
        self.now += 30
        self.location()
        [row] = [job for job in self.jobs() if job['relation_kind'] == 'reference']
        with mock.patch.object(self.service.decision_judge, 'explicit_preparation_request') as judged:
            result = self.service.preparation_scheduler(row, row['message'])(
                {'kind': 'reminder', 'goal': '출발 확인', 'due': self.due_iso(3600)})
        judged.assert_not_called()
        self.assertTrue(result['requires_owner_acceptance'])


    # --- P2-1: a stopped or cancelled request is never revived ----------------

    def test_stop_while_running_withdraws_the_request_and_the_answer_runs_nothing(self):
        stops = []

        def stop(_body):
            [work] = [row['id'] for row in self.jobs()]
            stops.append(self.service.ingest_stop({'chat': {'id': CHAT, 'type': 'private'},
                                                   'draft_id': draft_id_for(work)}, GENERATION))
            return {'content': '요청했어요.'}

        self.script = [{'content': None, 'tool_calls': [call('1', 'ask_location', reason='현재 위치가 필요해요.')]}, stop]
        work = self.receive(self.REQUEST)
        self.assertEqual(stops, ['running'])
        self.assertEqual(self.pending(), [])
        self.now += 30
        self.location()
        self.assertEqual(self.continued(), [])
        self.assertEqual([row['id'] for row in self.jobs()], [work])

    def test_a_stopped_or_cancelled_asking_work_is_not_continued_even_with_a_pending_request(self):
        for mark in ('stop', 'cancelled'):
            with self.subTest(mark=mark):
                work = self.ask()
                self.assertEqual(len(self.pending()), 1)
                if mark == 'stop':
                    self.store.append_config_list(WORK_STOP_KEY, work, 200)
                else:
                    with self.store.db() as db:
                        db.execute("UPDATE jobs SET status='cancelled' WHERE id=?", (work,))
                self.now += 30
                self.location()
                self.assertEqual(self.continued(), [])
                with self.store.db() as db:
                    db.execute('DELETE FROM jobs')

    def test_cancelling_the_asking_work_in_conversation_withdraws_its_request(self):
        work = self.ask()
        cancelled, text = self.service.cancel_focused_work(self.store.job(work), None)
        self.assertTrue(cancelled)
        self.assertIn('위치를 보내도 이어서 처리하지 않습니다', text)
        self.assertEqual(self.pending(), [])
        self.now += 30
        self.location()
        self.assertEqual(self.continued(), [])
        # Nothing left to withdraw: the ordinary "already finished" answer.
        self.assertFalse(self.service.cancel_focused_work(self.store.job(work), None)[0])

    # --- P3-5: a continuation's replayed message is not a new owner turn ------

    def test_a_continuation_skips_the_owner_utterance_judgments_and_runs(self):
        asking = self.ask()
        self.now += 30
        self.location()
        [row] = self.continued()
        judged_cancel = {'relation': FOLLOWUP_CANCEL, 'previous': self.store.job(asking)}
        seen = []
        self.script = [lambda body: seen.append(body['messages']) or {'content': '출발하셨네요.'}]
        with mock.patch.object(self.service, 'continuity_relation', return_value=judged_cancel) as relation, \
                mock.patch.object(self.service.decision_judge, 'parked_work_withdrawn') as withdrawn, \
                mock.patch.object(self.service.calendar_conversation, 'clear') as clear:
            self.assertTrue(self.service.run_one())
        relation.assert_not_called()
        withdrawn.assert_not_called()
        clear.assert_not_called()
        self.assertTrue(seen, 'the worker ran the continued request')
        self.assertIn(self.REQUEST, json.dumps(seen[0], ensure_ascii=False))
        self.assertEqual(self.store.job(row['id'])['status'], 'succeeded')
        # Control: the same words as an ordinary owner turn would be answered as a cancel, not run.
        control = self.store.enqueue(self.REQUEST, 'tg-control', f'telegram:{GENERATION}', CHAT)
        with mock.patch.object(self.service, 'continuity_relation', return_value=judged_cancel) as relation:
            self.assertTrue(self.service.run_one())
        relation.assert_called_once()
        self.assertEqual(len(seen), 1)
        self.assertIn('이전 요청은', self.store.job(control)['response'])

    # --- P2-3: no blind replay of the asking Work's effects (C8) -------------

    def test_the_continuation_is_told_what_the_asking_work_already_changed(self):
        self.script = [{'content': None, 'tool_calls': [call('1', 'save_note', content='티오프 07:10'),
                                                        call('2', 'ask_location', reason='현재 위치가 필요해요.')]},
                       finish('f', '1', '2', summary='메모하고 위치를 요청했어요.')]
        self.receive(self.REQUEST)
        self.now += 30
        self.location()
        [row] = self.continued()
        seen = []
        self.script = [lambda body: seen.append(body['messages']) or {'content': '출발하셨네요.'}]
        self.assertTrue(self.service.run_one())
        latest = [m['content'] for m in seen[0] if m['role'] == 'user'][-1]
        self.assertTrue(latest.startswith(CONTINUATION_EFFECT_NOTE_HEAD))
        self.assertIn('- save_note: outcome observed: succeeded', latest)
        self.assertNotIn('- ask_location', latest, 'the answered request is not an effect to re-check')
        self.assertTrue(latest.endswith(self.REQUEST))
        with self.store.db() as db:
            stored = db.execute("SELECT content FROM messages WHERE role='user' AND job_id=?", (row['id'],)).fetchone()
        self.assertEqual(stored['content'], self.REQUEST, 'the note is never stored as owner text')

    def test_an_effect_free_asking_work_adds_no_note_and_memory_approval_is_not_reissued(self):
        self.ask()
        self.now += 30
        self.location()
        [row] = self.continued()
        with mock.patch.object(self.service.decision_judge, 'explicit_memory_request') as judged:
            self.assertIsNone(self.service.owner_memory_approval(row, row['message'])())
        judged.assert_not_called()
        seen = []
        self.script = [lambda body: seen.append(body['messages']) or {'content': '출발하셨네요.'}]
        self.assertTrue(self.service.run_one())
        latest = [m['content'] for m in seen[0] if m['role'] == 'user'][-1]
        self.assertNotIn('AgentOS note', latest)


class PreparationContinuation(_LocationCase):
    """P2-2: a prepare run that asks for a location stays that preparation's run."""

    GOAL = '출발 시간 맞는지 확인해 줘'
    UNRELATED = '어제 병원 검사 결과 이야기 UNRELATED-MARK'

    def test_the_continuation_is_the_same_preparation_and_its_answer_is_kept(self):
        self.script = [{'content': '그랬군요.'}]
        self.web_turn(self.UNRELATED)
        row = self.scheduled(goal=self.GOAL, channel='telegram')
        self.now += 120
        self.assertTrue(self.tick())
        [asking] = self.runs(row['id'])
        self.script = [{'content': None, 'tool_calls': [call('1', 'ask_location', reason='출발 위치가 필요해요.')]},
                       finish('f', '1', summary='현재 위치를 요청했어요.')]
        self.assertTrue(self.service.run_one())
        self.assertEqual(self.store.job(asking['id'])['status'], 'succeeded')
        self.service.deliver_one()
        for _ in range(2):
            self.tick()
        current = self.service.preparations.get(row['id'])
        self.assertEqual((current['state'], current['last_run_job_id'], current['prepared_result_ref']),
                         ('running', asking['id'], None), 'the slot waits for the answer')

        self.now += 30
        self.location()
        [continuation] = [run for run in self.runs(row['id']) if run['id'] != asking['id']]
        self.assertEqual(prep.preparation_of(continuation['request_key']), row['id'])
        self.assertEqual(self.service.preparations.get(row['id'])['last_run_job_id'], continuation['id'])

        seen = []
        self.script = [lambda body: seen.append(json.dumps(body['messages'], ensure_ascii=False))
                       or {'content': f'출발하셨네요. (키 {SECRET})'}] * 2
        self.assertTrue(self.service.run_one())
        self.assertIn(self.GOAL, seen[0])
        self.assertIn('current_position_report', seen[0])
        self.assertNotIn('UNRELATED-MARK', seen[0], 'preparation history isolation holds')
        finished = self.store.job(continuation['id'])
        self.assertEqual(finished['status'], 'succeeded')
        self.assertIn('출발하셨네요', finished['response'])
        self.assertNotIn(SECRET, finished['response'], 'the preparation scrub applies')
        self.service.deliver_one()
        self.assertTrue(self.sends()[-1]['text'].startswith(f'미리 준비한 결과입니다 ({self.GOAL})'))

        self.tick()
        settled = self.service.preparations.get(row['id'])
        self.assertEqual((settled['prepared_result_ref'], settled['last_outcome'], settled['state']),
                         (continuation['id'], 'delivered', 'delivered'))
        self.assertIn('출발하셨네요', settled['prepared_text'])
        self.assertNotIn('요청했어요', settled['prepared_text'])
        settled_events = [e for e in self.store.task_events(continuation['id']) if e['tool'] == 'preparation']
        self.assertEqual(len(settled_events), 2, 'one continue record and one settlement')
        self.tick()
        self.assertEqual(self.service.preparations.get(row['id'])['updated_at'], settled['updated_at'], 'settled once')

    def asking_run(self):
        row = self.scheduled(goal=self.GOAL, channel='telegram')
        self.now += 120
        self.tick()
        [asking] = self.runs(row['id'])
        self.script = [{'content': None, 'tool_calls': [call('1', 'ask_location', reason='출발 위치가 필요해요.')]},
                       finish('f', '1', summary='현재 위치를 요청했어요.')]
        self.service.run_one()
        self.service.deliver_one()
        self.tick()
        self.assertEqual(len(self.pending()), 1)
        return row, asking

    def test_cancelling_the_preparation_withdraws_its_runs_request(self):
        """P3-1: Settings (and the ``p7q`` stop button, the same ``cancel_preparation``) withdraw it."""
        row, asking = self.asking_run()
        self.service.preparation_request({'operation': 'cancel', 'id': row['id']})
        self.assertEqual(self.service.preparations.get(row['id'])['state'], prep.STATE_CANCELLED)
        self.assertEqual(self.pending(), [])
        self.now += 30
        self.location()
        self.assertEqual([run['id'] for run in self.runs(row['id'])], [asking['id']])

    def test_a_run_of_an_inactive_preparation_is_never_continued(self):
        """P3-1: even with its request still pending, a cancelled or removed preparation's goal does not run."""
        for how in ('cancel', 'delete'):
            with self.subTest(how=how):
                row, asking = self.asking_run()
                self.service.preparations.cancel(row['id'])
                if how == 'delete':
                    self.service.preparations.delete(row['id'])
                self.assertEqual(len(self.pending()), 1)
                self.now += 30
                self.location()
                self.assertEqual(self.continued(), [])
                with self.store.db() as db:
                    db.execute('DELETE FROM jobs')

    def test_an_unanswered_request_expires_and_the_asking_run_settles(self):
        row = self.scheduled(goal=self.GOAL, channel='telegram')
        self.now += 120
        self.tick()
        [asking] = self.runs(row['id'])
        self.script = [{'content': None, 'tool_calls': [call('1', 'ask_location', reason='출발 위치가 필요해요.')]},
                       finish('f', '1', summary='현재 위치를 요청했어요.')]
        self.service.run_one()
        self.service.deliver_one()
        self.tick()
        self.assertEqual(self.service.preparations.get(row['id'])['state'], 'running')
        self.now += LOCATION_REQUEST_TTL_SECONDS + 1
        self.tick()
        settled = self.service.preparations.get(row['id'])
        self.assertEqual((settled['prepared_result_ref'], settled['state']), (asking['id'], 'delivered'))


if __name__ == '__main__':
    unittest.main()


class PlanAsksLocation(_LocationCase):
    """#1293 (owner 2026-10-10, "위치 공유가 너무 늦네"): the plan asks before any worker starts.

    The decision model judged the reply needs the owner's position and none is
    known; the location keyboard goes out without a worker run, and that
    question is the Work's whole reply.
    """
    REQUEST = '갈 커피 전문점 찾아줘'
    QUESTION = '지금 계신 곳 근처로 찾을게요. 현재 위치를 보내 주세요.'

    def setUp(self):
        super().setUp()
        from personal_agent.decision import OUTCOME_DECIDED, FixtureDecisionEngine, StructuredDecision, fixture_confidence
        self.schemas = []

        def structured(context, question, schema):
            self.schemas.append(schema)
            offered = 'ask_location' in schema['properties']
            data = {'worker': schema['properties']['worker']['enum'][0], 'model': '', 'brief': {'notes': ''},
                    'reason': 'fits', 'account_change': False, 'owner_situation': True,
                    **({'ask_location': self.QUESTION, 'location_button': '현재 위치 보내기'} if offered else {})}
            return StructuredDecision(OUTCOME_DECIDED, data, fixture_confidence())
        base = self.judge
        self.judge = FixtureDecisionEngine(judge=base._judge, structured=structured)
        self.service.use_decision_engine(self.judge)

    def keyboards(self):
        return [body for body in self.sends() if (body.get('reply_markup') or {}).get('keyboard')]

    def test_the_question_goes_out_before_any_worker_and_the_answer_continues_the_request(self):
        work = self.receive(self.REQUEST)
        self.assertEqual(self.model_calls, [], 'no worker ran')
        [prompt] = self.keyboards()
        self.assertEqual(prompt['text'], self.QUESTION)
        self.assertEqual(prompt['reply_markup']['keyboard'][0][0], {'text': '현재 위치 보내기', 'request_location': True})
        self.assertEqual([body['text'] for body in self.sends()], [self.QUESTION], 'the question is the one reply')
        row = self.store.job(work)
        self.assertEqual((row['status'], row['response'], row['delivery']), ('succeeded', self.QUESTION, 'none'))
        self.service.deliver_one()
        self.assertEqual(len(self.sends()), 1, 'nothing more is delivered')
        self.assertEqual([request['job_id'] for request in self.pending()], [work])

        self.now += 30
        self.location()
        [continuation] = self.continued()
        self.assertTrue(self.service.run_one())
        self.assertNotIn('ask_location', self.schemas[-1]['properties'], 'a continuation never asks again')
        self.assertTrue(self.model_calls, 'the worker runs, with the position')
        self.assertIn('current_position_report', json.dumps(self.model_calls[0], ensure_ascii=False))
        self.assertEqual(self.store.job(continuation['id'])['status'], 'succeeded')

    def test_a_web_work_is_not_offered_the_question(self):
        work = self.web_turn(self.REQUEST)
        self.assertNotIn('ask_location', self.schemas[-1]['properties'])
        self.assertEqual(self.keyboards(), [])
        self.assertTrue(self.model_calls)
        self.assertEqual(self.store.job(work)['status'], 'succeeded')

    def test_a_question_that_could_not_be_sent_runs_the_planned_worker(self):
        original = self._telegram

        def refusing(url, body=None, headers=None, timeout=60):
            if (body or {}).get('reply_markup', {}).get('keyboard'):
                return {'ok': False, 'error_code': 400, 'description': 'Bad Request'}
            return original(url, body, headers, timeout)
        self.service.telegram_transport = refusing
        work = self.receive(self.REQUEST)
        self.assertTrue(self.model_calls, 'the worker ran as before')
        self.assertEqual(self.pending(), [])
        self.assertNotEqual(self.store.job(work)['model'], 'orchestration')

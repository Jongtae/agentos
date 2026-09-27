"""SEC-CONT-01 (#730): an unsafe 'retry' judgment runs the owner's current message, never the old request.

Evidence class: model-free service integration through the real Telegram
ingest path, with a scripted DecisionEngine (the followup judgment) and a
scripted model transport that records the latest user message it was sent.
No live model, no browser engine (nothing here starts a WebKit worker).
"""
import json
import time
import unittest

from personal_agent.agent_runtime import ENGINE_UNMEDIATED, WORK_SOURCES_KEY
from personal_agent.conversation_handoff import FOLLOWUP_REFERENCE, FOLLOWUP_RETRY
from personal_agent.providers import ProviderError
from personal_agent.quickstart_service import (ALREADY_RETRIED_REFUSAL, EFFECT_RETRY_REFUSAL, RETRY_EFFECT_NOTE_HEAD,
                                               RETRY_EFFECT_NOTE_TAIL, RETRY_REFUSED_RAN_CURRENT,
                                               UNKNOWN_EFFECT_RETRY_REFUSAL)

import test_presence_projection as projection

ORIGINAL = '이전 요청을 처리해줘'
CURRENT = '그 요청 다시 해줘, 이번엔 더 짧게'
AGAIN = '한 번 더 다시 해줘'


class RetryRunsCurrent(projection.ProjectionTestCase):
    relation_engine = staticmethod(projection.ConversationContinuityTests.relation_engine)

    def setUp(self):
        super().setUp()
        self.first, _ = self.turn(ORIGINAL)   # no model yet: the Work fails
        self.assertEqual(self.first['status'], 'failed')
        self.connect_model()
        self.seen = []
        self.fail = False
        original = self.service.adapter.transport

        def capture(url, body, headers=None, timeout=60):
            if url.endswith('/api/chat') and not any(
                    (tool.get('function', {}).get('name') or tool.get('name')) == 'agentos_connection_probe'
                    for tool in body.get('tools', [])):
                self.seen.append([m['content'] for m in body.get('messages', []) if m.get('role') == 'user'][-1])
                if self.fail:
                    raise ProviderError('모델 서버에 연결할 수 없습니다.')
                return {'message': {'content': '처리했습니다.'}}
            return original(url, body, headers, timeout)
        self.service.adapter.transport = capture
        self.service.use_decision_engine(self.relation_engine({CURRENT: FOLLOWUP_RETRY, AGAIN: FOLLOWUP_RETRY}))

    def event(self, work_id, tool, status, detail):
        with self.store.db() as db:
            db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                       (work_id, tool, status, json.dumps(detail, ensure_ascii=False), time.time()))

    def continuity(self, job_id):
        [event] = [e for e in self.store.task_events(job_id) if e['tool'] == 'conversation_continuity']
        return event['trace']

    def mark_unmediated(self, work_id):
        rows = self.store.config(WORK_SOURCES_KEY, {}) or {}
        rows[work_id] = sorted(set(rows.get(work_id) or []) | {ENGINE_UNMEDIATED})
        self.store.put(WORK_SOURCES_KEY, rows)

    def test_an_unsafe_retry_runs_the_current_message_and_never_replays_the_old_request(self):
        self.mark_unmediated(self.first['id'])
        second, bubbles = self.turn(CURRENT)
        self.assertEqual(second['status'], 'succeeded', 'the refusal is not the final answer')
        self.assertEqual(set(self.seen), {CURRENT}, 'the current message ran; the old request was never sent')
        self.assertNotIn(ORIGINAL, self.seen)
        self.assertEqual(second['relation_kind'], FOLLOWUP_REFERENCE)
        self.assertEqual(second['related_job_id'], self.first['id'])
        trace = self.continuity(second['id'])
        self.assertEqual(trace['relation'], RETRY_REFUSED_RAN_CURRENT)
        self.assertFalse(trace['executed'])
        self.assertIn('중개하지 않은 엔진 작업', trace['reason'], 'the refusal reason is Evidence')
        self.assertEqual([text for _kind, text in bubbles][-1], '처리했습니다.')
        self.assertFalse(any('자동으로 다시 실행하지 않았습니다' in text for _kind, text in bubbles))

    def test_a_safe_retry_still_replays_the_canonical_request_exactly_once(self):
        second, _ = self.turn(CURRENT)
        self.assertEqual(second['status'], 'succeeded')
        self.assertEqual(set(self.seen), {ORIGINAL}, 'the canonical request is replayed, not the follow-up words')
        self.assertEqual(second['relation_kind'], FOLLOWUP_RETRY)
        trace = self.continuity(second['id'])
        self.assertEqual((trace['relation'], trace['executed']), (FOLLOWUP_RETRY, True))
        self.assertEqual(trace.get('source_work_id', self.first['id']), self.first['id'])

    def test_an_unknown_effect_work_is_never_replayed_and_the_current_message_runs(self):
        self.event(self.first['id'], 'calendar_draft_create', 'failed', {'effect': 'unknown', 'state': 'outcome-unknown'})
        second, bubbles = self.turn(CURRENT)
        [sent] = set(self.seen)
        self.assertTrue(sent.startswith(RETRY_EFFECT_NOTE_HEAD) and sent.endswith(CURRENT), sent)
        self.assertIn('- calendar_draft_create: outcome unknown', sent)
        trace = self.continuity(second['id'])
        self.assertEqual((trace['relation'], trace['executed'], trace['reason']),
                         (RETRY_REFUSED_RAN_CURRENT, False, UNKNOWN_EFFECT_RETRY_REFUSAL))
        self.assertIn('외부 결과가 불확실', bubbles[-1][1], 'the owner is still asked to check the earlier effect')
        self.assertIn('처리했습니다.', bubbles[-1][1])

    def test_an_effect_refusal_tells_the_worker_which_effect_tools_ran_without_their_arguments(self):
        self.event(self.first['id'], 'save_note', 'running', {'arguments': {'content': 'PRIVATE-ARGUMENT'}})
        self.event(self.first['id'], 'save_note', 'succeeded', {'evidence': {'id': 'n1'}})
        self.event(self.first['id'], 'pkg_press', 'failed', {'host_action': 'browser_click', 'arguments': {'target': '7'},
                                                             'url': 'https://shop.example.org/item?q=PRIVATE-QUERY'})
        second, _bubbles = self.turn(CURRENT)
        self.assertEqual(self.continuity(second['id'])['reason'], EFFECT_RETRY_REFUSAL)
        [sent] = set(self.seen)
        self.assertEqual(sent, '\n'.join([RETRY_EFFECT_NOTE_HEAD, '- save_note: outcome observed: succeeded',
                                          '- browser_click (host: shop.example.org): outcome observed: failed',
                                          RETRY_EFFECT_NOTE_TAIL]) + '\n\n' + CURRENT)
        for private in ('PRIVATE-ARGUMENT', 'PRIVATE-QUERY', 'n1', '/item'):
            self.assertNotIn(private, sent)
        self.assertEqual(second['status'], 'succeeded', 'the AI decides; AgentOS only informed it')

    def test_no_note_for_a_refusal_without_an_effect(self):
        self.mark_unmediated(self.first['id'])
        self.turn(CURRENT)
        self.assertEqual(set(self.seen), {CURRENT})
        self.assertFalse(any(RETRY_EFFECT_NOTE_HEAD in text for text in self.seen))

    def test_a_second_retry_on_a_refused_retry_chain_hits_the_once_only_guard_and_still_runs_the_message(self):
        self.mark_unmediated(self.first['id'])
        self.fail = True
        second, _ = self.turn(CURRENT)
        self.assertEqual(second['status'], 'failed')
        self.assertEqual(self.continuity(second['id'])['relation'], RETRY_REFUSED_RAN_CURRENT)
        self.assertTrue(self.service._already_retried(self.first['id']), 'the refused retry spent the retry attempt')
        self.fail = False
        self.seen.clear()
        third, _ = self.turn(AGAIN)
        trace = self.continuity(third['id'])
        self.assertEqual((trace['relation'], trace['related_work_id'], trace['reason']),
                         (RETRY_REFUSED_RAN_CURRENT, second['id'], ALREADY_RETRIED_REFUSAL))
        self.assertEqual(set(self.seen), {AGAIN}, 'neither earlier request is replayed; the current message runs')
        self.assertEqual(third['status'], 'succeeded')
        # The old retry chain's original Work is never replayed through the new Work either.
        self.assertFalse(self.service.safe_retry(self.store.job(second['id']))[0])


if __name__ == '__main__':
    unittest.main()

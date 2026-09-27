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
from personal_agent.quickstart_service import RETRY_REFUSED_RAN_CURRENT, UNKNOWN_EFFECT_RETRY_REFUSAL

import test_presence_projection as projection

ORIGINAL = '이전 요청을 처리해줘'
CURRENT = '그 요청 다시 해줘, 이번엔 더 짧게'


class RetryRunsCurrent(projection.ProjectionTestCase):
    relation_engine = staticmethod(projection.ConversationContinuityTests.relation_engine)

    def setUp(self):
        super().setUp()
        self.first, _ = self.turn(ORIGINAL)   # no model yet: the Work fails
        self.assertEqual(self.first['status'], 'failed')
        self.connect_model()
        self.seen = []
        original = self.service.adapter.transport

        def capture(url, body, headers=None, timeout=60):
            if url.endswith('/api/chat') and not any(
                    (tool.get('function', {}).get('name') or tool.get('name')) == 'agentos_connection_probe'
                    for tool in body.get('tools', [])):
                self.seen.append([m['content'] for m in body.get('messages', []) if m.get('role') == 'user'][-1])
                return {'message': {'content': '처리했습니다.'}}
            return original(url, body, headers, timeout)
        self.service.adapter.transport = capture
        self.service.use_decision_engine(self.relation_engine({CURRENT: FOLLOWUP_RETRY}))

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
        with self.store.db() as db:
            db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                       (self.first['id'], 'calendar_draft_create', 'failed',
                        json.dumps({'effect': 'unknown', 'state': 'outcome-unknown'}), time.time()))
        second, bubbles = self.turn(CURRENT)
        self.assertEqual(set(self.seen), {CURRENT})
        trace = self.continuity(second['id'])
        self.assertEqual((trace['relation'], trace['executed'], trace['reason']),
                         (RETRY_REFUSED_RAN_CURRENT, False, UNKNOWN_EFFECT_RETRY_REFUSAL))
        self.assertIn('외부 결과가 불확실', bubbles[-1][1], 'the owner is still asked to check the earlier effect')
        self.assertIn('처리했습니다.', bubbles[-1][1])


if __name__ == '__main__':
    unittest.main()

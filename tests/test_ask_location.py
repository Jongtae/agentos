"""OWNER-STATE-02 (#774 step 2): ``ask_location`` and the one-time continuation.

Evidence class: model-free, fixture transports.  A scripted compatible-API
model, a recording Telegram transport and a FixtureDecisionEngine replace only
the provider and the wires; the real QuickStore, ``AgentService`` (Telegram
ingress, ``run_one``), ``run_agent``, ``Capabilities`` and the context stores
run unchanged.  No live model, Telegram or device location is contacted, and
none is claimed.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from personal_agent.agent_runtime import (EFFECT_FREE_READS, OWNER_STATE_ACTIONS, READONLY_EXCLUDED, Capabilities,
                                          ToolError, evidence_summary)
from personal_agent.bounded_execution import BOUNDED_PROFILE, CLI_PROFILES, STRICT_PROFILE, profile_actions
from personal_agent.cli_browser_relay import RELAYED_LOCATION_REQUEST
from personal_agent.manifests import HOST_ACTIONS, WRITE_ACTIONS
from personal_agent.quickstart_store import QuickStore

from test_preparations import CHAT, GENERATION, _Case, call, finish

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


class Continuation(_Case):
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


if __name__ == '__main__':
    unittest.main()

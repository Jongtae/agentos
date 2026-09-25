"""A refused durable write must not be reported as a completed one.

#476 stopped a `failed`/`partial` turn from handing the owner the model's
claim. Its independent review then found the other half: `save_memory`
signals a refusal by *returning* `{'refused_because': ...}` with no
`outcome` key, so `run_agent` counts the call as fully successful, the turn
becomes `succeeded`, and the #476 renderer -- correct given a correct
status -- passes "기억했습니다" straight through to the owner. Nothing was
written; the candidate is pending their approval (#488).

`memory_write_refusal`'s own docstring already states the intent: "a
refusal is visible, not silent". These tests hold the whole turn to it, so
they assert on the text the owner actually receives rather than on the tool
result the model sees.
"""
import tempfile
import unittest
from pathlib import Path

from personal_agent.agent_runtime import CALENDAR_DRAFT_TOOLS, withheld_effect
from personal_agent.calendar import (CALENDAR_SPEC, CALENDAR_WRITE_SPEC,
                                     CalendarConnector)
from personal_agent.connector_contract import ConnectorRegistry, ConnectorState
from personal_agent.decision import OUTCOME_DECIDED, BinaryDecision, FixtureDecisionEngine, fixture_confidence
from personal_agent.google_calendar import CALENDAR_READ_SCOPE, CALENDAR_WRITE_SCOPE
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore

CHAT = 909
GENERATION = 'g1'
#: `connector_owner_id` binds a Telegram job's grants to the paired chat, not
#: to the local owner. Granting to the wrong identity makes the calendar tools
#: error instead of draft, which passes a "did not claim success" assertion
#: for entirely the wrong reason.
CONNECTOR_OWNER = f'telegram:{CHAT}'


class RefusedWriteTestCase(unittest.TestCase):
    """One Telegram owner, one scripted model, one recorded outbound seam."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parent))
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name) / 'data')
        self.sent = []
        self.plan = []          # [(tool, arguments_mapping), ...] consumed in order
        self.child_plan = []    # the same, for a delegated specialist's own turn
        self.text = '완료했습니다.'
        self.turn = 0

        def transport(url, body=None, headers=None, timeout=60):
            if url.endswith('/sendMessage'):
                self.sent.append(body['text'])
                return {'ok': True, 'result': {'message_id': len(self.sent)}}
            if url.endswith('/getMe'):
                return {'ok': True, 'result': {'username': 'owner_test_bot'}}
            if url.endswith('/getWebhookInfo'):
                return {'ok': True, 'result': {'url': ''}}
            if url.endswith('/getUpdates'):
                return {'ok': True, 'result': []}
            return {'ok': True, 'result': {}}

        def model(url, body, headers=None, timeout=60):
            tools = [t.get('function', {}).get('name') or t.get('name')
                     for t in body.get('tools', [])]
            if 'agentos_connection_probe' in tools:
                return {'message': {'content': '', 'tool_calls': [
                    {'id': 'probe',
                     'function': {'name': 'agentos_connection_probe', 'arguments': {}}}]}}
            # A specialist runs through the same adapter, and cannot delegate
            # again -- which is how its turn is told apart from the parent's.
            plan = self.plan if 'delegate_agent' in tools else self.child_plan
            if plan:
                name, arguments = plan.pop(0)
                self.turn += 1
                return {'message': {'content': '', 'tool_calls': [
                    {'id': f'call-{self.turn}',
                     'function': {'name': name, 'arguments': arguments}}]}}
            return {'message': {'content': self.text}}

        self.service = AgentService(self.store, ModelAdapter(model), transport,
                                    calendar=self.calendar())
        self.service.save_model({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434',
                                 'model': 'test-model', 'api_key': ''})
        self.assertTrue(self.service.test_model()['ok'])
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT,
                                    'generation': GENERATION})

    def calendar(self):
        """A connected read+write Calendar whose provider records every call."""
        self.calendar_calls = []

        class Provider:
            def query(inner, start, end, timezone, max_results):
                self.calendar_calls.append(('query', start, end))
                return [{'id': 'ev1', 'summary': '팀 회의', 'version': '"etag1"',
                         'start': start, 'end': end}]

            def create(inner, payload, idempotency_key):
                self.calendar_calls.append(('create', payload))
                return {'id': 'new1', 'version': '"etag2"'}

            def update(inner, event_id, event_version, changes):
                self.calendar_calls.append(('update', event_id))
                return {'id': event_id, 'version': '"etag3"'}

            def cancel(inner, event_id, event_version):
                self.calendar_calls.append(('cancel', event_id))
                return {'id': event_id, 'status': 'cancelled'}

        registry = ConnectorRegistry(self.store, (CALENDAR_SPEC, CALENDAR_WRITE_SPEC))
        for spec, scope in ((CALENDAR_SPEC, CALENDAR_READ_SCOPE),
                            (CALENDAR_WRITE_SPEC, CALENDAR_WRITE_SCOPE)):
            registry.transition(CONNECTOR_OWNER, spec.connector_id,
                                ConnectorState.CONNECTED, granted_scopes=(scope,))
        return CalendarConnector(self.store, Provider(), registry=registry)

    def ask(self, message):
        """Run one Telegram turn and return the job plus the terminal bubble."""
        job_id = self.store.enqueue(message, f'ask-{len(self.sent)}',
                                    channel=f'telegram:{GENERATION}', chat_id=CHAT)
        self.service.run_one()
        before = len(self.sent)
        self.service.deliver_one()
        job = self.store.job(job_id)
        bubble = self.sent[before] if len(self.sent) > before else None
        return job, bubble

    def tool_events(self, job_id):
        return [(row['tool'], row['status']) for row in self.store.task_events(job_id)]


class RefusedMemoryWriteTests(RefusedWriteTestCase):
    """The owner never asked for a memory, so the write is held as a candidate."""

    UNASKED = ('point-of-contact', '땅콩 알레르기가 있습니다')

    def test_a_refused_write_does_not_make_the_turn_succeed(self):
        self.plan = [('save_memory', {'memory_key': self.UNASKED[0],
                                      'content': self.UNASKED[1]})]
        self.text = '기억했습니다. 앞으로 땅콩을 피해 드릴게요.'
        job, _bubble = self.ask('오늘 점심 뭐 먹을까?')
        # Exactly 'failed', not merely "not succeeded": the only tool call did
        # not do its job, so claiming '일부 단계만 완료했습니다' would be the
        # same unobserved claim one step down.
        self.assertEqual(job['status'], 'failed')

    def test_the_owner_is_not_told_the_thing_was_remembered(self):
        self.plan = [('save_memory', {'memory_key': self.UNASKED[0],
                                      'content': self.UNASKED[1]})]
        self.text = '기억했습니다. 앞으로 땅콩을 피해 드릴게요.'
        _job, bubble = self.ask('오늘 점심 뭐 먹을까?')
        self.assertIsNotNone(bubble)
        self.assertNotIn('기억했습니다', bubble)

    def test_the_owner_is_told_what_is_actually_pending(self):
        """Not a machine slug: `no-owner-memory-request` means nothing to a person."""
        self.plan = [('save_memory', {'memory_key': self.UNASKED[0],
                                      'content': self.UNASKED[1]})]
        self.text = '기억했습니다.'
        job, bubble = self.ask('오늘 점심 뭐 먹을까?')
        self.assertNotIn('no-owner-memory-request', bubble)
        self.assertIn('기억 후보로 보관', bubble)
        self.assertTrue(job['error'], 'the job carries no cause')
        # #598 X1: the same cause in owner words; the id stays in job['error'].
        self.assertIn(job['owner_cause'], bubble)
        self.assertIn('save_memory', job['error'])
        self.assertNotIn('save_memory', bubble)

    def test_a_turn_that_did_other_work_is_partial_not_failed(self):
        """The distinction the outcome exists to carry must survive the fix."""
        root = Path(self.temp.name) / 'docs'
        root.mkdir()
        (root / 'pay.txt').write_text('급여 명세', encoding='utf-8')
        self.service.save_roots({'paths': [str(root)]})
        self.plan = [('find_files', {'query': '급여'}),
                     ('save_memory', {'memory_key': self.UNASKED[0],
                                      'content': self.UNASKED[1]})]
        self.text = '파일을 찾았고 기억했습니다.'
        job, bubble = self.ask('급여 파일 찾아줘')
        self.assertEqual(job['status'], 'partial')
        self.assertNotIn('기억했습니다', bubble)

    def test_the_candidate_is_preserved_as_pending_for_the_owner(self):
        """A refusal must not become a discarded write.

        Named for what it checks: the end-to-end approve/reject path is
        `test_pa1_memory_candidate_owner_path`, which builds on exactly this
        state. Review pointed out the old name promised an approval this
        never performed.
        """
        self.plan = [('save_memory', {'memory_key': self.UNASKED[0],
                                      'content': self.UNASKED[1]})]
        self.text = '기억했습니다.'
        self.ask('오늘 점심 뭐 먹을까?')
        self.assertEqual(self.store.memories(), [], 'nothing may enter canonical Memory')
        pending = self.store.memory_candidates()
        self.assertEqual([row['content'] for row in pending], [self.UNASKED[1]])
        self.assertEqual(pending[0]['state'], 'pending')

    def test_the_durable_tool_event_does_not_say_succeeded(self):
        """The web record must not disagree with the bubble."""
        self.plan = [('save_memory', {'memory_key': self.UNASKED[0],
                                      'content': self.UNASKED[1]})]
        self.text = '기억했습니다.'
        job, _bubble = self.ask('오늘 점심 뭐 먹을까?')
        self.assertIn(('save_memory', 'failed'), self.tool_events(job['id']))
        self.assertNotIn(('save_memory', 'succeeded'), self.tool_events(job['id']))

    def test_a_silent_model_still_gets_the_useful_pending_message(self):
        """The fix must not replace a helpful answer with a provider error.

        `fallback_response` already renders the refusal reason when the model
        returns no text at all. Marking the call unsuccessful must not take
        that away -- the owner would learn less than before the fix.
        """
        self.plan = [('save_memory', {'memory_key': self.UNASKED[0],
                                      'content': self.UNASKED[1]})]
        self.text = ''
        job, bubble = self.ask('오늘 점심 뭐 먹을까?')
        self.assertIn('기억 후보로 보관', bubble)
        self.assertNotIn('모델이 답변을 반환하지 않았습니다', bubble)
        self.assertNotIn('모델이 답변을 반환하지 않았습니다', job['error'] or '')


class AcceptedWriteTests(RefusedWriteTestCase):
    """The opposing pin. Without it, refusing every write passes this file."""

    def test_an_owner_requested_write_still_succeeds_and_is_reported(self):
        self.plan = [('save_memory', {'memory_key': 'meal-preference',
                                      'content': '땅콩 알레르기'})]
        self.text = '기억했습니다.'
        # #597: the fixture DecisionEngine judges this turn an explicit remember request.
        self.service.use_decision_engine(FixtureDecisionEngine(judge=lambda context, proposition: BinaryDecision(
            OUTCOME_DECIDED, True, fixture_confidence()) if context.purpose == 'explicit-memory-request' else None))
        job, bubble = self.ask('땅콩 알레르기가 있다는 걸 기억해 줘')
        self.assertEqual(job['status'], 'succeeded', job.get('error'))
        self.assertEqual(bubble, '기억했습니다.')
        self.assertEqual([row['content'] for row in self.store.memories()], ['땅콩 알레르기'])
        self.assertIn(('save_memory', 'succeeded'), self.tool_events(job['id']))

    def test_a_turn_with_an_ordinary_tool_is_unaffected(self):
        root = Path(self.temp.name) / 'docs'
        root.mkdir()
        (root / 'pay.txt').write_text('급여 명세', encoding='utf-8')
        self.service.save_roots({'paths': [str(root)]})
        self.plan = [('find_files', {'query': '급여'})]
        self.text = '급여 파일 한 건을 찾았습니다.'
        job, bubble = self.ask('급여 파일 찾아줘')
        self.assertEqual(job['status'], 'succeeded', job.get('error'))
        self.assertEqual(bubble, self.text)


class DeferredCalendarWriteTests(RefusedWriteTestCase):
    """The same defect class the audit for #488 found in the calendar tools.

    `calendar_draft_create` returns `{'applied': False,
    'requires_owner_approval': True, ...}` -- the same two-key shape as a held
    memory candidate, and with no `outcome` either. Drafting is the tool's
    documented contract, so this is a deferral rather than a refusal, but every
    observable consequence was identical: the turn reported `succeeded`, so
    nothing contradicted a model that said the event was booked.
    """

    DRAFT = {'summary': '병원 예약', 'start': '2026-09-25T10:00:00+09:00',
             'end': '2026-09-25T11:00:00+09:00', 'timezone': 'Asia/Seoul'}

    def test_drafting_an_event_is_not_reported_as_scheduling_it(self):
        self.plan = [('calendar_draft_create', self.DRAFT)]
        self.text = '9월 25일 오전 10시에 병원 예약 일정을 등록했습니다.'
        job, bubble = self.ask('모레 오전 10시에 병원 예약 잡아줘')
        # 'partial', not 'failed': independent review argued a draft is real,
        # inspectable work with a step remaining, and 'partial' also keeps
        # `result_available` true so the preview stays reachable from the card.
        self.assertEqual(job['status'], 'partial',
                         'nothing reached the calendar, yet the turn succeeded')
        self.assertNotIn('등록했습니다', bubble)
        # The tool's own next step, verbatim -- not a generic stand-in the
        # renderer could substitute without anyone noticing.
        self.assertIn('소유자가 이 미리보기를 승인해야 실제 일정에 반영됩니다.', bubble)

    def test_every_draft_tool_is_covered_not_only_create(self):
        """Review found `update` and `cancel` unpinned after the rule was
        keyed on tool names: shrinking `CALENDAR_DRAFT_TOOLS` to just
        `create` survived the whole suite, and #488's symptom returned for
        the other two.
        """
        plans = {
            'calendar_draft_create': self.DRAFT,
            'calendar_draft_update': {'event_id': 'ev1', 'event_version': '"etag1"',
                                      'summary': '병원 예약'},
            'calendar_draft_cancel': {'event_id': 'ev1', 'event_version': '"etag1"'},
        }
        self.assertEqual(set(plans), set(CALENDAR_DRAFT_TOOLS))
        for tool, arguments in plans.items():
            with self.subTest(tool=tool):
                case = type(self)(self._testMethodName)
                case.setUp()
                self.addCleanup(case.doCleanups)
                case.plan = [(tool, arguments)]
                case.text = '팀 회의 시간을 변경했습니다.'
                job, bubble = case.ask('내일 팀 회의 좀 바꿔줘')
                self.assertEqual(job['status'], 'partial')
                self.assertNotIn('변경했습니다', bubble)
                self.assertEqual([call[0] for call in case.calendar_calls], [])

    def test_nothing_reached_the_calendar_provider(self):
        """The opposing half of the claim: the draft really is only a draft."""
        self.plan = [('calendar_draft_create', self.DRAFT)]
        self.text = '일정을 등록했습니다.'
        self.ask('모레 오전 10시에 병원 예약 잡아줘')
        self.assertEqual([call[0] for call in self.calendar_calls], [],
                         'a draft must not call the provider')

    def test_the_draft_survives_for_the_owner_to_approve(self):
        """Truthful reporting must not turn a deferral into a discarded action."""
        self.plan = [('calendar_draft_create', self.DRAFT)]
        self.text = '일정을 등록했습니다.'
        job, _bubble = self.ask('모레 오전 10시에 병원 예약 잡아줘')
        drafts = self.service.calendar.pending(CONNECTOR_OWNER)
        self.assertEqual(len(drafts), 1, 'the draft was lost')
        event = [row for row in self.store.task_events(job['id'])
                 if row['tool'] == 'calendar_draft_create'][-1]
        self.assertEqual(event['status'], 'failed')
        # The tool event used to carry sorted key *names* only, so that
        # `applied` was False appeared nowhere in the durable record.
        self.assertIs(event['trace']['evidence']['applied'], False)
        self.assertIs(event['trace']['evidence']['requires_owner_approval'], True)

    def test_a_silent_model_is_not_answered_by_the_host_claiming_success(self):
        """`fallback_response` asserted completion in AgentOS's own voice.

        With no branch for the calendar tools it fell through to
        '요청한 작업을 완료했습니다.' -- not a model hallucination but the host
        stating that a calendar action had completed.
        """
        self.plan = [('calendar_draft_create', self.DRAFT)]
        self.text = ''
        job, bubble = self.ask('모레 오전 10시에 병원 예약 잡아줘')
        # The stored response is the durable record, and the #476 renderer
        # keeps it out of the bubble on a failed turn -- so asserting on the
        # bubble alone would pin nothing about what the host wrote down.
        self.assertNotIn('요청한 작업을 완료했습니다', job['response'])
        self.assertIn('승인', job['response'])
        self.assertNotIn('요청한 작업을 완료했습니다', bubble)
        self.assertIn('승인', bubble)

    def test_a_partly_completed_delegation_is_partial_not_failed(self):
        """Independent review of #492 caught this regression in the fix itself.

        `delegate_agent` is the one tool that already set `outcome`, and the
        line handling it used to mark the turn *and* still count the call.
        Folding it into the new branch made those exclusive, so a specialist
        that returned half a real report had its turn reported as an outright
        failure and its report withheld from the web card.
        """
        root = Path(self.temp.name) / 'docs'
        root.mkdir()
        (root / 'pay.txt').write_text('급여 명세', encoding='utf-8')
        self.service.save_roots({'paths': [str(root)]})
        # The specialist runs one tool that works and one that does not, which
        # is what makes its own outcome 'partial'.
        self.child_plan = [('find_files', {'query': '급여'}),
                           ('read_file', {'root_id': 'no-such-root', 'path': 'x.txt'})]
        self.plan = [('delegate_agent', {'agent_id': 'researcher',
                                         'task': '급여 자료를 검토해 줘'})]
        self.text = '검토를 마쳤습니다.'
        job, _bubble = self.ask('급여 자료 검토를 전문가에게 맡겨줘')
        # Re-review proved the direct-call version of this test did not cover
        # the regression it is named for: deleting `if withheld.advanced:
        # successful+=1` left it passing.
        self.assertEqual(job['status'], 'partial')
        card = next(task for task in self.service.task_progress(job['id'])['tasks']
                    if task['id'] == job['id'])
        self.assertTrue(card['result_available'],
                        "the specialist's report must stay reachable from the card")
        self.assertIn('위임한 전문 에이전트', job['error'])

    def test_the_draft_shape_alone_does_not_trigger_the_rule(self):
        """Review asked for the branch to be keyed on the tool.

        Any future connector returning this shape with a remote `next_step`
        would otherwise push that text into the Telegram bubble, where
        `_redact_reason` is the only thing standing in front of it.
        """
        remote = {'applied': False, 'requires_owner_approval': True,
                  'next_step': 'visit http://attacker.example to approve'}
        self.assertIsNone(withheld_effect('web_search', remote))
        self.assertIsNotNone(withheld_effect('calendar_draft_create', remote))

    def test_a_read_only_calendar_query_still_succeeds(self):
        """The opposing pin: reading is not a deferred write."""
        self.plan = [('calendar_query', {'start': '2026-09-25T00:00:00+09:00',
                                         'end': '2026-09-26T00:00:00+09:00',
                                         'timezone': 'Asia/Seoul'})]
        self.text = '팀 회의 하나가 있습니다.'
        job, bubble = self.ask('모레 일정 뭐 있어?')
        self.assertEqual(job['status'], 'succeeded', job.get('error'))
        self.assertEqual(bubble, self.text)
        self.assertEqual([call[0] for call in self.calendar_calls], ['query'])


if __name__ == '__main__':
    unittest.main()

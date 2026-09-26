"""Private provenance must close a public destination, wherever it came from.

The property under test is a routing-site one: *content that originated from a
private source must not reach a public destination*, decided from where a value
came from rather than from a scan of the outgoing string.  Every refusal below
is provoked with an outgoing query that carries **no** private surface form at
all, so a lexical guard over the outgoing text would let each one through.  The
positive pins in the other direction exist so a refuse-everything
implementation cannot pass the file.

Filed as PA1-J5 / #449, required as a precondition by PA1-RESEARCH-01 / #391.
"""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from personal_agent.agent_runtime import Capabilities, provenance_window, run_agent
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore

CFG = {'provider': 'compatible', 'endpoint': 'https://openrouter.ai/api/v1', 'model': 'm'}
SECRET = 'SECRET 급여 연 1억 2천, 계좌 110-222-333333'
# Deliberately shares not one token with SECRET: the model has paraphrased,
# which is exactly the case research.validate_public_query says it cannot see.
LAUNDERED = 'average compensation for a senior engineer in Seoul'


class Egress:
    """Stands in for LocalTools and records everything that reached the wire."""

    def __init__(self):
        self.plans = []

    def execute(self, plan):
        self.plans.append(plan)
        return {'tool': plan['tool'], 'results': [], 'sources': ['공개 웹'], 'retrieved_at': 1}


class RoutingSiteProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name) / 'data')
        self.root = Path(self.temp.name) / 'docs'
        self.root.mkdir()
        (self.root / 'pay.txt').write_text(SECRET, encoding='utf-8')
        AgentService(self.store).save_roots({'paths': [str(self.root)]})
        self.egress = Egress()

    def caps(self, **kwargs):
        return Capabilities(self.store, None, CFG, '', 'job', lambda *a: None,
                            network=self.egress, **kwargs)

    def script(self, parent_plan):
        """One transport for both agents; the specialist has no delegate_agent."""
        parent, child = [], []

        def call(index, name, args):
            return {'model': 'x', 'choices': [{'message': {'tool_calls': [
                {'id': str(index), 'function': {'name': name,
                                                'arguments': json.dumps(args, ensure_ascii=False)}}]}}]}

        def transport(url, body, headers=None, timeout=60):
            tools = {tool['function']['name'] for tool in body['tools']}
            if 'delegate_agent' not in tools:
                child.append(body)
                if len(child) == 1:
                    return call(90, 'web_search', {'query': LAUNDERED})
                return {'model': 'x', 'choices': [{'message': {'content': '보고서'}}]}
            parent.append(body)
            step = parent_plan(len(parent), body)
            if step is None:
                return {'model': 'x', 'choices': [{'message': {'content': '완료'}}]}
            return call(len(parent), *step)

        return transport, parent, child

    def drive(self, caps, transport, message):
        return run_agent(ModelAdapter(transport), CFG, '',
                         [{'role': 'user', 'content': message}], '', caps, lambda *a: None)

    # -- the decisive case ------------------------------------------------

    def test_a_document_read_by_the_parent_closes_the_specialist_web_search(self):
        """delegate_agent copies the parent's evidence into the child's prompt.

        Before this contract the child was built with a fresh empty evidence
        list and document_context defaulting to False, so the parent was
        refused and the specialist holding the same document text was not.
        All three built-in roles declare web_search.
        """
        def plan(step, body):
            if step == 1:
                return ('find_files', {'query': '급여'})
            if step == 2:
                hit = json.loads(body['messages'][-1]['content'])['files'][0]
                return ('read_file', {'root_id': hit['root_id'], 'path': hit['path']})
            if step == 3:
                return ('delegate_agent', {'agent_id': 'researcher', 'task': '공개 웹에서 확인해줘'})
            return None

        transport, _parent, child = self.script(plan)
        caps = self.caps()
        caps.adapter = ModelAdapter(transport)
        self.drive(caps, transport, '이 문서 내용을 공개 웹에서도 확인해줘')
        # The specialist really did receive the private material -- otherwise
        # this test would pass for the wrong reason.
        self.assertIn('110-222-333333', json.dumps(child[0], ensure_ascii=False))
        # ...and the outgoing query it composed shares no token with it, so a
        # lexical scan of the query would have let this through.
        self.assertNotIn('110-222-333333', LAUNDERED)
        # Nothing reached a public destination, from either agent.
        self.assertEqual(self.egress.plans, [])

    def test_a_specialist_delegated_from_a_clean_context_may_still_search(self):
        """The opposing pin: provenance, not a blanket refusal of delegation."""
        def plan(step, body):
            if step == 1:
                return ('delegate_agent', {'agent_id': 'researcher', 'task': '헤드폰을 비교해줘'})
            return None

        transport, _parent, child = self.script(plan)
        caps = self.caps()
        caps.adapter = ModelAdapter(transport)
        self.drive(caps, transport, '노이즈캔슬링 헤드폰 비교해줘')
        self.assertEqual([plan['tool'] for plan in self.egress.plans], ['web_search'])

    def test_a_document_read_by_the_specialist_closes_the_parent_web_search(self):
        """The mirror of the decisive case: provenance must flow back, not only down.

        Independent review found the downward propagation above was
        one-directional.  A *clean* parent could delegate the read to its
        specialist -- all three built-in roles declare find_files and
        read_file -- take the secret out of the returned report, which is
        spliced into the parent's context verbatim, and search the public web
        with it.  ``delegate_agent`` is also absent from ``run_agent``'s
        evidence allowlist, so the unattributed fail-closed default never
        covered this path either.

        The parent here performs no private read of its own; everything it
        knows came back from the child.
        """
        parent_bodies = []

        def transport(url, body, headers=None, timeout=60):
            tools = {tool['function']['name'] for tool in body['tools']}

            def call(name, args):
                return {'model': 'x', 'choices': [{'message': {'tool_calls': [
                    {'id': '1', 'function': {'name': name,
                                             'arguments': json.dumps(args, ensure_ascii=False)}}]}}]}

            if 'delegate_agent' not in tools:            # the specialist
                turn = len([b for b in child_bodies if True])
                child_bodies.append(body)
                if turn == 0:
                    return call('find_files', {'query': '급여'})
                if turn == 1:
                    hit = json.loads(body['messages'][-1]['content'])['files'][0]
                    return call('read_file', {'root_id': hit['root_id'], 'path': hit['path']})
                return {'model': 'x', 'choices': [{'message': {
                    'content': '전문가 보고: 계좌번호 110-222-333333'}}]}
            parent_bodies.append(body)
            if len(parent_bodies) == 1:
                return call('delegate_agent', {'agent_id': 'researcher', 'task': '급여 문서를 찾아 읽어줘'})
            if len(parent_bodies) == 2:
                return call('web_search', {'query': LAUNDERED})
            return {'model': 'x', 'choices': [{'message': {'content': '완료'}}]}

        child_bodies = []
        caps = self.caps()
        caps.adapter = ModelAdapter(transport)
        self.drive(caps, transport, '급여 정보를 찾아서 시세와 비교해줘')
        # The parent really did receive the secret back -- without this the
        # test would pass because nothing private ever moved.
        self.assertIn('110-222-333333',
                      json.dumps(parent_bodies[-1]['messages'], ensure_ascii=False))
        # ...the query it then composed shares no token with the secret...
        self.assertNotIn('110-222-333333', LAUNDERED)
        # ...and it was refused anyway, because the label came back with the report.
        self.assertEqual(self.egress.plans, [])
        self.assertEqual(caps.private_egress_provenance(), ['delegated:connected-document'])

    def test_a_specialist_that_read_nothing_private_leaves_the_parent_open(self):
        """The opposing pin for the back-propagation: it is provenance, not delegation."""
        def plan(step, body):
            if step == 1:
                return ('delegate_agent', {'agent_id': 'researcher', 'task': '헤드폰을 비교해줘'})
            if step == 2:
                return ('web_search', {'query': LAUNDERED})
            return None

        transport, _parent, _child = self.script(plan)
        caps = self.caps()
        caps.adapter = ModelAdapter(transport)
        self.drive(caps, transport, '헤드폰 비교해줘')
        self.assertEqual(caps.private_egress_provenance(), [])
        self.assertIn('web_search', [plan['tool'] for plan in self.egress.plans])

    # -- one test per labelled source, so no two can mask each other --------

    def test_read_file_alone_taints(self):
        """``read_file`` pins its own label.

        Review found ``read_file`` and ``find_files`` masked each other: every
        test that exercised one called the other first, so removing either
        label alone left the suite green.  This calls only ``read_file``.
        """
        caps = self.caps()
        caps.execute('read_file', {'root_id': caps.roots()[0]['id'], 'path': 'pay.txt'})
        self.assertEqual(caps.private_egress_provenance(), ['connected-document'])
        with self.assertRaises(ValueError):
            caps.execute('web_search', {'query': LAUNDERED})
        self.assertEqual(self.egress.plans, [])

    def test_find_files_alone_taints(self):
        """``find_files`` pins its own label; the hit list is already private."""
        caps = self.caps()
        caps.execute('find_files', {'query': '급여'})
        self.assertEqual(caps.private_egress_provenance(), ['connected-document'])
        with self.assertRaises(ValueError):
            caps.execute('web_search', {'query': LAUNDERED})
        self.assertEqual(self.egress.plans, [])

    def test_list_roots_alone_taints(self):
        """Folder basenames are owner-private.

        ``list_roots`` was the tool the labels forgot: review drove a folder
        name -- the motivating example was ``이혼소송_2026`` -- straight into a
        web_search query from an otherwise clean context.  Less material than
        a document's contents, the same destination.
        """
        caps = self.caps()
        roots = caps.execute('list_roots', {})
        self.assertTrue(roots['roots'])
        self.assertEqual(caps.private_egress_provenance(), ['owner-folder-names'])
        with self.assertRaises(ValueError):
            caps.execute('web_search', {'query': LAUNDERED})
        self.assertEqual(self.egress.plans, [])

    def test_list_roots_with_no_connected_folders_does_not_taint(self):
        """An empty root list is zero owner facts and must not close anything.

        Review reproduced the first-use case this breaks: nothing connected
        yet, the owner asks what is connected and then asks for the weather,
        and the weather lookup is refused on the strength of an empty list -
        with a message about connected-document contents. Provenance names a
        source that actually put something in this context.
        """
        bare = Capabilities(QuickStore(Path(self.temp.name) / 'empty'), None, CFG, '',
                            'job', lambda *a: None, network=self.egress)
        self.assertEqual(bare.execute('list_roots', {}), {'roots': []})
        self.assertEqual(bare.private_egress_provenance(), [])
        bare.execute('weather', {'city': '서울'})
        bare.execute('web_search', {'query': LAUNDERED})
        self.assertEqual([plan['tool'] for plan in self.egress.plans],
                         ['weather', 'web_search'])

    def test_weather_follows_the_history_window_like_the_other_destinations(self):
        """Disclosed consequence of guarding weather: #448 now answers for three.

        ``document_context`` contributes ``conversation-history``, whose window
        is in ``EGRESS_TAINT_WINDOWS``, so a file-workspace job in the visible
        16-message window closes a plain weather lookup for the rest of that
        conversation - exactly as it already closed web_search and
        public_page_read. weather is deliberately not exempted, because an
        exemption would make it more permissive than the other two under
        identical taint. Pinned here so the cost is visible and so #448 can
        change all three together, rather than discovering this one by
        surprise.
        """
        caps = self.caps(document_context=True)
        self.assertEqual(caps.private_egress_provenance(), ['conversation-history'])
        with self.assertRaises(ValueError):
            caps.execute('weather', {'city': '서울'})
        with self.assertRaises(ValueError):
            caps.execute('web_search', {'query': LAUNDERED})
        self.assertEqual(self.egress.plans, [])
        # ...and the turn-only reading of #448 reopens all of them together.
        self.assertEqual(caps.private_egress_provenance(windows={'turn'}), [])

    def test_weather_is_a_public_destination_and_is_closed(self):
        """``weather`` sends an arbitrary city string to a third-party geocoder.

        It sat unguarded between the two guarded branches, so the provenance
        model knew the context was private and this branch never asked.  Twelve
        tool calls per Work at 100 characters each is real exfiltration
        capacity, and it falsified the property this whole file asserts.
        """
        caps = self.caps()
        caps.execute('read_file', {'root_id': caps.roots()[0]['id'], 'path': 'pay.txt'})
        with self.assertRaises(ValueError):
            caps.execute('weather', {'city': '110-222-333333'})
        self.assertEqual(self.egress.plans, [])

    def test_weather_is_open_from_a_clean_context(self):
        """The opposing pin: weather is refused by provenance, not disabled."""
        caps = self.caps()
        caps.execute('weather', {'city': '서울'})
        self.assertEqual([plan['tool'] for plan in self.egress.plans], ['weather'])

    def test_weather_is_closed_for_a_tainted_specialist_too(self):
        """The delegated label closes it on the child side as well."""
        child = self.caps(inherited_provenance={'delegated:connected-document'})
        with self.assertRaises(ValueError):
            child.execute('weather', {'city': '110-222-333333'})
        self.assertEqual(self.egress.plans, [])

    def test_public_page_read_is_closed_by_provenance_not_by_the_old_flag(self):
        """``public_page_read`` must consult provenance, not ``evidence``.

        The pre-existing guard was ``if self.evidence or self.document_context``.
        Both halves of the replacement matter and only one was pinned: review
        reverted this branch alone to the old flag and the whole suite stayed
        green.  The two sources below are exactly the ones the flag cannot
        see -- ``list_notes`` records provenance through ``_from_private``
        without touching ``self.evidence``, and a delegated child is
        constructed with an empty evidence list by design.
        """
        scope = {'https://example.com/pricing'}
        url = 'https://example.com/pricing'

        facade = self.caps(public_page_scope=scope)
        facade.execute('list_notes', {})
        self.assertEqual(facade.evidence, [], 'precondition: the old flag is blind here')
        with self.assertRaises(ValueError) as refused:
            facade.execute('public_page_read', {'url': url})
        # #605: the refusal names the source that actually closed it.
        self.assertIn('저장된 메모', str(refused.exception))
        self.assertNotIn('연결 문서', str(refused.exception))

        child = self.caps(public_page_scope=scope,
                          inherited_provenance={'delegated:connected-document'})
        self.assertEqual(child.evidence, [], 'precondition: the old flag is blind here too')
        with self.assertRaises(ValueError):
            child.execute('public_page_read', {'url': url})

        self.assertEqual(self.egress.plans, [])

    def test_public_page_read_is_open_from_a_clean_approved_scope(self):
        """The opposing pin: an approved page is still reachable."""
        caps = self.caps(public_page_scope={'https://example.com/pricing'})
        caps.execute('public_page_read', {'url': 'https://example.com/pricing'})
        self.assertEqual([plan['tool'] for plan in self.egress.plans], ['public_page_read'])

    def test_an_unrecognised_provenance_label_is_treated_as_refusing(self):
        """The documented fail-closed default, asserted rather than only described.

        ``provenance_window`` maps an unknown label to ``'turn'`` so a source
        added later without a window entry closes public destinations instead
        of silently opening them.  Review found this stated in prose at the
        definition and in the commit message, with no test: flipping the
        default to a window outside ``EGRESS_TAINT_WINDOWS`` left the suite
        green.
        """
        self.assertEqual(provenance_window('a-source-added-next-year'), 'turn')
        self.assertEqual(provenance_window('delegated:a-source-added-next-year'), 'turn')
        caps = self.caps(inherited_provenance={'a-source-added-next-year'})
        self.assertEqual(caps.private_egress_provenance(), ['a-source-added-next-year'])
        with self.assertRaises(ValueError):
            caps.execute('web_search', {'query': LAUNDERED})
        self.assertEqual(self.egress.plans, [])

    def test_delegation_preserves_each_inherited_label_and_its_window(self):
        """The child inherits the parent's labels, not a single flat marker.

        Without this, a delegation out of a history-only context would arrive
        at the specialist labelled turn-scoped, and #448's per-turn answer
        would then mean something different on either side of the delegation
        boundary.  Observed on the child object because under the current
        window set both labels refuse, so behaviour alone cannot tell them
        apart -- that is the point of keeping the seam explicit.
        """
        children = []

        class Recorded(Capabilities):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                children.append(self)

        def plan(step, body):
            if step == 1:
                return ('find_files', {'query': '급여'})
            if step == 2:
                return ('delegate_agent', {'agent_id': 'researcher', 'task': '공개 웹에서 확인해줘'})
            return None

        transport, _parent, _child = self.script(plan)
        caps = self.caps(document_context=True)
        caps.adapter = ModelAdapter(transport)
        with mock.patch('personal_agent.agent_runtime.Capabilities', Recorded):
            self.drive(caps, transport, '문서를 찾고 공개 웹에서도 확인해줘')
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].private_provenance,
                         {'delegated:conversation-history', 'delegated:connected-document'})
        # Each label kept the window it had in the parent, so #448's answer
        # means the same thing on both sides of the delegation.
        self.assertEqual(children[0].private_egress_provenance({'turn'}),
                         ['delegated:connected-document'])
        self.assertEqual(children[0].private_egress_provenance({'history'}),
                         ['delegated:conversation-history'])
        self.assertEqual(self.egress.plans, [])

    # -- sources the evidence list never saw ------------------------------

    def test_execute_records_provenance_without_run_agent(self):
        """AgentOSMcpTools calls execute() directly for a subscription engine.

        Its allowed_tools are {'list_notes','web_search'}, so run_agent -- the
        only place that used to append to capabilities.evidence -- is never in
        the loop, and the evidence list stays empty while the engine holds the
        owner's notes.
        """
        self.store.enqueue('/note 병원 예약은 목요일', 'note')
        with self.store.db() as db:
            db.execute('INSERT OR IGNORE INTO notes VALUES (?,?,?)',
                       ('n1', '병원 예약은 목요일 오후 3시', time.time()))
        caps = self.caps(allowed_tools={'list_notes', 'web_search'})
        caps.execute('list_notes', {})
        self.assertEqual(caps.evidence, [], 'run_agent is not in this path')
        self.assertEqual(caps.private_egress_provenance(), ['personal-space'])
        with self.assertRaises(ValueError):
            caps.execute('web_search', {'query': LAUNDERED})
        self.assertEqual(self.egress.plans, [])

    def test_material_spliced_into_the_prompt_is_declared_at_construction(self):
        """The four quickstart_service branches that edit history[-1] directly.

        Reference-folder text, a Drive file, the owner context inbox and
        /summarize notes all enter the model's context without a tool call and
        without marking the current job, so provenance has to be declared by
        the caller that spliced them in.
        """
        for label in ('connected-document', 'connected-drive-file',
                      'owner-context-inbox', 'personal-space'):
            with self.subTest(label):
                caps = self.caps(inherited_provenance={label})
                self.assertEqual(caps.private_egress_provenance(), [label])
                with self.assertRaises(ValueError):
                    caps.execute('web_search', {'query': LAUNDERED})
        self.assertEqual(self.egress.plans, [])

    def test_memory_reads_taint_through_the_evidence_log(self):
        """list_memory/save_memory append to self.evidence inside execute().

        They are the reason EvidenceLog labels at the point of storage rather
        than being replaced by the _from_private calls above.
        """
        caps = self.caps()
        caps.execute('list_memory', {})
        self.assertEqual(caps.private_egress_provenance(), ['owner-memory'])
        with self.assertRaises(ValueError):
            caps.execute('web_search', {'query': LAUNDERED})
        self.assertEqual(self.egress.plans, [])

    def test_the_refusal_names_the_source_that_closed_the_destination(self):
        caps = self.caps(document_context=True, inherited_provenance={'owner-context-inbox'})
        self.assertEqual(caps.private_egress_provenance(),
                         ['conversation-history', 'owner-context-inbox'])

    def test_an_unrecognised_evidence_entry_taints_rather_than_passes(self):
        """Fail closed: no known-public result is ever put in the evidence list."""
        caps = self.caps()
        caps.evidence.append({'tool': 'some_future_connector', 'result': {}})
        self.assertEqual(caps.private_egress_provenance(), ['unattributed-tool-evidence'])
        with self.assertRaises(ValueError):
            caps.execute('web_search', {'query': LAUNDERED})

    def test_a_public_result_does_not_taint_the_next_public_call(self):
        """Otherwise the first search would close every later one."""
        caps = self.caps()
        caps.execute('web_search', {'query': 'first'})
        self.assertEqual(caps.private_egress_provenance(), [])
        caps.execute('web_search', {'query': 'second'})
        self.assertEqual(len(self.egress.plans), 2)

    # -- compatibility with whatever #448 decides -------------------------

    def test_the_history_window_is_a_separable_decision(self):
        """#448 asks only whether history-window taint still closes egress.

        Narrowing EGRESS_TAINT_WINDOWS to {'turn'} models the per-turn outcome.
        Under it the history-only conversation stops being refused -- which is
        #448's question to answer -- while every turn-scoped source, including
        one inherited through delegation, is refused exactly as before.  So the
        collection and propagation built here hold under either answer.
        """
        turn_only = {'turn'}
        history = self.caps(document_context=True)
        self.assertEqual(history.private_egress_provenance(), ['conversation-history'])
        self.assertEqual(history.private_egress_provenance(turn_only), [])

        this_turn = self.caps()
        hit = this_turn.execute('find_files', {'query': '급여'})['files'][0]
        this_turn.execute('read_file', {'root_id': hit['root_id'], 'path': hit['path']})
        self.assertEqual(this_turn.private_egress_provenance(turn_only), ['connected-document'])

        delegated = self.caps(inherited_provenance={'delegated:connected-document'})
        self.assertEqual(delegated.private_egress_provenance(turn_only),
                         ['delegated:connected-document'])
        # ...and an inherited history label keeps the history window, so the
        # #448 decision applies identically on both sides of a delegation.
        inherited_history = self.caps(inherited_provenance={'delegated:conversation-history'})
        self.assertEqual(inherited_history.private_egress_provenance(turn_only), [])


class ServiceProvenanceTests(unittest.TestCase):
    """The same property driven through the real job worker."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(self.temp.name)
        self.bodies = []
        self.searched = []

        def transport(url, body, headers=None, timeout=60):
            self.bodies.append(body)
            probing = any((tool.get('function', {}).get('name') or tool.get('name'))
                          == 'agentos_connection_probe' for tool in body.get('tools', []))
            if probing:
                return {'message': {'content': '',
                                    'tool_calls': [{'function': {'name': 'agentos_connection_probe',
                                                                 'arguments': {}}}]}}
            tools = [tool.get('function', {}).get('name') for tool in body.get('tools', [])]
            if 'web_search' in tools and not self.searched:
                self.searched.append(True)
                return {'message': {'content': '', 'tool_calls': [
                    {'function': {'name': 'web_search', 'arguments': {'query': LAUNDERED}}}]}}
            return {'message': {'content': '정리했습니다.'}}

        self.service = AgentService(self.store, ModelAdapter(transport), transport)
        self.service.save_model({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434',
                                 'model': 'test-model', 'api_key': ''})
        self.assertTrue(self.service.test_model()['ok'])

    def test_summarize_splices_the_notes_in_and_closes_public_search(self):
        self.store.enqueue('/note 병원 예약은 목요일 오후 3시', 'note')
        self.service.run_one()
        self.store.enqueue('/summarize', 'summary')
        self.service.run_one()
        job = self.store.jobs()[0]
        # The notes really were put in the model's prompt for this turn.
        self.assertTrue(any('병원 예약' in message.get('content', '')
                            for message in self.bodies[-1]['messages']))
        # The model asked for a public search anyway, and was refused.
        self.assertTrue(self.searched)
        refusals = [event for event in self.store.task_events(job['id'])
                    if event['tool'] == 'web_search' and event['status'] == 'failed']
        self.assertTrue(refusals, '/summarize left web_search open')


if __name__ == '__main__':
    unittest.main()

"""Private provenance is recorded wherever it came from; it no longer closes a public destination.

History: PA1-J5 / #449 (required by PA1-RESEARCH-01 / #391) made private
provenance close every public destination.  EGRESS-OPEN-01 / #826 (owner
decision 2026-09-28) removed that separation: a Work may read owner-private
material and look up the public web in the same turn, and in exchange each
Work shows which owner information it used and where it went
(``information_use``).  The labels below are still collected and propagated
- through delegation both ways, from tool results the evidence list never
sees, from material spliced into the prompt - because the turn record and
the information-use audit are built from them.  Every lookup below now goes
out, so a refuse-everything implementation cannot pass the file either.
"""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from personal_agent.agent_runtime import Capabilities, run_agent, work_sources
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

    # -- delegation: the labels still flow both ways; the lookup goes out ------

    def test_a_document_read_by_the_parent_reaches_the_specialist_and_its_search_goes_out(self):
        """delegate_agent copies the parent's evidence (and its labels) into the child."""
        children = []

        class Recorded(Capabilities):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                children.append(self)

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
        with mock.patch('personal_agent.agent_runtime.Capabilities', Recorded):
            self.drive(caps, transport, '이 문서 내용을 공개 웹에서도 확인해줘')
        # The specialist really did receive the private material...
        self.assertIn('110-222-333333', json.dumps(child[0], ensure_ascii=False))
        # ...its labels say so (the record the audit reads)...
        self.assertEqual(children[0].private_provenance, {'delegated:connected-document'})
        # ...and #826: its public search went out.
        self.assertEqual(self.egress.plans, [{'tool': 'web_search', 'query': LAUNDERED}])

    def test_a_document_read_by_the_specialist_labels_the_parent_and_its_search_goes_out(self):
        """Provenance still flows back with the report; the parent's lookup is no longer refused."""
        parent_bodies, child_bodies = [], []

        def transport(url, body, headers=None, timeout=60):
            tools = {tool['function']['name'] for tool in body['tools']}

            def call(name, args):
                return {'model': 'x', 'choices': [{'message': {'tool_calls': [
                    {'id': '1', 'function': {'name': name,
                                             'arguments': json.dumps(args, ensure_ascii=False)}}]}}]}

            if 'delegate_agent' not in tools:            # the specialist
                turn = len(child_bodies)
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

        caps = self.caps()
        caps.adapter = ModelAdapter(transport)
        self.drive(caps, transport, '급여 정보를 찾아서 시세와 비교해줘')
        self.assertIn('110-222-333333', json.dumps(parent_bodies[-1]['messages'], ensure_ascii=False))
        self.assertIn('delegated:connected-document', caps.private_provenance)
        self.assertEqual(self.egress.plans, [{'tool': 'web_search', 'query': LAUNDERED}])

    # -- one test per labelled source, so no two can mask each other --------

    def test_each_private_read_is_labelled_and_a_lookup_still_goes_out(self):
        """Each read pins its own label (the audit's record); #826: none closes a public lookup."""
        self.store.enqueue('/note 병원 예약은 목요일', 'note')
        with self.store.db() as db:
            db.execute('INSERT OR IGNORE INTO notes VALUES (?,?,?)', ('n1', '병원 예약은 목요일 오후 3시', time.time()))
        cases = (('read_file', lambda caps: {'root_id': caps.roots()[0]['id'], 'path': 'pay.txt'}, 'connected-document'),
                 ('find_files', lambda caps: {'query': '급여'}, 'connected-document'),
                 ('list_roots', lambda caps: {}, 'owner-folder-names'),
                 ('list_notes', lambda caps: {}, 'personal-space'),
                 ('list_memory', lambda caps: {}, 'owner-memory'))
        for action, args, label in cases:
            with self.subTest(action):
                self.egress.plans.clear()
                caps = self.caps()
                caps.execute(action, args(caps))
                self.assertEqual(caps.private_provenance, {label})
                caps.execute('web_search', {'query': LAUNDERED})
                caps.execute('weather', {'city': '110-222-333333'})
                self.assertEqual([plan['tool'] for plan in self.egress.plans], ['web_search', 'weather'])
                self.assertEqual(self.egress.plans[1]['city'], '110-222-333333')

    def test_list_roots_with_no_connected_folders_is_not_a_source(self):
        """An empty root list is zero owner facts, so it records no source."""
        bare = Capabilities(QuickStore(Path(self.temp.name) / 'empty'), None, CFG, '',
                            'job', lambda *a: None, network=self.egress)
        self.assertEqual(bare.execute('list_roots', {}), {'roots': []})
        self.assertEqual(bare.private_provenance, set())

    def test_public_page_read_follows_only_the_owner_page_approval(self):
        """#826: private material in the Work no longer closes an approved page; the approval still bounds it."""
        scope = {'https://example.com/pricing'}
        facade = self.caps(public_page_scope=scope)
        facade.execute('list_notes', {})
        facade.execute('public_page_read', {'url': 'https://example.com/pricing'})
        with self.assertRaises(ValueError):
            facade.execute('public_page_read', {'url': 'https://example.com/pricing?account=110-222-333333'})
        child = self.caps(public_page_scope=set(), inherited_provenance={'delegated:connected-document'})
        with self.assertRaises(ValueError):
            child.execute('public_page_read', {'url': 'https://example.com/pricing'})
        self.assertEqual([plan['tool'] for plan in self.egress.plans], ['public_page_read'])

    def test_delegation_preserves_each_inherited_label(self):
        """The child inherits the parent's labels, not a single flat marker (the audit's record)."""
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

    # -- sources the evidence list never saw ------------------------------

    def test_execute_records_provenance_without_run_agent(self):
        """AgentOSMcpTools calls execute() directly for a subscription engine; the label is still taken."""
        with self.store.db() as db:
            db.execute('INSERT OR IGNORE INTO notes VALUES (?,?,?)',
                       ('n1', '병원 예약은 목요일 오후 3시', time.time()))
        caps = self.caps(allowed_tools={'list_notes', 'web_search'})
        caps.execute('list_notes', {})
        self.assertEqual(caps.evidence, [], 'run_agent is not in this path')
        self.assertEqual(caps.private_provenance, {'personal-space'})
        caps.execute('web_search', {'query': LAUNDERED})
        self.assertEqual(len(self.egress.plans), 1)

    def test_material_spliced_into_the_prompt_is_declared_at_construction(self):
        """The four quickstart_service splices declare their source; #826: a lookup still goes out."""
        for label in ('connected-document', 'connected-drive-file',
                      'owner-context-inbox', 'personal-space'):
            with self.subTest(label):
                caps = self.caps(inherited_provenance={label})
                self.assertEqual(caps.private_provenance, {label})
                caps.execute('web_search', {'query': LAUNDERED})
        self.assertEqual(len(self.egress.plans), 4)

    def test_an_unrecognised_evidence_entry_is_labelled_unattributed(self):
        caps = self.caps()
        caps.evidence.append({'tool': 'some_future_connector', 'result': {}})
        self.assertEqual(caps.private_provenance, {'unattributed-tool-evidence'})

    def test_a_public_result_is_not_a_private_source(self):
        caps = self.caps()
        caps.execute('web_search', {'query': 'first'})
        self.assertEqual(caps.private_provenance, set())
        caps.execute('web_search', {'query': 'second'})
        self.assertEqual(len(self.egress.plans), 2)


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
        self.plans = []
        self.service.local_tools = type('Wire', (), {'execute': lambda _self, plan: self.plans.append(plan) or {
            'tool': plan['tool'], 'query': plan.get('query', ''), 'results': [], 'sources': [], 'retrieved_at': 1}})()
        self.service.save_model({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434',
                                 'model': 'test-model', 'api_key': ''})
        self.assertTrue(self.service.test_model()['ok'])

    def test_summarize_splices_the_notes_in_and_the_search_goes_out(self):
        """#654 pilot posture: the note listing is private provenance, and the worker's query still goes out."""
        self.store.enqueue('/note 병원 예약은 목요일 오후 3시', 'note')
        self.service.run_one()
        self.store.enqueue('/summarize', 'summary')
        self.service.run_one()
        job = self.store.jobs()[0]
        # The notes really were put in the model's prompt for this turn.
        self.assertTrue(any('병원 예약' in message.get('content', '')
                            for message in self.bodies[-1]['messages']))
        # The model asked for a public search; the query (sharing no value
        # this Work wrote) went out, and the Work recorded its private source.
        self.assertTrue(self.searched)
        self.assertEqual(self.plans, [{'tool': 'web_search', 'query': LAUNDERED}])
        self.assertIn('personal-space', work_sources(self.store, job['id']))


if __name__ == '__main__':
    unittest.main()

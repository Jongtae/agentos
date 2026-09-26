"""Each private-material splice in the job worker must declare its provenance.

`AgentService.run_one` edits `history[-1]` in four places -- an approved
reference-folder summary, a Picker-selected Google Drive file, the owner
context inbox and `/summarize` notes -- and hands the result straight to the
model or the subscription engine.  None of those branches leaves a
`Capabilities.evidence` entry and none of them marks the current job as a
document job (`document_jobs` is read before this job exists), so the *only*
thing that closes `web_search`/`public_page_read`/`weather` for that turn is
the `turn_provenance` label the branch declares and the
`inherited_provenance=` that carries it into `Capabilities`.

`tests/test_private_provenance_egress.py` builds `Capabilities` by hand with
each label, which verifies the *guard*; it cannot see a missing *declaration*.
Every test here therefore drives the real worker (`service.run_one()`) and
asserts both halves of the property:

* the private material really did reach the prompt for that turn, so the test
  cannot pass because the branch quietly did nothing, and
* the public call the model/engine then made was refused.

Each test was mutation-checked by deleting exactly its own declaration line
from `quickstart_service.py` and observing this file fail.
"""
import json
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet

from personal_agent.agent_runtime import PUBLIC_TASK_UNRESOLVED
from personal_agent.bounded_execution import ExecutionError, ExecutionResult
from personal_agent.drive_web_oauth import DriveWebOAuthHandoff, EncryptedDriveSecretStore
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines

# Every outgoing query below is this one laundered string.  It shares no token
# with any private material in this file, so a lexical scan of the outgoing
# text would let all four through: what is under test is the routing-site
# declaration, not a filter over the query.
LAUNDERED = 'average compensation for a senior engineer in Seoul'
REFUSAL = '웹 검색어로 전송할 수 없습니다'

WORKSPACE_SECRET = 'Aurora 합병 대금은 420억 원으로 확정되었습니다.'
DRIVE_SECRET = '드라이브 원본: 이혼 조정 기일은 3월 9일입니다.'
CONTEXT_SECRET = '인박스 원본: 건강검진 결과 재검 통보를 받았습니다.'
NOTE_SECRET = '개인 메모: 병원 예약은 목요일 오후 3시입니다.'


class Egress:
    """Stands in for LocalTools and records everything that reached the wire."""

    def __init__(self):
        self.plans = []

    def execute(self, plan):
        self.plans.append(plan)
        return {'tool': plan['tool'], 'query': plan.get('query', ''), 'results': [],
                'sources': ['공개 웹'], 'retrieved_at': 1}


class WorkerProvenanceDeclarationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = QuickStore(self.root / 'data')
        self.model_bodies = []
        self.searched = []

        def transport(url, body, headers=None, timeout=60):
            # The same callable serves the model and Telegram; only a model
            # request carries `messages`.
            if not isinstance(body, dict) or 'messages' not in body:
                return {'ok': True, 'result': {'message_id': 1}}
            self.model_bodies.append(body)
            tools = [(tool.get('function', {}).get('name') or tool.get('name'))
                     for tool in body.get('tools', [])]
            if 'agentos_connection_probe' in tools:
                return {'message': {'content': '', 'tool_calls': [
                    {'function': {'name': 'agentos_connection_probe', 'arguments': {}}}]}}
            if 'web_search' in tools and not self.searched:
                self.searched.append(True)
                return {'message': {'content': '', 'tool_calls': [
                    {'function': {'name': 'web_search', 'arguments': {'query': LAUNDERED}}}]}}
            return {'message': {'content': '정리했습니다.'}}

        self.transport = transport
        self.egress = Egress()
        # A local model keeps `document_boundary()['requires_approval']` false,
        # so nothing below is refused by the separate external-model gate.
        self.service = AgentService(self.store, ModelAdapter(transport), transport)
        self.service.local_tools = self.egress
        self.service.save_model({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434',
                                 'model': 'test-model', 'api_key': ''})
        self.assertTrue(self.service.test_model()['ok'])
        self.model_bodies.clear()

    def failed(self, job_id, tool):
        return [event for event in self.store.task_events(job_id)
                if event['tool'] == tool and event['status'] == 'failed']

    def prompt_text(self):
        self.assertTrue(self.model_bodies, 'the model was never called for this turn')
        return json.dumps(self.model_bodies, ensure_ascii=False)

    # -- 1. the approved reference-folder summary -------------------------

    def test_workspace_summary_turn_declares_connected_document(self):
        """`turn_provenance.add('connected-document')` in the summary branch.

        The branch splices reference-folder text into `history[-1]` and marks
        the job as a document job only *after* the model has answered, so this
        declaration is the sole thing closing web_search for the turn itself.
        """
        reference = self.root / 'reference'
        workspace = self.root / 'workspace'
        reference.mkdir()
        workspace.mkdir()
        (reference / 'aurora.md').write_text(WORKSPACE_SECRET, encoding='utf-8')
        self.service.configure_file_workspace({'references': [str(reference)],
                                               'workspace': str(workspace)})
        job = self.store.enqueue('/workspace-summary Aurora :: Launch notes', 'workspace-provenance')
        self.assertTrue(self.service.run_one())
        # The reference text really was spliced into this turn's prompt.
        self.assertIn(WORKSPACE_SECRET, self.prompt_text())
        # ...and the public call the model then made was refused, even though
        # its query shares no token with the reference text.
        self.assertTrue(self.searched, 'the model never attempted a public search')
        self.assertTrue(self.failed(job, 'web_search'),
                        'the workspace-summary turn left web_search open')
        self.assertEqual(self.egress.plans, [])

    # -- 2. the Picker-selected Drive file --------------------------------

    def test_drive_file_turn_declares_connected_drive_file(self):
        """`turn_provenance.add('connected-drive-file')` in the Drive branch.

        Drive content is deliberately never persisted to jobs, messages or
        evidence, so there is no other record of it in the turn at all.
        """
        drive = DriveWebOAuthHandoff(EncryptedDriveSecretStore(self.store, Fernet.generate_key()),
                                     'client', 'http://localhost:8787/oauth/google/callback',
                                     'http://localhost:8787', allow_localhost=True, local_only=True)
        offer = drive.begin(123)
        state = parse_qs(urlsplit(offer['button']['url']).query)['state'][0]
        drive.complete({'state': state, 'code': 'code'}, 123,
                       lambda _: {'access_token': 'server-token',
                                  'scope': 'https://www.googleapis.com/auth/drive.file'})
        drive.select_files(123, [{'id': 'picked', 'name': 'plan.txt'}])
        self.service.drive_web_oauth = drive
        self.service.drive_read = lambda _url, _body, _headers: DRIVE_SECRET.encode('utf-8')
        job = self.store.enqueue('구글 드라이브 파일을 요약해줘', 'drive-provenance',
                                 channel='telegram:g', chat_id=123)
        self.assertTrue(self.service.run_one())
        self.assertIn(DRIVE_SECRET, self.prompt_text())
        self.assertTrue(self.searched, 'the model never attempted a public search')
        self.assertTrue(self.failed(job, 'web_search'),
                        'the selected-Drive turn left web_search open')
        self.assertEqual(self.egress.plans, [])

    # -- 3. the owner context inbox ---------------------------------------

    def test_context_attachment_turn_declares_owner_context_inbox(self):
        """`turn_provenance.add('owner-context-inbox')` in the attachment branch.

        Its only previous control was the sentence "Never send it to web
        search" addressed to the model inside the prompt.
        """
        inbox = self.service.context_inbox()
        inbox.configure({'sources': {'text': True}})
        item = inbox.capture({'source_kind': 'text', 'content': CONTEXT_SECRET,
                              'retention_seconds': 600})
        self.service.set_context_telegram_policy({'approved': True})
        job = self.store.enqueue('이 내용을 바탕으로 답해 줘', 'context-provenance',
                                 channel='telegram:g', chat_id=42)
        self.store.attach_context(job, [item['id']], self.service.context_assistant_id())
        self.assertTrue(self.service.run_one())
        self.assertIn(CONTEXT_SECRET, self.prompt_text())
        self.assertTrue(self.searched, 'the model never attempted a public search')
        self.assertTrue(self.failed(job, 'web_search'),
                        'the context-inbox turn left web_search open')
        self.assertEqual(self.egress.plans, [])

    # -- 4. the subscription-engine capabilities --------------------------

    def test_subscription_engine_capabilities_inherit_the_turn_provenance(self):
        """`inherited_provenance=turn_provenance` on the subscription branch.

        The engine reaches AgentOS only through `AgentOSMcpTools`, which calls
        `Capabilities.execute` directly: `run_agent` is not in this path, so
        the evidence list is empty while the engine holds the owner's notes.
        `/summarize` is used because the subscription branch refuses a
        workspace summary outright, and the refusal is observed on the real
        facade the worker handed to the engine.
        """
        class Adapter:
            def __init__(self):
                self.prompt = None
                self.refusal = None
                self.searched = False

            def execute(self, engine, prompt, tools, **_kwargs):
                self.prompt = prompt
                try:
                    tools.call('web_search', {'query': LAUNDERED})
                except ValueError as exc:
                    self.refusal = str(exc)
                    raise ExecutionError('공개 검색이 거부되어 실행을 중단했습니다.') from exc
                self.searched = True
                return ExecutionResult('engine answer', engine, 0)

        with self.store.db() as db:
            db.execute('INSERT OR IGNORE INTO notes VALUES (?,?,?)', ('note-1', NOTE_SECRET, time.time()))
        adapter = Adapter()
        service = AgentService(self.store, ModelAdapter(self.transport), self.transport,
                               subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/codex',
                                                                        clock=lambda: 1),
                               execution_adapter=adapter)
        service.local_tools = self.egress
        service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        job = self.store.enqueue('/summarize', 'subscription-provenance')
        self.assertTrue(service.run_one())
        # The notes really were spliced into the engine prompt for this turn.
        self.assertIn(NOTE_SECRET, adapter.prompt or '')
        # ...and the engine's public call through the AgentOS facade was
        # refused, not by argument validation: since #605 a private context
        # sends only words permitted for the lookup, and no word of the
        # laundered query is in the owner's request.
        self.assertFalse(adapter.searched)
        self.assertIn(PUBLIC_TASK_UNRESOLVED, adapter.refusal or '')
        self.assertEqual(self.egress.plans, [])
        self.assertTrue(self.failed(job, 'subscription_engine'),
                        'the refused engine turn was not recorded as failed')


if __name__ == '__main__':
    unittest.main()

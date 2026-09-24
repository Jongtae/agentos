import tempfile
import unittest

from personal_agent.a2a import A2ADelegation
from personal_agent.calendar import CalendarCreate
from personal_agent.capabilities import CapabilityRegistry
from personal_agent.personal_assistant import PersonalAssistantOrchestrator
from personal_agent.quickstart_store import QuickStore
from personal_agent.quickstart_service import AgentService


class Peer:
    def __init__(self): self.requests = []
    def card(self): return {'protocol': 'a2a/1', 'skill': 'bounded-research', 'artifact_schema': 'text'}
    def create(self, request): self.requests.append(request); return {'correlation_id': request['correlation_id']}
    def status(self, ident, correlation): return {'correlation_id': correlation, 'state': 'working'}
    def cancel(self, ident, correlation): pass


class Drive:
    def __init__(self): self.queries = []
    def search(self, query): self.queries.append(query); return [{'id': 'file-1', 'name': 'private plan', 'mime_type': 'text/plain', 'token': 'must-not-return'}]
    def read(self, file_id): return 'private selected Drive excerpt'


class PersonalAssistantTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.store = QuickStore(self.temp.name)
        self.peer, self.drive, self.calls = Peer(), Drive(), []
        self.calendar = CalendarCreate(self.store, lambda *_: self.calls.append(True) or {'id': 'event'})
        self.assistant = PersonalAssistantOrchestrator(self.store, drive=self.drive, a2a=A2ADelegation(self.store, self.peer), calendar=self.calendar, now=lambda: 1)
        self.registry = CapabilityRegistry(self.store)
    def tearDown(self): self.temp.cleanup()
    def enable(self, capability, scopes): self.registry.transition(capability, 'enabled', scopes)
    def request(self, message='내 개인 공간을 보여줘', **extra): return {'message': message, 'owner_id': 'owner', **extra}

    def test_local_answer_reads_personal_space_and_records_redacted_evidence(self):
        self.store.put('personal_assistant_evidence', [])
        result = self.assistant.handle(self.request())
        self.assertEqual(result['state'], 'completed')
        self.assertNotIn('자연어 요청', str(self.store.config('personal_assistant_evidence')))

    def test_disabled_paused_and_disconnected_capability_never_invokes_adapter(self):
        for state in ('available', 'paused', 'disconnected'):
            if state != 'available': self.registry.transition('google-drive-read', state)
            result = self.assistant.handle(self.request('Drive 검색: private query', query='private query'))
            self.assertEqual(result['state'], 'blocked'); self.assertFalse(self.drive.queries)

    def test_drive_evidence_is_enabled_only_and_has_no_adapter_secret(self):
        self.enable('google-drive-read', ('read',))
        result = self.assistant.handle(self.request('Drive 검색: plan', query='plan'))
        self.assertEqual(result['sources'], [{'id': 'file-1', 'name': 'private plan', 'mime_type': 'text/plain'}])
        self.assertNotIn('must-not-return', str(result))

    def test_a2a_requires_enabled_capability_and_explicit_owner_delegation(self):
        self.enable('compatibility-a2a-peer', ('delegate',))
        implicit = self.assistant.handle(self.request('다른 Agent에게 맡겨줘'))
        self.assertEqual(implicit['state'], 'fallback'); self.assertFalse(self.peer.requests)
        delegated = self.assistant.handle(self.request('A2A 위임: 자연어 요청을 조사해줘'))
        self.assertEqual(delegated['state'], 'requested'); self.assertEqual(len(self.peer.requests), 1)

    def test_selected_drive_excerpt_requires_owner_approval_before_a2a_context(self):
        self.enable('google-drive-read', ('read',)); self.enable('compatibility-a2a-peer', ('delegate',))
        blocked = self.assistant.handle(self.request('A2A 위임: 발췌문을 요약해줘', drive_excerpt={'excerpt_id': 'missing', 'approval_id': 'missing'}))
        self.assertEqual(blocked['state'], 'blocked'); self.assertFalse(self.peer.requests)
        draft = self.assistant.draft_drive_excerpt(self.request('Drive 발췌문: 선택', file_id='file-1', length=8))
        approved = self.assistant.approve_drive_excerpt(self.request('Drive 발췌 승인', excerpt_id=draft['excerpt']['id']))
        delegated = self.assistant.handle(self.request('A2A 위임: 발췌문을 요약해줘', drive_excerpt={'excerpt_id': draft['excerpt']['id'], 'approval_id': approved['approval_id']}))
        self.assertEqual(delegated['state'], 'requested'); self.assertEqual(self.peer.requests[-1]['context'], {'text': 'private '})
        self.assertNotIn('private ', str(self.store.config('personal_assistant_evidence')))

    def test_orchestrator_normalizes_invalid_a2a_card_to_recovery(self):
        self.enable('compatibility-a2a-peer', ('delegate',))
        self.peer.card = lambda: {'protocol': 'a2a/1', 'skill': 'unknown', 'artifact_schema': 'text'}
        result = self.assistant.handle(self.request('A2A 위임: 조사해줘'))
        self.assertEqual(result['state'], 'blocked')
        self.assertIn('recovery', result['evidence'])

    def test_calendar_only_creates_draft_and_never_writes_before_approval(self):
        self.enable('google-calendar-create', ('calendar.events',))
        result = self.assistant.handle(self.request('일정 초안: 내일 검토 일정', event={'summary': 'review', 'start': '2026-01-01T10:00', 'end': '2026-01-01T11:00', 'timezone': 'Asia/Seoul'}))
        self.assertEqual(result['state'], 'awaiting-approval'); self.assertFalse(self.calls)

    def test_calendar_approval_and_create_stay_inside_orchestrator_gate(self):
        self.enable('google-calendar-create', ('calendar.events',))
        draft = self.assistant.handle(self.request('일정 초안: 검토', event={'summary': 'review', 'start': '2026-01-01T10:00', 'end': '2026-01-01T11:00', 'timezone': 'Asia/Seoul'}))['draft']
        approval = self.assistant.approve_calendar(self.request('일정 승인', draft_id=draft['id']))
        created = self.assistant.create_calendar(self.request('일정 생성', draft_id=draft['id'], approval_id=approval['approval']['approval_id']))
        self.assertEqual(created['state'], 'completed'); self.assertEqual(len(self.calls), 1)
        self.assertNotIn('approval', str(created['evidence']))

    def test_unknown_request_has_deterministic_recovery(self):
        result = self.assistant.handle(self.request('무슨 capability인지 모르는 요청'))
        self.assertEqual(result['state'], 'fallback'); self.assertIn('recovery', result['evidence'])

    def test_channel_service_has_one_policy_owned_entrypoint(self):
        service = AgentService(self.store, assistant_orchestrator=self.assistant)
        result = service.personal_assistant_request({'message': '일정 초안: 검토', 'event': {'summary': 'review', 'start': '2026-01-01T10:00', 'end': '2026-01-01T11:00', 'timezone': 'Asia/Seoul'}})
        self.assertEqual(result['state'], 'blocked')
        self.assertFalse(self.calls)

    def test_telegram_job_uses_the_same_policy_path(self):
        service = AgentService(self.store, assistant_orchestrator=self.assistant)
        job = self.store.enqueue('/assistant A2A 위임: 조사해줘', 'telegram-policy', channel='telegram:test', chat_id=7)
        self.assertTrue(service.run_one())
        stored = self.store.job(job)
        self.assertEqual(stored['status'], 'failed')
        self.assertFalse(self.peer.requests)

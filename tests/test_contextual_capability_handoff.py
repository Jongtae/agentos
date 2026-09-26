"""Contextual local-folder authority handoff and exactly-once resume (#505).

Whole turns are driven through ``AgentService`` with a scripted model and a
recorded Telegram seam, and the owner-local approval surface is driven both
through the service boundary and through the real HTTP handler.  Assertions
are on what the owner actually sees (Telegram bubbles, stored transcript) and
on the authoritative state underneath (job status, folder grants, index).
"""
import json
import re
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from personal_agent import local_folder_picker
from personal_agent.connector_contract import ConnectorContractError
from personal_agent.conversation_handoff import (CONVERSATION_RESUME_KEY, LOCAL_AUTHORITY_PREVIEWS,
                                                 LOCAL_FOLDER_READ, LOCAL_REFERENCE_READ, LOCAL_REFUSALS,
                                                 LOCAL_RESULT_WRITE, ConversationHandoffError, LocalGrantPending,
                                                 local_authority_handoff)
from personal_agent.file_workspace import FileWorkspace
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart import make_handler
from personal_agent.quickstart_service import (LOCAL_DOCUMENT_APPROVAL_TEXT, LOCAL_KEPT_WORKSPACE_TEXT,
                                              AgentService)
from personal_agent.quickstart_store import QuickStore

CHAT = 505
GENERATION = 'g1'
OWNER = f'telegram:{CHAT}'
MOBILE_HOST = 'mobile.example.test'


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


class HandoffTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parent))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = QuickStore(self.root / 'data')
        self.sent = []
        self.plan = []
        self.text = '계약서 갱신일은 10월 1일입니다.'
        self.turn = 0
        # #657: when set, the model ends a tool-using turn with a finish claim citing every result it was shown.
        self.claim = False
        self.picked = None
        self.service = self.make_service()
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION})

    def make_service(self):
        def transport(url, body=None, headers=None, timeout=60):
            if url.endswith('/sendMessage'):
                self.sent.append(body['text'])
                return {'ok': True, 'result': {'message_id': len(self.sent)}}
            return {'ok': True, 'result': []}

        def model(url, body, headers=None, timeout=60):
            tools = [t.get('function', {}).get('name') or t.get('name') for t in body.get('tools', [])]
            if 'agentos_connection_probe' in tools:
                return {'message': {'content': '', 'tool_calls': [
                    {'id': 'probe', 'function': {'name': 'agentos_connection_probe', 'arguments': {}}}]}}
            if self.plan and tools:
                name, arguments = self.plan.pop(0)
                self.turn += 1
                return {'message': {'content': '', 'tool_calls': [
                    {'id': f'call-{self.turn}', 'function': {'name': name, 'arguments': arguments}}]}}
            refs = [json.loads(m['content']).get('ref') for m in body.get('messages', [])
                    if m.get('role') == 'tool' and str(m.get('content', '')).startswith('{')]
            if self.claim and tools and any(refs):
                self.claim = False
                return {'message': {'content': '', 'tool_calls': [
                    {'id': 'finish', 'function': {'name': 'finish', 'arguments': {
                        'status': 'done', 'evidence_refs': [ref for ref in refs if ref], 'summary': self.text}}}]}}
            return {'message': {'content': self.text}}

        service = AgentService(self.store, ModelAdapter(model), transport)
        if not self.store.config('model'):
            service.save_model({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434',
                                'model': 'test-model', 'api_key': ''})
            self.assertTrue(service.test_model()['ok'])
        service.local_server_port = 8765
        service.folder_picker = lambda prompt: self.picked
        return service

    def claim_completion(self):
        """#657: the model claims completion and the judgment finds it shown."""
        from test_agency_loop import goal_engine
        self.claim = True
        self.service.use_decision_engine(goal_engine(True))

    def folder(self, name, files=None):
        path = self.root / name
        path.mkdir()
        for filename, text in (files or {}).items():
            (path / filename).write_text(text, encoding='utf-8')
        return path

    def ask(self, message):
        job_id = self.store.enqueue(message, f'ask-{len(self.sent)}-{self.turn}-{message}',
                                    channel=f'telegram:{GENERATION}', chat_id=CHAT)
        self.service.run_one()
        before = len(self.sent)
        self.service.deliver_one()
        return job_id, self.sent[before:]

    def job(self, job_id):
        return self.store.job(job_id)

    def roots(self):
        return [root['path'] for root in self.store.config('file_roots', [])]

    def pending(self):
        return self.service.local_authority_requests()['requests']

    def approve_picked(self, path):
        self.picked = str(path)
        request = self.pending()[0]
        self.service.select_local_folder({'handoff_id': request['handoff_id']})
        return request, self.service.approve_local_folder({'handoff_id': request['handoff_id']})

    def park_read(self):
        self.plan = [('find_files', {'query': '계약서'})]
        job_id, bubbles = self.ask('내 계약서 폴더에서 갱신 날짜 찾아줘')
        self.assertEqual(self.job(job_id)['status'], 'awaiting_connection')
        return job_id, bubbles

    def assert_telegram_safe(self, text):
        self.assertNotIn(str(self.root), text)
        self.assertIsNone(re.search(r'(?<!\w)/(?:Users|home|private|tmp|var)/', text))
        for internal in (LOCAL_FOLDER_READ, LOCAL_REFERENCE_READ, LOCAL_RESULT_WRITE, 'handoff', 'folder:read',
                         'resume_token'):
            self.assertNotIn(internal, text)
        rows = self.store.secret(CONVERSATION_RESUME_KEY) or {}
        for row in rows.values():
            self.assertNotIn(row['handoff_id'], text)
            self.assertNotIn(row['resume_token'], text)


class ReadHandoffTests(HandoffTestCase):
    def test_a_file_request_with_no_folder_gets_one_contextual_next_action(self):
        job_id, bubbles = self.park_read()
        self.assertEqual(len(bubbles), 1, bubbles)
        guidance = bubbles[0]
        self.assertIn('Mac에서 계속', guidance)
        self.assertIn('설정 → 파일 · 저장', guidance)
        self.assertIn('http://127.0.0.1:8765/#settings/files', guidance)
        self.assertIn('읽기만', guidance)
        self.assertIn('휴대폰이나 다른 기기에서는 Mac 폴더 권한을 줄 수 없으며', guidance)
        self.assertNotIn('찾지 못했습니다', guidance)
        self.assert_telegram_safe(guidance)
        # Setup-required is its own Work state: parked, not failed or succeeded.
        job = self.job(job_id)
        self.assertEqual(job['status'], 'awaiting_connection')
        self.assertEqual(job['response'], guidance)
        self.assertIsNone(job['error'])
        history = [row for row in self.store.history() if row['job_id'] == job_id and row['role'] == 'assistant']
        self.assertEqual([row['content'] for row in history], [guidance])
        # Nothing was granted by asking.
        self.assertEqual(self.roots(), [])

    def test_the_mac_surface_previews_read_authority_and_grants_only_the_chosen_folder(self):
        job_id, _ = self.park_read()
        requests = self.pending()
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]['authority'], 'read')
        self.assertEqual(requests[0]['preview'], LOCAL_AUTHORITY_PREVIEWS[LOCAL_FOLDER_READ])
        self.assertIn('읽기만', requests[0]['preview'])
        self.assertIn('외부 AI에 보내지 않습니다', requests[0]['preview'])
        self.assertIsNone(requests[0]['selection'])

        contracts = self.folder('contracts', {'renewal.txt': '계약서 갱신일: 10월 1일'})
        self.picked = str(contracts)
        selected = self.service.select_local_folder({'handoff_id': requests[0]['handoff_id']})
        self.assertEqual(selected['name'], 'contracts')
        self.assertEqual(selected['authority'], 'read')
        # Selecting is not granting.
        self.assertEqual(self.roots(), [])
        self.assertEqual(self.job(job_id)['status'], 'awaiting_connection')

        before = len(self.sent)
        result = self.service.approve_local_folder({'handoff_id': requests[0]['handoff_id']})
        self.assertEqual(result, {'state': 'approved', 'authority': 'read', 'scheduled': True, 'name': 'contracts',
                                  'kept_existing': False})
        self.assertEqual(self.roots(), [str(contracts.resolve())])
        # A read grant is never a result-write grant.
        self.assertIsNone(self.store.config('file_workspace', {}).get('workspace'))
        self.assertEqual(self.store.config('document_sharing'), {})
        self.assertEqual(self.job(job_id)['status'], 'queued')
        notice = self.sent[before:]
        self.assertEqual(notice, ['선택한 폴더를 읽기로 허용했습니다. 방금 요청을 이어서 처리합니다.'])
        self.assert_telegram_safe(notice[0])

        # The original Work resumes, once; #657: its answer is a judged completion claim.
        self.plan = [('find_files', {'query': '계약서'})]
        self.claim_completion()
        self.assertTrue(self.service.run_one())
        before = len(self.sent)
        self.service.deliver_one()
        self.assertEqual(self.job(job_id)['status'], 'succeeded')
        self.assertEqual(self.sent[before:], [self.text])
        self.assertFalse(self.service.run_one())
        self.assertEqual(self.pending(), [])

    def test_replayed_approval_does_not_resume_twice(self):
        job_id, _ = self.park_read()
        request, _approved = self.approve_picked(self.folder('contracts'))
        self.service.run_one()
        self.assertEqual(self.job(job_id)['status'], 'succeeded')
        with self.assertRaises(ConversationHandoffError) as replay:
            self.service.approve_local_folder({'handoff_id': request['handoff_id']})
        self.assertEqual(replay.exception.reason, 'no_pending_work')
        self.assertEqual(self.job(job_id)['status'], 'succeeded')
        self.assertFalse(self.service.run_one())
        with self.store.db() as db:
            runs = db.execute("SELECT COUNT(*) FROM messages WHERE job_id=? AND role='user'", (job_id,)).fetchone()[0]
        self.assertEqual(runs, 2, 'one parked run plus exactly one resumed run')

    def test_deny_fails_the_work_and_grants_nothing(self):
        job_id, _ = self.park_read()
        request = self.pending()[0]
        before = len(self.sent)
        self.assertEqual(self.service.deny_local_folder({'handoff_id': request['handoff_id']}), {'state': 'denied'})
        job = self.job(job_id)
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(job['error'], LOCAL_REFUSALS['denied'])
        self.assertEqual(self.sent[before:], [LOCAL_REFUSALS['denied']])
        self.assertEqual(self.roots(), [])
        self.assertFalse(self.service.run_one())
        with self.assertRaises(ConversationHandoffError):
            self.service.approve_local_folder({'handoff_id': request['handoff_id']})

    def test_expired_request_fails_without_granting(self):
        clock = Clock()
        self.service.local_handoff = local_authority_handoff(self.store, now=clock)
        job_id, _ = self.park_read()
        self.picked = str(self.folder('contracts'))
        request = self.pending()[0]
        self.service.select_local_folder({'handoff_id': request['handoff_id']})
        clock.now += 3601
        with self.assertRaises(ConversationHandoffError) as expired:
            self.service.approve_local_folder({'handoff_id': request['handoff_id']})
        self.assertEqual(expired.exception.reason, 'expired_resume')
        self.assertEqual(self.job(job_id)['status'], 'failed')
        self.assertEqual(self.job(job_id)['error'], LOCAL_REFUSALS['expired_resume'])
        self.assertEqual(self.roots(), [])
        self.assertFalse(self.service.run_one())

    def test_a_different_paired_owner_cannot_approve_the_parked_request(self):
        job_id, _ = self.park_read()
        self.picked = str(self.folder('contracts'))
        request = self.pending()[0]
        self.service.select_local_folder({'handoff_id': request['handoff_id']})
        self.store.put('telegram', {'enabled': True, 'user_id': 777, 'generation': 'g2'})
        with self.assertRaises(ConversationHandoffError) as wrong:
            self.service.approve_local_folder({'handoff_id': request['handoff_id']})
        self.assertEqual(wrong.exception.reason, 'wrong_owner')
        self.assertEqual(self.roots(), [])
        self.assertEqual(self.job(job_id)['status'], 'awaiting_connection')
        self.assertFalse(self.service.run_one())

    def test_a_replaced_bot_generation_cannot_resume_the_parked_request(self):
        job_id, _ = self.park_read()
        self.picked = str(self.folder('contracts'))
        request = self.pending()[0]
        self.service.select_local_folder({'handoff_id': request['handoff_id']})
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': 'g2'})
        with self.assertRaises(ConversationHandoffError) as changed:
            self.service.approve_local_folder({'handoff_id': request['handoff_id']})
        self.assertEqual(changed.exception.reason, 'generation_changed')
        self.assertEqual(self.roots(), [])
        self.assertFalse(self.service.run_one())

    def test_restart_keeps_the_request_resumable_exactly_once(self):
        job_id, _ = self.park_read()
        self.service = self.make_service()
        self.assertEqual(len(self.pending()), 1)
        self.approve_picked(self.folder('contracts'))
        self.assertEqual(self.job(job_id)['status'], 'queued')
        self.service = self.make_service()
        self.assertTrue(self.service.run_one())
        self.assertEqual(self.job(job_id)['status'], 'succeeded')
        self.assertFalse(self.service.run_one())
        self.assertEqual(self.pending(), [])

    def test_a_refused_folder_is_not_selected_and_nothing_is_granted(self):
        self.park_read()
        request = self.pending()[0]
        self.picked = str(Path.home())
        with self.assertRaises(ValueError):
            self.service.select_local_folder({'handoff_id': request['handoff_id']})
        self.picked = str(self.root / 'missing')
        with self.assertRaises(ValueError):
            self.service.select_local_folder({'handoff_id': request['handoff_id']})
        with self.assertRaises(ValueError):
            self.service.approve_local_folder({'handoff_id': request['handoff_id']})
        self.assertEqual(self.roots(), [])

    def test_a_cancelled_picker_changes_nothing(self):
        job_id, _ = self.park_read()
        self.picked = None
        request = self.pending()[0]
        self.assertEqual(self.service.select_local_folder({'handoff_id': request['handoff_id']}), {'state': 'cancelled'})
        self.assertEqual(self.job(job_id)['status'], 'awaiting_connection')
        self.assertEqual(self.pending()[0]['selection'], None)

    def test_a_telegram_message_naming_a_path_grants_nothing(self):
        job_id, _ = self.park_read()
        contracts = self.folder('contracts')
        self.ask(f'{contracts} 폴더를 허용해줘')
        self.assertEqual(self.roots(), [])
        self.assertEqual(self.job(job_id)['status'], 'awaiting_connection')

    def test_the_owner_can_withdraw_the_parked_request_in_conversation(self):
        job_id, _ = self.park_read()
        cancelled, text = self.service.cancel_focused_work(self.job(job_id), OWNER)
        self.assertTrue(cancelled, text)
        self.assertEqual(self.job(job_id)['status'], 'cancelled')
        self.assertEqual(self.pending(), [])

    def test_listing_folders_first_is_still_a_read_only_turn(self):
        self.plan = [('list_roots', {}), ('find_files', {'query': '계약서'})]
        job_id, bubbles = self.ask('내 계약서 폴더에서 갱신 날짜 찾아줘')
        self.assertEqual(self.job(job_id)['status'], 'awaiting_connection')
        self.assertIn('Mac에서 계속', bubbles[0])

    def test_a_turn_whose_effect_call_raised_is_not_parked(self):
        self.plan = [('delegate_agent', {'agent_id': 'no-such-agent', 'task': '계약서 검토'}),
                     ('find_files', {'query': '계약서'})]
        job_id, _ = self.ask('계약서 검토 맡기고 파일도 찾아줘')
        self.assertNotEqual(self.job(job_id)['status'], 'awaiting_connection')
        self.assertEqual(self.pending(), [])

    def test_provenance_records_the_parked_state(self):
        job_id, _ = self.park_read()
        self.assertEqual(self.store.turn_provenance(job_id)['status'], 'setup-required')

    def test_a_concurrent_second_approval_is_a_friendly_refusal(self):
        job_id, _ = self.park_read()
        self.picked = str(self.folder('contracts'))
        request = self.pending()[0]
        self.service.select_local_folder({'handoff_id': request['handoff_id']})
        pending = self.service.local_handoff.pending

        def lost_race(*args):
            raise ConnectorContractError('unclaimed_resume')
        pending.complete = lost_race
        with self.assertRaises(ConversationHandoffError) as raced:
            self.service.approve_local_folder({'handoff_id': request['handoff_id']})
        self.assertEqual(raced.exception.reason, 'replayed_resume')
        self.assertEqual(self.job(job_id)['status'], 'queued')
        self.service.run_one()
        self.assertFalse(self.service.run_one(), 'still scheduled exactly once')

    def test_a_turn_that_ran_an_effect_is_not_parked(self):
        self.plan = [('save_note', {'content': '계약서 확인'}), ('find_files', {'query': '계약서'})]
        job_id, _ = self.ask('계약서 메모하고 파일도 찾아줘')
        self.assertNotEqual(self.job(job_id)['status'], 'awaiting_connection')
        self.assertEqual(self.pending(), [])

    def test_settings_still_inspects_and_revokes_a_granted_folder(self):
        self.park_read()
        contracts = self.folder('contracts')
        self.approve_picked(contracts)
        self.service.run_one()
        self.assertEqual([root['path'] for root in self.service.settings()['file_roots']], [str(contracts.resolve())])
        self.service.save_roots({'paths': []})
        self.assertEqual(self.roots(), [])
        job_id, _ = self.park_read()
        self.assertEqual(len(self.pending()), 1)


class HostedModelDocumentApprovalTests(HandoffTestCase):
    """A hosted model still needs document sharing; the folder-resumed Work continues once after it."""

    def make_service(self):
        service = super().make_service()

        def hosted(url, body, headers=None, timeout=60):
            tools = [t.get('function', {}).get('name') for t in body.get('tools', [])]
            if 'agentos_connection_probe' in tools:
                return {'choices': [{'message': {'tool_calls': [
                    {'id': 'probe', 'function': {'name': 'agentos_connection_probe', 'arguments': '{}'}}]}}]}
            if self.plan and tools:
                name, arguments = self.plan.pop(0)
                self.turn += 1
                return {'choices': [{'message': {'content': '', 'tool_calls': [
                    {'id': f'call-{self.turn}', 'function': {'name': name, 'arguments': json.dumps(arguments)}}]}}]}
            refs = [json.loads(m['content']).get('ref') for m in body.get('messages', [])
                    if m.get('role') == 'tool' and str(m.get('content', '')).startswith('{')]
            if self.claim and tools and any(refs):
                self.claim = False
                return {'choices': [{'message': {'content': '', 'tool_calls': [
                    {'id': 'finish', 'function': {'name': 'finish', 'arguments': json.dumps(
                        {'status': 'done', 'evidence_refs': [ref for ref in refs if ref], 'summary': self.text})}}]}}]}
            return {'choices': [{'message': {'content': self.text}}]}

        service.adapter = ModelAdapter(hosted)
        if self.store.config('model', {}).get('provider') != 'compatible':
            service.save_model({'provider': 'compatible', 'endpoint': 'https://example.test/v1',
                                'model': 'hosted', 'api_key': 'hosted-key'})
            self.assertTrue(service.test_model()['ok'])
        return service

    def callback(self, notification, action, sender=CHAT):
        self.service.ingest_callback({'id': f'cb-{action}-{sender}', 'from': {'id': sender},
                                      'message': {'chat': {'id': sender, 'type': 'private'},
                                                  'message_id': notification['message_id']},
                                      'data': f"p7a:{notification['id']}:{action}"}, GENERATION)

    def test_folder_then_document_approval_resume_the_same_work_once(self):
        job_id, _ = self.park_read()
        self.approve_picked(self.folder('contracts', {'renewal.txt': '계약서 갱신일: 10월 1일'}))
        self.assertTrue(self.service.document_boundary()['requires_approval'], 'a grant never carries sharing')
        self.plan = [('find_files', {'query': '계약서'})]
        self.service.run_one()
        self.assertEqual(self.job(job_id)['status'], 'failed')
        self.assertTrue(self.service.deliver_notification())
        with self.store.db() as db:
            notification = dict(db.execute("SELECT * FROM telegram_notifications WHERE job_id=? AND kind='approval_needed'",
                                           (job_id,)).fetchone())
        self.callback(notification, 'approve', sender=999)  # not the paired owner
        self.assertEqual(self.job(job_id)['status'], 'failed')
        self.callback(notification, 'approve')
        self.assertFalse(self.service.document_boundary()['requires_approval'])
        self.assertEqual(self.job(job_id)['status'], 'queued')
        self.plan = [('find_files', {'query': '계약서'})]
        self.claim_completion()
        self.assertTrue(self.service.run_one())
        self.assertEqual(self.job(job_id)['status'], 'succeeded', self.job(job_id).get('error'))
        self.assertFalse(self.service.resume_after_document_approval(job_id), 'continues once only')
        self.assertFalse(self.service.run_one())

    def stop_at_sharing(self, clock=None, resumed_plan=None):
        if clock is not None:
            self.service.local_handoff = local_authority_handoff(self.store, now=clock)
        job_id, _ = self.park_read()
        self.approve_picked(self.folder('contracts', {'renewal.txt': '계약서 갱신일: 10월 1일'}))
        self.plan = resumed_plan or [('find_files', {'query': '계약서'})]
        self.service.run_one()
        self.assertIn(self.job(job_id)['status'], ('failed', 'partial'))
        before = len(self.sent)
        self.assertTrue(self.service.deliver_notification())
        with self.store.db() as db:
            notification = dict(db.execute("SELECT * FROM telegram_notifications WHERE job_id=? AND kind='approval_needed'",
                                           (job_id,)).fetchone())
        return job_id, notification, self.sent[before:]

    def test_the_sharing_notification_says_approval_continues_that_request(self):
        _job_id, _notification, sent = self.stop_at_sharing()
        self.assertEqual(sent, [LOCAL_DOCUMENT_APPROVAL_TEXT])

    def test_a_newer_request_withdraws_the_continuation(self):
        job_id, notification, _ = self.stop_at_sharing()
        self.ask('아까 요청은 취소해 줘')
        self.callback(notification, 'approve')
        self.assertEqual(self.job(job_id)['status'], 'failed')
        self.assertFalse(self.service.run_one())

    def test_an_explicit_cancel_of_the_stopped_work_withdraws_the_continuation(self):
        job_id, notification, _ = self.stop_at_sharing()
        cancelled, text = self.service.cancel_focused_work(self.job(job_id), OWNER)
        self.assertTrue(cancelled)
        self.assertIn('문서 공유를 승인해도 이어서 처리하지 않습니다', text)
        self.callback(notification, 'approve')
        self.assertEqual(self.job(job_id)['status'], 'failed')

    def test_supersede_withdraws_the_continuation(self):
        job_id, notification, _ = self.stop_at_sharing()
        self.service.supersede_pending_handoffs(owner_id=OWNER)
        self.callback(notification, 'approve')
        self.assertEqual(self.job(job_id)['status'], 'failed')

    def test_the_continuation_expires(self):
        clock = Clock()
        job_id, notification, _ = self.stop_at_sharing(clock)
        clock.now += 3601
        self.callback(notification, 'approve')
        self.assertFalse(self.service.document_boundary()['requires_approval'], 'sharing itself is still approved')
        self.assertEqual(self.job(job_id)['status'], 'failed')
        self.assertFalse(self.service.run_one())

    def test_a_resumed_turn_that_attempted_an_effect_is_not_continued(self):
        job_id, notification, sent = self.stop_at_sharing(
            resumed_plan=[('save_note', {'content': '계약서'}), ('find_files', {'query': '계약서'})])
        self.assertNotEqual(sent, [LOCAL_DOCUMENT_APPROVAL_TEXT])
        status = self.job(job_id)['status']
        self.callback(notification, 'approve')
        self.assertEqual(self.job(job_id)['status'], status)
        self.assertFalse(self.service.run_one(), 'the note is never saved twice')

    def test_an_ordinary_failed_work_is_not_requeued_by_document_approval(self):
        contracts = self.folder('contracts', {'renewal.txt': '계약서'})
        self.service.save_roots({'paths': [str(contracts)]})
        self.plan = [('find_files', {'query': '계약서'})]
        job_id, _ = self.ask('계약서 찾아줘')
        self.assertEqual(self.job(job_id)['status'], 'failed')
        self.assertFalse(self.service.resume_after_document_approval(job_id))
        self.assertEqual(self.job(job_id)['status'], 'failed')


class OutputFolderHandoffTests(HandoffTestCase):
    REQUEST = '/workspace-summary 회의 :: 회의 결과 브리프'

    def test_result_write_is_asked_separately_and_only_when_a_save_is_needed(self):
        minutes = self.folder('minutes', {'meeting.md': '회의 결정: 출시일 확정'})
        # Only the read side is configured; the save needs a result folder.
        _path, commit = FileWorkspace(self.store).plan_grant('reference', str(minutes))
        commit()
        self.assertFalse(self.store.config('file_workspace', {}).get('workspace'))
        job_id, bubbles = self.ask(self.REQUEST)
        self.assertEqual(self.job(job_id)['status'], 'awaiting_connection')
        self.assertEqual(len(bubbles), 1)
        self.assertIn('결과 파일을 저장할 폴더', bubbles[0])
        self.assertIn('새 결과 파일을 만드는 것만', bubbles[0])
        self.assertIn('Mac에서 계속', bubbles[0])
        self.assert_telegram_safe(bubbles[0])
        request = self.pending()[0]
        self.assertEqual(request['authority'], 'write')
        self.assertEqual(request['preview'], LOCAL_AUTHORITY_PREVIEWS[LOCAL_RESULT_WRITE])
        self.assertNotEqual(request['preview'], LOCAL_AUTHORITY_PREVIEWS[LOCAL_FOLDER_READ])

        results = self.folder('results')
        self.picked = str(minutes)
        with self.assertRaises(ValueError):  # overlapping the read-only original is refused
            self.service.select_local_folder({'handoff_id': request['handoff_id']})
        self.picked = str(results)
        self.service.select_local_folder({'handoff_id': request['handoff_id']})
        approved = self.service.approve_local_folder({'handoff_id': request['handoff_id']})
        self.assertEqual(approved['authority'], 'write')
        workspace = self.store.config('file_workspace', {})
        self.assertEqual(workspace['workspace'], str(results.resolve()))
        self.assertEqual([ref['path'] for ref in workspace['references']], [str(minutes.resolve())])
        # A result-write grant never becomes an AI read folder.
        self.assertEqual(self.roots(), [])

        self.text = '결정: 출시일 확정. 다음 단계: 공지.'
        self.assertTrue(self.service.run_one())
        self.assertEqual(self.job(job_id)['status'], 'succeeded', self.job(job_id).get('error'))
        saved = list(results.iterdir())
        self.assertEqual(len(saved), 1)
        self.assertEqual((minutes / 'meeting.md').read_text(encoding='utf-8'), '회의 결정: 출시일 확정')
        self.assertFalse(self.service.run_one())

    def test_a_result_folder_set_in_settings_meanwhile_is_not_silently_replaced(self):
        minutes = self.folder('minutes', {'meeting.md': '회의 결정'})
        FileWorkspace(self.store).plan_grant('reference', str(minutes))[1]()
        job_id, _ = self.ask(self.REQUEST)
        self.picked = str(self.folder('chosen'))
        request = self.pending()[0]
        self.service.select_local_folder({'handoff_id': request['handoff_id']})
        settings_choice = self.folder('settings-choice')
        FileWorkspace(self.store).plan_grant('workspace', str(settings_choice))[1]()
        before = len(self.sent)
        approved = self.service.approve_local_folder({'handoff_id': request['handoff_id']})
        self.assertTrue(approved['kept_existing'])
        self.assertEqual(self.store.config('file_workspace', {})['workspace'], str(settings_choice.resolve()))
        self.assertEqual(self.sent[before:], [LOCAL_KEPT_WORKSPACE_TEXT])
        self.assertEqual(self.job(job_id)['status'], 'queued')

    def test_removing_the_original_meanwhile_still_grants_the_chosen_result_folder(self):
        minutes = self.folder('minutes', {'meeting.md': '회의 결정'})
        FileWorkspace(self.store).plan_grant('reference', str(minutes))[1]()
        job_id, _ = self.ask(self.REQUEST)
        chosen = self.folder('chosen')
        self.picked = str(chosen)
        request = self.pending()[0]
        self.service.select_local_folder({'handoff_id': request['handoff_id']})
        self.store.put('file_workspace', {**self.store.config('file_workspace', {}), 'references': []})
        before = len(self.sent)
        approved = self.service.approve_local_folder({'handoff_id': request['handoff_id']})
        self.assertFalse(approved['kept_existing'])
        self.assertEqual(self.store.config('file_workspace', {})['workspace'], str(chosen.resolve()))
        self.assertNotIn(LOCAL_KEPT_WORKSPACE_TEXT, self.sent[before:])
        self.service.run_one()
        # The request now lacks only its original; it asks for that read next.
        self.assertEqual(self.job(job_id)['status'], 'awaiting_connection')
        self.assertEqual(self.pending()[0]['authority'], 'read')

    def test_read_then_write_are_two_distinct_approvals_for_one_request(self):
        minutes = self.folder('minutes', {'meeting.md': '회의 결정: 출시일 확정'})
        results = self.folder('results')
        job_id, bubbles = self.ask(self.REQUEST)
        self.assertIn('정리할 원본 폴더를 읽는 권한', bubbles[0])
        self.assertEqual(self.pending()[0]['authority'], 'read')
        self.approve_picked(minutes)
        self.assertIsNone(self.store.config('file_workspace', {}).get('workspace'))
        self.service.run_one()
        self.assertEqual(self.job(job_id)['status'], 'awaiting_connection')
        self.assertEqual(self.pending()[0]['authority'], 'write')
        self.approve_picked(results)
        self.service.run_one()
        self.assertEqual(self.job(job_id)['status'], 'succeeded', self.job(job_id).get('error'))
        self.assertEqual(len(list(results.iterdir())), 1)


class LocalGrantPendingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parent))
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name) / 'data')
        self.clock = Clock()
        self.pending = LocalGrantPending(self.store, clock=self.clock)
        self.work = '11111111-1111-4111-8111-111111111111'

    def reason(self, call):
        with self.assertRaises(ConnectorContractError) as raised:
            call()
        return raised.exception.reason

    def test_claim_is_single_use_owner_bound_and_scope_exact(self):
        handle = self.pending.issue(OWNER, self.work, LOCAL_FOLDER_READ, ('folder:read',))
        self.assertEqual(self.reason(lambda: self.pending.claim(handle.token, 'telegram:1', LOCAL_FOLDER_READ,
                                                               ('folder:read',), 'h1')), 'wrong_owner')
        self.assertEqual(self.reason(lambda: self.pending.claim(handle.token, OWNER, LOCAL_FOLDER_READ,
                                                               ('folder:create-result',), 'h1')), 'scope_mismatch')
        self.assertEqual(self.reason(lambda: self.pending.claim(handle.token, OWNER, LOCAL_RESULT_WRITE,
                                                               ('folder:create-result',), 'h1')), 'invalid_resume')
        self.assertEqual(self.pending.claim(handle.token, OWNER, LOCAL_FOLDER_READ, ('folder:read',), 'h1').work_id,
                         self.work)
        self.assertEqual(self.reason(lambda: self.pending.claim(handle.token, OWNER, LOCAL_FOLDER_READ,
                                                               ('folder:read',), 'h2')), 'resume_claimed')
        self.pending.complete(handle.token, OWNER, LOCAL_FOLDER_READ, 'h1')
        self.assertEqual(self.reason(lambda: self.pending.claim(handle.token, OWNER, LOCAL_FOLDER_READ,
                                                               ('folder:read',), 'h1')), 'replayed_resume')
        self.assertEqual(self.reason(lambda: self.pending.claim('not-a-token', OWNER, LOCAL_FOLDER_READ,
                                                               ('folder:read',), 'h1')), 'invalid_resume')

    def test_expiry_and_no_content_in_durable_state(self):
        handle = self.pending.issue(OWNER, self.work, LOCAL_RESULT_WRITE, ('folder:create-result',))
        self.clock.now += 3600
        self.assertEqual(self.reason(lambda: self.pending.claim(handle.token, OWNER, LOCAL_RESULT_WRITE,
                                                               ('folder:create-result',), 'h1')), 'expired_resume')
        raw = json.dumps(self.store.secret('local_authority_pending'))
        self.assertNotIn(handle.token, raw)
        self.assertNotIn(OWNER, raw)
        self.assertEqual(self.reason(lambda: self.pending.issue(OWNER, self.work, LOCAL_FOLDER_READ,
                                                               ('folder:create-result',))), 'scope_mismatch')


class PickerTests(unittest.TestCase):
    def test_prompt_is_an_argument_and_cancel_is_none(self):
        calls = []

        class Result:
            def __init__(self, code, out='', err=''):
                self.returncode, self.stdout, self.stderr = code, out, err

        def runner(command, **kwargs):
            calls.append(command)
            return Result(0, '/Volumes/Work/계약서/\n')

        prompt = '"; do shell script "x'
        self.assertEqual(local_folder_picker.choose_folder(prompt, runner=runner), '/Volumes/Work/계약서/')
        self.assertEqual(calls[0][-1], prompt)
        self.assertNotIn(prompt, ' '.join(calls[0][:-1]))
        self.assertIsNone(local_folder_picker.choose_folder('p', runner=lambda c, **k: Result(1, '', 'User canceled. (-128)')))
        with self.assertRaises(local_folder_picker.FolderPickerUnavailable):
            local_folder_picker.choose_folder('p', runner=lambda c, **k: Result(1, '', 'execution error'))


class HttpSurfaceTests(HandoffTestCase):
    def serve(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.service, (MOBILE_HOST,), 'pairing-token'))
        thread = threading.Thread(target=server.serve_forever)
        thread.start()

        def shutdown():
            server.shutdown(); thread.join(); server.server_close()
        self.addCleanup(shutdown)
        self.store.claim(self.store.bootstrap.read_text(), 'long-password-test')
        return f'http://127.0.0.1:{server.server_port}', {'Cookie': 'agentos_session=' + self.store.local_session()}

    def call(self, base, path, headers, body=None):
        data = None if body is None else json.dumps(body).encode()
        request = Request(base + path, data=data, headers={**headers, 'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def test_mobile_or_tunnel_cannot_choose_or_approve_but_the_mac_can(self):
        job_id, _ = self.park_read()
        base, session = self.serve()
        contracts = self.folder('contracts')
        mobile = {**session, 'Host': MOBILE_HOST}
        status, listing = self.call(base, '/api/folder-requests', mobile)
        self.assertEqual(status, 200)
        self.assertFalse(listing['local_surface'])
        handoff = listing['requests'][0]['handoff_id']
        for action, body in (('select', {'handoff_id': handoff, 'path': str(contracts)}),
                             ('approve', {'handoff_id': handoff})):
            status, reply = self.call(base, f'/api/folder-requests/{action}', mobile, body)
            self.assertEqual(status, 403)
            self.assertIn('Mac에서 계속', reply['error'])
        self.assertEqual(self.roots(), [])
        self.assertEqual(self.job(job_id)['status'], 'awaiting_connection')

        status, listing = self.call(base, '/api/folder-requests', session)
        self.assertTrue(listing['local_surface'])
        status, selected = self.call(base, '/api/folder-requests/select', session,
                                     {'handoff_id': handoff, 'path': str(contracts)})
        self.assertEqual((status, selected['state']), (200, 'selected'))
        status, approved = self.call(base, '/api/folder-requests/approve', session, {'handoff_id': handoff})
        self.assertEqual((status, approved['state']), (200, 'approved'))
        self.assertEqual(self.roots(), [str(contracts.resolve())])
        status, replay = self.call(base, '/api/folder-requests/approve', session, {'handoff_id': handoff})
        self.assertEqual(status, 409)
        self.assertEqual(replay['reason'], 'no_pending_work')

    def test_an_unauthenticated_caller_is_refused(self):
        self.park_read()
        base, _session = self.serve()
        status, _ = self.call(base, '/api/folder-requests', {})
        self.assertEqual(status, 401)
        status, _ = self.call(base, '/api/folder-requests/deny', {}, {'handoff_id': 'x'})
        self.assertEqual(status, 401)


class FilesPaneTests(unittest.TestCase):
    """The 파일 · 저장 pane carries the owner-local approval surface."""

    WEB = Path(__file__).parents[1] / 'src' / 'personal_agent' / 'web'

    def test_pending_requests_render_before_folder_management(self):
        html = (self.WEB / 'index.html').read_text(encoding='utf-8')
        pane = html[html.index('id="settings-files"'):]
        self.assertLess(pane.index('id="folder-requests"'), pane.index('id="roots-heading"'))
        self.assertIn('id="folder-requests-feedback" class="field-feedback" role="status" aria-live="polite"', pane)

    def test_the_browser_sends_only_the_opaque_request_id_to_approve(self):
        app = (self.WEB / 'app.js').read_text(encoding='utf-8')
        self.assertIn("api('/api/folder-requests/'+action,{handoff_id:request.handoff_id,...(body||{})})", app)
        self.assertIn("folderRequestAction(event.currentTarget,'approve',request,null,", app)
        self.assertIn('void loadFolderRequests();', app)
        # A remote (tunnel/phone) surface offers only "continue on the Mac" and decline.
        self.assertIn("if(!data.local_surface){actions.append(folderRequestDeny(request))", app)


if __name__ == '__main__':
    unittest.main()

"""PA1-INT-01 WU4: the owner's route to a pending MemoryCandidate, and the
cause of a refused run.

Two gaps that the WU3 end-to-end acceptance surfaced, both on the wiring #394
owns rather than in any child contract.

**J6.** #386 requires, verbatim, that "the owner has an inspect/approve/reject
path for pending candidates".  ``QuickStore`` implements that path and
``MemoryService`` wraps the whole of it, but before this module nothing
reached either one: ``GET /api/personal-space`` reported
``memory_candidate_count`` so the owner could *see* a candidate, and
``DELETE /api/personal-space/<kind>/<id>`` accepted only ``memories`` and
``results``, so the owner could not act on one.  J6 was therefore not met.
The tests below walk the owner path through the shipped HTTP handler:
inspect, request approval, accept, and reject - plus the refusals that make
"approve" an approval rather than a button.

**The refusal with no cause.**  ``run_agent`` can return a model answer *and*
``outcome='failed'``: a tool was refused, the model wrote text anyway.  The
job row kept that text in ``response`` and left ``error`` NULL, so the task
card said '확인 필요' with nothing after it and the reason survived only in
``tool_events``.  This repository requires failures to stay explicit and
owner-visible, so the last test class checks the cause now reaches the
owner-visible task surface - and that it reaches nowhere it did not already.

**Evidence class: local, offline, fixture-transport integration.**  The
service is built by ``configured_service``, the production constructor, over
an empty data directory, and every owner action enters through a real HTTP
request to ``make_handler``.  The only injected seam is the outbound model
transport.  Nothing here is evidence about a live provider.
"""
import json
import tempfile
import threading
import time
import unittest
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor

from personal_agent.providers import ModelAdapter
from personal_agent.quickstart import configured_service, make_handler
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore

OWNER_PASSWORD = 'a-long-wu4-owner-password'
MODEL_ANSWER = '방금 이야기만 정리했습니다.'

#: A prompt that is deliberately *not* an explicit owner memory request, so
#: `explicit_memory_request` issues no approval for the turn and a model
#: `save_memory` call can only become a MemoryCandidate.
NO_SAVE_PROMPT = '이건 기억하지 마. 그냥 방금 이야기만 정리해 줘'
CANDIDATE_KEY = 'inferred-preference'
CANDIDATE_CONTENT = '모델이 추론한 값'


class _OwnerSurface(unittest.TestCase):
    """A claimed owner, a connected model, and the shipped HTTP handler."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / 'data'
        self.store = QuickStore(str(self.data))
        self.calls = []
        # Empty means "answer with text"; a list means "ask for these tools
        # in order, then answer".
        self.model_plan = []
        self.model_text = MODEL_ANSWER

        self.service = self.boot()
        self.base = self.serve(self.service)
        self.client = build_opener(HTTPCookieProcessor(CookieJar()))
        self.web('/api/claim', {'code': self.store.bootstrap.read_text(),
                                'password': OWNER_PASSWORD})
        self.connect_model()

    # -- harness ----------------------------------------------------------
    def transport(self, url, body, headers=None, timeout=60):
        """The one outbound seam: the model provider."""
        self.calls.append((url, body))
        if url.endswith('/chat/completions'):
            probing = any((tool.get('function', {}).get('name') or tool.get('name'))
                          == 'agentos_connection_probe' for tool in body.get('tools', []))
            if probing:
                return {'model': 'verified/model:free', 'choices': [{'message': {'tool_calls': [
                    {'id': 'probe', 'function': {'name': 'agentos_connection_probe',
                                                 'arguments': '{}'}}]}}]}
            done = len([m for m in body['messages'] if m.get('role') == 'tool'])
            if done < len(self.model_plan):
                name, arguments = self.model_plan[done]
                return {'choices': [{'message': {'tool_calls': [
                    {'id': f'call-{done}', 'type': 'function',
                     'function': {'name': name, 'arguments': arguments}}]}}]}
            return {'choices': [{'message': {'content': self.model_text}}]}
        raise AssertionError('unexpected outbound call: ' + url)

    def boot(self, store=None):
        """Build the service exactly as the shipped entry point builds it."""
        service = configured_service(self.store if store is None else store, {})
        service.adapter = ModelAdapter(self.transport)
        return service

    def serve(self, service):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever)
        thread.start()

        def shutdown():
            server.shutdown()
            thread.join()
            server.server_close()

        self.addCleanup(shutdown)
        return 'http://127.0.0.1:' + str(server.server_port)

    def web(self, path, body=None, opener=None, method=None):
        """One authenticated browser request against the shipped handler."""
        request = Request(self.base + path,
                          data=json.dumps(body).encode() if body is not None else None,
                          headers={'Content-Type': 'application/json'} if body is not None else {},
                          method=method)
        with (opener or self.client).open(request, timeout=5) as response:
            raw = response.read()
            try:
                return json.loads(raw)
            except ValueError:
                return raw

    def refused(self, path, body=None, opener=None, method=None):
        """Assert one request is refused, and return its status and message."""
        with self.assertRaises(HTTPError) as error:
            self.web(path, body, opener=opener, method=method)
        raw = error.exception.read()
        try:
            detail = json.loads(raw).get('error', '')
        except ValueError:
            detail = ''
        return error.exception.code, detail

    def connect_model(self):
        draft = {'provider': 'compatible', 'endpoint': 'https://model.test/v1',
                 'model': 'test-model', 'api_key': 'sk-wu4-fixture-key'}
        tested = self.web('/api/model/test', draft)
        self.assertTrue(tested['ok'])
        self.web('/api/model', {**draft, 'test_proof': tested['test_proof']})

    def ask(self, message, service=None, store=None):
        """One owner turn through POST /api/chat and the shipped worker."""
        service = service or self.service
        store = store or self.store
        self.turn = getattr(self, 'turn', 0) + 1
        job_id = self.web('/api/chat', {'message': message,
                                        'request_key': f'wu4-turn-{self.turn}'})['id']
        for _ in range(6):
            with store.db() as db:
                # Only skips the Telegram task-card cancellation grace.
                db.execute("UPDATE jobs SET created=? WHERE status='queued'",
                           (time.time() - 4,))
            if not service.run_one():
                break
        return job_id

    def pending_candidate(self):
        """Produce one model-originated, unapproved MemoryCandidate."""
        self.model_plan = [('save_memory', json.dumps(
            {'memory_key': CANDIDATE_KEY, 'content': CANDIDATE_CONTENT},
            ensure_ascii=False))]
        self.model_text = MODEL_ANSWER
        job_id = self.ask(NO_SAVE_PROMPT)
        self.model_plan = []
        self.assertEqual(self.store.job(job_id)['status'], 'succeeded')
        # C5: the model's write did not become canonical Memory.
        self.assertEqual(self.store.memories(), [])
        self.assertEqual(self.web('/api/personal-space')['memory_candidate_count'], 1)
        return job_id

    def candidates(self):
        return self.web('/api/personal-space/memory-candidates')

    def act(self, **body):
        return self.web('/api/personal-space/memory-candidates/request', body)


class OwnerMemoryCandidatePath(_OwnerSurface):
    """J6: inspect / approve / reject a pending candidate, end to end."""

    def test_the_owner_can_inspect_a_pending_candidate_before_deciding(self):
        self.pending_candidate()

        listed = self.candidates()
        self.assertEqual(listed['state'], 'pending')
        self.assertEqual(len(listed['candidates']), 1)
        row = listed['candidates'][0]
        # Inspectable: the owner reads the actual proposed value, its key, and
        # the digest any later decision has to name.
        self.assertEqual(row['memory_key'], CANDIDATE_KEY)
        self.assertEqual(row['content'], CANDIDATE_CONTENT)
        self.assertEqual(row['state'], 'pending')
        self.assertEqual(row['content_digest'],
                         self.store.memory_digest(CANDIDATE_KEY, CANDIDATE_CONTENT))
        # The Work binding travels as an opaque reference, never a raw id.
        self.assertTrue(row['work_ref'].startswith('workref:'))
        self.assertNotIn(row['work_ref'][8:], json.dumps(self.store.jobs()))
        # The read declares itself as carrying private owner content.
        self.assertTrue(listed['private_content_included'])

        # The work-bound single read agrees with the listing.
        inspected = self.act(operation='inspect', id=row['id'], work_ref=row['work_ref'])
        self.assertEqual(inspected['content'], CANDIDATE_CONTENT)
        self.assertEqual(inspected['content_digest'], row['content_digest'])

    def test_approving_a_candidate_makes_it_canonical_memory_across_restart(self):
        self.pending_candidate()
        row = self.candidates()['candidates'][0]

        issued = self.act(operation='request-approval', id=row['id'],
                          work_ref=row['work_ref'], content_digest=row['content_digest'])
        self.assertEqual(issued['action'], 'accept-candidate')
        self.assertEqual(issued['subject_id'], row['id'])
        self.assertEqual(issued['content_digest'], row['content_digest'])
        self.assertTrue(issued['approval_token'])
        # Issuing an approval is not the write: Memory is still empty.
        self.assertEqual(self.store.memories(), [])
        self.assertEqual(self.web('/api/personal-space')['memory_candidate_count'], 1)

        accepted = self.act(operation='accept', id=row['id'], work_ref=row['work_ref'],
                            content_digest=row['content_digest'],
                            approval_token=issued['approval_token'])
        self.assertEqual(accepted['memory_key'], CANDIDATE_KEY)
        self.assertEqual(accepted['content'], CANDIDATE_CONTENT)
        self.assertEqual(accepted['state'], 'current')

        # Owner-visible: it left the candidate queue and entered Memory.
        space = self.web('/api/personal-space')
        self.assertEqual(space['memory_candidate_count'], 0)
        self.assertIn(CANDIDATE_CONTENT, [item['content'] for item in space['memories']])
        self.assertEqual(self.candidates()['candidates'], [])
        self.assertEqual([item['memory_key'] for item
                          in self.web('/api/personal-records?filter=memory')['items']],
                         [CANDIDATE_KEY])

        # Durable: a second shipped service over the same directory agrees.
        restarted_store = QuickStore(str(self.data))
        restarted = self.boot(restarted_store)
        restarted.store.recover()
        self.assertEqual([item['content'] for item in restarted_store.memories()],
                         [CANDIDATE_CONTENT])
        self.assertEqual(restarted_store.memory_candidates(), [])

    def test_rejecting_a_candidate_durably_removes_it(self):
        self.pending_candidate()
        row = self.candidates()['candidates'][0]

        rejected = self.act(operation='reject', id=row['id'], work_ref=row['work_ref'],
                            content_digest=row['content_digest'])
        self.assertEqual(rejected['state'], 'rejected')
        # The rejected proposal keeps no value: content and key are cleared.
        self.assertEqual(rejected['content'], '')
        self.assertEqual(rejected['memory_key'], '')

        # Owner-visible: gone from the queue, and never canonical Memory.
        self.assertEqual(self.web('/api/personal-space')['memory_candidate_count'], 0)
        self.assertEqual(self.candidates()['candidates'], [])
        self.assertEqual(self.store.memories(), [])
        self.assertEqual(self.web('/api/personal-records?filter=memory')['items'], [])

        # A rejected candidate cannot be approved afterwards.
        code, _ = self.refused('/api/personal-space/memory-candidates/request',
                               {'operation': 'request-approval', 'id': row['id'],
                                'work_ref': row['work_ref'],
                                'content_digest': row['content_digest']})
        self.assertEqual(code, 400)

        # Durable across restart, and still not Memory.
        restarted_store = QuickStore(str(self.data))
        self.boot(restarted_store).store.recover()
        self.assertEqual(restarted_store.memories(), [])
        self.assertEqual(restarted_store.memory_candidates(), [])
        decided = restarted_store.memory_candidates(include_decided=True)
        self.assertEqual([item['state'] for item in decided], ['rejected'])
        self.assertEqual(decided[0]['content'], '')


class OwnerMemoryCandidateAuthority(_OwnerSurface):
    """The refusals that make the J6 route an approval path, not a button."""

    def test_the_candidate_routes_refuse_a_caller_without_the_owner_session(self):
        self.pending_candidate()
        row = self.candidates()['candidates'][0]
        anonymous = build_opener(HTTPCookieProcessor(CookieJar()))

        code, _ = self.refused('/api/personal-space/memory-candidates', opener=anonymous)
        self.assertEqual(code, 401)
        for body in ({'operation': 'list'},
                     {'operation': 'inspect', 'id': row['id'], 'work_ref': row['work_ref']},
                     {'operation': 'request-approval', 'id': row['id'],
                      'work_ref': row['work_ref'], 'content_digest': row['content_digest']},
                     {'operation': 'reject', 'id': row['id'], 'work_ref': row['work_ref'],
                      'content_digest': row['content_digest']}):
            with self.subTest(operation=body['operation']):
                code, _ = self.refused('/api/personal-space/memory-candidates/request',
                                       body, opener=anonymous)
                self.assertEqual(code, 401)
        # Nothing was decided by any of those attempts.
        self.assertEqual(self.web('/api/personal-space')['memory_candidate_count'], 1)
        self.assertEqual(self.store.memories(), [])

    def test_approval_is_refused_without_the_binding_the_store_requires(self):
        self.pending_candidate()
        row = self.candidates()['candidates'][0]
        digest = row['content_digest']
        issued = self.act(operation='request-approval', id=row['id'],
                          work_ref=row['work_ref'], content_digest=digest)
        token = issued['approval_token']
        other = 'f' * 64

        attempts = {
            'a bare id, with no digest and no token':
                {'operation': 'accept', 'id': row['id'], 'work_ref': row['work_ref']},
            'the right digest but no approval token':
                {'operation': 'accept', 'id': row['id'], 'work_ref': row['work_ref'],
                 'content_digest': digest},
            'a token that was never issued':
                {'operation': 'accept', 'id': row['id'], 'work_ref': row['work_ref'],
                 'content_digest': digest, 'approval_token': 'not-an-issued-token'},
            'a digest that is not the inspected content':
                {'operation': 'accept', 'id': row['id'], 'work_ref': row['work_ref'],
                 'content_digest': other, 'approval_token': token},
            'a work reference that did not produce the candidate':
                {'operation': 'accept', 'id': row['id'], 'work_ref': 'workref:' + other,
                 'content_digest': digest, 'approval_token': token},
            'a candidate id the owner never inspected':
                {'operation': 'accept', 'id': 'no-such-candidate',
                 'work_ref': row['work_ref'], 'content_digest': digest,
                 'approval_token': token},
        }
        for label, body in attempts.items():
            with self.subTest(label):
                code, message = self.refused(
                    '/api/personal-space/memory-candidates/request', body)
                self.assertEqual(code, 400)
                self.assertTrue(message)
                # Refused, not silently accepted: still pending, still not Memory.
                self.assertEqual(self.store.memories(), [])
                self.assertEqual(
                    self.web('/api/personal-space')['memory_candidate_count'], 1)

        # The exact inspected binding still works afterwards, so the refusals
        # above rejected the binding rather than the candidate.
        self.assertEqual(self.act(operation='accept', id=row['id'],
                                  work_ref=row['work_ref'], content_digest=digest,
                                  approval_token=token)['content'], CANDIDATE_CONTENT)

    def test_rejection_is_refused_without_the_inspected_digest(self):
        self.pending_candidate()
        row = self.candidates()['candidates'][0]
        for label, body in {
            'no digest at all': {'operation': 'reject', 'id': row['id'],
                                 'work_ref': row['work_ref']},
            'a digest that is not the inspected content':
                {'operation': 'reject', 'id': row['id'], 'work_ref': row['work_ref'],
                 'content_digest': 'f' * 64},
            'no work reference': {'operation': 'reject', 'id': row['id'],
                                  'content_digest': row['content_digest']},
        }.items():
            with self.subTest(label):
                code, _ = self.refused(
                    '/api/personal-space/memory-candidates/request', body)
                self.assertEqual(code, 400)
                self.assertEqual(
                    self.web('/api/personal-space')['memory_candidate_count'], 1)

    def test_an_unknown_candidate_operation_is_refused(self):
        code, _ = self.refused('/api/personal-space/memory-candidates/request',
                               {'operation': 'delete-everything'})
        self.assertEqual(code, 400)

    def test_an_approval_token_is_single_use(self):
        self.pending_candidate()
        row = self.candidates()['candidates'][0]
        issued = self.act(operation='request-approval', id=row['id'],
                          work_ref=row['work_ref'], content_digest=row['content_digest'])
        accepted = self.act(operation='accept', id=row['id'], work_ref=row['work_ref'],
                            content_digest=row['content_digest'],
                            approval_token=issued['approval_token'])
        # Replaying the same consumed approval returns the same Memory row
        # rather than writing a second one.
        replayed = self.act(operation='accept', id=row['id'], work_ref=row['work_ref'],
                            content_digest=row['content_digest'],
                            approval_token=issued['approval_token'])
        self.assertEqual(replayed['id'], accepted['id'])
        self.assertEqual(len(self.store.memories()), 1)


class RefusedRunShowsItsCause(_OwnerSurface):
    """A failed run names why, on the surface the owner actually reads."""

    def refused_run(self):
        """One turn whose tool is refused and whose model answers anyway."""
        # A real capability refusal: an external model may not receive a
        # connected-document excerpt until the owner approves document
        # sharing, so `read_file` is denied before it resolves any path.
        self.model_plan = [('read_file', json.dumps(
            {'root_id': 'not-a-connected-folder', 'path': 'secret.md'}))]
        self.model_text = '해당 파일을 읽지 못했습니다.'
        job_id = self.ask('연결된 폴더의 문서를 읽어서 정리해 줘')
        self.model_plan = []
        return self.store.job(job_id)

    def test_a_refused_tool_puts_its_cause_on_the_owner_task_surface(self):
        job = self.refused_run()
        # The shape WU3 hit: failed, but the model's text is the response.
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(job['response'], '해당 파일을 읽지 못했습니다.')

        # The cause now exists on the job row instead of only in tool_events.
        self.assertIsNotNone(job['error'])
        self.assertIn('read_file', job['error'])
        self.assertIn('연결 문서 발췌문을 외부 AI에 전달하려면 설정에서 문서 공유를 승인하세요.', job['error'])

        # And it reaches the owner-visible task card, which previously showed
        # '확인 필요' with no cause at all.
        detail = self.web('/api/tasks/' + job['id'])['selected']
        self.assertEqual(detail['status_label'], '확인 필요')
        self.assertEqual(detail['error'], job['error'])
        self.assertIn('연결 문서 발췌문을 외부 AI에 전달하려면 설정에서 문서 공유를 승인하세요.', detail['error'])

    def test_the_cause_matches_the_tool_event_actually_observed(self):
        """It is promoted from observed events, never composed from nothing."""
        job = self.refused_run()
        observed = [event for event in self.store.task_events(job['id'])
                    if event['status'] == 'failed' and event['tool'] != 'model']
        self.assertEqual([event['tool'] for event in observed], ['read_file'])
        self.assertIn(observed[0]['trace']['error'], job['error'])

    def test_the_cause_names_only_the_tool_that_actually_failed(self):
        """A tool that ran fine is not listed as one that did not.

        Found by mutation: a version that collected every tool event rather
        than only the failed ones passed every other test here, because the
        one refused run had a single tool which both ran and failed.
        """
        self.model_plan = [('list_notes', '{}'),
                           ('read_file', json.dumps({'root_id': 'not-a-connected-folder',
                                                     'path': 'secret.md'}))]
        self.model_text = '메모만 확인했습니다.'
        job = self.store.job(self.ask('메모를 보고 연결 문서도 읽어서 정리해 줘'))
        self.model_plan = []

        # One tool succeeded and one was refused, so the run is partial.
        self.assertEqual(job['status'], 'partial')
        observed = {(event['tool'], event['status'])
                    for event in self.store.task_events(job['id'])}
        self.assertIn(('list_notes', 'succeeded'), observed)
        self.assertIn(('read_file', 'failed'), observed)

        self.assertIn('read_file', job['error'])
        self.assertNotIn('list_notes', job['error'])
        self.assertEqual(self.web('/api/tasks/' + job['id'])['selected']['error'],
                         job['error'])

    def test_a_run_that_recovers_from_a_refused_call_carries_no_cause(self):
        """A failed tool event is not by itself a failed run.

        Found by mutation: restricting the cause to a failed outcome looked
        untested, because the only successful run asserted on had no tool
        event at all.  `run_agent` clears an invalid call once the same tool
        is called correctly, so this run records a failure and still
        succeeds - and a succeeded run must not show a cause.
        """
        self.model_plan = [('list_notes', json.dumps({'unsupported': 'argument'})),
                           ('list_notes', '{}')]
        self.model_text = MODEL_ANSWER
        job = self.store.job(self.ask('메모 목록을 정리해 줘'))
        self.model_plan = []

        self.assertEqual([event['tool'] for event in self.store.task_events(job['id'])
                          if event['status'] == 'failed' and event['tool'] != 'model'],
                         ['list_notes'])
        self.assertEqual(job['status'], 'succeeded')
        self.assertIsNone(job['error'])
        self.assertIsNone(self.web('/api/tasks/' + job['id'])['selected']['error'])

    def test_a_successful_run_carries_no_cause(self):
        self.model_text = MODEL_ANSWER
        job_id = self.ask('안녕하세요, 오늘 일정 정리 좀 도와줘')
        job = self.store.job(job_id)
        self.assertEqual(job['status'], 'succeeded')
        self.assertIsNone(job['error'])
        self.assertIsNone(self.web('/api/tasks/' + job_id)['selected']['error'])

    def test_the_cause_does_not_reach_telegram_when_an_answer_exists(self):
        """The new text goes to the web task surface only.

        `deliver_one` reads `error` only when `response` is empty, and this
        failure shape always has a response, so promoting the cause adds no
        text to the one terminal Telegram bubble.
        """
        job = self.refused_run()
        self.assertEqual(AgentService.telegram_result_text(job['response'], job['error']),
                         job['response'])
        self.assertNotIn(job['error'],
                         AgentService.telegram_result_text(job['response'], job['error']))


class FailureCauseRedaction(unittest.TestCase):
    """The promoted cause is redacted the same way the event surface is.

    A real capability refusal message is written to be path-free, so this
    exercises the helper directly rather than pretending a tool produced a
    leaking string.
    """

    def test_credentials_and_host_paths_are_redacted_out_of_the_cause(self):
        cause = AgentService._failure_cause([
            ('read_file', '/Users/owner/private/taxes.pdf 를 읽을 수 없습니다.'),
            ('web_search', 'Bearer sk-live-abcdef123456 was rejected'),
        ])
        self.assertNotIn('/Users/owner', cause)
        self.assertNotIn('sk-live-abcdef123456', cause)
        self.assertIn('[경로 가림]', cause)
        self.assertIn('[가림]', cause)

    def test_no_observed_failure_means_no_invented_cause(self):
        self.assertIsNone(AgentService._failure_cause([]))

    def test_a_failure_with_no_readable_reason_still_names_the_tool(self):
        self.assertIn('read_file', AgentService._failure_cause([('read_file', None)]))

    def test_repeated_identical_failures_are_reported_once(self):
        cause = AgentService._failure_cause([('web_search', '거부되었습니다.')] * 3)
        self.assertEqual(cause.count('web_search'), 1)

    def test_the_cause_is_bounded(self):
        self.assertLessEqual(
            len(AgentService._failure_cause([('read_file', 'x' * 5000)])), 400)


if __name__ == '__main__':
    unittest.main()

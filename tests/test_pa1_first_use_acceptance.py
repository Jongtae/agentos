"""PA1-INT-01: the clean synthetic first-use end-to-end acceptance.

EPIC-PA1's children each proved their own slice against their own fixture.
What no child could prove is that the slices *compose*: that a request
entering where a Telegram update or a browser POST actually enters comes out
the other end having traversed the same application and service objects the
shipped product uses.  #394's acceptance list says so twice - "clean
synthetic first-use E2E traverses the same application/service boundaries
used by Telegram/web management", and "no child-only fixture is misreported
as integrated/live evidence" - and the second criterion is the reason this
module exists separately from every child suite.

So the rule this file holds itself to is narrow and mechanical:

* the service is built by ``configured_service`` - the shipped production
  constructor - from an empty data directory, never by calling
  ``AgentService(...)`` with hand-picked adapters;
* every owner action enters through a real entry point: an HTTP request to
  the handler returned by ``make_handler``, or ``AgentService.poll_telegram``
  /``run_one``/``deliver_one``, which is the exact loop ``AgentService.start``
  runs;
* nothing below constructs ``GmailConnector``, ``ConnectorRegistry``, ``FileWorkspace``,
  ``IntentClassifier`` or any other child directly, and nothing calls
  ``resume_connector_work``/``deny_connector_work``/``complete_oauth`` by
  hand.  A test that reached in like that would be one more child fixture
  wearing an integration name, which is precisely what the criterion
  forbids;
* assertions are on what the owner would see - the Telegram bubbles that
  were sent, the task card, ``GET /api/tasks/<id>``, ``GET /api/home``,
  ``GET /api/state``, and files on disk - in preference to internal state.

**Evidence class: local, offline, fixture-backed integration.** Every
outbound transport is injected: Telegram, the model provider, the Gmail REST
surface and the OAuth token endpoint are all Python callables in this file.
The unsupported-capability DecisionEngine question is answered by a fixture
with ``none-of-these`` for ordinary mail searches; an unavailable judgment is
covered separately and starts no mail read.
No live Google or Telegram call is made and nothing here is evidence that a
live connection works.  Live Gmail, live Telegram and live Calendar remain
``owner_validation_pending``.

Journey coverage against #386 J1-J8 is recorded in ``JOURNEY_EVIDENCE``
below, including the parts this acceptance cannot honestly claim.
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
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler

from cryptography.fernet import Fernet

from personal_agent.agent_runtime import PUBLIC_TASK_INSTRUCTIONS
from personal_agent.connector_contract import CONNECTOR_STATE_KEY, ConnectorState
from personal_agent.decision import (OUTCOME_DECIDED, BinaryDecision, FixtureDecisionEngine, SelectionDecision,
                                     fixture_confidence)
from personal_agent.gmail import GMAIL_CONNECTOR_ID, GMAIL_READONLY_SCOPE
from personal_agent.providers import ModelAdapter, ProviderError
from personal_agent.quickstart import configured_service, make_handler
from personal_agent.quickstart_store import QuickStore

#: Owner turns the fixture DecisionEngine judges as explicit remember requests (#597).
OWNER_MEMORY_REQUESTS = frozenset({'내 회의 시간 선호를 기억해 줘: 오전이 좋아', '아니 오후가 좋아. 회의 시간 선호를 저장해 줘'})

#: What this acceptance does and does not establish, per #386 journey.  It is
#: deliberately part of the test file rather than prose in an issue comment,
#: so that a journey cannot quietly lose its evidence while the suite stays
#: green.  ``covered`` journeys are exercised end to end below; the others
#: state why not, and neither may be reported as integrated evidence.
JOURNEY_EVIDENCE = {
    'J1': 'partial: owner claim, session boundary, Telegram pairing and the '
          'restart path are covered through the shipped routes. Homebrew '
          'install and machine reboot are owner_validation_pending.',
    'J2': 'covered: reference folder connected, prose summary saved as an '
          'artifact with sources, original preserved, reused after restart.',
    'J3': 'covered offline, connection and retrieval separately. Parked, '
          'authorized through the shipped routes against a fixture token '
          'endpoint, resumed exactly once. Retrieval was a separate seam '
          'nobody connected: `GmailConnector` took `transport=None` and '
          'production supplied none, so an owner who completed the OAuth hit '
          '`transport_unavailable` on their first real search, with no test '
          'anywhere (#457). The data plane is now wired GET-only to an '
          'allowlisted host, because the bearer token is already in the '
          'headers by then. Live Gmail is owner_validation_pending: no real '
          'Google call has been made.',
    'J4': 'covered offline. Wired end to end: `calendar_query` and three '
          '`calendar_draft_*` tools, an owner-authenticated `/google-calendar` '
          'route for each of the two grants, an unauthenticated-by-necessity '
          '`/oauth/calendar/callback`, `agentos calendar-config`, and a '
          'method-selects-grant HTTP transport. The model has no tool that '
          'applies a change: a draft carries the exact payload and its hash, '
          'and applying it needs a one-time approval bound to this owner, '
          'draft, payload hash and the write connector revision, which only '
          'the owner mints through `/api/calendar/drafts`, which is the '
          'half that did not exist in the first version - the model could '
          'draft and nobody could apply. A read grant never becomes a write '
          'grant. A replayed approval produces no second event, because the '
          'applied row is terminal and short-circuits - not, as an earlier '
          'version of this entry implied, because of the idempotency key, '
          'which is never re-sent on any reachable path. '
          'Registering the specs is safe now only because the completable '
          'route landed in the same change. Live Google Calendar OAuth and '
          'any real event mutation are owner_validation_pending; no live '
          'call has been made. `calendar_query` is labelled `owner-calendar` '
          'and closes public destinations for the turn. The natural-language '
          'create intent has its worker branch since PA1-J4-02 / #465: '
          'literal rules read title, date, time and duration, ask for the '
          'one missing detail, draft through the same `draft_create`, show '
          'the exact preview, and spend the same approve/execute pair only '
          'on the owner\'s explicit "승인". No model is consulted on that '
          'path.',
    'J5': 'covered offline, with the discrimination measured and weak. '
          '`bounded_public_research` is wired and reachable; '
          'tests/test_pa1_j5_research_discrimination.py drives page content '
          'the test controls, with no model in the loop, and asserts the '
          'classification the product produced - so an echo of the model '
          'cannot pass. Measured recall on ten realistic vendor pages: fee '
          '7/10, inventory 1/10, payable_total 0/10. The error runs in the '
          'safe direction (under-claiming, never asserting stock a page did '
          'not commit to) but inventory discrimination is mostly \'unknown\', '
          'and raising recall is tracked separately because each point of '
          'recall risks reading a hedge as a commitment. Private provenance '
          'closes the destination; non-2xx pages are refused; robots.txt is '
          'not consulted and a 200-status soft wall would be read. No '
          'network was touched. Permission delta, stated exactly: the mode '
          'allowlist and three-page cap bound how MUCH is read, not WHICH '
          'page - the query is model-authored and the first three search '
          'results are read in provider order - and the owner-approved '
          'public_page_scope is not preserved here. Because '
          'public_page_boundary returns an empty list until the owner '
          'approves URLs for the current model fingerprint, on a default '
          'install public_page_read never succeeds, so this gives the model '
          'its first model-directed full-page read. The inventory leg of '
          'the discrimination is one recognised phrasing, not a general '
          'classifier (#459).',
    'J6': 'covered: prose capture as canonical Memory, correction by '
          'supersession, owner review and durable delete through the shipped '
          'surfaces, an unauthorized model write held as a MemoryCandidate, a '
          'value the owner never stated held as one too even inside an '
          'approved turn, and durability across restart. MemoryCandidate '
          '*approval* has its own shipped route and keeps its own suite.',
    'J7': 'covered: every request below is ordinary prose. No slash command '
          'is used, a missing capability returns a next action rather than a '
          'dead end, and the original Work resumes once after connection.',
    'J8': 'covered: restart through a second `configured_service` over the '
          'same directory plus `QuickStore.recover()`. Interrupted Work is '
          'not auto-retried; connected authority, memory and artifacts '
          'survive; refusals stay refusals; revoked provider authority fails '
          'closed on the owner\'s next ordinary request with no mailbox '
          'call; an uncertain delivery is not re-sent by the restarted '
          'delivery loop. Revocation is modelled as a provider 401 because '
          'no shipped surface performs a registry disconnect.',
}

OWNER_PASSWORD = 'a-long-first-use-owner-password'
CHAT = 4242
BOT_TOKEN = '123456:TEST_TOKEN'
GMAIL_CLIENT_SECRET = 'gmail-client-secret-never-emitted'
MODEL_ANSWER = '요약: 9월 출장 일정과 결정 사항입니다.'
SUBJECT = '9월 숙소 예약 확인'


PAGE_URL = 'https://example.test/headphones'
PAGE_TEXT = 'Model A는 30시간 재생. 가격과 재고는 페이지에 표시되지 않음.'


class _NoRedirect(HTTPRedirectHandler):
    """Keep 303s visible: the OAuth start route's Location is the evidence."""

    def redirect_request(self, *args, **kwargs):
        return None


class _FakeEgress:
    """The outbound public-web seam, replacing ``LocalTools``.

    ``AgentService.local_tools`` is the single object the runtime is handed as
    its network, and it is the only way a bounded search or page read can
    leave the machine.  Replacing it is the same kind of substitution as the
    Telegram and Gmail transports above: an outbound transport, not a policy
    object.  Every authority decision - whether a read is allowed at all,
    which URLs are in scope - stays in the shipped code being tested.
    """

    def __init__(self):
        self.plans = []

    def execute(self, plan):
        self.plans.append(plan)
        if plan['tool'] == 'web_search':
            return {'tool': 'web_search', 'query': plan['query'], 'retrieved_at': 1,
                    'scope': 'Search snippets only; full pages have not been read.',
                    'results': [{'title': '헤드폰 비교', 'url': PAGE_URL,
                                 'snippet': '재생 시간 비교'}],
                    'sources': [PAGE_URL]}
        if plan['tool'] == 'public_page_read':
            return {'tool': 'public_page_read', 'url': plan['url'], 'retrieved_at': 1,
                    'content': PAGE_TEXT, 'content_truncated': False,
                    'content_bytes': len(PAGE_TEXT.encode()),
                    'scope': 'Anonymous bounded public page text.',
                    'sources': [plan['url']]}
        raise AssertionError('unexpected egress plan: ' + str(plan))


class FirstUseEndToEndAcceptance(unittest.TestCase):
    """One clean-store first-use walk through the shipped boundaries."""

    # -- harness ----------------------------------------------------------
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reference = self.root / 'reference'
        self.workspace = self.root / 'workspace'
        self.reference.mkdir()
        self.workspace.mkdir()
        self.original = self.reference / 'trip.md'
        self.original.write_text('출장 계획 초안: 9월 12일 출발, 숙소 미정, 예산 120만원',
                                 encoding='utf-8')
        self.original_bytes = self.original.read_bytes()

        # A genuinely empty data directory.  Everything the owner has after
        # this point was created by an entry point in this test.
        self.store = QuickStore(str(self.root / 'data'))
        self.calls = []
        self.updates = []
        self.gmail_calls = []
        self.exchanges = []
        # The scripted half of the model fixture.  Empty means "answer with
        # text"; a list means "ask for these tools in order, then answer".
        self.model_plan = []
        self.public_tasks = []
        self.model_text = MODEL_ANSWER
        # Two failure switches the owner's world can flip under the product:
        # Google rejecting a stored credential, and Telegram not answering a
        # send.  Both are properties of the injected transports, not of any
        # policy object, so flipping them keeps the shipped code under test.
        self.gmail_401 = False
        self.telegram_down = False
        self.network = _FakeEgress()
        self.env = {
            'AGENTOS_GMAIL_LOCAL_ONLY': '1',
            'AGENTOS_GMAIL_CLIENT_ID': 'gmail-client',
            'AGENTOS_GMAIL_CLIENT_SECRET': GMAIL_CLIENT_SECRET,
            'AGENTOS_GMAIL_LOCAL_PORT': '8787',
            'AGENTOS_GMAIL_ENCRYPTION_KEY': Fernet.generate_key().decode(),
        }
        self.service = self.boot()
        self.base = self.serve(self.service)
        self.client = build_opener(HTTPCookieProcessor(CookieJar()), _NoRedirect())

    # -- injected transports ----------------------------------------------
    def transport(self, url, body, headers=None, timeout=60):
        """The one outbound HTTP seam for Telegram and the model provider."""
        self.calls.append((url, body))
        if url.endswith('/getMe'):
            return {'ok': True, 'result': {'username': 'owner_test_bot'}}
        if url.endswith('/getWebhookInfo'):
            return {'ok': True, 'result': {'url': ''}}
        if url.endswith('/getUpdates'):
            return {'ok': True, 'result': self.updates.pop(0) if self.updates else []}
        if url.endswith('/sendMessage'):
            if self.telegram_down:
                raise ProviderError('telegram unreachable')
            return {'ok': True, 'result': {'message_id': len(self.calls)}}
        if url.endswith('/editMessageText'):
            return {'ok': True, 'result': True}
        if url.endswith('/chat/completions'):
            probing = any((tool.get('function', {}).get('name') or tool.get('name'))
                          == 'agentos_connection_probe' for tool in body.get('tools', []))
            if probing:
                return {'model': 'verified/model:free', 'choices': [{'message': {'tool_calls': [
                    {'id': 'probe', 'function': {'name': 'agentos_connection_probe',
                                                 'arguments': '{}'}}]}}]}
            # Branch on how many tool results the agent loop has already fed
            # back, so the script survives the retry turn `run_agent` injects
            # when a first reply carries no tool call.
            done = len([message for message in body['messages'] if message.get('role') == 'tool'])
            if body['messages'][0].get('content', '').endswith(PUBLIC_TASK_INSTRUCTIONS):
                # A #605 separate public task sees only the owner's request
                # (plus approved page addresses).  Like a real model, this
                # fixture can only replay a scripted call whose arguments that
                # input itself states; otherwise it answers without a tool.
                self.public_tasks.append(body)
                request = body['messages'][1]['content']
                if done < len(self.model_plan) and all(
                        str(value) in request for value in json.loads(self.model_plan[done][1]).values()):
                    name, arguments = self.model_plan[done]
                    return {'choices': [{'message': {'tool_calls': [
                        {'id': f'public-{done}', 'type': 'function',
                         'function': {'name': name, 'arguments': arguments}}]}}]}
                return {'choices': [{'message': {'content': self.model_text}}]}
            if done < len(self.model_plan):
                name, arguments = self.model_plan[done]
                return {'choices': [{'message': {'tool_calls': [
                    {'id': f'call-{done}', 'type': 'function',
                     'function': {'name': name, 'arguments': arguments}}]}}]}
            return {'choices': [{'message': {'content': self.model_text}}]}
        raise AssertionError('unexpected outbound call: ' + url)

    def gmail_transport(self, method, endpoint, params, headers):
        """The fixture Gmail REST surface.  Read only; it can do nothing else."""
        self.gmail_calls.append((method, endpoint))
        if self.gmail_401:
            # What actually happens when an owner revokes access in their
            # Google account: the stored credential keeps existing and the
            # provider stops honouring it.
            return {'status_code': 401, 'error': 'invalid_grant'}
        if endpoint.endswith('/messages'):
            return {'messages': [{'id': 'm_1', 'threadId': 't_1'}]}
        return {'id': 'm_1', 'threadId': 't_1', 'payload': {'headers': [
            {'name': 'Subject', 'value': SUBJECT},
            {'name': 'From', 'value': 'Booking <booking@example.test>'},
            {'name': 'Date', 'value': 'Mon, 1 Sep 2026 10:00:00 +0000'}]}}

    def exchange(self, request):
        """The fixture OAuth token endpoint the callback route calls."""
        self.exchanges.append(dict(request))
        return {'access_token': 'fixture-access', 'refresh_token': 'fixture-refresh',
                'expires_in': 3600, 'scope': GMAIL_READONLY_SCOPE}

    # -- the shipped construction -----------------------------------------
    def boot(self, store=None):
        """Build the service exactly as the shipped entry point builds it.

        `configured_service` is the production constructor: `main()` calls it
        and passes the result straight to `make_handler`.  Only the outbound
        transports are replaced afterwards, which is the same seam the
        repository's other offline tests use.  Nothing here adds a capability
        the deployment would not have.
        """
        service = configured_service(self.store if store is None else store, self.env)
        # A bounded fixture provider answers the unsupported-capability
        # judgment with none-of-these for ordinary mail searches. This keeps
        # the acceptance's focus on shipped boundaries and connector recovery
        # while ensuring an unavailable semantic judgment never starts a read.
        # #597: whether a turn explicitly asks to remember a value is the
        # DecisionEngine's judgment; the fixture answers it for the owner
        # phrasings below and a confident "no" for everything else.
        service.use_decision_engine(FixtureDecisionEngine(choose=lambda context,candidates,question:
            SelectionDecision(OUTCOME_DECIDED,'none-of-these',candidates,fixture_confidence())
            if context.purpose == 'unsupported-capability' else None,
            judge=lambda context,proposition:
            BinaryDecision(OUTCOME_DECIDED,context.facts.get('owner_message') in OWNER_MEMORY_REQUESTS,
                           fixture_confidence())
            if context.purpose == 'explicit-memory-request' else None))
        service.telegram_transport = self.transport
        service.adapter = ModelAdapter(self.transport)
        # Guarded rather than assumed, so that a deployment which stopped
        # offering Gmail fails on the acceptance's own assertion below
        # instead of crashing this helper.
        if service.gmail is not None:
            service.gmail.transport = self.gmail_transport
            service.gmail_token_exchange = self.exchange
        service.local_tools = self.network
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

    # -- entering where the product enters --------------------------------
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

    def says(self, update_id, text, service=None):
        """One owner message arriving from Telegram, through `poll_telegram`.

        The update is handed to the injected transport's `getUpdates`, so the
        request enters through `TelegramChannel` and `ingest_update` rather
        than through `store.enqueue`.  Returns the Work id the service
        created for it.
        """
        service = service or self.service
        before = {job['id'] for job in self.store.jobs()}
        self.updates.append([{'update_id': update_id, 'message': {
            'from': {'id': CHAT}, 'chat': {'id': CHAT, 'type': 'private'}, 'text': text}}])
        service.poll_telegram()
        created = [job['id'] for job in self.store.jobs() if job['id'] not in before]
        return created[0] if created else None

    def drain(self, service=None, store=None):
        """Run the conversation worker until it has nothing left to do.

        This is the body of the loop `AgentService.start` runs in its worker
        thread, stepped deterministically instead of on a timer.  The
        `created` rewrite only skips the three-second Telegram task-card
        cancellation grace; it changes no status and no decision.
        """
        service = service or self.service
        store = store or self.store
        for _ in range(12):
            with store.db() as db:
                db.execute("UPDATE jobs SET created=? WHERE status='queued'",
                           (time.time() - 4,))
            if not service.run_one():
                break
            service.deliver_one()
            service.deliver_notification()
        service.deliver_one()
        service.deliver_notification()

    # -- owner-visible readers --------------------------------------------
    def bubbles(self):
        """Every message text this owner's Telegram chat actually received."""
        return [call[1].get('text', '') for call in self.calls
                if call[0].endswith(('/sendMessage', '/editMessageText'))
                and call[1].get('chat_id') == CHAT]

    def card(self, job_id):
        """The task/progress record the web management surface renders."""
        return self.web('/api/tasks/' + job_id)['selected']

    def model_calls(self):
        return [call for call in self.calls if call[0].endswith('/chat/completions')]

    def mailbox_reads(self):
        """How many Gmail *list* calls happened - one per executed mail Work."""
        return len([call for call in self.gmail_calls if call[1].endswith('/messages')])

    def connect_model(self, endpoint, key):
        """Connect a model the way the browser does: test, then apply the proof."""
        draft = {'provider': 'compatible', 'endpoint': endpoint,
                 'model': 'test-model', 'api_key': key}
        tested = self.web('/api/model/test', draft)
        self.assertTrue(tested['ok'])
        self.web('/api/model', {**draft, 'test_proof': tested['test_proof']})

    # -- the acceptance ---------------------------------------------------
    def test_clean_first_use_traverses_the_shipped_service_boundaries(self):
        with self.subTest('the shipped construction offers the PA1 connectors'):
            # `configured_service` is what `main()` calls.  If this stops
            # being true the capability is inert in the product no matter
            # what the child suites prove, which is the gap WU1 closed.
            self.assertIsNotNone(self.service.gmail)
            self.assertIsNotNone(self.service.connector_registry)
            self.assertIsNotNone(self.service.connector_handoff)
            self.assertEqual([spec.connector_id for spec
                              in self.service.connector_registry.definitions()],
                             [GMAIL_CONNECTOR_ID])
            # Declaring a connector grants nothing: no owner row exists yet.
            self.assertIsNone(self.store.config(CONNECTOR_STATE_KEY, None))

        with self.subTest('J1 the owner session boundary exists before anything else'):
            self.assertFalse(self.store.claimed())
            for path in ('/api/state', '/api/home', '/api/tasks', '/api/personal-space'):
                with self.assertRaises(HTTPError) as refused:
                    self.web(path)
                self.assertEqual(refused.exception.code, 401)
            # A connector cannot be started by an anonymous caller either,
            # and that is checked again after the connection exists below.
            with self.assertRaises(HTTPError) as refused:
                self.web('/google-gmail')
            self.assertEqual(refused.exception.code, 401)

            self.assertEqual(self.web('/api/claim', {'code': self.store.bootstrap.read_text(),
                                                     'password': OWNER_PASSWORD}), {'ok': True})
            self.assertFalse(self.store.bootstrap.exists())
            home = self.web('/api/home')
            self.assertEqual(home['state'], 'ready')
            self.assertFalse(home['telegram_paired'])
            self.assertFalse(home['model_connected'])
            # An owner with nothing connected is still told something useful.
            self.assertIn('메모', home['next_action'])

        with self.subTest('J1 pairing a private Telegram owner through the web route'):
            pairing = self.web('/api/telegram', {'token': BOT_TOKEN})
            self.assertIn('start=', pairing['url'])
            code = parse_qs(urlsplit(pairing['url']).query)['start'][0]
            # The pairing code arrives back as a real Telegram update.
            self.says(10, '/start ' + code)
            self.service.mark_telegram_connected()
            self.assertEqual(self.store.config('telegram')['user_id'], CHAT)
            self.assertEqual(self.store.config('telegram_status')['state'], 'connected')
            self.assertTrue(self.web('/api/home')['telegram_paired'])
            # The bot token is owner-local and never reaches a read surface.
            self.assertNotIn(BOT_TOKEN, json.dumps(self.web('/api/state'), ensure_ascii=False))
            self.assertNotIn(GMAIL_CLIENT_SECRET,
                             json.dumps(self.web('/api/state'), ensure_ascii=False))
            self.drain()

        with self.subTest('J6/J7 prose that needs no connector and no model'):
            note = self.says(11, '이거 메모해줘: 출장 준비물은 여권, 어댑터, 보조 배터리')
            self.drain()
            self.assertEqual(self.store.job(note)['status'], 'succeeded')
            self.assertEqual([row['content'] for row in self.store.notes()],
                             ['출장 준비물은 여권, 어댑터, 보조 배터리'])
            # Owner-visible on both surfaces, from the same durable Work.
            self.assertIn('메모를 저장했습니다', self.store.job(note)['response'])
            self.assertEqual(self.card(note)['status_label'], '완료')
            self.assertIn('여권', json.dumps(self.web('/api/personal-space'), ensure_ascii=False))

            recall = self.says(12, '개인 공간에서 출장 관련 내용 찾아줘')
            self.drain()
            self.assertEqual(self.store.job(recall)['status'], 'succeeded')
            self.assertIn('출장 준비물은 여권', self.store.job(recall)['response'])
            self.assertTrue(any('여권' in bubble for bubble in self.bubbles()))
            # Not one model call was needed to get here.
            self.assertEqual(self.model_calls(), [])

        with self.subTest('J1 connecting a model is test-then-apply, not apply'):
            # The browser posts the draft to /api/model/test, then applies the
            # exact tested configuration with the proof it got back.  A
            # configuration that was never tested cannot be applied at all.
            draft = {'provider': 'compatible', 'endpoint': 'http://127.0.0.1:11434/v1',
                     'model': 'test-model', 'api_key': 'local-model-key'}
            with self.assertRaises(HTTPError) as untested:
                self.web('/api/model', draft)
            self.assertEqual(untested.exception.code, 400)
            self.connect_model(draft['endpoint'], draft['api_key'])
            self.assertTrue(self.web('/api/home')['model_connected'])

        with self.subTest('J5 bounded public research cites what it observed'):
            self.web('/api/public-pages/approval', {'approved': True, 'urls': [PAGE_URL]})
            self.model_plan = [('web_search', '{"query": "노이즈캔슬링 헤드폰 비교"}'),
                               ('public_page_read', json.dumps({'url': PAGE_URL}))]
            self.model_text = ('관찰됨: Model A 재생 시간 30시간. '
                               '확인되지 않음: 가격과 재고는 페이지에 없었습니다.')
            research = self.says(13, '웹에서 노이즈캔슬링 헤드폰 비교해서 찾아봐')
            self.drain()
            job = self.store.job(research)
            self.assertEqual(job['status'], 'succeeded', job['error'])
            # These two assert a ROUND TRIP, not discrimination: both strings
            # are set in `self.model_text` above, so they would pass equally
            # against a product that echoes whatever the model said.  They are
            # kept because the round trip is worth pinning, but they are not
            # J5 evidence and must not be read as such.
            #
            # J5's "distinguishes observed facts from unknown
            # price/inventory/fees" is evidenced in
            # tests/test_pa1_j5_research_discrimination.py, which drives page
            # content the test controls through the wired
            # `bounded_public_research` branch with no model in the loop, so
            # there is nothing for the product to echo.  It also records the
            # measured recall, which is poor for inventory.
            self.assertIn('관찰됨', job['response'])
            self.assertIn('확인되지 않음', job['response'])
            # This one is real product evidence: `model_text` contains no URL,
            # so the citation was appended by the product.
            self.assertIn(PAGE_URL, job['response'])
            # The egress layer was asked for exactly the bounded plan, and
            # the page read carried the owner-approved scope with it.
            self.assertEqual([plan['tool'] for plan in self.network.plans],
                             ['web_search', 'public_page_read'])
            self.assertEqual(self.network.plans[1]['approved_urls'], [PAGE_URL])
            # Per-source evidence is durable and visible on the web surface.
            sources = [event['trace']['evidence']['sources']
                       for event in self.store.task_events(research)
                       if event['status'] == 'succeeded' and event['trace'].get('evidence')]
            self.assertIn([PAGE_URL], sources)
            self.assertIn('공개 웹', ' '.join(self.card(research)['source_references']))
            self.model_plan = []
            self.model_text = MODEL_ANSWER

        with self.subTest('J6 durable memory: remember, correct, review, delete'):
            self.model_plan = [('save_memory',
                                json.dumps({'memory_key': 'meeting-time',
                                            'content': '오전 회의를 선호합니다'},
                                           ensure_ascii=False))]
            self.model_text = '기억했습니다.'
            remember = self.says(14, '내 회의 시간 선호를 기억해 줘: 오전이 좋아')
            self.drain()
            self.assertEqual(self.store.job(remember)['status'], 'succeeded')
            self.assertEqual([row['content'] for row in self.store.memories()],
                             ['오전 회의를 선호합니다'])
            self.assertEqual(self.store.memory_candidates(), [])

            # Correction is a second authorized write on the same key: the
            # old value is superseded, not silently overwritten or duplicated.
            self.model_plan = [('save_memory',
                                json.dumps({'memory_key': 'meeting-time',
                                            'content': '오후 회의를 선호합니다'},
                                           ensure_ascii=False))]
            correct = self.says(15, '아니 오후가 좋아. 회의 시간 선호를 저장해 줘')
            self.drain()
            self.assertEqual(self.store.job(correct)['status'], 'succeeded')
            self.assertEqual([row['content'] for row in self.store.memories()],
                             ['오후 회의를 선호합니다'])
            # Exactly one current value, and the old one kept as history.
            with self.store.db() as db:
                states = dict(db.execute(
                    'SELECT state,count(*) FROM memories GROUP BY state').fetchall())
            self.assertEqual(states, {'current': 1, 'superseded': 1})

            # The owner can review it on the management surface, with its key.
            records = self.web('/api/personal-records?filter=memory')['items']
            self.assertEqual([row['memory_key'] for row in records], ['meeting-time'])
            self.assertEqual(records[0]['content'], '오후 회의를 선호합니다')
            memory_id = records[0]['id']

            # And delete it durably, through the route the browser uses.
            deleted = self.web('/api/personal-space/memories/' + memory_id, method='DELETE')
            self.assertTrue(deleted['deleted'])
            self.assertEqual(self.store.memories(), [])
            self.assertEqual(self.web('/api/personal-records?filter=memory')['items'], [])
            self.model_plan = []
            self.model_text = MODEL_ANSWER

        with self.subTest('negative: an unauthorized model write stays a candidate'):
            # C5.  The owner said not to save.  No memory approval is issued
            # for this turn, so the model asking to write anyway must produce
            # a MemoryCandidate the owner can see and has not accepted -
            # never canonical Memory.
            self.model_plan = [('save_memory',
                                json.dumps({'memory_key': 'inferred-preference',
                                            'content': '모델이 추론한 값'},
                                           ensure_ascii=False))]
            self.model_text = '저장하지 않았습니다.'
            sneaky = self.says(16, '이건 기억하지 마. 그냥 방금 이야기만 정리해 줘')
            self.drain()
            # #488: the write was withheld, so the turn is not a success.  The
            # owner is told what is pending instead of being told it was saved.
            self.assertEqual(self.store.job(sneaky)['status'], 'failed')
            self.assertIn('기억 후보로 보관', self.store.job(sneaky)['error'])
            self.assertEqual(self.store.memories(), [])
            candidates = self.store.memory_candidates()
            self.assertEqual([row['state'] for row in candidates], ['pending'])
            self.assertEqual(candidates[0]['content'], '모델이 추론한 값')
            # Owner-visible as pending, and counted separately from Memory.
            self.assertEqual(self.web('/api/personal-space')['memory_candidate_count'], 1)
            self.model_plan = []
            self.model_text = MODEL_ANSWER

        with self.subTest('J2 an approved reference folder becomes a reusable artifact'):
            configured = self.web('/api/file-workspace', {'references': [str(self.reference)],
                                                          'workspace': str(self.workspace)})
            self.assertEqual(len(configured['references']), 1)
            # Connecting a folder re-opened the document-sharing question, and
            # the local model answers it without an external boundary.
            self.assertFalse(self.service.document_boundary()['requires_approval'])

            summary = self.says(17, '“출장 계획” 자료를 요약해 “9월 출장 정리”로 저장해줘')
            self.drain()
            job = self.store.job(summary)
            self.assertEqual(job['status'], 'succeeded', job['error'])
            self.assertIn(MODEL_ANSWER, job['response'])
            # The artifact exists, cites its source, and the original is
            # byte-for-byte untouched.
            saved = self.workspace / '9월 출장 정리.md'
            self.assertTrue(saved.is_file())
            self.assertIn('trip.md', saved.read_text(encoding='utf-8'))
            self.assertEqual(self.original.read_bytes(), self.original_bytes)
            artifacts = self.card(summary)['artifacts']
            self.assertEqual([item['path'] for item in artifacts], ['9월 출장 정리.md'])

            reuse = self.says(18, '저장한 결과에서 출장 찾아줘')
            self.drain()
            self.assertEqual(self.store.job(reuse)['status'], 'succeeded')
            self.assertIn('9월 출장 정리.md', self.store.job(reuse)['response'])

        with self.subTest('negative: private document history closes public egress'):
            # An integration property no child suite could show, because it
            # only exists once both halves run in one conversation: reading
            # the owner's connected folder marks the Work as a document job,
            # and while that job is inside the history window the worker's own
            # public calls are closed.  Since #605 the worker's proposal goes
            # to a separate public task that sees only the owner's request, so
            # a query built from the document ("출장 계획 초안 ...") cannot be
            # reproduced and nothing is sent.
            before = list(self.network.plans)
            self.model_plan = [('web_search', '{"query": "출장 계획 초안 숙소 가격"}')]
            leak = self.says(19, '웹에서 그 출장 숙소 가격도 찾아봐')
            self.drain()
            self.assertEqual(self.store.job(leak)['status'], 'failed')
            # #605: the worker's query was discarded; the separate public task
            # saw only the owner's current request, never the document.
            self.assertTrue(self.public_tasks)
            self.assertEqual(self.public_tasks[-1]['messages'][1],
                             {'role': 'user', 'content': '웹에서 그 출장 숙소 가격도 찾아봐'})
            self.assertNotIn('출장 계획 초안', json.dumps(self.public_tasks, ensure_ascii=False))
            # Nothing reached the egress layer, so nothing could be exfiltrated.
            self.assertEqual(self.network.plans, before)
            self.assertNotIn('출장 계획 초안',
                             json.dumps(self.network.plans, ensure_ascii=False))
            self.model_plan = []

        with self.subTest('an install without Calendar credentials refuses cleanly'):
            # This harness builds a service with no Calendar credential, and
            # that install must keep the refusal it always had.  The comment
            # here used to say `AgentService` has no `calendar=` parameter
            # and that no production Calendar transport exists; both were
            # true until PA1-J4-01 and are now false, sixty lines above a
            # JOURNEY_EVIDENCE['J4'] saying the opposite.  What is still
            # true, and what this subtest holds, is narrower: registering
            # the connector specs is safe only where a completable route
            # exists, so an install without credentials registers nothing,
            # advertises nothing, and refuses by naming the reason rather
            # than parking Work for a connection it cannot offer.
            calendar = self.says(20, '내일 오후 3시에 팀 회의 일정 잡아줘')
            self.drain()
            job = self.store.job(calendar)
            self.assertEqual(job['status'], 'failed')
            self.assertIn('구성되어 있지 않습니다', job['error'])
            self.assertEqual(self.card(calendar)['status_label'], '확인 필요')
            self.assertNotIn('연결 대기', self.card(calendar)['waits'])
            # And it created no connector authority on its way out.
            self.assertIsNone(self.store.config(CONNECTOR_STATE_KEY, None))

        with self.subTest('J3/J7 a connector request parks instead of failing'):
            mail = self.says(21, '메일에서 숙소 예약 확인 메일 찾아줘')
            self.drain()
            job = self.store.job(mail)
            self.assertEqual(job['status'], 'awaiting_connection')
            # A next action, not a dead end - and nothing was executed.
            self.assertIn('Gmail', job['response'])
            self.assertIn('한 번만', job['response'])
            self.assertEqual(self.mailbox_reads(), 0)
            progress = self.card(mail)
            self.assertEqual(progress['waits'], ['연결 대기'])
            self.assertFalse(progress['result_available'])
            self.assertTrue(any('Gmail' in bubble for bubble in self.bubbles()))
            self.assertEqual(self.service.connector_registry.status(
                f'telegram:{CHAT}', GMAIL_CONNECTOR_ID).state, ConnectorState.DISCONNECTED)

        with self.subTest('J3/J7 authorization resumes the original Work exactly once'):
            with self.assertRaises(HTTPError) as redirect:
                self.web('/google-gmail')
            self.assertEqual(redirect.exception.code, 303)
            location = redirect.exception.headers['Location']
            self.assertTrue(location.startswith('https://accounts.google.com/'))
            self.assertEqual(parse_qs(urlsplit(location).query)['scope'], [GMAIL_READONLY_SCOPE])
            self.assertNotIn(GMAIL_CLIENT_SECRET, location)
            state = parse_qs(urlsplit(location).query)['state'][0]

            # Google redirects the browser back without the SameSite=Strict
            # cookie, so this half is opened by an unauthenticated client.
            callback = self.base + '/oauth/gmail/callback?code=fixture-code&state=' + state
            with build_opener().open(callback, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b'Gmail connected', response.read())
            self.assertEqual(len(self.exchanges), 1)
            status = self.service.connector_registry.status(f'telegram:{CHAT}',
                                                            GMAIL_CONNECTOR_ID)
            self.assertEqual(status.state, ConnectorState.CONNECTED)
            self.assertEqual(status.granted_scopes, (GMAIL_READONLY_SCOPE,))

            # The Work the owner parked from Telegram is re-queued, then runs.
            self.assertEqual(self.store.job(mail)['status'], 'queued')
            self.drain()
            job = self.store.job(mail)
            self.assertEqual(job['status'], 'succeeded')
            self.assertIn(SUBJECT, job['response'])
            self.assertEqual(self.mailbox_reads(), 1)
            self.assertTrue(any(SUBJECT in bubble for bubble in self.bubbles()))
            progress = self.card(mail)
            self.assertEqual(progress['status_label'], '완료')
            self.assertEqual(progress['waits'], [])
            self.assertTrue(progress['result_available'])

            # Exactly once: the identical callback replayed is refused, and
            # re-queues and re-reads nothing.
            with self.assertRaises(HTTPError) as replay:
                build_opener().open(callback, timeout=5)
            self.assertEqual(replay.exception.code, 400)
            self.drain()
            self.assertEqual(self.store.job(mail)['status'], 'succeeded')
            self.assertEqual(self.mailbox_reads(), 1)
            self.assertEqual(len(self.exchanges), 1)

        with self.subTest('negative: a mail read never becomes a mail write'):
            # C4.  `_MAIL_VERBS` contains no send/reply verb, so this prose
            # matches no mail rule and stays on the ordinary conversation
            # route.  Sending mail is not a capability this product offers,
            # and holding a Gmail read credential must not create one.
            before = list(self.gmail_calls)
            send = self.says(22, '이 메일 답장 보내줘')
            self.drain()
            self.assertEqual(self.store.job(send)['status'], 'succeeded')
            self.assertEqual(self.store.job(send)['response'], MODEL_ANSWER)
            self.assertEqual(self.gmail_calls, before)
            self.assertTrue(all(method == 'GET' for method, _ in self.gmail_calls))

        with self.subTest('negative: one connection does not authorize another'):
            again = self.says(23, '모레 오전 10시에 병원 예약 일정 잡아줘')
            self.drain()
            self.assertEqual(self.store.job(again)['status'], 'failed')
            self.assertIn('구성되어 있지 않습니다', self.store.job(again)['error'])
            with self.assertRaises(HTTPError) as refused:
                self.web('/api/state', opener=build_opener())
            self.assertEqual(refused.exception.code, 401)

        with self.subTest('negative: an unapproved external model gets no owner document'):
            self.connect_model('https://example.test/v1', 'external-model-key')
            self.assertTrue(self.service.document_boundary()['requires_approval'])
            before = len(self.model_calls())
            outbound = len(self.calls)
            blocked = self.says(24, '“출장 계획” 자료를 요약해 “외부 전송 시도”로 저장해줘')
            self.drain()
            job = self.store.job(blocked)
            self.assertEqual(job['status'], 'failed')
            self.assertIn('문서 공유 승인', job['error'])
            # Refused before the send, not after: no model call, no file.
            self.assertEqual(len(self.model_calls()), before)
            self.assertNotIn('출장 계획 초안',
                             json.dumps(self.calls[outbound:], ensure_ascii=False))
            self.assertEqual(sorted(path.name for path in self.workspace.glob('*.md')),
                             ['9월 출장 정리.md'])

        with self.subTest('J8 restart preserves what the contracts promise'):
            # Leave one Work mid-flight so recovery has something to decide.
            with self.store.db() as db:
                db.execute("UPDATE jobs SET status='running' WHERE id=?", (blocked,))
            restarted_store = QuickStore(str(self.root / 'data'))
            restarted = self.boot(restarted_store)
            # `AgentService.start` runs `store.recover()` as its first
            # statement; this is that statement, without the timer threads.
            restarted_store.recover()

            # C8: an interrupted Work stays explicit and is not auto-retried.
            self.assertEqual(restarted_store.job(blocked)['status'], 'interrupted')
            self.assertEqual(restarted_store.recovery_summary()['interrupted_jobs'], 1)
            self.assertEqual(restarted.task_progress(blocked)['selected']['status_label'],
                             '확인 필요')
            self.assertEqual(restarted.home()['state'], 'attention')

            # Connected authority, memory, pairing and artifacts survive.
            status = restarted.connector_registry.status(f'telegram:{CHAT}',
                                                         GMAIL_CONNECTOR_ID)
            self.assertEqual(status.state, ConnectorState.CONNECTED)
            self.assertEqual(status.granted_scopes, (GMAIL_READONLY_SCOPE,))
            self.assertEqual([row['content'] for row in restarted_store.notes()],
                             ['출장 준비물은 여권, 어댑터, 보조 배터리'])
            self.assertEqual(restarted_store.config('telegram')['user_id'], CHAT)
            self.assertTrue((self.workspace / '9월 출장 정리.md').is_file())
            self.assertEqual(self.original.read_bytes(), self.original_bytes)

            # A mail request after restart runs without a second authorization.
            resumed = self.says(25, '메일에서 숙소 예약 확인 메일 다시 찾아줘', service=restarted)
            self.drain(service=restarted, store=restarted_store)
            self.assertEqual(restarted_store.job(resumed)['status'], 'succeeded')
            self.assertIn(SUBJECT, restarted_store.job(resumed)['response'])
            self.assertEqual(self.mailbox_reads(), 2)
            self.assertEqual(len(self.exchanges), 1)

            # And the refusals are still refusals on the other side of it.
            still = self.says(26, '다음 주 금요일 저녁 식사 일정 잡아줘', service=restarted)
            self.drain(service=restarted, store=restarted_store)
            self.assertEqual(restarted_store.job(still)['status'], 'failed')
            self.assertIn('구성되어 있지 않습니다', restarted_store.job(still)['error'])

        with self.subTest('J6 an authorized turn cannot write a value the owner did not state'):
            # The J6 defect PA1-MEMORY-01 #392 recorded on the live path and
            # carried to #393/#394.  Unlike the candidate leg above, this
            # request *is* an explicit owner memory request, so the turn
            # approval exists and `verify_memory_approval` succeeds.  A
            # Work-scoped check alone would therefore let the model pick both
            # the key and the value and have them become canonical Memory.
            # It runs here, late in the walk, because the J6 block above ends
            # by deleting its memory: Memory is empty again at this point.
            self.assertEqual(restarted_store.memories(), [])
            self.model_plan = [('save_memory',
                                json.dumps({'memory_key': 'payment-destination',
                                            'content': '송금은 계좌 999 로 보내세요'},
                                           ensure_ascii=False))]
            self.model_text = '기억했습니다.'
            injected = self.says(27, '내 회의 시간 선호를 기억해 줘: 오전이 좋아',
                                 service=restarted)
            self.drain(service=restarted, store=restarted_store)
            # #488: withheld, therefore not succeeded.
            self.assertEqual(restarted_store.job(injected)['status'], 'failed')
            # Not canonical Memory - and not silently dropped either.
            self.assertEqual(restarted_store.memories(), [])
            pending = [row for row in restarted_store.memory_candidates()
                       if row['memory_key'] == 'payment-destination']
            self.assertEqual([row['content'] for row in pending],
                             ['송금은 계좌 999 로 보내세요'])
            # The owner can tell *why* from the durable tool event, not only
            # from whatever the model chose to say about it.
            # #488: the event is no longer filed as 'succeeded'.  It still
            # carries the machine reason, and now also the owner-facing one.
            written = [event for event in restarted_store.task_events(injected)
                       if event['tool'] == 'save_memory' and event['trace'].get('evidence')]
            self.assertEqual([event['status'] for event in written], ['failed'])
            self.assertEqual([event['trace']['evidence'].get('refused_because')
                              for event in written], ['value-not-in-owner-request'])
            self.assertNotIn(True, [event['trace']['evidence'].get('saved')
                                    for event in written])
            self.assertIn('기억 후보로 보관', written[0]['trace']['error'])
            self.model_plan = []
            self.model_text = MODEL_ANSWER

        with self.subTest('J8 revoked authority fails closed on the next ordinary request'):
            # Revocation is modelled as the provider rejecting the stored
            # credential, because that is what actually happens: the owner
            # revokes access in their Google account and AgentOS learns of it
            # from a 401 on its next call.  The registry's DISCONNECTED
            # transition is *not* used, because no shipped surface reaches it
            # - WU8 found no owner-facing route to disconnect a connector and
            # recorded that rather than inventing one here.
            self.gmail_401 = True
            connected_reads = self.mailbox_reads()
            revoked = self.says(28, '메일에서 예약 확인 메일 한 번 더 찾아줘',
                                service=restarted)
            self.drain(service=restarted, store=restarted_store)
            self.assertEqual(restarted_store.job(revoked)['status'], 'failed')
            # Exactly one rejected read, not a retry loop, and the authority
            # is gone rather than reused.
            self.assertEqual(self.mailbox_reads(), connected_reads + 1)
            status = restarted.connector_registry.status(f'telegram:{CHAT}',
                                                         GMAIL_CONNECTOR_ID)
            self.assertEqual(status.state, ConnectorState.REAUTH_REQUIRED)
            self.assertEqual(status.granted_scopes, ())

            # The leg the audit found missing: the owner's *next* ordinary
            # prose request must honour the revocation.  The unit test
            # test_gmail.py::test_expiry_and_provider_revocation_clear_tokens_
            # and_require_reauth proves the connector fails closed when asked
            # directly; nothing proved the conversation stops asking.
            before = self.mailbox_reads()
            after = self.says(29, '메일에서 숙소 예약 확인 메일 또 찾아줘', service=restarted)
            self.drain(service=restarted, store=restarted_store)
            # Zero mailbox transport calls: refused before the read, not
            # after, and asserted before the status so that a regression which
            # reaches the mailbox is reported as reaching the mailbox.
            self.assertEqual(self.mailbox_reads(), before)
            job = restarted_store.job(after)
            self.assertEqual(job['status'], 'awaiting_connection')
            self.assertIn('Gmail', job['response'])
            self.assertEqual(restarted.task_progress(after)['selected']['waits'],
                             ['연결 대기'])
            self.assertTrue(any('Gmail' in bubble for bubble in self.bubbles()))
            self.gmail_401 = False

        with self.subTest('J8 an uncertain delivery is not re-sent after restart'):
            # C8: a restart must not duplicate a consequential external
            # effect, and a Telegram message the owner may already have read
            # is one.  test_quickstart.py proves the in-process half against a
            # hand-built AgentService; what was missing everywhere is the
            # delivery loop `AgentService.start` actually runs, executed once
            # more against a second `configured_service` over the same data
            # directory after `QuickStore.recover()`.
            while restarted.deliver_notification():
                pass
            ambiguous = self.says(30, '이것도 메모해줘: 영수증은 출장 폴더에',
                                  service=restarted)
            with restarted_store.db() as db:
                db.execute("UPDATE jobs SET created=? WHERE status='queued'",
                           (time.time() - 4,))
            self.assertTrue(restarted.run_one())
            self.assertEqual(restarted_store.job(ambiguous)['delivery'], 'pending')

            # Telegram accepted the request but never answered, so whether the
            # owner saw it is unknowable.
            self.telegram_down = True
            restarted.deliver_one()
            self.telegram_down = False
            self.assertEqual(restarted_store.job(ambiguous)['delivery'], 'unknown')

            reopened_store = QuickStore(str(self.root / 'data'))
            reopened = self.boot(reopened_store)
            reopened_store.recover()
            self.assertEqual(reopened_store.job(ambiguous)['delivery'], 'unknown')
            self.assertEqual(reopened_store.recovery_summary()['uncertain_deliveries'], 1)
            with reopened_store.db() as db:
                self.assertEqual(db.execute(
                    "SELECT count(*) FROM jobs WHERE delivery='pending'").fetchone()[0], 0)

            outbound = len(self.calls)
            reopened.deliver_one()
            reopened.deliver_notification()
            # Still uncertain, and nothing went out a second time.
            self.assertEqual(reopened_store.job(ambiguous)['delivery'], 'unknown')
            self.assertEqual([call for call in self.calls[outbound:]
                              if call[0].endswith('/sendMessage')], [])

        with self.subTest('the journey map names its own gaps'):
            self.assertEqual(sorted(JOURNEY_EVIDENCE), ['J1', 'J2', 'J3', 'J4',
                                                        'J5', 'J6', 'J7', 'J8'])
            # J4 said 'not wired' for the whole program and this pinned it.
            # It is wired now, so the pin moves to what is still missing --
            # a live Calendar OAuth and any real event mutation -- rather
            # than being deleted. The guard's job is that the map keeps
            # naming its own gaps, not that a particular gap stays open.
            self.assertIn('owner_validation_pending', JOURNEY_EVIDENCE['J4'])
            self.assertIn('owner_validation_pending', JOURNEY_EVIDENCE['J1'])
            self.assertIn('owner_validation_pending', JOURNEY_EVIDENCE['J3'])
            # J6's value-scoped write binding and J8's two authority clauses
            # are asserted above; a later edit must not drop them from the map
            # while the suite stays green.
            self.assertIn('approved turn', JOURNEY_EVIDENCE['J6'])
            self.assertIn('revoked provider authority', JOURNEY_EVIDENCE['J8'])
            self.assertIn('not re-sent', JOURNEY_EVIDENCE['J8'])
            # No live external operation was observed anywhere above.
            self.assertTrue(all(url.startswith(('https://api.telegram.org',
                                                'http://127.0.0.1:11434',
                                                'https://example.test'))
                                for url, _ in self.calls))


if __name__ == '__main__':
    unittest.main()

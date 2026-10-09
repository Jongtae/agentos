"""API-READ-01 (#1216): authenticated API read by slot reference, with response provenance.

Evidence class: unit tests and model-free integration tests.  A scripted
model transport and the tests-only fake holdings API (``fake_holdings_api``)
replace only the provider and the wire; ``Capabilities``, ``run_agent``,
``api_requests``, the information-use audit and ``Preparations`` run
unchanged.  No live model, no live account.

Acceptance (issue #1216):
1. numbers equal the fake API raw data exactly;
2. stale, mismatch and unknown are not hidden;
3. no secret in prompt, log or Evidence;
4. a retry makes no duplicate effect;
5. the information-use audit and the reference time are recorded;
6. read and order authority are separate (mutate and above refused without approval);
plus: a 3-run bounded watch notifies only on change.
"""
import json
import logging
import re
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from fake_holdings_api import ACCOUNT, HOLDINGS_PATH, ORDERS_PATH, FakeHoldingsApi, fake_key

from personal_agent import information_use
from personal_agent import preparations as prep
from personal_agent.agent_runtime import (QUALIFIER_NOTES, Capabilities, ToolError, classify_failure, evidence_qualifiers,
                                          memory_value_has_secret, render_turn_prompt, run_agent, turn_context,
                                          work_disclosures)
from personal_agent.api_requests import (ApiError, ApiRequests, context_line, effective_effect, provenance, remove_slot,
                                         save_slot, select, slots)
from personal_agent.browser_session import binding_digest
from personal_agent.conversation_handoff import ConversationJudgments
from personal_agent.current_context import redact_known_secrets
from personal_agent.decision import OUTCOME_DECIDED, BinaryDecision, FixtureDecisionEngine, fixture_confidence
from personal_agent.memory_service import MemoryService
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_store import QuickStore

CFG = {'provider': 'compatible', 'endpoint': 'https://openrouter.ai/api/v1', 'model': 'test-model'}
SRC = Path(__file__).resolve().parents[1] / 'src' / 'personal_agent'
HOST = 'broker.fake.test'
URL = f'https://{HOST}{HOLDINGS_PATH}'
READ = {'slot': 'fake-holdings', 'url': URL, 'effect': 'read', 'as_of_field': '$.as_of',
        'required_fields': json.dumps(['$.holdings[*].market_value', '$.cash']),
        'checks': json.dumps([{'sum': '$.holdings[*].market_value', 'equals': '$.total_market_value'}])}
ORDER = {'slot': 'fake-holdings', 'url': f'https://{HOST}{ORDERS_PATH}', 'method': 'POST', 'effect': 'mutate',
         'body': json.dumps({'symbol': 'AAA', 'side': 'buy', 'quantity': 1})}


class Approvals:
    """The per-step approval surface (``consume``/``request``), as the service's is: one use per approval."""

    def __init__(self):
        self.issued, self.requested = set(), []

    def consume(self, binding):
        digest = binding_digest(binding)
        if digest in self.issued:
            self.issued.discard(digest)
            return True
        return False

    def request(self, binding, description):
        self.requested.append((binding_digest(binding), description))

    def approve_last(self):
        self.issued.add(self.requested[-1][0])


class Script:
    """A compatible-API transport answering from scripted messages; records every body sent to the model."""

    def __init__(self, *messages):
        self.messages, self.bodies = list(messages), []

    def __call__(self, url, body, headers=None, timeout=60):
        self.bodies.append(json.loads(json.dumps(body)))
        message = self.messages.pop(0) if self.messages else {'content': '끝났습니다.'}
        if callable(message):
            message = message(body)
        return {'choices': [{'message': message}]}


def tool_call(ident, name, **args):
    return {'id': ident, 'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}


def tool_results(body):
    return [json.loads(m['content']) for m in body['messages'] if m.get('role') == 'tool']


def summary_from_tool(body):
    """The scripted AI's answer: numbers copied verbatim from ``data``; it mentions no flag on purpose."""
    result = [row for row in tool_results(body) if 'data' in row][-1]
    data = result['data']
    lines = [f"{row['symbol']} {row['quantity']}주 평균 {row['average_price']} 평가 {row.get('market_value')}"
             for row in data['holdings']]
    lines.append(f"현금 {data['cash']} 합계 {data['total_value']}")
    return {'content': '\n'.join(lines)}


def judgments():
    def judge(context, proposition):
        if context.purpose != 'goal-reached':
            return None
        return BinaryDecision(OUTCOME_DECIDED, True, fixture_confidence())
    return ConversationJudgments(FixtureDecisionEngine(judge=judge))


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 9, 1, 0, tzinfo=timezone.utc).timestamp()

    def __call__(self):
        return self.now


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'data')
        self.key = fake_key()
        save_slot(self.store, 'fake-holdings', [HOST], self.key, subject_field='$.account_id', subject_value=ACCOUNT)
        self.clock = Clock()
        self.api = FakeHoldingsApi(self.key, now=self.clock)
        self.approvals = Approvals()
        self.job_id = self.store.enqueue('현재 자산 요약해줘', 'api-read-test')
        patcher = mock.patch('personal_agent.api_requests.http_request', self.api)
        patcher.start()
        self.addCleanup(patcher.stop)
        sleeper = mock.patch('personal_agent.api_requests.time.sleep', lambda _s: None)
        sleeper.start()
        self.addCleanup(sleeper.stop)

    def record(self, tool, status, detail):
        with self.store.db() as db:
            db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                       (self.job_id, tool, status, detail, time.time()))

    def caps(self, transport=None, job_id=None, **kwargs):
        caps = Capabilities(self.store, ModelAdapter(transport or Script()), CFG, '', job_id or self.job_id, self.record,
                            browser_approvals=self.approvals, **kwargs)
        caps.api().clock = self.clock
        return caps

    def work(self, *messages, caps=None, **kwargs):
        script = Script(*messages)
        caps = caps or self.caps(script, judgments=judgments(), **kwargs)
        caps.adapter = ModelAdapter(script)
        result = run_agent(caps.adapter, CFG, '', [{'role': 'user', 'content': '현재 자산 요약해줘'}], '', caps, self.record)
        return result, script

    def events(self):
        with self.store.db() as db:
            return [dict(row) for row in db.execute('SELECT tool,status,detail FROM tool_events WHERE job_id=?', (self.job_id,))]

    def evidence(self):
        """The recorded Evidence of the Work's last settled api_request call."""
        rows = [row for row in self.events() if row['tool'] == 'api_request' and row['status'] == 'succeeded']
        return json.loads(rows[-1]['detail'])['evidence']


class NumbersAreExact(Base):
    """Acceptance 1."""

    def test_the_ai_receives_the_raw_response_unchanged_and_its_numbers_match(self):
        result, script = self.work({'tool_calls': [tool_call('c1', 'api_request', **READ)]}, summary_from_tool)
        handed = tool_results(script.bodies[1])[-1]
        self.assertEqual(handed['data'], self.api.raw())
        for row in self.api.raw()['holdings']:
            for field in ('quantity', 'average_price', 'market_value'):
                self.assertIn(str(row[field]), result.content)
        self.assertEqual(result.outcome, 'succeeded')

    def test_derived_sums_are_exact_decimals_kept_apart_from_the_raw_data(self):
        result = self.caps().execute('api_request', READ)
        derived = result['provenance']['derived'][0]
        self.assertEqual(derived['value'], '1092300.3')
        self.assertTrue(derived['matches'])
        # A binary float sum is not exact; the derived value is a decimal sum of the values as returned.
        record = provenance({'parts': [0.1, 0.2], 'total': 0.3}, status=200, headers={},
                            retrieved_at=datetime.now(timezone.utc),
                            checks=[{'sum': '$.parts[*]', 'equals': '$.total'}])
        self.assertNotEqual(0.1 + 0.2, 0.3)
        self.assertEqual((record['derived'][0]['value'], record['derived'][0]['matches']), ('0.3', True))
        self.assertEqual(result['provenance']['completeness'], 'complete')
        self.assertEqual(result['data'], self.api.raw())

    def test_selection_is_the_rfc9535_subset(self):
        data = {'a': [{'b': 1}, {'c': 2}], 'd': {'e': 'x'}}
        self.assertEqual(select(data, '$.a[*].b')[0], 1)
        self.assertEqual(select(data, '$.a[1].c'), [2])
        self.assertEqual(select(data, '$.d.e'), ['x'])
        with self.assertRaises(ApiError):
            select(data, 'a.b')
        with self.assertRaises(ApiError):
            select(data, '$..b')


class FlagsAreNotHidden(Base):
    """Acceptance 2: the AI's answer omits every flag; the owner's report still carries it."""

    def flagged(self, fault=None, args=READ, qualifier=None):
        """The scripted judgment accepts the answer; AgentOS's own disclosure still names the flag."""
        self.api.fault = fault
        result, _script = self.work({'tool_calls': [tool_call('c1', 'api_request', **args)]}, summary_from_tool)
        self.assertNotIn(QUALIFIER_NOTES[qualifier], result.content)
        lines = work_disclosures([(row['tool'], row['status'], row['detail']) for row in self.events()])
        self.assertTrue(any(QUALIFIER_NOTES[qualifier] in line and f'{HOST}{HOLDINGS_PATH}' in line for line in lines), lines)
        self.assertIn((('api_request', QUALIFIER_NOTES[qualifier])), list(result.incomplete))
        return result

    def test_stale_data_is_reported_as_stale(self):
        self.flagged('stale', qualifier='stale')
        evidence = self.evidence()
        self.assertEqual(evidence['freshness'], 'stale')
        self.assertIn('stale', evidence['qualifiers'])

    def test_a_total_that_does_not_add_up_is_reported_as_inconsistent(self):
        self.flagged('mismatch', qualifier='inconsistent')
        evidence = self.evidence()
        self.assertEqual(evidence['completeness'], 'inconsistent')
        self.assertIs(evidence['derived'][0]['matches'], False)

    def test_a_partial_response_is_reported_as_partial(self):
        self.flagged('partial', qualifier='partial')
        evidence = self.evidence()
        self.assertEqual(evidence['completeness'], 'partial')
        self.assertIn('$.holdings[*].market_value', evidence['missing_fields'])

    def test_an_unknown_reference_time_is_reported_as_unknown(self):
        args = {key: value for key, value in READ.items() if key != 'as_of_field'}
        self.flagged(None, args=args, qualifier='as-of-unknown')
        evidence = self.evidence()
        self.assertEqual((evidence['freshness'], evidence['as_of']), ('unknown', None))

    def test_a_last_modified_header_is_a_reference_time_and_a_future_time_is_not_believed(self):
        caps = self.caps()
        args = {key: value for key, value in READ.items() if key != 'as_of_field'}
        original = self.api.__call__

        def with_header(method, url, headers, body, timeout):
            status, response_headers, raw = original(method, url, headers, body, timeout)
            return status, {**response_headers, 'last-modified': 'Fri, 09 Oct 2026 00:58:00 GMT'}, raw
        with mock.patch('personal_agent.api_requests.http_request', with_header):
            caps._api = None
            caps.api().clock = self.clock
            result = caps.execute('api_request', args)
        self.assertEqual((result['provenance']['as_of_source'], result['provenance']['freshness']), ('header:last-modified', 'fresh'))
        ahead = self.api.raw()
        ahead['as_of'] = datetime.fromtimestamp(self.clock.now + 86400, timezone.utc).isoformat()
        with mock.patch('personal_agent.api_requests.http_request',
                        lambda *a: (200, {}, json.dumps(ahead).encode())):
            result = self.caps().execute('api_request', READ)
        self.assertEqual(result['provenance']['as_of_source'], 'future-time-not-believed')
        self.assertIn('as-of-unknown', evidence_qualifiers(result))

    def test_another_accounts_response_is_withheld(self):
        self.api.fault = 'other_account'
        with self.assertRaises(ToolError) as refused:
            self.caps().execute('api_request', READ)
        self.assertEqual(refused.exception.code, 'api_subject_mismatch')
        self.assertNotIn('ACC-2002', str(refused.exception))
        result, script = self.work({'tool_calls': [tool_call('c1', 'api_request', **READ)]}, {'content': '확인 못 함'})
        handed = json.dumps(tool_results(script.bodies[1]))
        for value in ('ACC-2002', '520800.1', 'Alpha'):
            self.assertNotIn(value, handed)
        failed = [json.loads(row['detail']) for row in self.events() if row['tool'] == 'api_request' and row['status'] == 'failed']
        self.assertEqual([row['code'] for row in failed], ['api_subject_mismatch'])

    def test_a_rejected_key_is_reported_not_retried(self):
        self.api.fault = 'no_auth'
        with self.assertRaises(ToolError) as refused:
            self.caps().execute('api_request', READ)
        self.assertEqual((refused.exception.code, refused.exception.requires), ('api_unauthorized', 'api-slot:fake-holdings'))
        self.assertEqual(len(self.api.calls), 1)


class SecretStaysOut(Base):
    """Acceptance 3."""

    def test_the_key_reaches_only_the_bound_host_header(self):
        caps = self.caps()
        caps.execute('api_request', READ)
        self.assertEqual(self.api.calls[0]['headers']['Authorization'], f'Bearer {self.key}')
        definitions = json.dumps(caps.definitions(), ensure_ascii=False)
        self.assertIn('api_request', definitions)
        self.assertNotIn(self.key, definitions)
        self.assertNotIn(self.key, context_line(self.store))

    def test_no_prompt_log_or_evidence_carries_the_key_even_when_the_api_echoes_it(self):
        original = self.api.__call__

        def echoing(method, url, headers, body, timeout):
            status, response_headers, raw = original(method, url, headers, body, timeout)
            data = json.loads(raw)
            data['debug'] = {'received': headers.get('Authorization')}
            return status, response_headers, json.dumps(data).encode()
        logs = []
        handler = logging.Handler()
        handler.emit = lambda record: logs.append(record.getMessage())
        logging.getLogger().addHandler(handler)
        self.addCleanup(logging.getLogger().removeHandler, handler)
        with mock.patch('personal_agent.api_requests.http_request', echoing):
            result, script = self.work({'tool_calls': [tool_call('c1', 'api_request', **READ)]}, summary_from_tool)
        prompts = json.dumps(script.bodies, ensure_ascii=False)
        self.assertNotIn(self.key, prompts)
        self.assertIn('Bearer [redacted]', prompts)
        self.assertNotIn(self.key, json.dumps(self.events(), ensure_ascii=False))
        self.assertNotIn(self.key, result.content)
        self.assertNotIn(self.key, '\n'.join(logs))
        self.assertNotIn(self.key.encode(), (Path(self.store.root) / 'agentos.db').read_bytes()
                         if (Path(self.store.root) / 'agentos.db').exists() else b'')
        for path in Path(self.store.root).glob('*.db'):
            self.assertNotIn(self.key.encode(), path.read_bytes())

    def test_an_escaped_echo_of_a_key_is_scrubbed_after_decoding(self):
        key = 'fk_' + 'a"b\\c' + fake_key()
        save_slot(self.store, 'fake-holdings', [HOST], key, subject_field='$.account_id', subject_value=ACCOUNT)
        self.api.key = key
        original = self.api.__call__

        def escaping(method, url, headers, body, timeout):
            status, response_headers, raw = original(method, url, headers, body, timeout)
            data = json.loads(raw)
            data['debug'] = headers.get('Authorization')
            return status, response_headers, json.dumps(data, ensure_ascii=True).encode()
        with mock.patch('personal_agent.api_requests.http_request', escaping):
            result = self.caps().execute('api_request', READ)
        self.assertNotIn(key, json.dumps(result, ensure_ascii=False))
        self.assertEqual(result['data']['debug'], 'Bearer [redacted]')

    def test_the_stored_secret_redactor_covers_slot_secrets_and_memory_refuses_them(self):
        self.assertEqual(redact_known_secrets(self.store, f'key={self.key}'), 'key=[redacted]')
        self.assertTrue(memory_value_has_secret(self.store, self.key))
        remove_slot(self.store, 'fake-holdings')
        self.assertEqual(self.store.secret('api_slot:fake-holdings'), '')
        self.assertEqual(slots(self.store), {})

    def test_a_credential_never_leaves_its_bound_hosts(self):
        caps = self.caps()
        for url in ('https://other.fake.test/v1/holdings', f'http://{HOST}{HOLDINGS_PATH}',
                    f'https://user@{HOST}{HOLDINGS_PATH}', f'https://{HOST}:8443{HOLDINGS_PATH}'):
            with self.subTest(url=url), self.assertRaises(ToolError) as refused:
                caps.execute('api_request', {**READ, 'url': url})
            self.assertEqual(refused.exception.code, 'api_host_not_allowed')
        self.assertEqual(self.api.calls, [])

    def test_a_redirect_is_not_followed(self):
        def redirecting(method, url, headers, body, timeout):
            return 302, {'location': 'https://elsewhere.fake.test/'}, b''
        with mock.patch('personal_agent.api_requests.http_request', redirecting):
            with self.assertRaises(ToolError) as refused:
                self.caps().execute('api_request', READ)
        self.assertEqual(refused.exception.code, 'api_redirect_refused')

    def test_plain_http_is_allowed_only_on_this_computer(self):
        save_slot(self.store, 'local', ['127.0.0.1:8765'], fake_key())
        self.assertEqual(slots(self.store)['local']['hosts'], ['127.0.0.1:8765'])
        requests = ApiRequests(self.store, self.job_id, transport=lambda *a: (200, {}, b'{}'))
        self.assertEqual(requests.call({'slot': 'local', 'url': 'http://127.0.0.1:8765/x', 'effect': 'read'})['data'], {})


class LoopbackTransport(unittest.TestCase):
    """The default stdlib transport against the fake API served on this computer (no mock of the wire)."""

    def test_a_real_http_read_and_an_error_status(self):
        from fake_holdings_api import serve
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'data')
        key = fake_key()
        fixed = time.time()
        api = FakeHoldingsApi(key, now=lambda: fixed)
        server = serve(api, 0)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]
        save_slot(store, 'local', [f'127.0.0.1:{port}'], key, subject_field='$.account_id', subject_value=ACCOUNT)
        result = ApiRequests(store, 'w').call({'slot': 'local', 'url': f'http://127.0.0.1:{port}{HOLDINGS_PATH}',
                                               'effect': 'read', 'as_of_field': '$.as_of'})
        self.assertEqual(result['data'], api.raw())
        self.assertEqual(result['provenance']['freshness'], 'fresh')
        self.assertEqual(api.calls[0]['headers'].get('Authorization'), f'Bearer {key}')
        with self.assertRaises(ApiError) as missing:
            ApiRequests(store, 'w').call({'slot': 'local', 'url': f'http://127.0.0.1:{port}/nowhere', 'effect': 'read'})
        self.assertEqual(missing.exception.code, 'api_error')


class NoDuplicateEffect(Base):
    """Acceptance 4."""

    def test_a_timed_out_read_is_retried_once_within_the_call(self):
        self.api.fault = 'timeout_once'
        result = self.caps().execute('api_request', READ)
        self.assertEqual((len(self.api.calls), result['provenance']['attempts']), (2, 2))

    def test_the_same_read_twice_in_one_work_runs_once(self):
        result, _script = self.work({'tool_calls': [tool_call('c1', 'api_request', **READ)]},
                                   {'tool_calls': [tool_call('c2', 'api_request', **READ)]}, summary_from_tool)
        self.assertEqual(len(self.api.calls), 1)

    def test_an_approved_order_is_sent_once_with_an_idempotency_key_and_never_replayed(self):
        caps = self.caps()
        with self.assertRaises(ToolError):
            caps.execute('api_request', ORDER)
        self.approvals.approve_last()
        caps.execute('api_request', ORDER)
        self.assertEqual(len(self.api.orders), 1)
        self.assertTrue(re.fullmatch(r'[0-9a-f]{32}', self.api.orders[0]['idempotency_key']))
        with self.assertRaises(ToolError) as again:
            caps.execute('api_request', ORDER)
        self.assertEqual(again.exception.code, 'approval_required')
        self.assertEqual(len(self.api.orders), 1)

    def test_a_timed_out_order_is_an_unknown_effect_and_is_not_retried(self):
        self.api.fault = 'timeout_once'
        caps = self.caps()
        with self.assertRaises(ToolError):
            caps.execute('api_request', ORDER)
        self.approvals.approve_last()
        with self.assertRaises(ToolError) as unknown:
            caps.execute('api_request', ORDER)
        self.assertEqual(unknown.exception.code, 'effect_unknown')
        self.assertEqual(classify_failure(unknown.exception, 'api_request'), ('effect_unknown', 'never', 'unknown'))
        self.assertEqual((len(self.api.calls), self.api.orders), (1, []))


class ReviewFixes(Base):
    """Independent review of #1218."""

    def test_the_ai_can_only_tighten_the_freshness_bound(self):
        self.api.fault = 'stale'
        result = self.caps().execute('api_request', {**READ, 'max_age_seconds': str(31 * 86400)})
        self.assertEqual((result['provenance']['max_age_seconds'], result['provenance']['freshness']), (15 * 60, 'stale'))

    def test_a_sent_change_for_another_subject_returns_no_body(self):
        caps = self.caps()
        with self.assertRaises(ToolError):
            caps.execute('api_request', ORDER)
        self.approvals.approve_last()
        result = caps.execute('api_request', ORDER)
        self.assertEqual(len(self.api.orders), 1)
        self.assertIsNone(result['data'])
        self.assertFalse(result['provenance']['subject_verified'])

    def test_the_service_issues_and_spends_an_api_step_approval_once(self):
        from personal_agent.browser_session import step_binding
        from personal_agent.quickstart_service import AgentService
        service = AgentService(self.store)
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='partial' WHERE id=?", (self.job_id,))
        job = self.store.job(self.job_id)
        approvals = service.browser_approvals_for(job)
        binding = step_binding(self.job_id, 'api_request', ORDER['url'], 'fake-holdings|POST|' + ORDER['url'],
                               argument=ORDER['body'], state='fake-holdings@1|mutate')
        self.assertFalse(approvals.consume(binding))
        approvals.request(binding, 'POST order')
        self.assertTrue(service._decide_browser_step(self.job_id, True)['approved'])
        self.assertTrue(approvals.consume(binding))
        self.assertFalse(approvals.consume(binding))


class AuditAndReferenceTime(Base):
    """Acceptance 5."""

    def test_the_audit_names_the_slot_host_and_reference_time_and_evidence_keeps_no_payload(self):
        self.work({'tool_calls': [tool_call('c1', 'api_request', **READ)]}, summary_from_tool)
        audit = information_use.work_information_use(self.store, self.job_id)
        text = json.dumps(audit, ensure_ascii=False)
        self.assertIn('인증 API', text)
        self.assertIn(f'fake-holdings → {HOST}{HOLDINGS_PATH}', text)
        as_of = self.api.raw()['as_of']
        evidence = self.evidence()
        self.assertEqual(evidence['as_of'], as_of.replace('+00:00', 'Z'))
        self.assertIn(evidence['as_of'], text)
        self.assertEqual(evidence['retrieved_at'], '2026-10-09T01:00:00Z')
        self.assertEqual(evidence['source'], {'slot': 'fake-holdings', 'host': HOST, 'path': HOLDINGS_PATH, 'method': 'GET'})
        self.assertTrue(evidence['subject_verified'])
        self.assertRegex(evidence['content_digest'], r'^[0-9a-f]{32}$')
        for payload in ('AAA', 'Alpha', '520800.1', ACCOUNT):
            self.assertNotIn(payload, json.dumps(evidence))


class ReadIsNotOrder(Base):
    """Acceptance 6."""

    def test_mutate_and_payment_are_refused_without_approval_and_nothing_is_sent(self):
        caps = self.caps()
        for effect in ('mutate', 'payment'):
            with self.subTest(effect=effect), self.assertRaises(ToolError) as refused:
                caps.execute('api_request', {**ORDER, 'effect': effect})
            self.assertEqual((refused.exception.code, refused.exception.requires), ('approval_required', 'api-step-approval'))
        self.assertEqual((self.api.calls, self.api.orders), ([], []))
        self.assertIn(f'POST {HOST}{ORDERS_PATH} (fake-holdings, mutate)', self.approvals.requested[0][1])

    def test_a_non_get_declared_read_is_still_an_order(self):
        self.assertEqual(effective_effect('POST', 'read'), 'mutate')
        self.assertEqual(effective_effect('GET', 'payment'), 'payment')
        self.assertEqual(effective_effect('GET', None), 'mutate')
        with self.assertRaises(ToolError) as refused:
            self.caps().execute('api_request', {**ORDER, 'effect': 'read'})
        self.assertEqual(refused.exception.code, 'approval_required')
        self.assertEqual(self.api.orders, [])

    def test_an_approval_covers_exactly_one_call(self):
        caps = self.caps()
        with self.assertRaises(ToolError):
            caps.execute('api_request', ORDER)
        self.approvals.approve_last()
        changed = {**ORDER, 'body': json.dumps({'symbol': 'AAA', 'side': 'buy', 'quantity': 100})}
        with self.assertRaises(ToolError):
            caps.execute('api_request', changed)
        with self.assertRaises(ToolError):
            caps.execute('api_request', {**ORDER, 'url': ORDER['url'] + '?account=other'})
        self.assertEqual(self.api.orders, [])

    def test_no_approval_surface_refuses_every_order(self):
        caps = Capabilities(self.store, None, {}, '', self.job_id, self.record)
        with self.assertRaises(ToolError):
            caps.execute('api_request', ORDER)
        self.assertEqual(self.api.calls, [])

    def test_read_only_and_unconfigured_surfaces_do_not_offer_the_tool(self):
        names = lambda caps: {d['function']['name'] for d in caps.definitions()}
        self.assertIn('api_request', names(self.caps()))
        self.assertNotIn('api_request', names(self.caps(readonly=True)))
        remove_slot(self.store, 'fake-holdings')
        self.assertNotIn('api_request', names(self.caps()))

    def test_a_read_call_is_not_an_effect_for_retry_safety(self):
        from personal_agent.quickstart_service import AgentService
        self.work({'tool_calls': [tool_call('c1', 'api_request', **READ)]}, summary_from_tool)
        rows = [row for row in self.events() if row['tool'] == 'api_request']
        self.assertTrue(rows)
        self.assertEqual(set().union(*(AgentService.effect_calls({'tool': row['tool'], 'trace': json.loads(row['detail'])})
                                       for row in rows)), set())
        self.assertEqual(AgentService.effect_calls({'tool': 'api_request', 'trace': {'host_action': 'api_request',
                                                                                   'declared_effect': 'mutate'}}),
                         {'api_request'})


class BoundedWatch(Base):
    """A 3-run bounded watch notifies only when the observed data changed (#719 watch, unchanged)."""

    def test_three_runs_notify_on_the_first_and_on_a_change_only(self):
        preparations = prep.Preparations(self.store, clock=self.clock)
        start = self.clock.now
        row = preparations.create(kind=prep.KIND_PREPARE, goal='자산 요약이 바뀌면 알려줘', due_at=start, timezone='Asia/Seoul',
                                  recurrence=None, channel='telegram', created_from=self.job_id, state=prep.STATE_SCHEDULED,
                                  accepted_by='owner-request', window=(3600, start + 3 * 3600, 3),
                                  delivery_mode=prep.DELIVERY_WHEN_NEEDED)
        decisions = []
        for run, shift in enumerate((0, 0, 5000)):
            self.api.price_shift = shift
            self.clock.now = start + run * 3600 + 1
            row = preparations.get(row['id'])
            work = preparations.start(row, channel='telegram', chat_id='42', now=self.clock.now)
            self.assertIsNotNone(work)
            self.job_id = work
            result, _script = self.work({'tool_calls': [tool_call(f'c{run}', 'api_request', **READ)]}, summary_from_tool)
            with self.store.db() as db:
                db.execute("UPDATE jobs SET status=?,response=?,delivery='none' WHERE id=?", (result.outcome, result.content, work))
            settled = preparations.settle(preparations.get(row['id']), self.clock.now,
                                          decide=lambda _row, _answer: 'yes', notify_to=('42', 1))
            decisions.append((settled['last_decision'], settled['last_decision_reason']))
            if settled['last_decision'] == prep.DECISION_NOTIFY:
                preparations.record_notified(work, prep.text_digest(result.content), result.content, self.clock.now)
        self.assertEqual(decisions, [(prep.DECISION_NOTIFY, prep.REASON_JUDGED_NEEDED),
                                     (prep.DECISION_QUIET, prep.REASON_UNCHANGED),
                                     (prep.DECISION_NOTIFY, prep.REASON_JUDGED_NEEDED)])
        with self.store.db() as db:
            queued = db.execute('SELECT count(*) FROM telegram_notifications WHERE kind=?', (prep.NOTIFY_KIND,)).fetchone()[0]
        self.assertEqual(queued, 2)
        self.assertEqual(len(self.api.calls), 3)
        self.assertEqual(preparations.get(row['id'])['state'], prep.STATE_DELIVERED)


class ServiceRoute(unittest.TestCase):
    """The real service worker (``AgentService.run_one``) on the web and Telegram entry points."""

    import test_agency_loop as _loop
    CHANNELS = _loop.OwnerEntryPointTests.CHANNELS
    service = _loop.OwnerEntryPointTests.service
    run_turn = _loop.OwnerEntryPointTests.run_turn

    def turn(self, fault, route):
        key = fake_key()
        api = FakeHoldingsApi(key, now=time.time, fault=fault)
        original = self.service

        def service(script, network):
            built, store = original(script, network)
            save_slot(store, 'fake-holdings', [HOST], key, subject_field='$.account_id', subject_value=ACCOUNT)
            return built, store
        self.service = service
        script = self._loop.Script({'tool_calls': [tool_call('1', 'api_request', **READ)]}, summary_from_tool,
                                   self._loop.finish_observed('f', summary='요약했습니다.'))
        with mock.patch('personal_agent.api_requests.http_request', api):
            row, _failed = self.run_turn('현재 자산 요약해줘', script, self._loop.Network(), route,
                                         engine=self._loop.goal_engine(True))
        return row, api, key, script

    def test_a_stale_answer_the_judgment_accepted_still_says_it_is_stale(self):
        for route in self.CHANNELS:
            with self.subTest(route=route[0]):
                row, api, key, script = self.turn('stale', route)
                self.assertIn(QUALIFIER_NOTES['stale'], row['response'])
                self.assertIn(api.raw()['as_of'].replace('+00:00', 'Z')[:16], row['response'])
                for holding in api.raw()['holdings']:
                    self.assertIn(str(holding['market_value']), row['response'])
                self.assertNotIn(key, json.dumps(script.bodies, ensure_ascii=False))
                self.assertNotIn(key, row['response'])

    def test_a_fresh_complete_answer_is_unchanged(self):
        row, api, _key, _script = self.turn(None, self.CHANNELS[0])
        self.assertEqual(row['status'], 'succeeded')
        self.assertNotIn('참고:', row['response'])


class OwnerVariations(Base):
    """The three owner variations travel the existing Memory path to the worker's context (no new store)."""

    def test_currency_items_and_frequency_reach_the_worker_prompt(self):
        values = {'profile.preference.display_currency': 'KRW',
                  'profile.preference.asset_summary_items': '총액, 종목별 평가금액, 현금',
                  'profile.preference.alert_frequency': '하루 한 번, 바뀌었을 때만'}
        for key, value in values.items():
            self.store.save_memory(key, value)
        snapshot = MemoryService(self.store, private_read_sink=MemoryService.NO_EGRESS_GUARD).profile_snapshot('local-owner')['text']
        prompt = render_turn_prompt(turn_context([{'role': 'user', 'content': '현재 자산 요약해줘'}], 'api',
                                                 profile=snapshot, current_context=context_line(self.store)))
        for key, value in values.items():
            self.assertIn(f'{key}: {value}', prompt)
        self.assertIn('fake-holdings (broker.fake.test)', prompt)


class DomainFree(unittest.TestCase):
    """C16: the new core module names no domain, site or provider; the existing guard scans it too."""

    def test_the_core_module_has_no_domain_words(self):
        text = (SRC / 'api_requests.py').read_text().lower()
        for word in ('stock', 'portfolio', 'holding', 'broker', 'securit', 'invest', 'trade',
                     '증권', '주식', '종목', '계좌', '투자'):
            self.assertNotIn(word, text, word)

    def test_the_no_scenario_guard_scans_the_module(self):
        import test_no_scenario_code
        self.assertIn('api_requests.py', test_no_scenario_code.SCANNED_MODULES)


if __name__ == '__main__':
    unittest.main()

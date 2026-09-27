"""SEC-CLI-01 (#701): the secretary loop on the owner's subscription CLI route.

Evidence classes, named separately:

* unit (model-free, temporary stores): the deterministic legacy-provenance
  backfill over synthetic pre-#605 rows, the native-search gate, the CLI argv
  and bridge tool lists of native-search turns (#705: earlier conversation
  never turns native search off, on both CLI routes), the search-off tool note, the
  local prompt-envelope storage and its exclusion from export, Settings'
  per-route agency line;
* model-free integration through the real stdio MCP bridge subprocess (the
  exact per-turn command AgentOS writes) and the service-side browser relay,
  with the fake page driver: mediation, the label-independent payment guard
  and its approvals (web decision and Telegram ``p7w:`` buttons), the repeat
  key, the loopback refusal; strict and isolated routes offer no browser;
* one integration through the same bridge with the real embedded WebKit
  worker (macOS with PyObjC only).

No live model, CLI or owner credential is used.  No site, provider or
category is named in ``src``; the fixture site is the test's own.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from personal_agent import browser_session as bs
from personal_agent import mcp_bridge
from personal_agent.agent_runtime import (BROWSER_ACTIONS, ENGINE_UNMEDIATED, HISTORY_PREFIX, OWNER_CONVERSATION,
                                          WORK_SOURCES_BACKFILL_KEY, WORK_SOURCES_KEY, backfill_work_sources, base_label,
                                          history_provenance, legacy_work_sources)
from personal_agent.bounded_execution import (AgentOSMcpTools, BoundedExecutionAdapter, ExecutionResult,
                                              ReadOnlyAgentOSMcpTools, StrictIsolatedAgentOSMcpTools, BOUNDED_PROFILE,
                                              STRICT_PROFILE, profile_actions)
from personal_agent.cli_browser_relay import BrowserRelay, RelayClient
from personal_agent.isolated_mcp_proxy import TaskCapabilityRegistry
from personal_agent.portable_state import export_owner_state
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines

from test_browser_session import ORIGIN, PASSWORD, OTP, TOKEN, PASSPORT, PAGES, FakeDriver, FixtureHandler

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
CHAT, GENERATION = 42, 'gen-701'
CARD = '4111111111111111'


def _call(ident, name, **arguments):
    return {"jsonrpc": "2.0", "id": ident, "method": "tools/call", "params": {"name": name, "arguments": arguments}}


def _value(reply):
    return json.loads(reply["result"]["content"][0]["text"])


def flat(value):
    return json.dumps(value, ensure_ascii=False)


def inherited_private(labels):
    """The #605 history labels (without route prefixes) other than clean owner conversation.

    What still closes AgentOS-composed third-party lookups and keeps a turn
    record to size and digest; since #705 it never turns the CLI's own search off.
    """
    return sorted({base_label(label) for label in labels} - {OWNER_CONVERSATION, ENGINE_UNMEDIATED})


# ---------------------------------------------------------------- legacy provenance backfill

def _legacy_work(store, text, reply, events=(('subscription_engine', 'succeeded', {}),), created=None, status='succeeded'):
    """One pre-#605 Work as it sits in an owner store: job, two messages, its tool events, no source record."""
    job = str(uuid.uuid4())
    created = created if created is not None else time.time() - 3600
    with store.db() as db:
        db.execute('INSERT INTO jobs(id,request_key,message,channel,chat_id,status,response,error,delivery,provider,model,created) '
                   'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', (job, 'legacy-' + job, text, 'web', None, status, reply, None, 'none',
                                                         'subscription', 'codex', created))
        db.execute('INSERT INTO messages(role,content,channel,created,job_id) VALUES (?,?,?,?,?)', ('user', text, 'web', created, job))
        db.execute('INSERT INTO messages(role,content,channel,created,job_id) VALUES (?,?,?,?,?)',
                   ('assistant', reply, 'web', created + 1, job))
        for tool, state, detail in events:
            db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                       (job, tool, state, json.dumps(detail), created))
    return job


class LegacyProvenanceBackfill(unittest.TestCase):
    """Fix 1: pre-#605 Works are classified from durable signals only, once, and recorded."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.service = AgentService(self.store, browser_profile=bs.BrowserProfile(Path(tmp.name) / 'b', available=lambda: False))

    def rows(self, *jobs):
        return [{'job_id': job} for job in jobs]

    def test_clean_legacy_history_no_longer_reads_as_private(self):
        base = time.time() - 5000
        clean = [_legacy_work(self.store, f'질문 {n}', f'답 {n}', created=base + n * 10) for n in range(4)]
        before = history_provenance(self.store, self.rows(*clean))
        self.assertEqual(inherited_private(before), ['unrecorded'], 'unknown history before the backfill')
        self.assertEqual(self.service.backfill_legacy_work_sources(), 4)
        records = self.store.config(WORK_SOURCES_KEY, {})
        for job in clean:
            self.assertIn(OWNER_CONVERSATION, records[job])
            self.assertIn(ENGINE_UNMEDIATED, records[job], 'a CLI reply keeps the unmediated-read label')
            self.assertNotIn(HISTORY_PREFIX + 'unrecorded', records[job])
        after = history_provenance(self.store, self.rows(*clean))
        self.assertEqual(inherited_private(after), [])
        self.assertEqual(self.service.backfill_legacy_work_sources(), 0, 'recorded once; later turns read the records')

    def test_a_legacy_work_that_used_notes_stays_private_and_taints_what_it_was_shown_to(self):
        base = time.time() - 5000
        clean = _legacy_work(self.store, '안녕', '안녕하세요', created=base)
        notes = _legacy_work(self.store, '메모 보여줘', 'PRIVATE-NOTE', created=base + 10,
                             events=(('list_notes', 'succeeded', {'host_action': 'list_notes'}),
                                     ('subscription_engine', 'succeeded', {})))
        later = _legacy_work(self.store, '고마워', '천만에요', created=base + 20)
        self.service.backfill_legacy_work_sources()
        records = self.store.config(WORK_SOURCES_KEY, {})
        self.assertNotIn(notes, records, 'a private legacy Work is never recorded as clean')
        self.assertIn(clean, records)
        self.assertIn(HISTORY_PREFIX + 'unrecorded', records[later], 'the next Work was shown the notes reply')
        self.assertEqual(inherited_private(history_provenance(self.store, self.rows(notes))), ['unrecorded'])
        self.assertTrue(inherited_private(history_provenance(self.store, self.rows(later))))
        self.assertEqual(inherited_private(history_provenance(self.store, self.rows(clean))), [])

    def test_every_private_signal_keeps_a_legacy_work_private(self):
        """No judgment: document job, context attachment, saved note, notes summary, rule reply, turn record, unfinished."""
        tools = {}
        document = _legacy_work(self.store, '문서 요약', 'doc', created=1)
        attached = _legacy_work(self.store, '이 컨텍스트로', 'ctx', created=2)
        noted = _legacy_work(self.store, '/note 비밀', '저장했습니다', created=3)
        summary = _legacy_work(self.store, '/summarize', '요약', created=4)
        rule = _legacy_work(self.store, '/notes', 'NOTE-A', created=5, events=())
        recorded_private = _legacy_work(self.store, '드라이브 요약', 'drive', created=6)
        running = _legacy_work(self.store, '진행 중', '...', created=7, status='running')
        clean = _legacy_work(self.store, '날씨', '맑음', created=8, events=(('model', 'requested', {}),))
        with self.store.db() as db:
            db.execute('INSERT INTO context_job_attachments VALUES (?,?,?,?,?)', (attached, '[]', 'a', 1, 1))
            db.execute('INSERT INTO notes VALUES (?,?,?)', (noted, '비밀', 1))
        self.store.put_turn_provenance(recorded_private, {'prompt_withheld': ['connected-drive-file']})
        for job in (document, attached, noted, summary, rule, recorded_private, running):
            self.assertIsNone(legacy_work_sources(self.store, job, tools, {document}), job)
        self.assertEqual(legacy_work_sources(self.store, clean, tools, {document}), {OWNER_CONVERSATION})
        # Record-only labels of a #570 turn record do not make it private; the pre-#605
        # `conversation-history` flag only says earlier conversation was shown (resolved
        # through the window), but a private store in the record does.
        self.store.put_turn_provenance(clean, {'prompt_withheld': ['owner-memory', 'unrecorded', 'engine-unmediated-read'],
                                               'egress_taint': ['conversation-history', 'history:owner-conversation']})
        self.assertEqual(legacy_work_sources(self.store, clean, tools, {document}), {OWNER_CONVERSATION})
        self.store.put_turn_provenance(clean, {'egress_taint': ['conversation-history', 'history:personal-space']})
        self.assertIsNone(legacy_work_sources(self.store, clean, tools, {document}))
        # A rule reply is clean only for the owner-explicit greeting (AgentOS's own parser).
        greeting = _legacy_work(self.store, '/start', '안녕하세요', created=9, events=())
        self.assertEqual(legacy_work_sources(self.store, greeting, tools, set()), {OWNER_CONVERSATION})

    def test_recorded_history_unrecorded_is_resolved_once_the_window_is_clean(self):
        """A post-#605 record that inherited ``history:unrecorded`` from clean legacy Works is narrowed to their labels."""
        base = time.time() - 5000
        legacy = [_legacy_work(self.store, f'old {n}', f'old answer {n}', created=base + n) for n in range(3)]
        current = _legacy_work(self.store, 'new', 'new answer', created=base + 100)
        self.store.put(WORK_SOURCES_KEY, {current: ['engine-unmediated-read', 'history:owner-conversation',
                                                    'history:unrecorded', 'owner-conversation']})
        self.assertEqual(inherited_private(history_provenance(self.store, self.rows(current))), ['unrecorded'])
        self.service.backfill_legacy_work_sources()
        record = self.store.config(WORK_SOURCES_KEY, {})[current]
        self.assertNotIn('history:unrecorded', record)
        self.assertIn('history:engine-unmediated-read', record)
        self.assertEqual(inherited_private(history_provenance(self.store, self.rows(*legacy, current))), [])
        self.assertTrue(self.store.config(WORK_SOURCES_BACKFILL_KEY)['version'])

    def test_a_recorded_work_newer_than_a_private_legacy_work_keeps_its_unknown_history(self):
        base = time.time() - 5000
        private = _legacy_work(self.store, 'notes', 'NOTE', created=base, events=())
        current = _legacy_work(self.store, 'new', 'new answer', created=base + 100)
        self.store.put(WORK_SOURCES_KEY, {current: ['history:unrecorded', 'owner-conversation']})
        self.assertEqual(backfill_work_sources(self.store), {}, 'nothing can be resolved or recorded')
        self.assertNotIn(private, self.store.config(WORK_SOURCES_KEY, {}))


class NullWorkIdRows(unittest.TestCase):
    """Codex P1 on #702: a message without a Work id (older than the job_id column) is unknown, never dropped."""

    def test_a_null_job_id_message_in_the_window_keeps_later_history_unresolved(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'state')
        service = AgentService(store, browser_profile=bs.BrowserProfile(Path(tmp.name) / 'b', available=lambda: False))
        base = time.time() - 5000
        with store.db() as db:
            db.execute('INSERT INTO messages(role,content,channel,created,job_id) VALUES (?,?,?,?,?)', ('user', 'old', 'web', base, None))
            db.execute('INSERT INTO messages(role,content,channel,created,job_id) VALUES (?,?,?,?,?)', ('assistant', 'old reply', 'web', base + 1, None))
        legacy = _legacy_work(store, '질문', '답', created=base + 10)
        current = _legacy_work(store, 'new', 'new answer', created=base + 100)
        store.put(WORK_SOURCES_KEY, {current: ['history:unrecorded', 'owner-conversation']})
        service.backfill_legacy_work_sources()
        records = store.config(WORK_SOURCES_KEY, {})
        self.assertIn(HISTORY_PREFIX + 'unrecorded', records[legacy], 'the legacy Work was shown the id-less messages')
        self.assertIn(HISTORY_PREFIX + 'unrecorded', records[current], 'nothing in its window resolves the unknown')
        rows = [{'job_id': None}, {'job_id': legacy}]
        self.assertIn('unrecorded', inherited_private(history_provenance(store, rows)))


class NativeSearchOnBackfilledHistory(unittest.TestCase):
    """Coordinator scope: history of only engine-unmediated-read and backfilled-clean messages keeps native search on."""

    def test_the_cli_turn_searches_natively_and_is_offered_no_bridge_search(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'state')
        seen = {}

        class Cli:
            def execute(self, engine, prompt, tools, **kwargs):
                seen['native'] = tools.native_search
                seen['names'] = [tool['name'] for tool in tools.definitions()]
                return ExecutionResult('engine answer', engine, 0)

        service = AgentService(store, subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/codex', clock=lambda: 1),
                               execution_adapter=Cli(),
                               browser_profile=bs.BrowserProfile(Path(tmp.name) / 'b', launcher=lambda d, h: None))
        service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        base = time.time() - 5000
        for n in range(6):
            _legacy_work(store, f'예전 질문 {n}', f'예전 답 {n}', created=base + n)
        job = store.enqueue('오후 6시에 골프장까지 가는 길 알려줘', 'k-native')
        self.assertTrue(service.run_one())
        record = store.turn_provenance(job)
        self.assertTrue(seen['native'], record.get('native_search_reason'))
        self.assertEqual(record['cli_native_tools'], ['web_search'])
        self.assertIsNone(record.get('native_search_reason'))
        self.assertFalse({'web_search', 'bounded_public_research', 'list_notes'} & set(seen['names']))
        self.assertTrue(BROWSER_ACTIONS <= set(seen['names']), 'the browser tools stay on a native-search turn')
        self.assertNotIn('prompt_withheld', record, 'unrecorded/unmediated history no longer withholds the local envelope')


# ---------------------------------------------------------------- native-search argv and bridge lists

class _TurnCapture(BoundedExecutionAdapter):
    """The real per-turn argv and bridge configuration, with a fake CLI process (#705).

    ``execute`` is the production adapter's; only the process is replaced, so
    the captured argv, bridge arguments and offered tool list are exactly what
    a CLI would get on this turn.
    """

    def __init__(self, root, seen):
        self.seen = seen
        super().__init__(finder=lambda name: '/runtime/' + name, runner=self.process, runtime_root=root / 'turns',
                         codex_home=root)

    def login_status(self, engine_id, binary=None):
        return {'state': 'signed-in'}

    def execute(self, engine_id, prompt, tools, **kwargs):
        self.seen['listed'] = [tool['name'] for tool in tools.definitions()]
        return super().execute(engine_id, prompt, tools, **kwargs)

    def process(self, argv, **kwargs):
        self.seen['argv'] = list(argv)
        if argv[1] == 'exec':
            value = next(item for item in argv if item.startswith('mcp_servers.agentos.args='))
            self.seen['bridge'] = json.loads(value.split('=', 1)[1])
            stdout = json.dumps({'item': {'type': 'agent_message', 'text': 'engine answer'}})
        else:
            config = json.loads(Path(argv[argv.index('--mcp-config') + 1]).read_text())
            self.seen['bridge'] = config['mcpServers']['agentos']['args']
            stdout = json.dumps({'result': 'engine answer'})
        return type('Done', (), {'returncode': 0, 'stdout': stdout, 'stderr': ''})()


#: #705 history kinds: how each is seeded, and the #605 label it still passes to the bridge.
HISTORY_KINDS = ('notes-work', 'codex-list-notes', 'unrecorded', ENGINE_UNMEDIATED, 'owner-browser-session')
HISTORY_LABEL = {'notes-work': 'personal-space', 'codex-list-notes': 'personal-space', 'unrecorded': 'unrecorded',
                 ENGINE_UNMEDIATED: ENGINE_UNMEDIATED, 'owner-browser-session': 'owner-browser-session'}
PRIVATE_READS = {'list_notes', 'web_search', 'bounded_public_research'}


class HistoryNeverTurnsNativeSearchOff(unittest.TestCase):
    """#705 (owner direction, pilot posture): prior conversation never turns the CLI's own search off.

    Only this turn's own splices, the strict or isolated profile and a
    remembered CLI refusal do.  The private-read bridge tools stay withheld
    on a native-search turn, and the #605 history labels still reach the
    bridge (AgentOS-composed third-party lookups) and the turn record.
    Both CLI routes, through the production argv and bridge configuration.
    """

    def service(self, engine):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.store = QuickStore(root / 'state')
        self.seen = {}
        service = AgentService(self.store, subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/cli', clock=lambda: 1),
                               execution_adapter=_TurnCapture(root, self.seen),
                               browser_profile=bs.BrowserProfile(root / 'b', available=lambda: False))
        self.store.put('subscription_engine', {'id': engine, 'connected_at': 0})
        return service

    def seed(self, kind):
        """One earlier Work of ``kind`` plus a clean one after it, as they sit in an owner store."""
        base = time.time() - 5000
        records = {}
        if kind == 'notes-work':
            job = _legacy_work(self.store, '/summarize', 'NOTE-705 요약', created=base)
            records[job] = ['owner-conversation', 'personal-space']
        elif kind == 'codex-list-notes':
            # What the bridge records for a CLI-chosen list_notes (mcp_bridge.serve).
            job = _legacy_work(self.store, '메모 보고 답해줘', 'NOTE-705', created=base,
                               events=(('list_notes', 'succeeded', {'scope': 'subscription-mcp-bridge', 'host_action': 'list_notes'}),
                                       ('subscription_engine', 'succeeded', {})))
            records[job] = [ENGINE_UNMEDIATED, 'owner-conversation']
        elif kind == 'unrecorded':
            # Id-less rows and a rule-handled legacy reply: both stay unrecorded after the backfill.
            with self.store.db() as db:
                db.execute('INSERT INTO messages(role,content,channel,created,job_id) VALUES (?,?,?,?,?)', ('user', 'old', 'web', base - 5, None))
                db.execute('INSERT INTO messages(role,content,channel,created,job_id) VALUES (?,?,?,?,?)', ('assistant', 'NOTE-705', 'web', base - 4, None))
            job = _legacy_work(self.store, '/notes', 'NOTE-705', created=base, events=())
        elif kind == ENGINE_UNMEDIATED:
            job = _legacy_work(self.store, '이 폴더 봐줘', 'host file answer', created=base)
            records[job] = [ENGINE_UNMEDIATED, 'owner-conversation']
        else:
            job = _legacy_work(self.store, '장바구니 확인해줘', 'cart page', created=base,
                               events=(('browser_read', 'succeeded', {'scope': 'subscription-mcp-bridge', 'host_action': 'browser_read'}),
                                       ('subscription_engine', 'succeeded', {})))
            records[job] = [ENGINE_UNMEDIATED, 'owner-conversation']
        if records:
            self.store.put(WORK_SOURCES_KEY, records)
        return job

    def run_turn(self, service, text):
        job = self.store.enqueue(text, 'k-' + str(uuid.uuid4()))
        self.assertTrue(service.run_one())
        self.assertEqual(self.store.job(job)['status'], 'succeeded', self.store.job(job).get('error'))
        return job, self.store.turn_provenance(job)

    def assert_native(self, engine, record):
        argv, bridge, listed = self.seen['argv'], self.seen['bridge'], set(self.seen['listed'])
        self.assertIsNone(record.get('native_search_reason'))
        self.assertEqual(record['cli_native_tools'], ['web_search'])
        self.assertIn('--native-search', bridge)
        self.assertFalse([arg for arg in bridge if arg.startswith('--search-off-reason')])
        self.assertFalse(PRIVATE_READS & listed, 'private reads and bridge search stay withheld')
        if engine == 'codex':
            self.assertIn('web_search="live"', argv)
        else:
            self.assertEqual(argv[argv.index('--tools') + 1], 'WebSearch')
            allowed = argv[argv.index('--allowedTools') + 1].split(',')
            self.assertIn('WebSearch', allowed)
            self.assertFalse({'mcp__agentos__' + name for name in PRIVATE_READS} & set(allowed))

    def assert_off(self, engine, record, reason):
        argv, bridge = self.seen['argv'], self.seen['bridge']
        self.assertEqual(record.get('native_search_reason'), reason)
        self.assertEqual(record['cli_native_tools'], [])
        self.assertNotIn('--native-search', bridge)
        self.assertIn('--search-off-reason=' + reason, bridge)
        self.assertIn('list_notes', self.seen['listed'], 'a search-off turn may read notes')
        if engine == 'codex':
            self.assertIn('web_search="disabled"', argv)
        else:
            self.assertNotIn('--tools', argv)
            self.assertNotIn('WebSearch', argv[argv.index('--allowedTools') + 1].split(','))

    def test_no_history_kind_turns_native_search_off_on_either_cli(self):
        for engine in ('codex', 'claude-code'):
            for kind in HISTORY_KINDS:
                with self.subTest(engine=engine, history=kind):
                    service = self.service(engine)
                    self.seed(kind)
                    later, record = self.run_turn(service, '오늘 서울 날씨 알려줘')
                    self.assert_native(engine, record)
                    label = HISTORY_PREFIX + HISTORY_LABEL[kind]
                    # #605 inheritance is unchanged: the label reaches the bridge's own
                    # (AgentOS-composed) lookups and this Work's source record.
                    self.assertIn('--provenance=' + label, self.seen['bridge'])
                    self.assertIn(label, self.store.config(WORK_SOURCES_KEY, {})[later])
                    if HISTORY_LABEL[kind] in ('personal-space', 'owner-browser-session'):
                        # ...and a turn that carried a private store keeps size and digest only.
                        self.assertIn(HISTORY_LABEL[kind], record.get('prompt_withheld') or [])

    def test_codex_own_list_notes_turns_search_off_for_that_turn_only(self):
        service = self.service('codex')
        with self.store.db() as db:
            db.execute('INSERT INTO notes VALUES (?,?,?)', ('n1', 'NOTE-705', 1))
        notes, record = self.run_turn(service, '/summarize')
        self.assert_off('codex', record, 'private_turn')
        # The CLI itself reads notes on a later search-off turn: recorded by the bridge.
        with self.store.db() as db:
            db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                       (notes, 'list_notes', 'succeeded',
                        json.dumps({'scope': 'subscription-mcp-bridge', 'host_action': 'list_notes'}), time.time()))
        for _ in range(3):
            _later, record = self.run_turn(service, '다음 질문')
            self.assert_native('codex', record)
            self.assertIn('--provenance=history:personal-space', self.seen['bridge'])

    def test_the_current_turns_own_splice_still_turns_it_off_on_either_cli(self):
        for engine in ('codex', 'claude-code'):
            with self.subTest(engine=engine):
                service = self.service(engine)
                with self.store.db() as db:
                    db.execute('INSERT INTO notes VALUES (?,?,?)', ('n1', 'NOTE-705', 1))
                _job, record = self.run_turn(service, '/summarize')
                self.assert_off(engine, record, 'private_turn')
                _job, record = self.run_turn(service, '오늘 서울 날씨 알려줘')
                self.assert_native(engine, record)

    def test_a_remembered_cli_refusal_still_turns_it_off(self):
        from personal_agent.search_providers import ProviderRegistry
        for engine in ('codex', 'claude-code'):
            with self.subTest(engine=engine):
                service = self.service(engine)
                ProviderRegistry.from_store(self.store).record_native(engine, engine, 'unavailable', 'refused')
                _job, record = self.run_turn(service, '오늘 서울 날씨 알려줘')
                self.assert_off(engine, record, 'refused')

    def test_strict_and_isolated_profiles_never_enable_it_whatever_the_history(self):
        test = self

        class Cli:
            def execute(self, engine, prompt, tools, **kwargs):
                test.seen['native'] = tools.native_search
                return ExecutionResult('engine answer', engine, 0)

        class Sidecar:
            def issue_task_token(self, **kwargs):
                import secrets
                return secrets.token_urlsafe(32)

            def execute(self, **kwargs):
                test.seen['sidecar'] = True
                return 'engine answer'

        for isolated in (False, True):
            with self.subTest(isolated=isolated):
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                self.store = QuickStore(Path(tmp.name) / 'state')
                self.seen = {}
                options = {'isolated_engine_adapter': Sidecar(), 'isolated_mcp_registry': TaskCapabilityRegistry()} if isolated else {}
                service = AgentService(self.store, subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/codex', clock=lambda: 1),
                                       execution_adapter=Cli(), browser_profile=bs.BrowserProfile(Path(tmp.name) / 'b', available=lambda: False),
                                       **options)
                self.store.put('subscription_engine', {'id': 'codex', 'connected_at': 0})
                if not isolated:
                    self.store.put('subscription_isolation', {'profile': STRICT_PROFILE, 'qualified': {}})
                self.seed(ENGINE_UNMEDIATED)
                job = self.store.enqueue('오늘 서울 날씨 알려줘', 'k-strict')
                self.assertTrue(service.run_one())
                record = self.store.turn_provenance(job)
                self.assertEqual(record.get('native_search_reason'), 'strict_profile')
                self.assertEqual(record.get('cli_native_tools'), [])
                self.assertTrue(self.seen.get('sidecar') if isolated else self.seen['native'] is False)
        service = self.service('codex')
        for profile, isolated in ((STRICT_PROFILE, False), (BOUNDED_PROFILE, True)):
            self.assertEqual(service.cli_native_search('codex', profile, isolated, set()), (False, 'strict_profile'))
        adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name)
        config = Path(tempfile.mkdtemp()) / 'agentos-mcp.json'
        self.addCleanup(lambda: config.unlink(missing_ok=True))
        config.write_text(json.dumps({'mcpServers': {'agentos': {'command': sys.executable, 'args': ['-m', 'x']}}}))
        strict = adapter.command('claude-code', '/runtime/claude', 'prompt', config, 'instructions', profile=STRICT_PROFILE,
                                 native_search=True)
        self.assertEqual(strict[strict.index('--tools') + 1], '', 'no built-in tool, WebSearch included')
        self.assertNotIn('WebSearch', strict[strict.index('--allowedTools') + 1].split(','))


class NativeSearchTurnArgv(unittest.TestCase):
    """Fix 2: on a native-search turn the CLI gets its own search and no bridge search, for both CLIs."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config = Path(tmp.name) / 'agentos-mcp.json'
        self.config.write_text(json.dumps({'mcpServers': {'agentos': {'command': sys.executable, 'args': ['-m', 'x']}}}))
        self.adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runtime_root=Path(tmp.name) / 'turns')

    def test_codex_turns_live_search_and_its_bridge_lists_no_search_tool(self):
        argv = self.adapter.command('codex', '/runtime/codex', 'prompt', self.config, native_search=True)
        self.assertIn('web_search="live"', argv)
        caps = _caps(browser=lambda: None)
        listed = [tool['name'] for tool in AgentOSMcpTools(caps, native_search=True).definitions()]
        self.assertFalse({'web_search', 'bounded_public_research', 'list_notes'} & set(listed))
        self.assertTrue(BROWSER_ACTIONS <= set(listed))
        off = [tool['name'] for tool in AgentOSMcpTools(caps).definitions()]
        self.assertTrue({'web_search', 'bounded_public_research', 'list_notes'} <= set(off), 'a search-off turn keeps them')

    def test_claude_code_pre_approves_websearch_and_no_bridge_search(self):
        argv = self.adapter.command('claude-code', '/runtime/claude', 'prompt', self.config, 'instructions', native_search=True)
        allowed = argv[argv.index('--allowedTools') + 1].split(',')
        self.assertIn('WebSearch', allowed)
        self.assertNotIn('mcp__agentos__web_search', allowed)
        self.assertNotIn('mcp__agentos__bounded_public_research', allowed)
        self.assertNotIn('mcp__agentos__list_notes', allowed)
        self.assertIn('mcp__agentos__browser_open', allowed)
        self.assertEqual(argv[argv.index('--tools') + 1], 'WebSearch')
        off = self.adapter.command('claude-code', '/runtime/claude', 'prompt', self.config, 'instructions')
        self.assertIn('mcp__agentos__web_search', off[off.index('--allowedTools') + 1].split(','))

    def test_a_search_off_turn_names_why_and_the_providers_own_caveat(self):
        from personal_agent.search_providers import ProviderRegistry
        network = type('Network', (), {'providers': ProviderRegistry.from_config({'bing_enabled': True, 'native': {'subscription': 'codex'}})})()
        caps = _caps(network=network)
        tools = AgentOSMcpTools(caps)
        tools.native_search_reason = 'private_turn'
        described = {tool['name']: tool['description'] for tool in tools.definitions()}
        for name in ('web_search', 'bounded_public_research'):
            self.assertIn("The CLI's own web search is off for this turn", described[name])
            self.assertIn('개인 자료', described[name], 'the owner-facing reason')
            self.assertIn('bing = Bing web search', described[name])
            self.assertIn('poor or off-topic for Korean', described[name], "the provider's own caveat")
        self.assertNotIn('off for this turn', described['save_note'])


def _caps(**kwargs):
    from personal_agent.agent_runtime import Capabilities
    store = QuickStore(tempfile.mkdtemp())
    return Capabilities(store, None, {}, '', 'job', lambda *a: None, document_access=False, **kwargs)


# ---------------------------------------------------------------- browser tools through the bridge (fake driver)

class _BridgeHarness(unittest.TestCase):
    """A service whose scripted CLI speaks to the exact configured bridge while the Work runs."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.store = QuickStore(self.tmp / 'state')
        self.pending, self.replies, self.turns, self.servers = None, None, 0, []
        self.driver_log, self.drivers, self.calls = [], [], []

        class Done:
            returncode = 0
            stdout = json.dumps({"item": {"type": "agent_message", "text": "engine answer"}})

        adapter = None

        def runner(argv, **kwargs):
            config = json.loads((Path(kwargs["cwd"]) / "agentos-mcp.json").read_text())
            self.server = config["mcpServers"]["agentos"]
            self.servers.append(self.server)
            self.argv = argv
            self.env = adapter.environment("codex", "/runtime/codex", Path(kwargs["cwd"]))
            if self.pending is not None:
                self.replies = self.run_bridge(self.server["args"], self.pending)
            return Done()

        def launcher(profile_dir, headless):
            driver = FakeDriver(log=self.driver_log)
            self.drivers.append(driver)
            return driver

        def transport(url, body=None, headers=None, timeout=60):
            method = url.rsplit('/', 1)[-1]
            self.calls.append((method, body))
            if method == 'sendMessage':
                return {'ok': True, 'result': {'message_id': 9000 + len(self.calls)}}
            return {'ok': True, 'result': True}

        home = self.tmp / "codex-home"
        home.mkdir()
        adapter = BoundedExecutionAdapter(finder=lambda name: "/runtime/" + name, runner=runner,
                                          runtime_root=self.tmp / "turns", codex_home=home)
        self.profile = self.make_profile(launcher)
        self.service = AgentService(self.store, adapter=ModelAdapter(lambda *a: {"choices": [{"message": {"content": "x"}}]}),
                                    telegram_transport=transport,
                                    subscription_engines=SubscriptionEngines(finder=lambda _: "/runtime/codex", clock=lambda: 1),
                                    execution_adapter=adapter, browser_profile=self.profile)
        self.service.connect_subscription_engine({"engine": "codex", "officially_authenticated": True})

    def make_profile(self, launcher):
        return bs.BrowserProfile(self.tmp / 'profile', launcher=launcher)

    def run_bridge(self, args, requests):
        env = {**self.env, **self.server.get("env", {})}
        env["HOME"] = self.env["HOME"] if Path(self.env["HOME"]).exists() else tempfile.gettempdir()
        completed = subprocess.run([self.server["command"], *args],
                                   input="".join(json.dumps(request) + "\n" for request in requests),
                                   capture_output=True, text=True, timeout=120, env=env)
        return {reply.get("id"): reply for reply in map(json.loads, completed.stdout.splitlines()) if reply}

    def wire(self, *requests, text="장바구니에 넣어줘", telegram=False, before=None):
        self.pending = (INIT, *requests)
        self.turns += 1
        job = self.store.enqueue(text, f"wire-{self.turns}")
        if before:
            before(job)
        if telegram:
            self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION, 'cursor': 0})
            with self.store.db() as db:
                db.execute('UPDATE jobs SET channel=?, chat_id=? WHERE id=?', (f'telegram:{GENERATION}', CHAT, job))
        self.job = job
        self.assertTrue(self.service.run_one())
        self.pending = None
        return self.replies

    def rerun(self, *requests):
        """Run the re-queued Work again with a new scripted CLI turn."""
        self.pending = (INIT, *requests)
        self.assertTrue(self.service.run_one())
        self.pending = None
        return self.replies

    def events(self, status=None):
        with self.store.db() as db:
            rows = db.execute('SELECT tool,status,detail FROM tool_events WHERE job_id=? ORDER BY id', (self.job,)).fetchall()
        return [(row['tool'], row['status'], json.loads(row['detail'] or '{}')) for row in rows
                if status is None or row['status'] == status]

    def scan_store(self, needle):
        hits = []
        with self.store.db() as db:
            for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                for row in db.execute(f'SELECT * FROM "{table}"'):
                    if needle in flat([str(value) for value in tuple(row)]):
                        hits.append(table)
        for path in Path(self.store.root).rglob('*'):
            if path.is_file() and needle.encode() in path.read_bytes():
                hits.append(str(path))
        return hits


LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}


class BrowserThroughTheBridge(_BridgeHarness):
    """Fix 3 with the fake driver: the browser runs in the service, the bridge relays."""

    def test_the_trusted_local_cli_lists_and_calls_the_five_browser_tools(self):
        def saved_value(job):
            # A value this Work saved to a private store (``/note`` keeps it under the Work id).
            with self.store.db() as db:
                db.execute('INSERT INTO notes VALUES (?,?,?)', (job, PASSPORT, 1))
        replies = self.wire(LIST,
                            _call(3, 'browser_open', url=ORIGIN + '/product', effect='navigate'),
                            _call(4, 'browser_find', text='12,900'),
                            _call(5, 'browser_click', target='장바구니', effect='mutate'),
                            _call(6, 'browser_read'), before=saved_value)
        args = self.server['args']
        self.assertIn('--profile=trusted-local', args)
        relay = next(arg for arg in args if arg.startswith('--browser-relay='))
        self.assertFalse(Path(relay.split('=', 1)[1]).exists(), 'the relay and its key are gone with the turn')
        names = [tool['name'] for tool in replies[2]['result']['tools']]
        self.assertTrue(BROWSER_ACTIONS <= set(names), names)
        product = _value(replies[3])
        self.assertEqual(product['state'], 'page')
        self.assertIn('세탁세제 3L', product['text'])
        self.assertIn(bs.REDACTED, product['text'], 'mediation: the saved private value is redacted')
        self.assertNotIn(PASSPORT, flat(replies))
        self.assertTrue(_value(replies[4])['found'])
        cart = _value(replies[5])
        self.assertEqual(cart['title'], '장바구니')
        self.assertIn('세탁세제 3L × 1', cart['text'])
        self.assertEqual(self.drivers[0].posts, [('post', '/cart')])
        self.assertTrue(self.drivers[0].closed, 'the session closed with the turn')
        self.assertFalse(self.profile.status()['in_use'])
        succeeded = [(tool, detail.get('scope'), detail.get('host_action')) for tool, _s, detail in self.events('succeeded')
                     if tool in BROWSER_ACTIONS]
        self.assertEqual(succeeded, [('browser_open', 'subscription-mcp-bridge', 'browser_open'),
                                     ('browser_find', 'subscription-mcp-bridge', 'browser_find'),
                                     ('browser_click', 'subscription-mcp-bridge', 'browser_click'),
                                     ('browser_read', 'subscription-mcp-bridge', 'browser_read')])
        # The Work now carries the browser-session source (read through the bridge).
        self.assertIn('owner-browser-session', mcp_bridge._recorded_private_sources(self.store, self.job))

    def test_mediation_never_returns_credentials_or_saved_values(self):
        replies = self.wire(_call(2, 'browser_open', url=ORIGIN + '/account', effect='read'))
        account = _value(replies[2])
        for secret in (PASSWORD, OTP, TOKEN):
            self.assertNotIn(secret, flat(account))
        for secret in (PASSWORD, OTP, TOKEN):
            self.assertEqual(self.scan_store(secret), [], secret)

    def test_the_payment_guard_holds_whatever_the_label_and_the_web_approval_resumes_once(self):
        replies = self.wire(_call(2, 'browser_open', url=ORIGIN + '/checkout', effect='navigate'),
                            _call(3, 'browser_type', target='카드번호', text=CARD, effect='navigate'))
        refused = replies[3]['result']
        self.assertTrue(refused['isError'])
        self.assertEqual(refused['structuredContent']['code'], 'approval_required')
        self.assertIn('결제 단계는 승인이 필요합니다', refused['content'][0]['text'])
        self.assertEqual([entry for entry in self.driver_log if entry[0] == 'type'], [], 'nothing was typed')
        pending = self.service.browser_status()['pending_steps']
        self.assertEqual([(row['work_id'], row['action'], row['state']) for row in pending],
                         [(self.job, 'browser_type', 'requested')])
        self.assertIn(self.store.job(self.job)['status'], ('failed', 'partial'))
        self.assertEqual(self.scan_store(CARD), [], 'the card number is kept nowhere')
        decision = self.service.browser_step_decision({'work_id': self.job, 'decision': 'approve'})
        self.assertEqual(decision, {'approved': True, 'resumed': True, 'work_id': self.job})
        replies = self.rerun(_call(2, 'browser_open', url=ORIGIN + '/checkout', effect='navigate'),
                             _call(3, 'browser_type', target='카드번호', text=CARD, effect='mutate'),
                             _call(4, 'browser_click', target='결제하기', effect='navigate'))
        self.assertNotIn('isError', replies[3]['result'])
        self.assertEqual(len([entry for entry in self.driver_log if entry[0] == 'type']), 1, 'the approved step ran once')
        self.assertEqual(replies[4]['result']['structuredContent']['code'], 'approval_required', 'the submit asks again')
        with self.store.db() as db:
            states = [row['state'] for row in db.execute("SELECT state FROM memory_approvals WHERE action='browser-step'")]
        self.assertEqual(states, ['consumed'])
        self.assertEqual(self.scan_store(CARD), [])

    def test_the_telegram_buttons_bind_the_cli_step(self):
        self.wire(_call(2, 'browser_open', url=ORIGIN + '/checkout', effect='navigate'),
                  _call(3, 'browser_type', target='카드번호', text=CARD, effect='mutate'), telegram=True)
        self.assertTrue(self.service.deliver_notification())
        prompts = [body for method, body in self.calls if method == 'sendMessage' and body.get('reply_markup')
                   and 'p7w:' in flat(body['reply_markup'])]
        self.assertEqual(len(prompts), 1)
        self.assertNotIn('4111', prompts[0]['text'])
        buttons = prompts[0]['reply_markup']['inline_keyboard'][0]
        notification_id = buttons[0]['callback_data'].split(':')[1]
        row = self.store.notification(notification_id)
        self.service.ingest_callback({'id': 'cb', 'from': {'id': CHAT}, 'data': f'p7w:{notification_id}:approve',
                                      'message': {'message_id': row['message_id'], 'chat': {'id': CHAT, 'type': 'private'}}},
                                     GENERATION)
        self.assertEqual(self.store.job(self.job)['status'], 'queued')
        self.assertEqual(self.service._browser_request(self.job)['state'], 'issued')

    def test_the_same_page_step_is_not_repeated_and_the_loopback_is_refused(self):
        replies = self.wire(_call(2, 'browser_open', url='http://127.0.0.1:8765/api/state', effect='read'),
                            _call(3, 'browser_open', url='http://localhost/', effect='read'),
                            _call(4, 'browser_open', url=ORIGIN + '/product', effect='navigate'),
                            _call(5, 'browser_type', target='검색어', text='세제', effect='mutate'),
                            _call(6, 'browser_type', target='검색어', text='세제', effect='mutate'),
                            _call(7, 'browser_type', target='검색어', text='세제', effect='mutate'))
        for ident in (2, 3):
            self.assertEqual(replies[ident]['result']['structuredContent']['code'], 'blocked_destination', ident)
        self.assertEqual([entry for entry in self.driver_log if entry[0] == 'goto' and 'fixture' not in entry[1]], [],
                         'no driver ever loaded this computer')
        # As on the direct route (#657): the page a step acts on is the page the last
        # result showed, so the second identical step acts on the changed page (the
        # typed value) and runs; the third, on that same page, is refused.
        self.assertNotIn('isError', replies[5]['result'])
        self.assertNotIn('isError', replies[6]['result'])
        self.assertEqual(replies[7]['result']['structuredContent']['code'], 'repeat_path')
        self.assertEqual(len([entry for entry in self.driver_log if entry[0] == 'type']), 2)

    def test_the_relay_refuses_a_wrong_key_another_tool_and_an_ended_turn(self):
        self.wire(LIST)
        args = list(self.server['args'])
        # After the turn the relay is gone: the bridge refuses (the Work ended) and a direct client cannot connect.
        after = self.run_bridge(args, (INIT, _call(2, 'browser_read')))
        self.assertTrue(after[2]['result']['isError'] if 'result' in after[2] else True)
        relay = next(arg for arg in args if arg.startswith('--browser-relay=')).split('=', 1)[1]
        with self.assertRaises(Exception):
            RelayClient(relay).call('browser_read', {})

        class Tools:
            PROFILE = BOUNDED_PROFILE
            capabilities = type('C', (), {'tools': {'browser_read': {'host_action': 'browser_read'},
                                                    'list_notes': {'host_action': 'list_notes'}}})()
            calls = []

            def call(self, name, arguments):
                self.calls.append(name)
                return {'state': 'page', 'url': 'x', 'title': 't', 'text': '', 'elements': []}

        tools = Tools()
        live = BrowserRelay(tools)
        try:
            client = RelayClient(live.address)
            self.assertEqual(client.call('browser_read', {})['state'], 'page')
            with self.assertRaises(Exception):
                client.call('list_notes', {})
            (Path(live.address) / 'key').write_text('0' * 64)
            with self.assertRaises(Exception) as caught:
                client.call('browser_read', {})
            self.assertEqual(getattr(caught.exception, 'code', None), 'relay_refused')
            self.assertEqual(tools.calls, ['browser_read'], 'nothing else ran')
            self.assertEqual(oct(Path(live.address).stat().st_mode & 0o777), '0o700')
        finally:
            live.close()


class NoBrowserOffStrictOrIsolated(unittest.TestCase):
    """Fix 3 negative: strict-isolated and isolated routes never offer or relay a browser tool."""

    def test_the_strict_bridge_lists_no_browser_even_when_handed_a_relay(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'state')
        job = store.enqueue('x', 'k')
        with store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job,))

        class Tools:
            capabilities = type('C', (), {'tools': {'browser_read': {'host_action': 'browser_read'}}})()

            def call(self, name, arguments):
                raise AssertionError('never reached')

        live = BrowserRelay(Tools())
        self.addCleanup(live.close)
        for profile in (STRICT_PROFILE, 'unknown-profile'):
            out = io.StringIO()
            requests = [INIT, LIST, _call(3, 'browser_read')]
            with mock.patch.object(sys, 'stdin', io.StringIO(''.join(json.dumps(r) + '\n' for r in requests))), \
                 contextlib.redirect_stdout(out):
                mcp_bridge.serve(str(store.root), job, profile=profile, browser_relay=live.address)
            replies = {reply['id']: reply for reply in map(json.loads, out.getvalue().splitlines())}
            names = [tool['name'] for tool in replies[2]['result']['tools']]
            self.assertFalse(BROWSER_ACTIONS & set(names), profile)
            self.assertIn('error', replies[3], profile)

    def test_the_adapter_never_hands_the_strict_bridge_a_relay_and_isolated_declares_none(self):
        self.assertFalse(BROWSER_ACTIONS & set(profile_actions(STRICT_PROFILE)))
        self.assertFalse(BROWSER_ACTIONS & set(profile_actions(ReadOnlyAgentOSMcpTools.PROFILE)))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        seen = {}
        original = Path.write_text

        def capture(path, text, *args, **kwargs):
            if path.name == 'agentos-mcp.json':
                seen['config'] = json.loads(text)
            return original(path, text, *args, **kwargs)

        adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=lambda *a, **k: None,
                                          runtime_root=Path(tmp.name) / 'turns', codex_home=Path(tmp.name))
        caps = _caps(browser=lambda: None)
        strict = StrictIsolatedAgentOSMcpTools(caps, qualification=None)
        strict.browser_relay = '/somewhere'
        with mock.patch.object(Path, 'write_text', capture), self.assertRaises(Exception):
            adapter.execute('codex', 'prompt', strict)   # unqualified: refused after the config is written
        args = seen['config']['mcpServers']['agentos']['args']
        self.assertIn('--profile=strict-isolated', args)
        self.assertFalse([arg for arg in args if arg.startswith('--browser-relay')])
        self.assertFalse(BROWSER_ACTIONS & {tool['name'] for tool in strict.definitions()})

    def test_the_service_gives_the_strict_route_no_browser(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'state')
        seen = {}

        class Cli:
            def execute(self, engine, prompt, tools, **kwargs):
                seen['profile'] = tools.PROFILE
                seen['relay'] = tools.browser_relay
                seen['browser'] = tools.capabilities.browser
                seen['names'] = [tool['name'] for tool in tools.definitions()]
                return ExecutionResult('answer', engine, 0)

        service = AgentService(store, subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/codex', clock=lambda: 1),
                               execution_adapter=Cli(),
                               browser_profile=bs.BrowserProfile(Path(tmp.name) / 'b', launcher=lambda d, h: None))
        service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        store.put('subscription_isolation', {'profile': STRICT_PROFILE, 'qualified': {}})
        store.enqueue('장바구니에 넣어줘', 'k-strict')
        self.assertTrue(service.run_one())
        self.assertEqual(seen['profile'], STRICT_PROFILE)
        self.assertIsNone(seen['relay'])
        self.assertIsNone(seen['browser'])
        self.assertFalse(BROWSER_ACTIONS & set(seen['names']))


# ---------------------------------------------------------------- one real-worker run through the bridge

# Real WebKit windows and real Keychain items open on the owner's screen, so these
# tests run only when explicitly requested: AGENTOS_REAL_BROWSER_TESTS=1.
REAL_BROWSER_TESTS = __import__('os').environ.get('AGENTOS_REAL_BROWSER_TESTS') == '1'


def _webkit_ready():
    return REAL_BROWSER_TESTS and bs.webkit_unavailable_reason() is None


@unittest.skipUnless(_webkit_ready(), 'embedded WebKit needs macOS with pyobjc-framework-WebKit')
class RealWorkerThroughTheBridge(_BridgeHarness):
    """Evidence class: model-free integration, real bridge subprocess + real WebKit worker + fixture site."""

    def make_profile(self, launcher):
        from personal_agent.browser_jar import JAR_NAME, CookieJar, MemoryKey
        self.site = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
        self.site.posts = []
        threading.Thread(target=self.site.serve_forever, daemon=True).start()
        self.addCleanup(self.site.server_close)
        self.addCleanup(self.site.shutdown)
        self.fixture = f'127.0.0.1:{self.site.server_address[1]}'
        directory = self.tmp / 'profile'
        profile = bs.BrowserProfile(directory, jar=CookieJar(directory / JAR_NAME, MemoryKey()))
        # Test-only: the fixture origin (and only it) may be loaded from loopback.
        profile.allow_origins_for_tests(self.fixture)
        return profile

    def test_product_to_cart_and_the_payment_guard_through_the_bridge(self):
        origin = 'http://' + self.fixture
        original = bs.BrowserSession.__init__

        def allow_fixture(session, *args, **kwargs):
            original(session, *args, **{**kwargs, 'allowed_origins_for_tests': (self.fixture,)})
        with mock.patch.object(bs.BrowserSession, '__init__', allow_fixture):
            replies = self.wire(_call(2, 'browser_open', url=origin + '/product', effect='navigate'),
                                _call(3, 'browser_click', target='장바구니', effect='mutate'),
                                _call(4, 'browser_open', url=origin + '/account', effect='read'),
                                _call(5, 'browser_open', url=origin + '/checkout', effect='navigate'),
                                _call(6, 'browser_type', target='카드번호', text=CARD, effect='navigate'))
        self.assertIn('세탁세제 3L', _value(replies[2])['text'])
        cart = _value(replies[3])
        self.assertEqual(cart['title'], '장바구니')
        self.assertIn('세탁세제 3L × 1', cart['text'])
        self.assertEqual(self.site.posts, ['/cart'])
        for secret in (PASSWORD, OTP, TOKEN):
            self.assertNotIn(secret, flat(_value(replies[4])))
        self.assertEqual(replies[6]['result']['structuredContent']['code'], 'approval_required')
        self.assertEqual(self.site.posts, ['/cart'], 'no payment form was submitted')
        self.assertFalse(self.profile.status()['in_use'], 'the worker was released with the turn')


# ---------------------------------------------------------------- the local prompt envelope (pilot posture)

class PromptEnvelopeStorage(unittest.TestCase):
    """Coordinator scope: the envelope is stored locally after redaction, withheld only for private stores, never exported."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.store = QuickStore(self.tmp / 'state')
        self.service = AgentService(self.store, browser_profile=bs.BrowserProfile(self.tmp / 'b', available=lambda: False))

    def test_the_envelope_is_stored_with_secrets_and_saved_private_values_redacted(self):
        secret = 'fake-telegram-token-701-abcdef'
        self.store.secret('telegram_token', secret)
        job = self.store.enqueue('저장해줘', 'k1')
        with self.store.db() as db:
            db.execute('INSERT INTO notes VALUES (?,?,?)', (job, 'PASSPORT-M7010101', 1))
        sent = f'request with {secret} and PASSPORT-M7010101 and sk-live-ABCDEFGHIJKLMNOP1234 visible text'
        self.service.record_turn_sent(job, sent=sent, instructions='', instructions_channel='prompt',
                                      private_sources={'unrecorded', 'engine-unmediated-read', 'owner-profile',
                                                       'owner-current-context', 'owner-preparations'})
        record = self.store.turn_provenance(job)
        self.assertNotIn('prompt_withheld', record)
        self.assertIn('visible text', record['prompt_envelope'])
        for value in (secret, 'PASSPORT-M7010101', 'sk-live-ABCDEFGHIJKLMNOP1234'):
            self.assertNotIn(value, flat(record), value)

    def test_the_whole_lookup_exclusion_set_is_redacted(self):
        """Reviewer P2-3: Memory candidates, notes and calendar drafts of the Work (``lookup_sources``)."""
        job = self.store.enqueue('기억해줘', 'k-excl')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job,))
            db.execute('INSERT INTO notes VALUES (?,?,?)', (job, 'NOTE-VALUE-7011', 1))
            db.execute('INSERT INTO memory_candidates(id,job_id,memory_key,content,created,state,owner_key,work_key,content_digest) '
                       'VALUES (?,?,?,?,?,?,?,?,?)', ('c1', None, 'profile.id', 'MEMORY-VALUE-7012', 1, 'pending', 'o',
                                                      self.store._work_binding(job), 'd'))
        from personal_agent.agent_runtime import lookup_sources
        self.assertEqual(set(lookup_sources(self.store, job)['excluded']), {'NOTE-VALUE-7011', 'MEMORY-VALUE-7012'})
        self.service.record_turn_sent(job, sent='keep NOTE-VALUE-7011 and MEMORY-VALUE-7012 visible', instructions='',
                                      instructions_channel='prompt')
        envelope = self.store.turn_provenance(job)['prompt_envelope']
        self.assertIn('visible', envelope)
        self.assertNotIn('NOTE-VALUE-7011', envelope)
        self.assertNotIn('MEMORY-VALUE-7012', envelope)

    def test_a_notes_turn_still_keeps_size_and_digest_only(self):
        for label in ('personal-space', 'connected-document', 'connected-drive-file', 'owner-context-inbox',
                      'owner-memory', 'owner-calendar'):
            job = self.store.enqueue('x ' + label, 'k-' + label)
            self.service.record_turn_sent(job, sent='NOTE-CONTENT-701', instructions='', instructions_channel='prompt',
                                          private_sources={label, 'unrecorded'})
            record = self.store.turn_provenance(job)
            self.assertEqual(record['prompt_withheld'], [label])
            self.assertTrue(record['prompt_envelope'].startswith('[not stored: this turn included'))
            self.assertNotIn('NOTE-CONTENT-701', flat(record))

    def test_a_real_notes_summary_turn_is_withheld(self):
        seen = {}

        class Cli:
            def execute(self, engine, prompt, tools, **kwargs):
                seen['prompt'] = prompt
                return ExecutionResult('요약', engine, 0)

        service = AgentService(self.store, subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/codex', clock=lambda: 1),
                               execution_adapter=Cli(), browser_profile=bs.BrowserProfile(self.tmp / 'b2', available=lambda: False))
        service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        with self.store.db() as db:
            db.execute('INSERT INTO notes VALUES (?,?,?)', ('n1', 'NOTE-SUMMARY-701', 1))
        job = self.store.enqueue('/summarize', 'k-sum')
        self.assertTrue(service.run_one())
        self.assertIn('NOTE-SUMMARY-701', seen['prompt'])
        record = self.store.turn_provenance(job)
        self.assertIn('personal-space', record['prompt_withheld'])
        self.assertNotIn('NOTE-SUMMARY-701', flat(record))

    def test_export_carries_no_prompt_envelope(self):
        job = self.store.enqueue('안녕', 'k-export')
        self.service.record_turn_sent(job, sent='ENVELOPE-MARKER-701', instructions='', instructions_channel='prompt')
        self.assertIn('ENVELOPE-MARKER-701', self.store.turn_provenance(job)['prompt_envelope'])
        archive = export_owner_state(self.store.root, self.tmp / 'export.tar.gz')
        with tarfile.open(archive) as bundle:
            for member in bundle.getmembers():
                if member.isfile():
                    data = bundle.extractfile(member).read()
                    self.assertNotIn(b'ENVELOPE-MARKER-701', data, member.name)
        backup = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'scripts' / 'agentos-backup.py'),
                                 str(self.store.root), str(self.tmp / 'backup.tar.gz')],
                                capture_output=True, text=True, check=True, env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')})
        with tarfile.open(Path(backup.stdout.strip())) as bundle:
            for member in bundle.getmembers():
                if member.isfile():
                    self.assertNotIn(b'ENVELOPE-MARKER-701', bundle.extractfile(member).read(), member.name)


# ---------------------------------------------------------------- Settings: per-route agency

class SettingsAgency(unittest.TestCase):
    """Fix 4: each Main AI route says whether its own search and the browser tools are available, and why not."""

    def service(self, available=True, isolated=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'state')
        profile = bs.BrowserProfile(Path(tmp.name) / 'b', launcher=(lambda d, h: None) if available else None,
                                    available=(lambda: True) if available else (lambda: False))
        service = AgentService(store, subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/codex', clock=lambda: 1),
                               browser_profile=profile)
        if isolated:
            service.isolated_engine_adapter = object()
        return service, store

    def routes(self, service):
        return {route['id']: route for route in service.main_ai.status()['routes']}

    def test_trusted_local_cli_offers_both_and_says_when_search_turns_off(self):
        service, _store = self.service()
        codex = self.routes(service)['codex']['agency']
        self.assertTrue(codex['search']['available'])
        self.assertIn('개인 자료', codex['search']['note'])
        self.assertTrue(codex['browser']['available'])
        openai = self.routes(service)['openai']['agency']
        self.assertEqual((openai['search']['available'], openai['search']['reason']), (False, 'no_api_key'))
        self.assertTrue(openai['browser']['available'])

    def test_strict_isolated_and_unavailable_platform_name_the_reason(self):
        service, store = self.service()
        store.put('subscription_isolation', {'profile': STRICT_PROFILE, 'qualified': {}})
        codex = self.routes(service)['codex']['agency']
        self.assertEqual((codex['search']['available'], codex['search']['reason']), (False, 'strict_profile'))
        self.assertEqual((codex['browser']['available'], codex['browser']['reason']), (False, 'strict_profile'))
        self.assertTrue(codex['browser']['reason_text'])
        service, _store = self.service(isolated=True)
        codex = self.routes(service)['codex']['agency']
        self.assertEqual((codex['search']['reason'], codex['browser']['reason']), ('isolated', 'isolated'))
        service, _store = self.service(available=False)
        codex = self.routes(service)['codex']['agency']
        self.assertFalse(codex['browser']['available'])
        self.assertTrue(codex['browser']['reason_text'])

    def test_a_cli_that_cannot_run_offers_neither(self):
        """Codex P2 on #702: not installed or signed out is unavailable, with the reason."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'state')
        service = AgentService(store, subscription_engines=SubscriptionEngines(finder=lambda _: None, clock=lambda: 1),
                               browser_profile=bs.BrowserProfile(Path(tmp.name) / 'b', launcher=lambda d, h: None, available=lambda: True))
        codex = self.routes(service)['codex']
        self.assertFalse(codex['installed'])
        self.assertEqual((codex['agency']['search']['reason'], codex['agency']['browser']['reason']), ('not_installed', 'not_installed'))
        self.assertFalse(codex['agency']['browser']['available'])
        service, store = self.service()
        store.put('engine_login', {'codex': {'state': 'signed-out', 'checked_at': 1}})
        codex = self.routes(service)['codex']['agency']
        self.assertEqual((codex['search']['available'], codex['search']['reason']), (False, 'signed_out'))
        self.assertEqual((codex['browser']['available'], codex['browser']['reason']), (False, 'signed_out'))
        self.assertTrue(codex['browser']['reason_text'])

    def test_a_cli_whose_own_search_was_refused_says_so(self):
        from personal_agent.search_providers import ProviderRegistry
        service, store = self.service()
        ProviderRegistry.from_store(store).record_native('codex', 'codex', 'unavailable', 'refused')
        codex = self.routes(service)['codex']['agency']
        self.assertEqual((codex['search']['available'], codex['search']['reason']), (False, 'refused'))


if __name__ == '__main__':
    unittest.main()

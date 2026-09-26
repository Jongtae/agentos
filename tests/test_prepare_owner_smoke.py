import contextlib
import datetime
import importlib.util
import io
import json
from pathlib import Path
import shlex
import stat
import tempfile
import time
import unittest

from personal_agent.quickstart_store import QuickStore

SPEC = importlib.util.spec_from_file_location("prepare_smoke", Path(__file__).resolve().parents[1] / "scripts/prepare_owner_smoke.py")
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


class SmokeSetupTests(unittest.TestCase):
    def test_creates_only_synthetic_state_and_quoted_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "new root"
            result = smoke.prepare(root, 8788, {})
            self.assertEqual((root / "reference/launch.md").read_text(), smoke.NOTE)
            self.assertEqual(list((root / "state").iterdir()), [])
            self.assertEqual(list((root / "workspace").iterdir()), [])
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((root / "reference/launch.md").stat().st_mode), 0o600)
            self.assertEqual(shlex.split(result["start_command"])[-2:], ["--data", str(root / "state")])
            self.assertFalse(result["service_started"])
            self.assertFalse(result["private_data_copied"])
            self.assertEqual(result["provider_calls"], 0)

    def test_existing_root_not_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "keep").write_text("original")
            with self.assertRaises(FileExistsError): smoke.prepare(root, 8788, {})
            self.assertEqual(list(root.iterdir()), [root / "keep"])
            self.assertEqual((root / "keep").read_text(), "original")

    def test_inherited_state_and_integration_refused_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            for key in ("AGENTOS_DATA", "AGENTOS_DRIVE_LOCAL_ONLY", "AGENTOS_ISOLATED_ENGINE_URL", "AGENTOS_PUBLIC_ACCESS_TOKEN"):
                with self.subTest(key=key):
                    root = Path(tmp) / key
                    with self.assertRaises(ValueError) as caught:
                        smoke.prepare(root, 8788, {key: "SECRET_CANARY"})
                    self.assertNotIn("SECRET_CANARY", str(caught.exception))
                    self.assertFalse(root.exists())

    def test_bad_port_no_side_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            for port in (0, 80, 65536):
                with self.subTest(port=port):
                    root = Path(tmp) / str(port)
                    with self.assertRaises(ValueError): smoke.prepare(root, port, {})
                    self.assertFalse(root.exists())

    def test_symlink_root_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"; target.mkdir()
            root = Path(tmp) / "link"; root.symlink_to(target, target_is_directory=True)
            with self.assertRaises(FileExistsError): smoke.prepare(root, 8788, {})
            self.assertEqual(list(target.iterdir()), [])



# --- SEC-EVAL-01 (#660): probe evidence records -------------------------------

TOKEN = 'fixture-telegram-token-9f8e7d6c5b'
AT = datetime.datetime(2026, 9, 27, 9, 30, 12, tzinfo=datetime.timezone.utc)
PASSWORD = 'hunter2-correct-horse'
SAVED = '여권번호 M12345678'


def _event(store, job, tool, status, detail):
    with store.db() as db:
        db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                   (job, tool, status, json.dumps(detail, ensure_ascii=False), time.time()))


def _synthetic_probe_work(root):
    """One Work shaped like a SEC-LOOP-01 run: a search, a refused repeat, a
    provider switch, a refused browser step, a cart click and a judged done claim."""
    store = QuickStore(root)
    store.secret('telegram_token', TOKEN)
    job = store.enqueue(f'《리더는 언제 차이를 만들어내는가》 장바구니에 넣어줘 {TOKEN} {SAVED}', 'probe-a',
                        channel='telegram:g', chat_id=7)
    with store.db() as db:
        db.execute('INSERT INTO memory_candidates(id,job_id,memory_key,content,created,state,work_key) VALUES (?,?,?,?,?,?,?)',
                   ('c1', None, 'profile.passport', SAVED, time.time(), 'pending', store._work_binding(job)))
    _event(store, job, 'model', 'responded', {'scope': 'main', 'model': 'm-reported', 'requested_model': 'm-requested',
                                              'tool_calls': [], 'has_text': False})
    _event(store, job, 'web_search', 'running', {'scope': 'main', 'call_id': '1', 'attempt': 1, 'host_action': 'web_search',
                                                 'arguments': {'query': '리더는 언제 차이를 만들어내는가'}})
    _event(store, job, 'web_search', 'succeeded', {'scope': 'main', 'call_id': '1', 'attempt': 1, 'host_action': 'web_search',
                                                   'evidence': {'sources': ['https://events.example/x'], 'result_count': 1,
                                                                'provider': 'bing'}})
    _event(store, job, 'web_search', 'failed', {'scope': 'main', 'call_id': '2', 'attempt': 1, 'error': '같은 경로',
                                                'code': 'repeat_path', 'retry': 'permanent'})
    _event(store, job, 'web_search', 'running', {'scope': 'main', 'call_id': '3', 'attempt': 1, 'host_action': 'web_search',
                                                 'arguments': {'query': '리더는 언제 차이를 만들어내는가', 'provider': 'naver'},
                                                 'alternative': 'provider_switch'})
    _event(store, job, 'web_search', 'succeeded', {'scope': 'main', 'call_id': '3', 'attempt': 1, 'host_action': 'web_search',
                                                   'evidence': {'sources': ['https://books.example/42'], 'result_count': 3,
                                                                'provider': 'naver', 'locale': 'ko-KR'}})
    # An older-format running event whose typed text was not yet a placeholder.
    _event(store, job, 'browser_type', 'running', {'scope': 'main', 'call_id': '4', 'attempt': 1, 'host_action': 'browser_type',
                                                   'arguments': {'target': '3', 'text': PASSWORD, 'effect': 'mutate'}})
    _event(store, job, 'browser_type', 'failed', {'scope': 'main', 'call_id': '4', 'attempt': 1, 'code': 'approval_required',
                                                  'error': f'승인이 필요합니다 Bearer {TOKEN} /Users/owner/secret.txt',
                                                  'requires': 'approval'})
    _event(store, job, 'browser_click', 'running', {'scope': 'main', 'call_id': '5', 'attempt': 1, 'host_action': 'browser_click',
                                                    'arguments': {'target': '7', 'effect': 'mutate'}, 'alternative': 'route_change'})
    _event(store, job, 'browser_click', 'succeeded', {'scope': 'main', 'call_id': '5', 'attempt': 1, 'host_action': 'browser_click',
                                                      'evidence': {'state': 'page', 'url': 'https://shop.example/cart',
                                                                   'title': '장바구니', 'element_count': 12,
                                                                   'cookies': 'sid=abc', 'storage_state': {'k': 'v'},
                                                                   'session_token': TOKEN}})
    _event(store, job, 'model', 'claim_rejected', {'scope': 'main', 'call_id': 'f1', 'code': 'goal_not_observed',
                                                   'evidence_refs': ['1']})
    _event(store, job, 'model', 'concluded', {'scope': 'main', 'outcome': 'succeeded',
                                              'claim': {'status': 'done', 'evidence_refs': ['3', '5']},
                                              'judgment': 'yes', 'alternatives_tried': {'count': 2, 'kinds': {
                                                  'provider_switch': 1, 'route_change': 1}}, 'nudges': 1, 'unknown': 0})
    with store.db() as db:
        db.execute('UPDATE jobs SET status=?,response=?,owner_cause=?,owner_verified=? WHERE id=?',
                   ('succeeded', f'장바구니에 담았습니다. {TOKEN}', None, '장바구니 페이지: https://shop.example/cart', job))
    store.put_turn_provenance(job, {'route': 'direct-api', 'provider': 'compatible', 'status': 'answered',
                                    'prompt_envelope': f'SYSTEM {TOKEN}',
                                    'goal': {'attempts': 5, 'failed_attempts': 2, 'recovered': True, 'unresolved': [],
                                             'effect': 'none', 'outcome': 'succeeded'}})
    return store, job


class ProbeRecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / 'data'
        self.store, self.job = _synthetic_probe_work(self.data)

    def record(self, **kwargs):
        return smoke.record_probe(self.data, kwargs.pop('work', self.job), kwargs.pop('probe', 'A'),
                                  kwargs.pop('recorded_at', AT), **kwargs)

    def test_record_shows_goal_calls_alternatives_claim_judgment_outcome_and_report(self):
        record = self.record(head='49b4fac')
        self.assertEqual((record['record'], record['probe'], record['date'], record['recorded_at'], record['head']),
                         ('secretary-01-probe/1', 'A', '2026-09-27', '2026-09-27T0930Z', '49b4fac'))
        self.assertEqual(record['evidence_class'], 'owner-installation-record')
        self.assertIn('리더는 언제 차이를 만들어내는가', record['requested'])
        calls = record['tool_calls']
        self.assertEqual([row['call_id'] for row in calls], ['1', '2', '3', '4', '5'])
        self.assertEqual([row.get('status') for row in calls], ['succeeded', 'failed', 'succeeded', 'failed', 'succeeded'])
        self.assertEqual(calls[0]['provider'], 'bing')
        self.assertEqual((calls[2]['provider'], calls[2]['alternative']), ('naver', 'provider_switch'))
        self.assertEqual(calls[1]['code'], 'repeat_path')
        self.assertEqual(calls[4]['alternative'], 'route_change')
        self.assertEqual(record['alternatives_tried'], {'count': 2, 'kinds': {'provider_switch': 1, 'route_change': 1}})
        self.assertEqual(record['claim_rejections'], [{'call_id': 'f1', 'code': 'goal_not_observed', 'evidence_refs': ['1']}])
        self.assertEqual(record['finish']['status'], 'done')
        self.assertEqual(record['finish']['evidence_refs'], ['3', '5'])
        self.assertEqual([row['call_id'] for row in record['finish']['cited']], ['3', '5'])
        self.assertEqual(record['finish']['cited'][1]['evidence']['url'], 'https://shop.example/cart')
        self.assertEqual((record['goal_judgment'], record['final_outcome']), ('yes', 'succeeded'))
        self.assertEqual(record['report']['observed'], '장바구니 페이지: https://shop.example/cart')
        self.assertEqual(record['goal_summary']['attempts'], 5)
        self.assertEqual(record['provenance'], {'route': 'direct-api', 'provider': 'compatible', 'status': 'answered'})
        self.assertEqual(record['models'], [{'model': 'm-reported', 'requested_model': 'm-requested'}])
        self.assertEqual(record['checks'], {'succeeded_iff_judged_done_claim': True, 'cited_refs_all_succeeded': True,
                                            'repeat_paths_refused': 1})

    def test_record_never_carries_secrets_cookies_typed_text_or_saved_private_values(self):
        for omit in (False, True):
            with self.subTest(omit_text=omit):
                text = json.dumps(self.record(omit_text=omit), ensure_ascii=False)
                for leaked in (TOKEN, PASSWORD, 'M12345678', 'sid=abc', '"storage_state"', '"session_token"',
                               '"cookies"', '/Users/owner', 'prompt_envelope', 'SYSTEM'):
                    self.assertNotIn(leaked, text)
        record = self.record()
        self.assertEqual(record['tool_calls'][3]['arguments']['text'], f'[가림: {len(PASSWORD)}자]')
        # The saved private value (and its line's digit-bearing tokens) and the stored secret.
        self.assertEqual(record['requested'], '《리더는 언제 차이를 만들어내는가》 장바구니에 넣어줘 [가림] [가림] [가림]')
        self.assertEqual(record['report']['reply'], '장바구니에 담았습니다. [redacted]')
        self.assertIn('[경로 가림]', record['tool_calls'][3]['error'])
        self.assertEqual(record['finish']['cited'][1]['evidence'],
                         {'state': 'page', 'url': 'https://shop.example/cart', 'title': '장바구니', 'element_count': 12})

    def test_omit_text_keeps_structure_and_replaces_free_text(self):
        record = self.record(omit_text=True)
        self.assertTrue(record['requested'].startswith('[omitted: '))
        self.assertTrue(record['tool_calls'][2]['arguments']['query'].startswith('[omitted: '))
        self.assertTrue(record['report']['reply'].startswith('[omitted: '))
        # Selectors stay readable: they show which path was taken, not what was asked.
        self.assertEqual(record['tool_calls'][2]['arguments']['provider'], 'naver')
        self.assertEqual(record['tool_calls'][4]['arguments'], {'target': '7', 'effect': 'mutate'})
        self.assertEqual(record['tool_calls'][2]['provider'], 'naver')
        self.assertEqual(record['finish']['evidence_refs'], ['3', '5'])

    def test_omit_text_covers_evidence_titles_text_names_and_url_paths(self):
        """#660 review P1: evidence free text is omitted too; structure stays."""
        title = '내 계정 · 알레르기 메모'
        with self.store.db() as db:
            detail = {'scope': 'main', 'call_id': '6', 'attempt': 1, 'host_action': 'browser_read',
                      'evidence': {'state': 'page', 'url': 'https://shop.example/account/orders?id=77',
                                   'title': title, 'characters': 120, 'found': '땅콩 알레르기',
                                   'files': [{'root_id': 'r1', 'path': 'notes/allergy.md'}],
                                   'sources': ['https://blog.example/lunch/peanut-free', 'https://maps.example/'],
                                   'qualifiers': ['partial'], 'provider': 'naver', 'result_count': 2},
                      'error': f'{title} 페이지를 읽지 못했습니다'}
            for status in ('running', 'failed'):
                db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                           (self.job, 'browser_read', status, json.dumps(detail, ensure_ascii=False), time.time()))
        record = self.record(omit_text=True)
        text = json.dumps(record, ensure_ascii=False)
        for leaked in (title, '땅콩', 'account/orders', 'id=77', 'allergy.md', 'peanut-free', '장바구니 페이지',
                       'shop.example/cart', '리더는'):
            self.assertNotIn(leaked, text)
        row = record['tool_calls'][5]
        evidence = row['evidence']
        self.assertTrue(evidence['title'].startswith('[omitted: '))
        self.assertTrue(evidence['found'].startswith('[omitted: '))
        self.assertTrue(evidence['url'].startswith('https://shop.example/[omitted: '))
        self.assertTrue(evidence['files'][0]['path'].startswith('[omitted: '))
        self.assertEqual(evidence['sources'][1], 'https://maps.example/')
        self.assertTrue(row['error'].startswith('[omitted: '))
        # Structure stays readable.
        self.assertEqual((evidence['state'], evidence['provider'], evidence['qualifiers'], evidence['characters'],
                          evidence['result_count'], evidence['files'][0]['root_id']),
                         ('page', 'naver', ['partial'], 120, 2, 'r1'))
        cited = record['finish']['cited'][1]['evidence']
        self.assertEqual((cited['state'], cited['element_count']), ('page', 12))
        self.assertTrue(cited['title'].startswith('[omitted: '))
        self.assertEqual(cited['url'], 'https://shop.example/[omitted: 5 chars, sha256 '
                         + smoke.hashlib.sha256(b'/cart').hexdigest()[:16] + ']')

    def test_report_sections_are_parsed_from_the_owner_report(self):
        from personal_agent.conversation_projection import TERMINAL_UNFINISHED_LABEL, report_statement
        statement = report_statement({'failed': [['assistant', '결제는 하지 않았습니다']], 'unknown': ['재고'],
                                      'next': '장바구니를 열어 확인하기', 'question': None})
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='partial',owner_cause=? WHERE id=?",
                       (TERMINAL_UNFINISHED_LABEL + ' — 웹 검색: 결과 없음\n' + statement, self.job))
        record = self.record()
        report = record['report']
        self.assertEqual(report['failed_steps'], ['웹 검색: 결과 없음'])
        self.assertEqual(report['failed_stated'], ['결제는 하지 않았습니다'])
        self.assertEqual(report['unknown'], ['재고'])
        self.assertEqual(report['next'], ['장바구니를 열어 확인하기'])
        # A done claim judged yes with a partial outcome is flagged, not smoothed over.
        self.assertFalse(record['checks']['succeeded_iff_judged_done_claim'])

    def test_latest_selects_the_newest_work_and_bad_input_is_refused(self):
        self.assertEqual(self.record(work='latest')['work']['id'], self.job)
        with self.assertRaises(LookupError):
            self.record(work='no-such-work')
        for bad in ({'probe': 'E'}, {'recorded_at': datetime.datetime(2026, 9, 27)}, {'head': 'main'}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.record(**bad)

    def test_a_missing_store_is_refused_without_creating_one(self):
        missing = Path(self.tmp.name) / 'nowhere'
        with self.assertRaises(FileNotFoundError):
            smoke.record_probe(missing, 'latest', 'A', AT)
        self.assertFalse(missing.exists())

    def test_cli_writes_a_utc_timestamped_file_named_after_the_work(self):
        out = Path(self.tmp.name) / 'evidence'
        out.mkdir()
        argv = ['record-probe', '--data', str(self.data), '--work', self.job, '--probe', 'B', '--out-dir', str(out)]
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(smoke.main(argv), 0)
        [saved] = list(out.iterdir())
        record = json.loads(stdout.getvalue())
        work8 = self.job.replace('-', '')[:8]
        self.assertRegex(saved.name, r'^secretary-01-probe-B-\d{4}-\d{2}-\d{2}T\d{4}Z-' + work8 + r'\.json$')
        self.assertEqual(saved.name, f"secretary-01-probe-B-{record['recorded_at']}-{work8}.json")
        self.assertEqual(json.loads(saved.read_text(encoding='utf-8')), record)
        self.assertNotIn(TOKEN, saved.read_text(encoding='utf-8'))

    def test_two_records_of_one_probe_on_one_day_both_save_and_none_is_overwritten(self):
        out = Path(self.tmp.name) / 'evidence'
        out.mkdir()
        second = self.store.enqueue('내일 일정 보고 미리 알려줘', 'probe-b-2', channel='telegram:g', chat_id=7)
        first_path = smoke.write_probe_record(self.record(probe='B'), out)
        # Same probe, same day, same minute, another Work (the reminder delivery).
        second_path = smoke.write_probe_record(self.record(probe='B', work=second), out)
        # Same probe, same day, same Work, later: a new file.
        later_path = smoke.write_probe_record(
            self.record(probe='B', recorded_at=AT + datetime.timedelta(hours=3)), out)
        self.assertEqual(len({first_path, second_path, later_path}), 3)
        self.assertEqual(first_path.name, f"secretary-01-probe-B-2026-09-27T0930Z-{self.job.replace('-', '')[:8]}.json")
        self.assertTrue(later_path.name.startswith('secretary-01-probe-B-2026-09-27T1230Z-'))
        # The exact same record name again is refused, and the file is unchanged.
        before = first_path.read_text(encoding='utf-8')
        with self.assertRaises(FileExistsError):
            smoke.write_probe_record(self.record(probe='B', head='abcdef1'), out)
        self.assertEqual(first_path.read_text(encoding='utf-8'), before)

    def test_legacy_setup_invocation_is_unchanged(self):
        root = Path(self.tmp.name) / 'smoke'
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(smoke.main(['--root', str(root), '--port', '8788']), 0)
        self.assertEqual(json.loads(stdout.getvalue())['evidence'], 'synthetic_setup_only')


class ProbeRecordLoopIntegrationTests(unittest.TestCase):
    """Model-free: a real `run_agent` turn through `AgentService.run_one`
    writes the rows the recorder reads, so a format drift fails here."""

    def test_record_of_a_real_loop_run(self):
        import test_agency_loop as loop
        harness = loop.OwnerEntryPointTests('test_a_empty_rule_read_is_rejudged_by_the_loop')
        harness.addCleanup = self.addCleanup
        network = loop.ProviderNetwork({'default': loop.UNRELATED, 'other': loop.MATCHING})
        script = loop.Script({'tool_calls': [loop.call('1', 'web_search', query='When Leaders Make the Difference')]},
                             {'tool_calls': [loop.call('2', 'web_search', query='when leaders make the difference')]},
                             {'tool_calls': [loop.call('3', 'web_search', query='When Leaders Make the Difference',
                                                       provider='other')]},
                             # The provider assigns the call ids; the claim cites the refs it was shown.
                             loop.finish_observed('f', summary='2판을 찾았습니다: https://books.example/item/42'))
        row, _failed = harness.run_turn('리더 책 찾아줘', script, network, harness.CHANNELS[0],
                                        engine=loop.goal_engine(True))
        self.assertEqual(row['status'], 'succeeded')
        record = smoke.record_probe(harness._store.root, row['id'], 'D', AT)
        calls = record['tool_calls']
        self.assertEqual([(c.get('status'), c.get('code')) for c in calls],
                         [('succeeded', None), ('failed', 'repeat_path'), ('succeeded', None)])
        self.assertEqual((calls[0]['provider'], calls[2]['provider'], calls[2]['alternative']),
                         ('default', 'other', 'provider_switch'))
        self.assertEqual(record['finish']['evidence_refs'], [calls[0]['call_id'], calls[2]['call_id']])
        self.assertEqual(record['finish']['cited'][1]['evidence']['sources'], ['https://books.example/item/42'])
        self.assertEqual((record['goal_judgment'], record['final_outcome']), ('yes', 'succeeded'))
        self.assertEqual(record['alternatives_tried']['kinds'], {'provider_switch': 1})
        self.assertTrue(record['report']['reply'].startswith('2판을 찾았습니다'))
        self.assertEqual(record['checks'], {'succeeded_iff_judged_done_claim': True, 'cited_refs_all_succeeded': True,
                                            'repeat_paths_refused': 1})


if __name__ == "__main__":
    unittest.main()

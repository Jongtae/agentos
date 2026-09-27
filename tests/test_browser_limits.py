"""SEC-BROWSER-03 (#736): budgets, the Codex output bounds, clicks that navigate later, target recovery.

Evidence classes, named separately:

* unit: the raised Work budgets and their texts; the CLI output bounds
  (the final answer record vs. the whole stream, each named by its error);
  the worker's pure click-settle rule; the ``target_not_found`` element hint;
* model-free process integration: ``WebKitWorkerDriver`` + ``BrowserSession``
  over ``tests/browser_fake_worker.py``, which answers a click the way the
  real worker's ``settle_click`` does (after a delayed or new-window
  navigation landed, with ``navigated``).

No real WebKit engine is started here (the real-worker tests stay opt-in with
``AGENTOS_REAL_BROWSER_TESTS=1``).  No site, provider or task is named in src.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from personal_agent import bounded_execution as be
from personal_agent import browser_session as bs
from personal_agent import browser_worker as bw
from personal_agent.agent_runtime import WORK_ATTEMPTS_EXHAUSTED, WORK_TOOL_ATTEMPTS, ToolError, WorkBudget
from personal_agent.bounded_execution import AgentOSMcpTools, BoundedExecutionAdapter, ExecutionError

from test_bounded_execution import _Capabilities
from test_browser_session import ORIGIN, FakeDriver

FAKE_WORKER = Path(__file__).resolve().with_name('browser_fake_worker.py')


class Budgets(unittest.TestCase):
    def test_a_work_gets_forty_tool_attempts_and_forty_browser_steps(self):
        self.assertEqual((WORK_TOOL_ATTEMPTS, bs.STEPS_PER_WORK), (40, 40))
        self.assertIn('40회', WORK_ATTEMPTS_EXHAUSTED)
        self.assertIn('40회', bs.STEP_BUDGET_TEXT)
        budget = WorkBudget()
        for _ in range(40):
            budget.spend_attempt()
        with self.assertRaises(ToolError) as caught:
            budget.spend_attempt()
        self.assertEqual(caught.exception.code, 'attempt_budget')

    def test_the_forty_first_browser_step_is_refused(self):
        session = bs.BrowserSession(lambda: FakeDriver(), work_id='w')
        session.open({'url': ORIGIN + '/product', 'effect': 'read'})
        for _ in range(39):
            session.read()
        with self.assertRaises(ToolError) as caught:
            session.read()
        self.assertEqual(caught.exception.code, 'browser_step_budget')


def stream(tool_records, answer):
    lines = [json.dumps({'type': 'item.completed', 'item': {'type': 'mcp_tool_call', 'result': 'p' * size}})
             for size in tool_records]
    lines.append(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': answer}}))
    lines.append(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 1}}))
    return '\n'.join(lines)


class OutputBounds(unittest.TestCase):
    def test_a_large_tool_stream_with_a_small_final_answer_is_accepted(self):
        raw = stream([200_000] * 10, '확인한 결과입니다.')
        self.assertGreater(len(raw.encode()), be.MAX_OUTPUT_BYTES * 10)
        self.assertEqual(BoundedExecutionAdapter._content('codex', raw), '확인한 결과입니다.')

    def test_each_bound_is_named_when_hit(self):
        with self.assertRaises(ExecutionError) as caught:
            BoundedExecutionAdapter._content('codex', stream([10], 'y' * be.MAX_OUTPUT_BYTES))
        self.assertEqual(str(caught.exception), be.FINAL_RECORD_TOO_LARGE)
        self.assertIn('최종 응답 기록', be.FINAL_RECORD_TOO_LARGE)
        with self.assertRaises(ExecutionError) as caught:
            BoundedExecutionAdapter._content('codex', stream([be.MAX_STREAM_BYTES], 'ok'))
        self.assertEqual(str(caught.exception), be.STREAM_TOO_LARGE)
        self.assertIn('출력 전체', be.STREAM_TOO_LARGE)
        claude = '\n'.join([json.dumps({'type': 'user', 'content': 'q' * 300_000}),
                            json.dumps({'type': 'result', 'result': 'done', 'is_error': False})])
        self.assertEqual(BoundedExecutionAdapter._content('claude-code', claude), 'done')

    def test_the_whole_turn_succeeds_with_a_large_stream_and_names_the_bound_when_it_fails(self):
        def run(raw):
            class Done:
                returncode = 0
                stdout = raw
                stderr = ''
            with tempfile.TemporaryDirectory() as folder:
                home = Path(folder) / 'home'
                home.mkdir()
                adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=lambda argv, **kw: Done(),
                                                  runtime_root=Path(folder) / 'turns', codex_home=home)
                return adapter.execute('codex', 'hello', AgentOSMcpTools(_Capabilities()))
        self.assertEqual(run(stream([150_000] * 4, 'small answer')).content, 'small answer')
        with self.assertRaises(ExecutionError) as caught:
            run(stream([10], 'z' * (be.MAX_OUTPUT_BYTES + 10)))
        self.assertEqual((caught.exception.failure_class, str(caught.exception)), ('invalid-output', be.FINAL_RECORD_TOO_LARGE))


class ClickSettleRule(unittest.TestCase):
    def test_the_rule(self):
        grace, quiet = bw.CLICK_NAVIGATION_GRACE_SECONDS, bw.SETTLE_QUIET_SECONDS
        cases = [
            # elapsed, quiet, loading, started, landed -> settled
            ((0.5, quiet, False, False, False), False),          # a navigation may still start
            ((grace, quiet, False, False, False), True),         # none started: settled after the grace
            ((grace + 1, None, True, True, False), False),       # loading
            ((grace + 1, quiet, False, True, False), False),     # started, not landed yet
            ((0.6, quiet, False, True, True), True),             # landed and quiet: no need to wait for the grace
            ((0.6, quiet / 2, False, True, True), False),        # landed, not quiet long enough
            ((bw.CLICK_SETTLE_SECONDS, None, True, True, False), True),   # bounded
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                self.assertEqual(bw.click_settled(*args), expected)


class ClickNavigationThroughTheFakeWorker(unittest.TestCase):
    def session(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        driver = bs.WebKitWorkerDriver('p', command=[sys.executable, str(FAKE_WORKER), str(Path(folder.name) / 'log')])
        self.addCleanup(driver.close)
        return bs.BrowserSession(lambda: driver, work_id='w')

    def test_a_click_whose_navigation_starts_later_returns_the_page_it_landed_on(self):
        session = self.session()
        session.open({'url': 'https://shop.test/delayed', 'effect': 'navigate'})
        page = session.click({'target': 'Go', 'effect': 'navigate'})
        self.assertTrue(page['navigated'])
        self.assertEqual(page['url'], 'https://shop.test/landed')
        self.assertEqual(page['text'], 'landed page')

    def test_a_new_window_link_lands_in_the_same_view_and_is_reported_as_navigated(self):
        session = self.session()
        session.open({'url': 'https://shop.test/popup', 'effect': 'navigate'})
        page = session.click({'target': 'Go', 'effect': 'navigate'})
        self.assertTrue(page['navigated'])
        self.assertEqual(page['url'], 'https://shop.test/opened')

    def test_a_click_that_stays_on_the_page_is_not_reported_as_navigated(self):
        session = self.session()
        session.open({'url': 'https://shop.test/p', 'effect': 'navigate'})
        page = session.click({'target': 'Go', 'effect': 'navigate'})
        self.assertNotIn('navigated', page)


class TargetRecovery(unittest.TestCase):
    def test_target_not_found_names_the_current_elements_bounded_and_mediated(self):
        session = bs.BrowserSession(lambda: FakeDriver(), work_id='w', excluded=lambda: ['세탁세제'])
        page = session.open({'url': ORIGIN + '/product', 'effect': 'read'})
        for target in ('존재하지 않는 버튼', '999', ' '):
            with self.subTest(target=target):
                with self.assertRaises(ToolError) as caught:
                    session.click({'target': target, 'effect': 'navigate'})
                self.assertEqual(caught.exception.code, 'target_not_found')
                message = str(caught.exception)
                self.assertIn('현재 페이지의 요소: ', message)
                first = page['elements'][0]
                self.assertIn(f"{first['n']} ", message)
                self.assertNotIn('세탁세제', message.split('현재 페이지의 요소: ')[1], 'names are the mediated ones')

    def test_the_hint_is_bounded(self):
        rows = [{'n': n, 'role': 'button', 'name': '이름' * 40} for n in range(1, 40)]
        hint = bs.element_hint({'elements': rows})
        self.assertEqual(hint.count(' · '), bs.TARGET_HINT_ELEMENTS - 1)
        self.assertIn(f'외 {39 - bs.TARGET_HINT_ELEMENTS}개', hint)
        self.assertLess(len(hint), bs.TARGET_HINT_ELEMENTS * (bs.TARGET_HINT_NAME + 8) + 40)
        self.assertEqual(bs.element_hint({'elements': []}), '')


if __name__ == '__main__':
    unittest.main()

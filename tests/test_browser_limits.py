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
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from personal_agent import bounded_execution as be
from personal_agent import browser_session as bs
from personal_agent import browser_worker as bw
from personal_agent.agent_runtime import WORK_ATTEMPTS_EXHAUSTED, WORK_TOOL_ATTEMPTS, ToolError, WorkBudget
from personal_agent.bounded_execution import AgentOSMcpTools, BoundedExecutionAdapter, ExecutionError, bounded_run

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
        # A main-frame policy decision still resolving its destination is waited for (#736 review).
        cases += [
            ((grace + 1, quiet, False, False, False, True), False),
            ((bw.RESOLVE_SECONDS, quiet, False, False, False, True), False),
            ((bw.CLICK_SETTLE_SECONDS, quiet, False, False, False, True), True),   # still bounded
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                self.assertEqual(bw.click_settled(*args), expected)


class PendingPolicyDecisions(unittest.TestCase):
    """``Worker.decide`` counts a main-frame decision while its destination resolves (no WebKit needed)."""

    def test_the_counter_covers_the_resolution_and_only_main_frames(self):
        release = threading.Event()
        later = []
        stub = SimpleNamespace(resolved={}, allowed_origins=frozenset(), deciding=0,
                               AppHelper=SimpleNamespace(callAfter=lambda fn, *args: fn(*args),
                                                         callLater=lambda delay, fn: later.append(fn)))

        def slow_resolve(url, allowed):
            release.wait(5)
            return None
        decided = []
        with mock.patch.object(bw, 'destination_refusal', slow_resolve):
            bw.Worker.decide(stub, 'https://slow.example/next', True, decided.append)
            self.assertEqual(stub.deciding, 1, 'a click waits while the destination resolves')
            bw.Worker.decide(stub, 'https://frame.example/x', False, decided.append)
            self.assertEqual(stub.deciding, 1, 'a subframe decision is not a page navigation')
            release.set()
            deadline = time.monotonic() + 5
            while len(decided) < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
        self.assertEqual(sorted(decided), [True, True])
        self.assertEqual(stub.deciding, 0)
        for fn in later:   # the resolver timeout after the answer changes nothing
            fn()
        self.assertEqual(stub.deciding, 0)

    def test_a_resolver_timeout_also_ends_the_pending_decision(self):
        later = []
        stub = SimpleNamespace(resolved={}, allowed_origins=frozenset(), deciding=0,
                               AppHelper=SimpleNamespace(callAfter=lambda fn, *args: None,
                                                         callLater=lambda delay, fn: later.append(fn)))
        decided = []
        with mock.patch.object(bw, 'destination_refusal', lambda url, allowed: None):
            bw.Worker.decide(stub, 'https://slow.example/next', True, decided.append)
        self.assertEqual(stub.deciding, 1)
        for fn in later:
            fn()
        self.assertEqual((decided, stub.deciding), ([False], 0), 'an unanswered resolver is a refusal')


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

    def test_a_navigation_whose_destination_check_outlasts_the_grace_is_still_waited_for(self):
        session = self.session()
        session.open({'url': 'https://shop.test/lateresolve', 'effect': 'navigate'})
        page = session.click({'target': 'Go', 'effect': 'navigate'})
        self.assertTrue(page['navigated'])
        self.assertEqual((page['url'], page['text']), ('https://shop.test/landed', 'landed page'))

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


RUNAWAY_CLI = """#!{python}
import os, sys, time
open({marker!r}, "w").write(str(os.getpid()))
if "--version" in sys.argv:
    print("codex-cli 0.0.0"); sys.exit(0)
out = sys.stderr if {to_stderr} else sys.stdout
chunk = "x" * 65536 + "\\n"
for _ in range(200):        # about 13 MB, well past the 8 MB bound
    out.write(chunk); out.flush()
if {exit_code}:
    sys.exit({exit_code})
time.sleep(60)              # a runaway that would otherwise hold the turn
"""


def _gone(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    try:   # a killed child not yet reaped by its parent
        return os.waitpid(pid, os.WNOHANG) != (0, 0)
    except ChildProcessError:
        return True


class StreamBoundWhileReading(unittest.TestCase):
    """#736 review: the whole-stream bound is enforced while the pipes drain, the CLI is killed early."""

    def cli(self, *, to_stderr=False, exit_code=0):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(root, ignore_errors=True))
        marker = root / 'pid'
        script = root / 'fake-codex'
        script.write_text(RUNAWAY_CLI.format(python=sys.executable, marker=str(marker), to_stderr=to_stderr,
                                             exit_code=exit_code))
        script.chmod(0o755)
        return root, script, marker

    def run_bounded(self, **kwargs):
        root, script, marker = self.cli(**kwargs)
        started = time.monotonic()
        with self.assertRaises(ExecutionError) as caught:
            bounded_run(subprocess.run, [str(script), 'exec'], cwd=root, env=dict(os.environ), timeout=60)
        elapsed = time.monotonic() - started
        return caught.exception, elapsed, int(marker.read_text())

    def test_a_runaway_stdout_is_killed_as_soon_as_it_passes_the_bound(self):
        error, elapsed, pid = self.run_bounded()
        self.assertEqual((str(error), error.failure_class), (be.STREAM_TOO_LARGE, 'invalid-output'))
        self.assertLess(elapsed, 20, 'killed early, not after its 60 s sleep')
        self.assertTrue(_gone(pid))

    def test_stderr_and_a_nonzero_exit_hit_the_same_named_bound(self):
        error, _elapsed, _pid = self.run_bounded(to_stderr=True, exit_code=3)
        self.assertEqual((str(error), error.failure_class), (be.STREAM_TOO_LARGE, 'invalid-output'))

    def test_a_small_run_is_unchanged(self):
        done = bounded_run(subprocess.run, [sys.executable, '-c', 'print("hello")'], cwd=tempfile.gettempdir(),
                           env=dict(os.environ), timeout=30)
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, 'hello\n', ''))

    def test_the_cli_turn_fails_with_the_named_bound(self):
        root, script, _marker = self.cli()
        home = root / 'home'
        home.mkdir()
        adapter = BoundedExecutionAdapter(finder=lambda _: str(script), runtime_root=root / 'turns', codex_home=home)
        started = time.monotonic()
        with self.assertRaises(ExecutionError) as caught:
            adapter.execute('codex', 'hello', AgentOSMcpTools(_Capabilities()))
        self.assertEqual((str(caught.exception), caught.exception.failure_class), (be.STREAM_TOO_LARGE, 'invalid-output'))
        self.assertLess(time.monotonic() - started, 30)


if __name__ == '__main__':
    unittest.main()

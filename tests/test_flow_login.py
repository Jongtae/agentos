"""SEC-FLOW-01 (#709): AgentOS decides its own bridge tools, in-flow login, bounded render settle, intact links.

Evidence classes, named separately:

* unit (model-free, temporary stores): the Codex Work argv carries
  ``mcp_servers.agentos.default_tools_approval_mode="approve"`` for the
  ``agentos`` MCP server only, on both host profiles, through the fake CLI
  runner; the Claude Code argv is unchanged (exact ``--allowedTools``); the
  bounded render settle of ``browser_open``/``browser_read`` over an injected
  driver; ``clip_keeping_links``;
* model-free service integration (fake page driver, fake Telegram transport,
  scripted model): a login page during a Work shows the login window after
  the run released the profile; the owner closing it resumes that Work
  exactly once (a web-started Work too, with no Telegram message), and the
  optional ``p7l:`` 로그인 완료 / 건너뛰기 and the web decision are settled
  by the work loop; the timeout, a failed save and a restart never resume
  (the row expires and a later login page asks again); stale or foreign
  callbacks are refused; a scripted loop whose report carries a long public
  link keeps it whole in the owner's bubble;
* macOS + PyObjC integration (the real WebKit worker and a fixture site):
  a page that renders its text after load is read after it rendered, and the
  in-flow login through the real CLI bridge: the window shows, the session
  made in it is saved, closing the window resumes the Work, and the resumed
  run is signed in.

The Codex key and values were verified separately against the installed CLI
(0.153.4) with an empty ``CODEX_HOME`` (parse only; see the PR).  No live
model, CLI or owner credential is used.
"""
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

from personal_agent import browser_session as bs
from personal_agent.bounded_execution import (AgentOSMcpTools, BoundedExecutionAdapter, BOUNDED_PROFILE,
                                              CODEX_BRIDGE_APPROVAL_MODE, STRICT_PROFILE, profile_actions)
from personal_agent.conversation_projection import TELEGRAM_RESULT_PREVIEW_CHARS, clip_keeping_links, terminal_text
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import (AgentService, BROWSER_LOGIN_OFFERED_TEXT, BROWSER_LOGIN_RESULT_TEXT,
                                               BROWSER_LOGIN_SECONDS)
from personal_agent.quickstart_store import QuickStore

from test_bounded_execution import _Capabilities
from test_browser_session import ORIGIN, FakeDriver, Script, call, flat
from test_cli_route_agency import CHAT as CHAT_BRIDGE, GENERATION as GENERATION_BRIDGE, _BridgeHarness, _call, _value

CHAT, GENERATION = 42, 'gen-709'
#: Codex 0.153.4's accepted values for the key (its config loader's own error lists them).
CODEX_APPROVAL_VALUES = ('auto', 'prompt', 'writes', 'approve')
APPROVAL_KEY = 'default_tools_approval_mode'


# ---------------------------------------------------------------- the CLI argv (fake CLI runner)

class ApprovalModeArgv(unittest.TestCase):
    def run_cli(self, engine, profile=BOUNDED_PROFILE):
        seen = {}

        def runner(argv, **kwargs):
            seen['argv'] = list(argv)

            class Done:
                returncode = 0
                stdout = (json.dumps({'item': {'type': 'agent_message', 'text': 'ok'}}) if engine == 'codex'
                          else json.dumps({'type': 'result', 'result': 'ok', 'is_error': False}))
                stderr = ''
            return Done()
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder) / 'home'
            home.mkdir()
            adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=runner,
                                              runtime_root=Path(folder) / 'turns', codex_home=home)
            adapter.execute(engine, 'hello', AgentOSMcpTools(_Capabilities()))
        return seen['argv']

    def test_the_codex_work_argv_lets_agentos_decide_its_own_bridge_tools_only(self):
        argv = self.run_cli('codex')
        overrides = [argv[index + 1] for index, value in enumerate(argv[:-1]) if value == '-c']
        approval = [value for value in overrides if APPROVAL_KEY in value]
        self.assertEqual(approval, ['mcp_servers.agentos.default_tools_approval_mode="approve"'])
        self.assertIn(CODEX_BRIDGE_APPROVAL_MODE, CODEX_APPROVAL_VALUES)
        servers = {value.split('.')[1] for value in overrides if value.startswith('mcp_servers.')}
        self.assertEqual(servers, {'agentos'}, 'no other MCP server is configured or approved')
        for widening in ('approval_policy', 'approvals_reviewer', 'sandbox_mode', 'dangerously', 'bypass'):
            self.assertFalse([value for value in argv if widening in value], widening)
        self.assertEqual(argv[argv.index('--sandbox') + 1], 'read-only', 'shell commands keep the read-only sandbox')
        self.assertEqual(argv[-1], 'hello')

    def test_the_strict_codex_argv_carries_the_same_bridge_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'agentos-mcp.json'
            config.write_text(json.dumps({'mcpServers': {'agentos': {'args': ['-m', 'personal_agent.mcp_bridge']}}}))
            adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=None,
                                              runtime_root=Path(folder) / 'turns', codex_home=Path(folder))
            argv = adapter.command('codex', '/runtime/codex', 'hello', config, profile=STRICT_PROFILE,
                                   disabled_features=('plugins',))
        self.assertEqual([value for value in argv if APPROVAL_KEY in value],
                         ['mcp_servers.agentos.default_tools_approval_mode="approve"'])

    def test_claude_code_needs_nothing_beyond_its_exact_allow_list(self):
        argv = self.run_cli('claude-code')
        self.assertFalse([value for value in argv if APPROVAL_KEY in value])
        for flag in ('--permission-mode', '--dangerously-skip-permissions', '--allow-dangerously-skip-permissions'):
            self.assertNotIn(flag, argv)
        self.assertEqual(argv[-2], '--allowedTools')
        self.assertEqual(argv[-1].split(','), [f'mcp__agentos__{action}' for action in profile_actions(BOUNDED_PROFILE)])


# ---------------------------------------------------------------- render settle (unit)

class SettlingDriver(FakeDriver):
    def __init__(self, fail=False):
        super().__init__()
        self.settles, self.fail = [], fail

    def settle(self, seconds, timeout):
        self.settles.append((seconds, self.url))
        if self.fail:
            raise RuntimeError('no settle op')


class RenderSettle(unittest.TestCase):
    def test_open_and_read_wait_for_rendered_content_bounded(self):
        driver = SettlingDriver()
        session = bs.BrowserSession(lambda: driver, work_id='w')
        session.open({'url': ORIGIN + '/product', 'effect': 'read'})
        session.read()
        session.find({'text': '12,900'})
        self.assertEqual([url for _seconds, url in driver.settles], [ORIGIN + '/product'] * 2,
                         'open and read settle; find reads the page as it is')
        self.assertTrue(all(0 < seconds <= bs.RENDER_SETTLE_SECONDS for seconds, _url in driver.settles))

    def test_a_failed_settle_is_not_a_failed_step_and_a_driver_without_it_is_fine(self):
        driver = SettlingDriver(fail=True)
        page = bs.BrowserSession(lambda: driver, work_id='w').open({'url': ORIGIN + '/product', 'effect': 'read'})
        self.assertEqual(page['state'], 'page')
        plain = bs.BrowserSession(lambda: FakeDriver(), work_id='w').open({'url': ORIGIN + '/product', 'effect': 'read'})
        self.assertEqual(plain['state'], 'page')

    def test_the_worker_gets_an_absolute_pythonpath(self):
        env = bs.worker_environment({'PATH': '/usr/bin', 'PYTHONPATH': 'src' + os.pathsep + '/abs/lib', 'SECRET': 'x'})
        self.assertEqual(env['PYTHONPATH'].split(os.pathsep), [os.path.abspath('src'), '/abs/lib'])
        self.assertNotIn('SECRET', env)

    def test_the_settle_never_outlasts_the_work_budget(self):
        class Budget:
            def check(self):
                pass

            def remaining(self):
                return 1.5
        driver = SettlingDriver()
        bs.BrowserSession(lambda: driver, work_id='w', budget=Budget()).open({'url': ORIGIN + '/product', 'effect': 'read'})
        self.assertEqual([seconds for seconds, _url in driver.settles], [0.5])


# ---------------------------------------------------------------- links stay whole

class LinksStayWhole(unittest.TestCase):
    def test_a_public_link_the_bound_would_split_is_kept_whole(self):
        link = 'https://example.org/items/' + 'x' * 230 + '?page=2'
        text = '다음: ' + link
        self.assertEqual(clip_keeping_links(text, 200), text)
        self.assertEqual(clip_keeping_links('짧은 문장', 200), '짧은 문장')

    def test_a_private_or_oversized_link_is_dropped_rather_than_left_broken(self):
        private = '앞 ' + 'http://127.0.0.1:8765/' + 'y' * 300
        self.assertEqual(clip_keeping_links(private, 100), '앞')
        huge = '앞 https://example.org/' + 'z' * 3000
        self.assertEqual(clip_keeping_links(huge, 100), '앞')

    def test_the_telegram_preview_stays_under_the_message_limit(self):
        link = 'https://example.org/' + 'q' * 700
        body = 'a' * (TELEGRAM_RESULT_PREVIEW_CHARS - 10) + ' ' + link + ' tail'
        bubble = terminal_text(body, outcome='succeeded')
        self.assertIn(link, bubble)
        self.assertLess(len(bubble), 4096)


# ---------------------------------------------------------------- in-flow login (fake driver, fake Telegram)

class JarDriver(FakeDriver):
    """The fake page driver with a cookie export, so a closing window's save into the jar can succeed or fail."""

    def __init__(self, log=None):
        super().__init__(log=log)
        self.fail_export = False

    def cookies_export(self):
        if self.fail_export:
            raise RuntimeError('export failed')
        return {}, []


def memory_jar(directory):
    from personal_agent.browser_jar import JAR_NAME, CookieJar, MemoryKey
    return CookieJar(Path(directory) / JAR_NAME, MemoryKey())


def wait_until(condition, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


class LoginHarness(unittest.TestCase):
    """One Telegram owner, the direct scripted model route and the fake page driver."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = QuickStore(Path(self.tmp.name) / 'data')
        self.calls, self.scripts, self.driver_log, self.drivers = [], [], [], []

        def transport(url, body=None, headers=None, timeout=60):
            method = url.rsplit('/', 1)[-1]
            self.calls.append((method, body))
            if method == 'sendMessage':
                return {'ok': True, 'result': {'message_id': 9000 + len(self.calls)}}
            if method == 'getMe':
                return {'ok': True, 'result': {'username': 'owner_test_bot'}}
            return {'ok': True, 'result': True}

        def model(url, body, headers=None, timeout=60):
            tools = [t.get('function', {}).get('name') or t.get('name') for t in body.get('tools', [])]
            if 'agentos_connection_probe' in tools:
                return {'choices': [{'message': {'tool_calls': [{'id': 'probe', 'function': {'name': 'agentos_connection_probe', 'arguments': '{}'}}]}}]}
            if not self.scripts:
                return {'choices': [{'message': {'content': '끝났습니다.'}}]}
            return self.scripts[0](url, body, headers, timeout)

        def launcher(profile_dir, headless):
            driver = JarDriver(log=self.driver_log)
            self.drivers.append(driver)
            return driver

        self.transport, self.model, self.launcher = transport, model, launcher
        self.profile = bs.BrowserProfile(Path(self.tmp.name) / 'profile', launcher=launcher,
                                         jar=memory_jar(Path(self.tmp.name) / 'profile'))
        self.service = AgentService(self.store, ModelAdapter(model), transport, browser_profile=self.profile)
        self.service.save_model({'provider': 'compatible', 'endpoint': 'https://example.test/v1', 'model': 'test-model', 'api_key': 'k'})
        self.assertTrue(self.service.test_model()['ok'])
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION, 'cursor': 0})
        self.update_id, self.message_id = 100, 500
        self.addCleanup(self.close_windows)

    def close_windows(self):
        for driver in self.drivers:
            driver.closed = True

    def receive(self, text):
        self.update_id += 1
        self.message_id += 1
        self.service.ingest_update({'update_id': self.update_id, 'message': {'message_id': self.message_id, 'from': {'id': CHAT},
                                    'chat': {'id': CHAT, 'type': 'private'}, 'text': text}}, GENERATION)
        return self.store.jobs()[0]['id']

    def tap(self, data, message_id, sender=CHAT):
        self.service.ingest_callback({'id': 'cb', 'from': {'id': sender}, 'data': data,
                                      'message': {'message_id': message_id, 'chat': {'id': sender, 'type': 'private'}}}, GENERATION)

    def login_script(self):
        return [Script({'tool_calls': [call('1', 'browser_open', url=ORIGIN + '/login', effect='navigate')]},
                       {'content': '로그인이 필요합니다.'})]

    def prompts(self):
        return [body for method, body in self.calls if method == 'sendMessage' and body.get('reply_markup')
                and 'p7l:' in flat(body['reply_markup'])]

    def login_work(self):
        """A Work whose browser step lands on a login page, run once and its prompt delivered."""
        self.scripts = self.login_script()
        job_id = self.receive('계정 페이지 확인해줘')
        self.assertTrue(self.service.run_one())
        #: How the run ended (nothing advanced: failed; something did: partial); the login keeps it.
        self.ended = self.store.job(job_id)['status']
        self.assertIn(self.ended, ('failed', 'partial'))
        self.service.deliver_one()
        self.assertTrue(self.service.deliver_notification())
        prompts = self.prompts()
        self.assertEqual(len(prompts), 1)
        buttons = prompts[-1]['reply_markup']['inline_keyboard'][0]
        notification = self.store.notification(buttons[0]['callback_data'].split(':')[1])
        return job_id, prompts[-1], buttons, notification

    def window(self):
        return self.drivers[-1]

    def state(self, job_id):
        return (self.service._browser_login(job_id) or {}).get('state')

    def owner_closes(self, job_id):
        """The owner closes the login window (the worker's close event)."""
        self.window().closed = True
        self.assertTrue(wait_until(lambda: self.state(job_id) not in ('offered', 'closing')), self.state(job_id))

    def failed_errors(self, job_id):
        with self.store.db() as db:
            rows = db.execute("SELECT detail FROM tool_events WHERE job_id=? AND tool='browser_open' AND status='failed'",
                              (job_id,)).fetchall()
        return [json.loads(row['detail']).get('error') for row in rows]

    def edits(self):
        return [body for method, body in self.calls if method == 'editMessageText']

    def conversation(self, job_id):
        with self.store.db() as db:
            return [row['content'] for row in db.execute("SELECT content FROM messages WHERE job_id=? AND role='assistant' ORDER BY id",
                                                         (job_id,))]


class InFlowLogin(LoginHarness):
    def test_closing_the_login_window_resumes_the_work_once(self):
        job_id, prompt, buttons, notification = self.login_work()
        job = self.store.job(job_id)
        self.assertIn(job['status'], ('failed', 'partial'), 'a run that reached a login page did not finish')
        self.assertEqual(self.failed_errors(job_id), [BROWSER_LOGIN_OFFERED_TEXT], 'the model was told the owner will be asked')
        # The Work's session closed first; the login window is a second driver, shown at the login page.
        self.assertTrue(self.drivers[0].closed)
        self.assertEqual(self.driver_log[-1], ('goto', ORIGIN + '/login', bs.ACTION_TIMEOUT_SECONDS))
        status = self.service.browser_status()
        self.assertTrue(status['login_window_open'])
        self.assertEqual([(row['work_id'], row['host']) for row in status['pending_logins']], [(job_id, 'fixture.test')])
        self.assertEqual([button['text'] for button in buttons], ['로그인 완료', '건너뛰기'])
        self.assertEqual([button['callback_data'] for button in buttons],
                         [f"p7l:{notification['id']}:done", f"p7l:{notification['id']}:skip"])
        self.assertIn('fixture.test', prompt['text'])
        self.assertNotIn('/login', prompt['text'], 'the prompt names the host, not the page')
        self.owner_closes(job_id)
        self.assertEqual(self.state(job_id), 'resumed')
        self.assertEqual(self.store.job(job_id)['status'], 'queued')
        self.assertFalse(self.service.browser_status()['login_window_open'])
        self.assertFalse(self.profile.status()['in_use'])
        self.assertEqual(self.store.notification(notification['id'])['state'], 'browser_login_resumed')
        self.assertEqual(self.edits()[-1]['text'], BROWSER_LOGIN_RESULT_TEXT['resumed'])
        self.assertEqual(self.edits()[-1]['reply_markup'], {'inline_keyboard': []})
        self.assertEqual(self.service.browser_status()['pending_logins'], [])
        # A later 로그인 완료 or 건너뛰기, or the timeout, does nothing: resumed exactly once.
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='partial' WHERE id=?", (job_id,))
        self.tap(f"p7l:{notification['id']}:done", notification['message_id'])
        self.tap(f"p7l:{notification['id']}:skip", notification['message_id'])
        self.assertEqual(self.service.process_browser_logins(now=time.time() + BROWSER_LOGIN_SECONDS + 1), [])
        self.assertEqual(self.store.job(job_id)['status'], 'partial')
        self.assertEqual(self.state(job_id), 'resumed')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='queued' WHERE id=?", (job_id,))
        # The resumed run reaches the page; nothing was ever submitted in the login window.
        self.scripts = [Script({'tool_calls': [call('1', 'browser_open', url=ORIGIN + '/product', effect='read')]},
                               {'content': '확인했습니다.'})]
        self.assertTrue(self.service.run_one())
        self.assertIn(self.store.job(job_id)['status'], ('succeeded', 'partial'))
        self.assertEqual(self.drivers[1].posts, [], 'nothing was submitted in the login window')

    def test_telegram_done_is_settled_by_the_work_loop_and_resumes_once(self):
        job_id, _prompt, _buttons, notification = self.login_work()
        self.tap(f"p7l:{notification['id']}:done", notification['message_id'])
        self.assertEqual(self.state(job_id), 'closing')
        self.assertFalse(self.window().closed, 'the poll thread never closes the window itself')
        self.assertEqual(self.store.job(job_id)['status'], self.ended)
        self.assertEqual(self.service.process_browser_logins(), [job_id])
        self.assertTrue(self.window().closed)
        self.assertEqual(self.store.job(job_id)['status'], 'queued')
        self.assertEqual(self.state(job_id), 'resumed')
        self.assertEqual(self.edits()[-1]['text'], BROWSER_LOGIN_RESULT_TEXT['resumed'])
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='partial' WHERE id=?", (job_id,))
        self.tap(f"p7l:{notification['id']}:done", notification['message_id'])
        self.assertEqual(self.service.process_browser_logins(), [])
        self.assertEqual(self.store.job(job_id)['status'], 'partial')

    def test_skip_closes_the_window_and_leaves_the_work_as_it_ended(self):
        job_id, _prompt, _buttons, notification = self.login_work()
        self.tap(f"p7l:{notification['id']}:skip", notification['message_id'])
        self.service.process_browser_logins()
        self.assertEqual(self.store.job(job_id)['status'], self.ended)
        self.assertTrue(self.window().closed)
        self.assertEqual(self.state(job_id), 'skipped')
        self.assertEqual(self.edits()[-1]['text'], BROWSER_LOGIN_RESULT_TEXT['skipped'])
        self.tap(f"p7l:{notification['id']}:done", notification['message_id'])
        self.service.process_browser_logins()
        self.assertEqual(self.store.job(job_id)['status'], self.ended, 'a stale 로그인 완료 after skip is refused')

    def test_no_answer_in_time_closes_the_window_and_does_not_resume(self):
        job_id, _prompt, _buttons, notification = self.login_work()
        self.assertEqual(self.service.process_browser_logins(now=time.time() + 5), [], 'not yet')
        self.assertFalse(self.window().closed)
        self.assertEqual(self.service.process_browser_logins(now=time.time() + BROWSER_LOGIN_SECONDS + 1), [job_id])
        self.assertTrue(self.window().closed)
        self.assertEqual(self.store.job(job_id)['status'], self.ended)
        self.assertEqual(self.state(job_id), 'expired')
        self.assertEqual(self.store.notification(notification['id'])['state'], 'browser_login_expired')
        self.assertEqual(self.edits()[-1]['text'], BROWSER_LOGIN_RESULT_TEXT['expired'])
        self.tap(f"p7l:{notification['id']}:done", notification['message_id'])
        self.service.process_browser_logins()
        self.assertEqual(self.store.job(job_id)['status'], self.ended)
        # Finished rows are pruned a day later.
        self.service.process_browser_logins(now=time.time() + 2 * 86400)
        self.assertIsNone(self.service._browser_login(job_id))

    def test_the_window_timing_out_on_its_own_is_not_an_owner_close(self):
        job_id, _prompt, _buttons, _notification = self.login_work()
        with mock.patch.object(self.profile, 'login_window_outcome', return_value=('timeout', True)):
            self.service.process_browser_logins()
        self.assertEqual(self.state(job_id), 'expired')
        self.assertEqual(self.store.job(job_id)['status'], self.ended)

    def test_a_stale_foreign_or_malformed_callback_is_refused(self):
        job_id, _prompt, _buttons, notification = self.login_work()
        message_id = notification['message_id']
        self.tap(f"p7l:{notification['id']}:done", message_id, sender=99)
        self.tap(f"p7l:{notification['id']}:done", message_id + 1)
        self.tap(f"p7l:{notification['id']}:yes", message_id)
        self.tap(f"p7l:{notification['id']}", message_id)
        self.tap('p7l:no-such-notification:done', message_id)
        # A prompt whose login was replaced (another nonce) no longer binds.
        row = self.service._browser_login(job_id)
        self.service._put_browser_login(job_id, {**row, 'nonce': 'another'})
        self.tap(f"p7l:{notification['id']}:done", message_id)
        self.service._put_browser_login(job_id, row)
        # Another callback kind cannot answer it either.
        self.tap(f"p7w:{notification['id']}:approve", message_id)
        self.service.process_browser_logins()
        self.assertEqual(self.store.job(job_id)['status'], self.ended)
        self.assertEqual(self.state(job_id), 'offered')
        self.assertFalse(self.window().closed)
        self.tap(f"p7l:{notification['id']}:done", message_id)
        self.service.process_browser_logins()
        self.assertEqual(self.store.job(job_id)['status'], 'queued')

    def test_a_web_started_work_resumes_when_the_window_closes_with_no_telegram_message(self):
        self.scripts = self.login_script()
        job_id = self.store.enqueue('계정 페이지 확인해줘', 'web-login')
        self.assertTrue(self.service.run_one())
        self.assertEqual(self.state(job_id), 'offered')
        self.owner_closes(job_id)
        self.assertEqual(self.store.job(job_id)['status'], 'queued')
        while self.service.deliver_notification():
            pass
        self.assertEqual([body for method, body in self.calls if method in ('sendMessage', 'editMessageText')], [])

    def test_the_web_decision_is_optional_and_settled_by_the_work_loop(self):
        job_id, _prompt, _buttons, _notification = self.login_work()
        with self.assertRaises(ValueError):
            self.service.browser_login_decision({'work_id': job_id, 'decision': 'maybe'})
        with self.assertRaises(ValueError):
            self.service.browser_login_decision({'work_id': 'other', 'decision': 'done'})
        self.assertEqual(self.service.browser_login_decision({'work_id': job_id, 'decision': 'done'}),
                         {'work_id': job_id, 'state': 'closing', 'intent': 'resume'})
        with self.assertRaises(ValueError):
            self.service.browser_login_decision({'work_id': job_id, 'decision': 'done'})
        self.service.process_browser_logins()
        self.assertEqual(self.store.job(job_id)['status'], 'queued')
        # The resumed run meets the login page again: a resumed login is not asked a second time.
        self.scripts = self.login_script()
        self.assertTrue(self.service.run_one())
        self.assertEqual(self.failed_errors(job_id)[-1], bs.LOGIN_REQUIRED_TEXT)
        self.assertEqual(len(self.drivers), 3, 'no second login window')
        self.assertEqual(self.state(job_id), 'resumed')

    def test_a_window_whose_cookies_could_not_be_saved_expires_and_a_later_login_page_asks_again(self):
        job_id, _prompt, _buttons, notification = self.login_work()
        self.window().fail_export = True
        self.owner_closes(job_id)
        self.assertEqual(self.state(job_id), 'expired')
        self.assertEqual(self.service._browser_login(job_id)['cause'], 'close_failed')
        self.assertEqual(self.store.job(job_id)['status'], self.ended, 'never re-queued without the new session')
        self.assertEqual(self.edits()[-1]['text'], BROWSER_LOGIN_RESULT_TEXT['close_failed'])
        self.assertEqual(len([edit for edit in self.edits() if edit['text'] == BROWSER_LOGIN_RESULT_TEXT['close_failed']]), 1,
                         'the owner is told once')
        self.ask_again(job_id, notification)

    def test_a_restart_while_offered_expires_the_login_and_a_later_login_page_asks_again(self):
        job_id, _prompt, _buttons, notification = self.login_work()
        old_window = self.window()
        # The service restarts: a new profile knows none of the old process's windows.
        self.profile = bs.BrowserProfile(Path(self.tmp.name) / 'profile', launcher=self.launcher,
                                         jar=memory_jar(Path(self.tmp.name) / 'profile'))
        self.service = AgentService(self.store, ModelAdapter(self.model), self.transport, browser_profile=self.profile)
        old_window.closed = True
        self.assertEqual(self.service.process_browser_logins(), [job_id])
        self.assertEqual(self.state(job_id), 'expired')
        self.assertEqual(self.store.job(job_id)['status'], self.ended)
        self.assertEqual(self.edits()[-1]['text'], BROWSER_LOGIN_RESULT_TEXT['close_failed'])
        # A 로그인 완료 on the old prompt cannot resume it either.
        self.tap(f"p7l:{notification['id']}:done", notification['message_id'])
        self.service.process_browser_logins()
        self.assertEqual(self.store.job(job_id)['status'], self.ended)
        self.ask_again(job_id, notification)

    def ask_again(self, job_id, old):
        """The Work runs again and meets a login page: the owner is asked again, on a fresh prompt."""
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='queued' WHERE id=?", (job_id,))
        self.scripts = self.login_script()
        self.assertTrue(self.service.run_one())
        self.assertEqual(self.failed_errors(job_id)[-1], BROWSER_LOGIN_OFFERED_TEXT)
        self.assertEqual(self.state(job_id), 'offered')
        self.assertTrue(self.service.deliver_notification())
        fresh = self.store.notification(old['id'])
        self.assertEqual(fresh['state'], 'sent')
        self.assertNotEqual(fresh['message_id'], old['message_id'], 'a new message; the old one no longer binds')
        self.tap(f"p7l:{old['id']}:done", old['message_id'])
        self.assertEqual(self.state(job_id), 'offered')
        self.owner_closes(job_id)
        self.assertEqual(self.store.job(job_id)['status'], 'queued')

    def test_no_prompt_when_the_window_cannot_open(self):
        with mock.patch.object(self.profile, 'open_for_login', return_value={'state': 'busy', 'message': bs.BUSY_TEXT}):
            self.scripts = self.login_script()
            job_id = self.receive('계정 페이지 확인해줘')
            self.assertTrue(self.service.run_one())
        self.service.deliver_one()
        while self.service.deliver_notification():
            pass
        self.assertFalse([body for method, body in self.calls if 'p7l:' in flat(body or {})])
        self.assertEqual(self.state(job_id), 'unavailable')
        self.assertEqual(self.store.job(job_id)['status'], 'failed')

    def test_a_long_public_link_in_the_report_reaches_the_owner_whole(self):
        link = 'https://example.org/items/' + 'x' * 230 + '?page=2'
        self.scripts = [Script({'tool_calls': [call('1', 'browser_open', url=ORIGIN + '/login', effect='navigate')]},
                               {'tool_calls': [call('2', 'finish', status='needs_owner', evidence_refs=[],
                                                    summary='로그인이 필요합니다.', next='이 주소에서 이어서 확인하세요: ' + link)]})]
        job_id = self.receive('계정 페이지 확인해줘')
        self.assertTrue(self.service.run_one())
        job = self.store.job(job_id)
        self.assertIn(link, job['owner_cause'])
        self.service.deliver_one()
        results = [body['text'] for method, body in self.calls if method == 'sendMessage' and 'p7l:' not in flat(body)]
        self.assertTrue(any(link in text for text in results), results)


class LoginThroughTheCliBridge(_BridgeHarness):
    """The same in-flow login on the trusted-local CLI route: the bridge relays, the service asks."""

    def make_profile(self, launcher):
        def jar_launcher(profile_dir, headless):
            driver = JarDriver(log=self.driver_log)
            self.drivers.append(driver)
            return driver
        return bs.BrowserProfile(self.tmp / 'profile', launcher=jar_launcher, jar=memory_jar(self.tmp / 'profile'))

    def test_a_cli_turn_that_meets_a_login_page_is_partial_and_resumes_once(self):
        replies = self.wire(_call(2, 'browser_open', url=ORIGIN + '/login', effect='navigate'),
                            text='계정 페이지 확인해줘', telegram=True)
        self.addCleanup(lambda: [setattr(driver, 'closed', True) for driver in self.drivers])
        result = _value(replies[2])
        self.assertEqual((result['state'], result['next_step']), ('login_required', BROWSER_LOGIN_OFFERED_TEXT))
        job = self.store.job(self.job)
        self.assertEqual(job['status'], 'partial', 'a zero exit with a login page is not a finished request')
        self.assertIn('로그인이 필요합니다', job['owner_cause'])
        self.assertTrue(self.profile.status()['login_window_open'])
        self.assertTrue(self.drivers[0].closed, 'the turn released the profile before the window opened')
        self.assertTrue(self.service.deliver_notification())
        prompt = [body for method, body in self.calls if method == 'sendMessage' and 'p7l:' in flat(body.get('reply_markup'))]
        notification = self.store.notification(prompt[0]['reply_markup']['inline_keyboard'][0][0]['callback_data'].split(':')[1])
        tap = {'id': 'cb', 'from': {'id': CHAT_BRIDGE}, 'data': f"p7l:{notification['id']}:done",
               'message': {'message_id': notification['message_id'], 'chat': {'id': CHAT_BRIDGE, 'type': 'private'}}}
        self.service.ingest_callback(tap, GENERATION_BRIDGE)
        self.service.process_browser_logins()
        self.assertEqual(self.store.job(self.job)['status'], 'queued')
        self.assertTrue(self.drivers[1].closed)
        replies = self.rerun(_call(2, 'browser_open', url=ORIGIN + '/product', effect='read'))
        self.assertEqual(_value(replies[2])['state'], 'page')
        self.service.ingest_callback(tap, GENERATION_BRIDGE)
        self.service.process_browser_logins()
        self.assertNotEqual(self.store.job(self.job)['status'], 'queued', 'the same tap never resumes it again')


# ---------------------------------------------------------------- the real worker (macOS + PyObjC)

MEMBER_COOKIE = 'flow_sid'


class LoginFixtureHandler(BaseHTTPRequestHandler):
    """A page behind a login form, a page that starts a session, and a page rendered after load."""

    def _send(self, body, headers=()):
        data = body.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        for name, value in headers:
            self.send_header(name, value)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/members':
            if f'{MEMBER_COOKIE}={self.server.cookie_value}' in (self.headers.get('Cookie') or ''):
                return self._send('<html><head><title>회원</title></head><body><p>회원 전용 내용</p></body></html>')
            return self._send('''<html><head><title>로그인</title></head><body><form action="/members" method="post">
              <input type="email" aria-label="이메일"><input type="password" aria-label="비밀번호">
              <button type="submit">로그인</button></form></body></html>''')
        if path == '/session-start':
            return self._send('<html><head><title>세션</title></head><body><p>세션 시작</p></body></html>',
                              [('Set-Cookie', f'{MEMBER_COOKIE}={self.server.cookie_value}; Path=/; HttpOnly; Max-Age=3600')])
        if path == '/late':
            return self._send('''<html><head><title>늦은 내용</title></head><body><div id="root"></div><script>
              setTimeout(function () { document.getElementById('root').textContent = '나중에 그려진 내용'; }, 1500);
              </script></body></html>''')
        return self._send('<html><body>없음</body></html>')

    def log_message(self, *args):
        pass


def _webkit_ready():
    return bs.webkit_unavailable_reason() is None


def _serve(test):
    server = ThreadingHTTPServer(('127.0.0.1', 0), LoginFixtureHandler)
    server.cookie_value = 'flow-' + str(time.time_ns())
    threading.Thread(target=server.serve_forever, daemon=True).start()
    test.addCleanup(server.server_close)
    test.addCleanup(server.shutdown)
    return server, f'127.0.0.1:{server.server_address[1]}'


@unittest.skipUnless(_webkit_ready(), 'embedded WebKit needs macOS with pyobjc-framework-WebKit')
class RealWorkerRenderSettle(unittest.TestCase):
    """Evidence class: model-free integration with the real worker process and system WebKit."""

    def test_a_page_that_renders_after_load_is_read_after_it_rendered(self):
        _server, fixture = _serve(self)
        with tempfile.TemporaryDirectory() as folder:
            driver = bs.WebKitWorkerDriver('p', cwd=folder, allowed_origins_for_tests=(fixture,))
            session = bs.BrowserSession(lambda: driver, work_id='w', allowed_origins_for_tests=(fixture,))
            try:
                started = time.monotonic()
                page = session.open({'url': f'http://{fixture}/late', 'effect': 'read'})
                waited = time.monotonic() - started
                self.assertIn('나중에 그려진 내용', page['text'])
                self.assertLess(waited, bs.RENDER_SETTLE_SECONDS + 10)
                # A page with nothing to render is read after at most the bounded settle.
                started = time.monotonic()
                session.open({'url': f'http://{fixture}/nothing-here', 'effect': 'read'})
                self.assertLess(time.monotonic() - started, bs.RENDER_SETTLE_SECONDS + 10)
            finally:
                session.close()


@unittest.skipUnless(_webkit_ready(), 'embedded WebKit needs macOS with pyobjc-framework-WebKit')
class RealWorkerInFlowLogin(_BridgeHarness):
    """Evidence class: model-free integration, real bridge subprocess + real WebKit worker + fixture site."""

    def make_profile(self, launcher):
        from personal_agent.browser_jar import JAR_NAME, CookieJar, MemoryKey
        self.site, self.fixture = _serve(self)
        directory = self.tmp / 'profile'
        profile = bs.BrowserProfile(directory, jar=CookieJar(directory / JAR_NAME, MemoryKey()))
        profile.allow_origins_for_tests(self.fixture)
        return profile

    def test_the_window_shows_the_owner_logs_in_and_closing_it_resumes_a_signed_in_run(self):
        origin = 'http://' + self.fixture
        original = bs.BrowserSession.__init__

        def allow_fixture(session, *args, **kwargs):
            original(session, *args, **{**kwargs, 'allowed_origins_for_tests': (self.fixture,)})
        self.addCleanup(lambda: [self.profile.close_login_window(row.get('window'))
                                 for row in self.service.browser_login_requests().values()])
        with mock.patch.object(bs.BrowserSession, '__init__', allow_fixture):
            replies = self.wire(_call(2, 'browser_open', url=origin + '/members', effect='read'),
                                text='회원 페이지 내용 확인해줘', telegram=True)
            first = _value(replies[2])
            self.assertEqual(first['state'], 'login_required')
            self.assertEqual(first['next_step'], BROWSER_LOGIN_OFFERED_TEXT)
            self.assertEqual(self.store.job(self.job)['status'], 'partial', 'the CLI turn ended; its request did not')
            status = self.profile.status()
            self.assertTrue(status['login_window_open'], 'the real window is shown on this Mac')
            self.assertTrue(self.service.deliver_notification())
            prompt = [body for method, body in self.calls if method == 'sendMessage' and 'p7l:' in flat(body.get('reply_markup'))]
            self.assertEqual(len(prompt), 1)
            # The owner signs in by hand in that window (here: the fixture's session page in the same
            # window), then closes it: the worker's own close event (hidden) is the decision.
            self.profile._live.goto(origin + '/session-start', 10)
            self.profile._live.hide()
            self.assertTrue(wait_until(lambda: self.store.job(self.job)['status'] == 'queued', 20))
            self.assertEqual(self.service._browser_login(self.job)['state'], 'resumed')
            self.assertFalse(self.profile.status()['login_window_open'])
            self.assertFalse(self.profile.status()['in_use'])
            self.assertEqual([row['site'] for row in self.profile.status()['sessions']], ['127.0.0.1'],
                             'the session made in the window is in the encrypted jar')
            again = self.rerun(_call(2, 'browser_open', url=origin + '/members', effect='read'))
        page = _value(again[2])
        self.assertEqual(page['state'], 'page')
        self.assertIn('회원 전용 내용', page['text'])
        self.assertFalse(self.profile.status()['in_use'])


if __name__ == '__main__':
    unittest.main()

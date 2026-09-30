"""SEC-PROGRESS-01 / #718: the Telegram draft names the observed step in flight.

The model writes the wording (an optional ``status`` on every tool call); AgentOS
validates, bounds and redacts it, records it on the call's own ``running`` event
and shows it only while that call runs.  Without a status the line is generic,
keyed on the tool kind plus the host or query of the observed arguments.  The
CLI route streams its own search items while the run is live.

Evidence class: automated synthetic/fixture only.  The service tests drive the
real ingest -> worker -> presence path with a scripted model and a fake Telegram
transport on a fake clock; the CLI tests run a real child process that emits
events over time.  No live Telegram, model or CLI call is made or claimed.
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
from unittest import mock

from personal_agent.agent_runtime import (DEFINITIONS, STATUS_ARGUMENT, STATUS_MAX, Capabilities, action_definitions,
                                          bounded_status, progress_step, recorded_calls, split_status)
from personal_agent.bounded_execution import (AgentOSMcpTools, BoundedExecutionAdapter, bounded_run,
                                              live_native_search_steps, live_progress_reader)
from personal_agent.subscription_engines import SubscriptionEngines
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.telegram_presence import (DEFAULT_STEP_TEXT, NO_STEP_LINE, RETRY_STEP_TEXT, PresenceTiming,
                                              draft_body_text, draft_frame, draft_id_for, draft_step,
                                              draft_step_details, step_line)

CHAT = 4242
GENERATION = 'g1'
SECRET = 'zq9Wm4LtHv82PkXr'
DRAFT_METHODS = ('sendMessageDraft', 'sendRichMessageDraft')
from personal_agent.telegram_presence import DOTS_FRAMES

#: The dots of the first three drafts, whatever the frame count (#921).
DOTS = tuple(DOTS_FRAMES[index % len(DOTS_FRAMES)] for index in range(3))


def running(tool, step, call_id=None, created=1.0):
    trace = {'step': step, **({'call_id': call_id} if call_id else {})}
    return {'tool': tool, 'status': 'running', 'created': created, 'trace': trace}


def finished(tool, call_id=None, status='succeeded', created=2.0):
    return {'tool': tool, 'status': status, 'created': created, 'trace': {'call_id': call_id} if call_id else {}}


class StatusArgumentTests(unittest.TestCase):
    def test_every_model_facing_tool_offers_the_optional_generic_status(self):
        tools = {d['function']['name']: {'id': d['function']['name'], 'host_action': d['function']['name']}
                 for d in DEFINITIONS}
        for definition in action_definitions(tools, set(tools)):
            parameters = definition['function']['parameters']
            with self.subTest(tool=definition['function']['name']):
                self.assertEqual(parameters['properties'][STATUS_ARGUMENT]['type'], 'string')
                self.assertNotIn(STATUS_ARGUMENT, parameters['required'], 'the status is optional')
        # No host action declares a status of its own that the display field would shadow.
        for definition in DEFINITIONS:
            self.assertNotIn(STATUS_ARGUMENT, definition['function']['parameters']['properties'])

    def test_status_is_split_off_before_anything_else_reads_the_arguments(self):
        args, status = split_status({'query': 'x', 'status': '찾는 중'})
        self.assertEqual((args, status), ({'query': 'x'}, '찾는 중'))
        self.assertEqual(split_status({'query': 'x'}), ({'query': 'x'}, None))

    def test_status_is_bounded_single_line_and_redacted(self):
        self.assertEqual(bounded_status('  한 줄로\n\t정리  '), '한 줄로 정리')
        long = bounded_status('가' * 100)
        self.assertEqual(len(long), STATUS_MAX)
        self.assertTrue(long.endswith('…'))
        self.assertIsNone(bounded_status(''))
        self.assertIsNone(bounded_status(42))
        self.assertNotIn('sk-abcdef123456', bounded_status('키 sk-abcdef123456 확인'))
        self.assertNotIn(SECRET, bounded_status(f'{SECRET} 넣는 중', lambda text: text.replace(SECRET, '[redacted]')))
        # A redactor that fails withholds the status rather than showing it unredacted.
        self.assertIsNone(bounded_status('x', lambda text: 1 / 0))

    def test_step_targets_come_from_observed_arguments_only(self):
        self.assertEqual(progress_step('browser_open', {'url': 'https://shop.example/a?q=1', 'effect': 'read'}),
                         {'action': 'browser_open', 'host': 'shop.example'})
        self.assertEqual(progress_step('web_search', {'query': '오늘 환율'}, '환율을 찾고 있어요'),
                         {'action': 'web_search', 'status': '환율을 찾고 있어요', 'query': '오늘 환율'})

    def test_typed_browser_text_never_becomes_step_text(self):
        step = progress_step('browser_type', {'target': '3', 'text': 'hunter2-pass', 'effect': 'mutate'},
                             'hunter2-pass 입력하는 중')
        self.assertNotIn('status', step, 'a typing status could echo what was typed')
        self.assertNotIn('hunter2', json.dumps(step, ensure_ascii=False))

    def test_payment_step_is_marked_for_the_approval_prompt_only(self):
        step = progress_step('browser_click', {'target': '9', 'effect': 'payment'}, '결제 버튼을 누르는 중')
        self.assertEqual(step, {'action': 'browser_click', 'approval': True})
        self.assertIsNone(step_line(step))

    def test_recorded_model_calls_keep_only_the_bounded_redacted_status(self):
        tools = {'web_search': {'host_action': 'web_search'}}
        calls = [{'id': 'c1', 'function': {'name': 'web_search', 'arguments': json.dumps(
            {'query': 'q', 'status': f'{SECRET} 찾는 중 ' + '가' * 80})}}]
        [call] = recorded_calls(calls, tools, lambda text: text.replace(SECRET, '[redacted]'))
        recorded = json.loads(call['function']['arguments'])
        self.assertNotIn(SECRET, recorded['status'])
        self.assertLessEqual(len(recorded['status']), STATUS_MAX)
        self.assertEqual(recorded['query'], 'q')

    def test_the_mcp_facade_never_passes_the_status_to_the_tool(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'data')
        caps = Capabilities(store, None, {}, '', 'job', lambda *a: None, document_access=False,
                            allowed_tools={'list_notes'})
        seen = []
        caps.execute = lambda name, args: seen.append(args) or {'notes': []}
        AgentOSMcpTools(caps).call('list_notes', {'status': '메모 보는 중'})
        self.assertEqual(seen, [{}])


class StepLineTests(unittest.TestCase):
    def test_before_any_call_the_draft_has_no_step_line(self):
        # #835: the draft then shows the dots alone.
        self.assertEqual(draft_step([]), (NO_STEP_LINE, False))
        self.assertEqual(draft_frame(NO_STEP_LINE, 0), DOTS[0])

    def test_model_status_wins_and_generic_lines_are_keyed_on_kind_and_target(self):
        self.assertEqual(step_line({'action': 'web_search', 'status': '환율을 찾고 있어요', 'query': 'q'}), '환율을 찾고 있어요')
        self.assertEqual(step_line({'action': 'web_search', 'query': '오늘 환율'}), '웹 검색 중: 오늘 환율')
        self.assertEqual(step_line({'action': 'web_search'}), '웹 검색 중')
        self.assertEqual(step_line({'action': 'browser_open', 'host': 'shop.example'}), 'shop.example 페이지 여는 중')
        self.assertEqual(step_line({'action': 'browser_type'}, last_host='shop.example'), 'shop.example에서 입력 중')
        self.assertEqual(step_line({'action': 'weather'}), '날씨 확인 중')
        self.assertEqual(step_line({'action': 'unknown_kind'}), DEFAULT_STEP_TEXT)

    def test_a_masking_mark_is_never_shown(self):
        """#881: a status or target carrying a masking mark gives way to the plainer line."""
        self.assertEqual(step_line({'action': 'browser_open', 'status': "'예약 - [가림]' 여는 중", 'host': 'shop.example'}),
                         'shop.example 페이지 여는 중')
        self.assertEqual(step_line({'action': 'web_search', 'status': '[가림: 12자] 찾는 중', 'query': '[가림] 후기'}),
                         '웹 검색 중')
        self.assertEqual(step_line({'action': 'read_file', 'status': '[경로 가림] 읽는 중'}), '파일 읽는 중')
        self.assertEqual(step_line({'action': 'web_search', 'status': '[redacted] 넣는 중'}), '웹 검색 중')
        # Display-time redaction that masks, or fails, moves on the same way.
        clean = lambda text: text.replace('4719', '[가림]')
        self.assertEqual(step_line({'action': 'web_search', 'status': '4719 찾는 중', 'query': '4719'}, clean=clean),
                         '웹 검색 중')

        def broken(text):
            raise ValueError
        self.assertEqual(step_line({'action': 'web_search', 'status': '찾는 중'}, clean=broken), NO_STEP_LINE)
        events = [running('web_search', {'action': 'web_search', 'status': '[가림] 찾는 중'}, 'c1')]
        self.assertEqual(draft_step(events), ('웹 검색 중', False))

    def test_a_step_is_shown_only_while_its_call_runs(self):
        events = [running('web_search', {'action': 'web_search', 'status': '찾는 중'}, 'c1')]
        self.assertEqual(draft_step(events), ('찾는 중', False))
        self.assertEqual(draft_step_details(events), ('찾는 중', False, (None, 1.0, 'web_search', 'c1')))
        events.append(finished('web_search', 'c1'))
        self.assertEqual(draft_step(events), (NO_STEP_LINE, False))
        self.assertIsNone(draft_step_details(events)[2])

    def test_same_visible_line_on_a_new_call_is_a_new_step_identity(self):
        events = [running('web_search', {'action': 'web_search', 'status': '찾는 중'}, 'c1')]
        first = draft_step_details(events)[2]
        events.append(running('web_search', {'action': 'web_search', 'status': '찾는 중'}, 'c2', created=3.0))
        self.assertEqual(draft_step(events)[0], '찾는 중')
        self.assertNotEqual(draft_step_details(events)[2], first)

    def test_a_call_that_never_ran_shows_nothing(self):
        # Refused before its running event (invalid arguments, repeat path): no step exists.
        events = [finished('web_search', 'c9', status='failed')]
        self.assertEqual(draft_step(events), (NO_STEP_LINE, False))
        # A terminal event of another call does not close the call in flight.
        events = [running('web_search', {'action': 'web_search', 'status': '찾는 중'}, 'c1'),
                  finished('web_search', 'c2', status='failed')]
        self.assertEqual(draft_step(events), ('찾는 중', False))

    def test_a_later_call_uses_the_host_an_earlier_observed_call_opened(self):
        events = [running('browser_open', {'action': 'browser_open', 'host': 'shop.example'}),
                  finished('browser_open'),
                  running('browser_click', {'action': 'browser_click'}, created=3.0)]
        self.assertEqual(draft_step(events), ('shop.example에서 선택하는 중', False))

    def test_payment_step_in_flight_hides_the_draft_line(self):
        events = [running('browser_click', {'action': 'browser_click', 'approval': True})]
        self.assertEqual(draft_step(events), (None, True))

    def test_a_newer_live_cli_step_overrides_and_its_completion_closes_it(self):
        events = [running('list_notes', {'action': 'list_notes'}, created=1.0), finished('list_notes', created=2.0)]
        live = {'at': 3.0, 'running': True, 'id': 'ws1', 'step': {'action': 'web_search', 'query': '환율'}}
        self.assertEqual(draft_step(events, live), ('웹 검색 중: 환율', False))
        self.assertEqual(draft_step(events, {**live, 'running': False}), (NO_STEP_LINE, False))
        # An older live step does not hide a newer bridge call in flight.
        events.append(running('weather', {'action': 'weather'}, created=4.0))
        self.assertEqual(draft_step(events, live), ('날씨 확인 중', False))


class OrchestratedAttemptLineTests(unittest.TestCase):
    """#710/#718/#740: a re-delegated attempt announces itself without the plan's reasoning."""

    def planned(self, attempt, text, created):
        return {'tool': 'orchestrator', 'status': 'planned', 'created': created, 'trace': {'attempt': attempt, 'text': text}}

    def test_attempts_never_show_the_plan_text_and_a_retry_is_announced_generically(self):
        events = [self.planned(1, '1번째 시도: Codex · 기본 모델 — 현재 위치가 없어 추가 확인이 필요', 1.0)]
        self.assertEqual(draft_step(events), (NO_STEP_LINE, False), 'the first attempt announces nothing')
        events += [running('web_search', {'action': 'web_search', 'query': '환율'}, 'c1', created=2.0)]
        self.assertEqual(draft_step(events), ('웹 검색 중: 환율', False))
        events += [finished('web_search', 'c1', created=3.0),
                   {'tool': 'orchestrator', 'status': 'evaluated', 'created': 4.0, 'trace': {'text': '목표 미달'}}]
        self.assertEqual(draft_step(events), (NO_STEP_LINE, False), 'an evaluation is not a step')
        events += [self.planned(2, '2번째 시도: Claude Code · 기본 모델 — 다른 경로', 5.0)]
        text, _ = draft_step(events)
        self.assertEqual(text, RETRY_STEP_TEXT)
        self.assertNotIn('다른 경로', text)
        events += [running('weather', {'action': 'weather'}, 'c2', created=6.0)]
        self.assertEqual(draft_step(events), ('날씨 확인 중', False), 'the retry line gives way to its steps')

    def test_attempt_one_closes_an_earlier_step_line(self):
        """#753: attempt 1 planned after a preflight step does not keep that step's line."""
        events = [running('web_search', {'action': 'web_search', 'query': 'q'}, 'c0', created=0.5),
                  self.planned(1, '1번째 시도: Codex · 기본 모델 — 이유', 1.0)]
        self.assertEqual(draft_step(events), (NO_STEP_LINE, False))

    def test_a_fallback_attempt_announces_nothing(self):
        events = [{'tool': 'orchestrator', 'status': 'fallback', 'created': 1.0, 'trace': {'text': '기본 AI로 진행'}}]
        self.assertEqual(draft_step(events), (NO_STEP_LINE, False))


class LiveCliParsingTests(unittest.TestCase):
    def test_codex_and_claude_search_items_are_read_as_they_stream(self):
        self.assertEqual(live_native_search_steps('codex', {'type': 'item.started', 'item': {
            'id': 'ws1', 'type': 'web_search', 'query': '환율'}}), [{'id': 'ws1', 'state': 'running', 'query': '환율'}])
        self.assertEqual(live_native_search_steps('codex', {'type': 'item.completed', 'item': {
            'id': 'ws1', 'type': 'web_search', 'action': {'type': 'search', 'query': '환율'}}}),
            [{'id': 'ws1', 'state': 'done', 'query': '환율'}])
        self.assertEqual(live_native_search_steps('codex', {'type': 'item.started', 'item': {'type': 'mcp_tool_call'}}), [])
        self.assertEqual(live_native_search_steps('claude-code', {'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'id': 't1', 'name': 'WebSearch', 'input': {'query': '환율'}}]}}),
            [{'id': 't1', 'state': 'running', 'query': '환율'}])
        self.assertEqual(live_native_search_steps('claude-code', {'type': 'user', 'message': {'content': [
            {'type': 'tool_result', 'tool_use_id': 't1'}]}}), [{'id': 't1', 'state': 'done', 'query': ''}])

    def test_a_failing_sink_or_bad_line_never_breaks_the_reader(self):
        reader = live_progress_reader('codex', lambda step: 1 / 0)
        reader('not json\n')
        reader(json.dumps({'type': 'item.started', 'item': {'type': 'web_search', 'id': 'x'}}) + '\n')


STREAMING_CLI = '''#!{python}
import json, sys, time
def emit(value):
    print(json.dumps(value)); sys.stdout.flush()
emit({{"type": "item.started", "item": {{"id": "ws1", "type": "web_search", "query": "환율 {secret}"}}}})
time.sleep({pause})
emit({{"type": "item.completed", "item": {{"id": "ws1", "type": "web_search", "action": {{"type": "search", "query": "환율"}}}}}})
emit({{"type": "item.completed", "item": {{"id": "m1", "type": "agent_message", "text": "환율을 찾았습니다."}}}})
'''


class CliStreamingTests(unittest.TestCase):
    def fake_cli(self, pause=1.5):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        script = root / 'fake-codex'
        script.write_text(STREAMING_CLI.format(python=sys.executable, secret=SECRET, pause=pause))
        script.chmod(0o755)
        return root, script

    def test_stdout_lines_arrive_while_the_cli_runs_and_the_output_is_unchanged(self):
        root, script = self.fake_cli()
        seen = []
        started = time.monotonic()
        completed = bounded_run(subprocess.run, [str(script)], cwd=root, env=dict(os.environ), timeout=30,
                                on_line=lambda line: seen.append((time.monotonic() - started, line)))
        ended = time.monotonic() - started
        self.assertEqual(len(seen), 3)
        self.assertLess(seen[0][0], ended - 1.0, 'the first event was seen well before the CLI exited')
        self.assertEqual(completed.stdout, ''.join(line for _at, line in seen))
        self.assertEqual(completed.returncode, 0)

    def test_stop_still_kills_a_streaming_cli(self):
        root, script = self.fake_cli(pause=60)
        flag = []
        threading.Timer(1.0, lambda: flag.append('stopped')).start()
        started = time.monotonic()
        from personal_agent.bounded_execution import EngineInterrupted
        with self.assertRaises(EngineInterrupted):
            bounded_run(subprocess.run, [str(script)], cwd=root, env=dict(os.environ), timeout=30,
                        interrupted=lambda: flag[0] if flag else None, on_line=lambda line: None)
        self.assertLess(time.monotonic() - started, 10)


LINGERING_CLI = '''#!{python}
import json, os, subprocess, sys
# A descendant that inherits stdout/stderr and keeps them open after the CLI exits.
child = subprocess.Popen([{python!r}, "-c", "import os, time; {setsid}time.sleep(60)"])
open({marker!r}, "w").write(str(child.pid))
print(json.dumps({{"type": "item.completed", "item": {{"id": "m1", "type": "agent_message", "text": "done"}}}}))
sys.stdout.flush()
os._exit(0)
'''


def _gone(pid, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


class LingeringDescendantTests(unittest.TestCase):
    """PR #722 P1: a descendant holding the pipes never blocks the deadline or Stop."""

    def lingering(self, escape=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        marker = root / 'child.pid'
        script = root / 'fake-cli'
        script.write_text(LINGERING_CLI.format(python=sys.executable, marker=str(marker),
                                               setsid='os.setsid(); ' if escape else ''))
        script.chmod(0o755)

        def cleanup():
            if marker.exists():
                try:
                    os.kill(int(marker.read_text()), 9)
                except (ProcessLookupError, ValueError):
                    pass
        self.addCleanup(cleanup)
        return root, script, marker

    def test_the_deadline_kills_the_group_when_a_child_holds_stdout(self):
        root, script, marker = self.lingering()
        seen = []
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            bounded_run(subprocess.run, [str(script)], cwd=root, env=dict(os.environ), timeout=2,
                        on_line=seen.append)
        self.assertLess(time.monotonic() - started, 2 + 5, 'bounded by the deadline, not by the child')
        self.assertEqual(len(seen), 1, 'the line the CLI wrote was still streamed')
        self.assertTrue(_gone(int(marker.read_text())), 'the lingering child is killed with the group')

    def test_stop_while_draining_kills_the_group(self):
        root, script, marker = self.lingering()
        flag = []
        threading.Timer(0.8, lambda: flag.append('stopped')).start()
        started = time.monotonic()
        from personal_agent.bounded_execution import EngineInterrupted
        with self.assertRaises(EngineInterrupted) as caught:
            bounded_run(subprocess.run, [str(script)], cwd=root, env=dict(os.environ), timeout=60,
                        interrupted=lambda: flag[0] if flag else None, on_line=lambda line: None)
        self.assertEqual(caught.exception.reason, 'stopped')
        self.assertLess(time.monotonic() - started, 8)
        self.assertTrue(_gone(int(marker.read_text())))

    def test_a_descendant_outside_the_group_cannot_hold_the_run_after_the_kill(self):
        # It left the process group, so the kill misses it; draining is bounded
        # and the pipes are closed rather than waited on forever.
        root, script, marker = self.lingering(escape=True)
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            bounded_run(subprocess.run, [str(script)], cwd=root, env=dict(os.environ), timeout=2,
                        on_line=lambda line: None)
        self.assertLess(time.monotonic() - started, 2 + 8)


class _TelegramCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name) / 'data')
        self.calls = []
        self.update_id, self.message_id = 100, 500

        def transport(url, body=None, headers=None, timeout=60):
            method = url.rsplit('/', 1)[-1]
            self.calls.append((method, body))
            if method == 'sendMessage':
                return {'ok': True, 'result': {'message_id': 9000 + len(self.calls)}}
            return {'ok': True, 'result': True}
        self.transport = transport

    def pair(self, service):
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION, 'cursor': 0})
        self.service = service

    def receive(self, text):
        self.update_id += 1
        self.message_id += 1
        self.service.ingest_update({'update_id': self.update_id, 'message': {
            'message_id': self.message_id, 'from': {'id': CHAT}, 'chat': {'id': CHAT, 'type': 'private'},
            'text': text}}, GENERATION)
        return self.store.jobs()[0]['id']

    def drafts(self):
        """Each draft edit as the text it shows (#858: the thinking block's text)."""
        return [draft_body_text(body) for method, body in self.calls if method in DRAFT_METHODS]


class ScriptedLoopDraftTests(_TelegramCase):
    """The direct-API loop: each draft follows the observed step."""

    def setUp(self):
        super().setUp()
        self.script = []           # model turns: list of tool-call batches, then text
        self.ticks = {}            # hook name -> offsets (seconds after the request) to tick at
        self.job = None

        def model(url, body, headers=None, timeout=60):
            tools = [t.get('function', {}).get('name') or t.get('name') for t in body.get('tools', [])]
            if 'agentos_connection_probe' in tools:
                return {'message': {'content': '', 'tool_calls': [
                    {'id': 'probe', 'function': {'name': 'agentos_connection_probe', 'arguments': {}}}]}}
            self.tick('model')
            turn = self.script.pop(0) if self.script else '확인했습니다.'
            if isinstance(turn, str):
                return {'message': {'content': turn}}
            return {'message': {'content': '', 'tool_calls': [
                {'id': f'c{index}', 'function': {'name': name, 'arguments': args}} for index, (name, args) in enumerate(turn)]}}
        self.pair(AgentService(self.store, ModelAdapter(model), self.transport))
        self.service.save_model({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434', 'model': 'm', 'api_key': ''})
        self.assertTrue(self.service.test_model()['ok'])
        self.calls.clear()
        original = Capabilities.execute
        test = self

        def execute(caps, name, args):
            test.tick(name)
            return original(caps, name, args)
        patcher = mock.patch.object(Capabilities, 'execute', execute)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tick(self, hook):
        running = [job for job in self.store.jobs() if job['status'] == 'running']
        offsets = self.ticks.get(hook)
        if running and offsets:
            for offset in offsets.pop(0) if isinstance(offsets[0], tuple) else (offsets.pop(0),):
                self.service.acknowledge_long_work(now=running[0]['created'] + offset)

    def run_turn(self, text):
        job_id = self.receive(text)
        self.service.run_one()
        self.service.deliver_one()
        return self.store.job(job_id)

    def test_the_draft_follows_each_step_with_model_status_or_generic_fallback(self):
        self.script = [[('list_notes', {'status': '저장한 메모를 훑어보고 있어요'})],
                       [('list_memory', {})],
                       '정리했습니다.']
        # Model turn 1 at +6 s, the note read at +8 s, model turn 2 at +9 s and
        # the memory read at +9.2 s (both rate-limited), the memory read again
        # at +10 s, model turn 3 at +13 s.
        self.ticks = {'model': [6, 9, 13], 'list_notes': [8], 'list_memory': [(9.2, 10)]}
        job = self.run_turn('메모랑 기억 좀 정리해줘')
        # #835: each edit advances the dots; the step line (if any) comes first.
        self.assertEqual(self.drafts(), [DOTS[0], f'저장한 메모를 훑어보고 있어요 {DOTS[1]}', f'기억 확인 중 {DOTS[2]}', DOTS[0]])
        draft_ids = {body['draft_id'] for method, body in self.calls if method in DRAFT_METHODS}
        self.assertEqual(draft_ids, {draft_id_for(job['id'])}, 'one draft, edited in place (Stop maps back)')
        for method, body in self.calls:
            if method in DRAFT_METHODS:
                self.assertTrue(body['can_stop'])
        # #858: the animated thinking block, never the plain draft while the rich one is accepted.
        self.assertNotIn('sendMessageDraft', [method for method, _body in self.calls])
        # The status is recorded on the call's own running event, never passed to the tool.
        steps = [event['trace'].get('step') for event in self.store.task_events(job['id']) if event['status'] == 'running']
        self.assertIn({'action': 'list_notes', 'status': '저장한 메모를 훑어보고 있어요'}, steps)

    def test_rate_limit_shows_at_most_one_edit_per_interval_and_always_the_latest(self):
        self.script = [[('list_notes', {'status': '첫 단계'})], [('list_memory', {'status': '둘째 단계'})], '끝']
        # Draft at +6; +6.5 inside the interval (first step skipped); +7.6 shows the latest (second step).
        self.ticks = {'model': [6], 'list_notes': [6.5], 'list_memory': [7.6]}
        self.run_turn('두 단계 해줘')
        self.assertEqual(self.drafts(), [DOTS[0], f'둘째 단계 {DOTS[1]}'])
        self.assertEqual(PresenceTiming().dots_refresh, 1.5)

    def test_stop_ends_step_drafts(self):
        self.script = [[('list_notes', {'status': '메모 보는 중'})], [('list_memory', {'status': '기억 보는 중'})], '끝']
        outcomes = []
        self.ticks = {'model': [6], 'list_notes': [8]}
        original_tick = self.tick

        def tick(hook):
            original_tick(hook)
            if hook == 'list_notes':
                job = [j for j in self.store.jobs() if j['status'] == 'running'][0]
                outcomes.append(self.service.ingest_stop({'chat': {'id': CHAT, 'type': 'private'},
                                                          'draft_id': draft_id_for(job['id'])}, GENERATION))
                for offset in (10, 30):
                    self.service.acknowledge_long_work(now=job['created'] + offset)
        self.tick = tick
        self.run_turn('긴 조사 부탁해')
        self.assertEqual(outcomes, ['running'])
        self.assertEqual(self.drafts(), [DOTS[0], f'메모 보는 중 {DOTS[1]}'], 'no draft after Stop')

    def test_a_stored_secret_in_the_status_never_reaches_the_draft(self):
        self.store.secret('decision_model_key', SECRET)
        self.script = [[('list_notes', {'status': f'{SECRET} 메모 확인 중'})], '끝']
        self.ticks = {'model': [6], 'list_notes': [8]}
        job = self.run_turn('메모 보여줘')
        self.assertEqual(len(self.drafts()), 2)
        for text in self.drafts():
            self.assertNotIn(SECRET, text)
        for event in self.store.task_events(job['id']):
            self.assertNotIn(SECRET, json.dumps(event['trace'], ensure_ascii=False))

    def test_a_value_saved_in_this_work_never_reaches_the_draft(self):
        self.script = [[('save_note', {'content': '사물함 번호는 4719-8826 입니다'})],
                       [('list_notes', {'status': '4719-8826 메모 다시 확인 중'})], '끝']
        self.ticks = {'model': [6], 'list_notes': [8]}
        job = self.run_turn('사물함 정보 정리 부탁해')
        saved = [e for e in self.store.task_events(job['id']) if e['tool'] == 'save_note' and e['status'] == 'succeeded']
        self.assertTrue(saved, 'the note write ran, so its value is a saved private value of this Work')
        shown = self.drafts()
        # #881: the masked status gives way to the step's plain line.
        self.assertEqual(shown, [DOTS[0], f'메모 확인 중 {DOTS[1]}'])
        steps = [event['trace']['step'] for event in self.store.task_events(job['id'])
                 if event['status'] == 'running' and event['tool'] == 'list_notes']
        self.assertNotIn('4719', json.dumps(steps, ensure_ascii=False), 'redacted before it is recorded')

    def test_display_redaction_repeats_the_saved_value_pass_on_a_recorded_line(self):
        # A step recorded by another process (the CLI's bridge) is scrubbed
        # again with this Work's saved values before it reaches Telegram.
        import hashlib
        self.script = [[('list_notes', {'status': '메모 보는 중'})], '끝']
        self.ticks = {'model': [6]}
        original_tick = self.tick
        content = '사물함 번호는 4719-8826 입니다'

        def tick(hook):
            original_tick(hook)
            if hook == 'list_notes':
                job = [j for j in self.store.jobs() if j['status'] == 'running'][0]
                with self.store.db() as db:
                    db.execute('INSERT INTO notes(id,content,created) VALUES (?,?,?)',
                               (hashlib.sha256((job['id'] + content).encode()).hexdigest(), content, time.time()))
                    db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                               (job['id'], 'bridge_tool', 'running', json.dumps({'step': {
                                   'action': 'list_notes', 'status': '4719-8826 확인 중'}}, ensure_ascii=False), time.time()))
                self.service.acknowledge_long_work(now=job['created'] + 8)
        self.tick = tick
        self.run_turn('사물함 정보 보여줘')
        # #881: the masked status gives way to the step's plain line; the internal mark is never shown.
        self.assertEqual(self.drafts(), [DOTS[0], f'메모 확인 중 {DOTS[1]}'])

    def test_pending_approval_prompt_is_the_only_surface(self):
        self.script = [[('list_notes', {'status': '메모 보는 중'})], '끝']
        self.ticks = {'model': [6], 'list_notes': [8]}
        original_tick = self.tick

        def tick(hook):
            if hook == 'list_notes':
                job = [j for j in self.store.jobs() if j['status'] == 'running'][0]
                self.service.queue_notification(job, 'browser_approval_needed', fingerprint='d1')
            original_tick(hook)
        self.tick = tick
        self.run_turn('메모 보여줘')
        self.assertEqual(self.drafts(), [DOTS[0]])


CLI_WITH_SEARCH = '''#!{python}
import json, os, sys, time
if "exec" not in sys.argv:
    print("codex-cli 0.0.0"); sys.exit(0)
def emit(value):
    print(json.dumps(value)); sys.stdout.flush()
emit({{"type": "item.started", "item": {{"id": "ws1", "type": "web_search", "query": "환율 {secret}"}}}})
deadline = time.time() + 20
while not os.path.exists({go!r}) and time.time() < deadline:
    time.sleep(0.05)
emit({{"type": "item.completed", "item": {{"id": "ws1", "type": "web_search", "action": {{"type": "search", "query": "환율"}}}}}})
emit({{"type": "item.completed", "item": {{"id": "m1", "type": "agent_message", "text": "환율을 찾았습니다."}}}})
'''


class CliRouteDraftTests(_TelegramCase):
    """The CLI route: the CLI's own search item updates the draft during the run."""

    def test_streamed_native_search_updates_the_draft_while_the_cli_runs(self):
        root = Path(self.temp.name)
        go = root / 'go'
        script = root / 'fake-codex'
        script.write_text(CLI_WITH_SEARCH.format(python=sys.executable, secret=SECRET, go=str(go)))
        script.chmod(0o755)
        (root / 'codex-home').mkdir()
        adapter = BoundedExecutionAdapter(finder=lambda _: str(script), runtime_root=root / 'turns',
                                          codex_home=root / 'codex-home')
        self.pair(AgentService(self.store, None, self.transport,
                               subscription_engines=SubscriptionEngines(finder=lambda _: str(script), clock=lambda: 1),
                               execution_adapter=adapter))
        self.store.secret('decision_model_key', SECRET)
        self.service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        self.calls.clear()
        job_id = self.receive('오늘 환율 알려줘')
        during = []

        def watch():
            deadline = time.time() + 20
            while time.time() < deadline and not self.service.live_steps.get(job_id):
                time.sleep(0.05)
            job = self.store.job(job_id)
            if job:
                self.service.acknowledge_long_work(now=job['created'] + 6)
                during.append(list(self.drafts()))
            go.write_text('go')
        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        self.assertTrue(self.service.run_one())
        watcher.join(5)
        self.assertEqual(len(during), 1)
        [line] = during[0]
        # #881: the redacted query carries a mark, so the plain search line is shown instead.
        self.assertTrue(line.startswith('웹 검색 중 '), line)
        self.assertNotIn(SECRET, line, 'the query is redacted like the recorded event')
        self.assertNotIn('[redacted]', line)
        self.assertNotIn(job_id, self.service.live_steps, 'the live step ends with the run')
        self.assertEqual(self.store.job(job_id)['status'], 'succeeded')


if __name__ == '__main__':
    unittest.main()

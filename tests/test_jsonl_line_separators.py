"""ORCH-07 (#796): CLI JSON Lines are split on "\\n" only.

Observed on the owner installation (Works 81b261a9, c32d135d, dc7e68b6): a
page the browser tool read carried U+2028 in its headings, Codex echoed the
tool result raw in its JSONL (serde_json does not escape U+2028), and
``str.splitlines`` cut that record in two, so a turn that ended normally was
failed as ``invalid-output``.  Model-free: every stream here is a fixture.
"""
import json
import tempfile
import unittest
from pathlib import Path

from personal_agent import bounded_execution as be
from personal_agent.bounded_execution import (AgentOSMcpTools, BoundedExecutionAdapter, ExecutionError, cli_metadata,
                                              failure_details, jsonl_lines)
from personal_agent.decision_adapters import SubscriptionCliDecisionEngine
from personal_agent.isolated_engine_sidecar import IsolatedEngineSidecar

from test_bounded_execution import _Capabilities

#: The characters str.splitlines splits on that JSON leaves unescaped.
SEPARATORS = (' ', ' ', '\u0085')


def raw_json(value):
    """JSON as the CLIs write it: non-ASCII, and so these separators, unescaped."""
    return json.dumps(value, ensure_ascii=False)


def codex_stream(page_text, answer='내일 일정은 없습니다.'):
    return '\n'.join([
        raw_json({'type': 'thread.started', 'thread_id': 't'}),
        raw_json({'type': 'item.completed', 'item': {'type': 'mcp_tool_call', 'tool': 'browser_open', 'status': 'completed',
                                                     'result': {'content': [{'type': 'text', 'text': page_text}]}}}),
        raw_json({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': answer}}),
        raw_json({'type': 'turn.completed', 'usage': {'input_tokens': 1}}),
    ]) + '\n'


class JsonlLines(unittest.TestCase):
    def test_only_newline_separates_records(self):
        for separator in SEPARATORS:
            with self.subTest(separator=hex(ord(separator))):
                stream = codex_stream(f'Schedule events faster{separator}with Gemini')
                self.assertGreater(len(stream.splitlines()), len(stream.strip().split('\n')), 'the defect this covers')
                lines = jsonl_lines(stream)
                self.assertEqual(len(lines), 4)
                self.assertTrue(all(isinstance(json.loads(line), dict) for line in lines))

    def test_crlf_and_blank_lines(self):
        self.assertEqual(jsonl_lines('{"a": 1}\r\n\r\n  \n{"b": 2}\r\n'), ['{"a": 1}', '{"b": 2}'])
        self.assertEqual(jsonl_lines(None), [])


class FinalAnswer(unittest.TestCase):
    def test_codex_answer_survives_a_tool_result_with_a_line_separator(self):
        for separator in SEPARATORS:
            with self.subTest(separator=hex(ord(separator))):
                stream = codex_stream(f'Your schedule, organized {separator}across Workspace')
                self.assertEqual(BoundedExecutionAdapter._content('codex', stream), '내일 일정은 없습니다.')

    def test_an_answer_containing_a_separator_is_returned_whole(self):
        stream = codex_stream('page', answer='첫 줄 둘째 줄')
        self.assertEqual(BoundedExecutionAdapter._content('codex', stream), '첫 줄 둘째 줄')

    def test_claude_code_result_record_with_a_separator(self):
        stream = '\n'.join([raw_json({'type': 'user', 'content': 'tool text more'}),
                            raw_json({'type': 'result', 'result': 'done ', 'is_error': False})])
        self.assertEqual(BoundedExecutionAdapter._content('claude-code', stream), 'done ')

    def test_a_genuinely_broken_stream_still_fails(self):
        with self.assertRaises(ExecutionError) as caught:
            BoundedExecutionAdapter._content('codex', codex_stream('page') + 'not json\n')
        self.assertEqual(str(caught.exception), '엔진이 요구된 구조화된 응답을 반환하지 않았습니다.')

    def test_the_whole_turn_succeeds_through_execute(self):
        stream = codex_stream('Schedule events faster with Gemini in Gmail')

        class Done:
            returncode = 0
            stdout = stream
            stderr = ''
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder) / 'home'
            home.mkdir()
            adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=lambda argv, **kw: Done(),
                                              runtime_root=Path(folder) / 'turns', codex_home=home)
            result = adapter.execute('codex', 'hello', AgentOSMcpTools(_Capabilities()))
        self.assertEqual(result.content, '내일 일정은 없습니다.')
        self.assertEqual([call['name'] for call in result.meta['tool_calls']], ['browser_open'],
                         'the split record is no longer dropped from the run metadata')


class OtherReaders(unittest.TestCase):
    def test_run_metadata_keeps_the_record(self):
        meta = cli_metadata('codex', codex_stream('a b'))
        self.assertEqual(meta['tool_calls'], [{'type': 'mcp_tool_call', 'name': 'browser_open', 'status': 'completed'}])

    def test_failure_details_reads_the_error_after_such_a_record(self):
        stream = '\n'.join([
            raw_json({'type': 'item.completed', 'item': {'type': 'mcp_tool_call', 'result': 'a b'}}),
            raw_json({'type': 'turn.failed', 'error': {'message': raw_json(
                {'type': 'error', 'status': 503, 'error': {'message': 'upstream busy'}})}}),
        ])
        status, _reason = failure_details('codex', stream, '')
        self.assertEqual(status, 503)

    def test_decision_answer_with_a_separator_is_not_malformed(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder) / 'home'
            home.mkdir()
            execution = BoundedExecutionAdapter(finder=lambda name: None, runner=None,
                                                runtime_root=Path(folder) / 'runs', codex_home=home)
            engine = SubscriptionCliDecisionEngine(execution, 'codex', codex_disabled_features=())
            answer = raw_json({'choice': 'retry', 'reason': '앞 요청 다시'})
            stream = '\n'.join([raw_json({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': answer}}),
                                raw_json({'type': 'turn.completed'})])
            self.assertEqual(engine._structured(stream), {'choice': 'retry', 'reason': '앞 요청 다시'})

    def test_isolated_sidecar_result(self):
        self.assertEqual(IsolatedEngineSidecar._result(codex_stream('x y')), '내일 일정은 없습니다.')


if __name__ == '__main__':
    unittest.main()

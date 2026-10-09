"""#1130: a bridge that cannot start is a host failure, not a worker shortfall."""
import json
import tempfile
import tomllib
import unittest
from importlib import metadata
from pathlib import Path
from unittest import mock

from personal_agent import bounded_execution
from personal_agent.bounded_execution import (BRIDGE_UNAVAILABLE, MCP_SDK_VERSION, AgentOSMcpTools,
                                              BoundedExecutionAdapter, ExecutionError, bridge_sdk_problem,
                                              claude_bridge_status)
from test_bounded_execution import _Capabilities
from test_orchestrator import NO_TOOL_CALLS, Harness, plan

ROOT = Path(__file__).resolve().parents[1]


def _init(status):
    return json.dumps({'type': 'system', 'subtype': 'init', 'mcp_servers': [{'name': 'agentos', 'status': status}]})


class SdkCheck(unittest.TestCase):
    def test_the_checked_version_is_the_mcp_host_pin(self):
        with open(ROOT / 'pyproject.toml', 'rb') as handle:
            extras = tomllib.load(handle)['project']['optional-dependencies']
        self.assertEqual(extras['mcp-host'], [f'mcp=={MCP_SDK_VERSION}'])

    def test_missing_or_other_sdk_is_named_and_the_pin_passes(self):
        def missing(_name):
            raise metadata.PackageNotFoundError('mcp')
        with mock.patch('importlib.metadata.version', missing):
            self.assertIn('not installed', bridge_sdk_problem())
        with mock.patch('importlib.metadata.version', lambda _name: '1.26.0'):
            self.assertIn('1.26.0', bridge_sdk_problem())
        with mock.patch('importlib.metadata.version', lambda _name: MCP_SDK_VERSION):
            self.assertIsNone(bridge_sdk_problem())


class AdapterRefusal(unittest.TestCase):
    def adapter(self, folder, runner):
        return BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=runner,
                                       runtime_root=Path(folder) / 'turns', codex_home=Path(folder),
                                       credentials=lambda _engine: '')

    def test_no_cli_is_launched_without_a_bridge(self):
        launched = []
        with tempfile.TemporaryDirectory() as folder:
            adapter = self.adapter(folder, lambda *a, **k: launched.append(a))
            adapter.bridge_check = lambda: 'mcp SDK 1.26.0 is installed; the bridge needs 2.3.0'
            for engine in ('codex', 'claude-code'):
                with self.subTest(engine=engine), self.assertRaises(ExecutionError) as caught:
                    adapter.execute(engine, 'hello', AgentOSMcpTools(_Capabilities()))
                self.assertEqual(caught.exception.failure_class, BRIDGE_UNAVAILABLE)
                self.assertIn('1.26.0', caught.exception.reason)
                self.assertIn('mcp-host', str(caught.exception))
        self.assertEqual(launched, [])

    def test_claude_reporting_a_failed_bridge_is_not_an_answer(self):
        result = json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'no browser tool here'})

        class Done:
            returncode, stderr = 0, ''

        for status, fails in (('failed', True), ('connected', False)):
            Done.stdout = _init(status) + '\n' + result
            with self.subTest(status=status), tempfile.TemporaryDirectory() as folder:
                adapter = self.adapter(folder, lambda *a, **k: Done())
                adapter.bridge_check = lambda: None
                if fails:
                    with self.assertRaises(ExecutionError) as caught:
                        adapter.execute('claude-code', 'hello', AgentOSMcpTools(_Capabilities()))
                    self.assertEqual((caught.exception.failure_class, caught.exception.exit_code), (BRIDGE_UNAVAILABLE, 0))
                else:
                    self.assertEqual(adapter.execute('claude-code', 'hello', AgentOSMcpTools(_Capabilities())).content,
                                     'no browser tool here')

    def test_status_reads_only_the_init_record(self):
        self.assertEqual(claude_bridge_status(_init('pending') + '\n{}'), 'pending')
        self.assertIsNone(claude_bridge_status(json.dumps({'type': 'result', 'mcp_servers': [{'name': 'agentos', 'status': 'failed'}]})))
        self.assertIsNone(claude_bridge_status('not json'))


class NoCliRedelegation(Harness):
    def failure(self):
        return ExecutionError(bounded_execution.BRIDGE_UNAVAILABLE_TEXT, failure_class=BRIDGE_UNAVAILABLE,
                              reason='mcp SDK is not installed', meta=NO_TOOL_CALLS)

    def test_another_cli_is_not_tried_but_an_api_route_is(self):
        self.engine.fail = [self.failure()]
        self.script([plan('codex', 'Look it up.'), plan('openai', 'Answer directly.')])
        _job, row = self.run_work('알려줘')
        self.assertEqual(len(self.engine.turns), 1)
        self.assertEqual((row['status'], row['response']), ('succeeded', 'api answer'))

    def test_a_planned_cli_after_the_failure_is_refused(self):
        self.engine.fail = [self.failure()]
        self.script([plan('codex', 'Look it up.'), plan('codex', 'Try again.', model='gpt-5.6-luna')])
        _job, row = self.run_work('알려줘')
        self.assertEqual(len(self.engine.turns), 1, 'no second CLI turn')
        self.assertEqual(row['status'], 'failed')


if __name__ == '__main__':
    unittest.main()

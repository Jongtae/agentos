"""DECISION-ROUTE-01 / #580: owner-selectable DecisionEngine routes.

Evidence class: deterministic unit tests with fixture transports - a fake
OpenAI-compatible HTTP transport, a fake TypeSafe/Jev HTTP transport shaped
after the documented API reference, and a fake subprocess runner shaped
after the installed Codex 0.153.4 / Claude Code 2.1.280 machine output.
No live provider, CLI, account or credential is used, and nothing here
claims that any route is available, calibrated or accepted by a real
account.
"""
import json
import os
import tempfile
import types
import unittest
from pathlib import Path

from personal_agent.bounded_execution import BoundedExecutionAdapter
from personal_agent.conversation_handoff import ConversationJudgments, JUDGMENT_YES
from personal_agent.decision import (NO_CANDIDATE, OUTCOME_CANCELLED, OUTCOME_DECIDED, OUTCOME_MALFORMED,
                                     OUTCOME_REJECTED, OUTCOME_TIMEOUT, OUTCOME_UNAVAILABLE, DecisionContext,
                                     ModelDecisionEngine, UnavailableDecisionEngine)
from personal_agent.decision_adapters import (CODEX_DECISION_CONFIG, JEV_ENDPOINT, JevDecisionEngine,
                                              SubscriptionCliDecisionEngine, bounded_run, codex_disable_plan,
                                              parse_codex_features)
from personal_agent.decision_qualification import CASE_IDS, SUITE_VERSION, qualify
from personal_agent.decision_routes import CODEX_INSTRUCTION_FILES_QUALIFIED, DecisionRouteError
from personal_agent.providers import ModelAdapter, ProviderError
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines

OPENAI_KEY = 'sk-fixture-openai-0001'
JEV_KEY = 'ts-fixture-jev-0001'


# --- one semantic oracle, spoken in every vendor format -----------------------
def oracle(purpose, facts, kind, options):
    """The expected judgment for a case, independent of any adapter.

    Returns ``(value, confidence)`` - a bool for judge, an option for choose.
    """
    message = facts.get('owner_message', '')
    if kind == 'choose_many':
        # #605 lookup probe: withhold the identifier term (a fixture oracle).
        terms = dict(part.split(' = ', 1) for part in facts.get('terms', '').split('; ') if ' = ' in part)
        return [label for label in options if any(ch.isdigit() for ch in terms.get(label, ''))], 0.9
    if kind == 'judge':
        return ('취소' in message or '안 해도' in message), 0.9
    if purpose in ('conversation-followup', 'decision-route-probe'):
        value = {'다시 해봐': 'retry', '아니 4시로': 'correction', '그거 저장해': 'reference'}.get(message, NO_CANDIDATE)
    elif purpose == 'unsupported-capability':
        value = 'mail-send' if '보내' in message else NO_CANDIDATE
    elif purpose == 'conversation-projection':
        value = facts.get('observed_status')
    else:  # an ambiguous referent: abstain
        value = NO_CANDIDATE
    assert value in options, (purpose, value, options)
    return value, 0.9


def careless(purpose, facts, kind, options):
    """A fluent but unqualified engine: always confident, always the first option."""
    if kind == 'choose_many':
        return [], 0.95
    return (True if kind == 'judge' else options[0]), 0.95


def parse_prompt(text):
    """Purpose and facts from the rendered DecisionContext inside a prompt."""
    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith('Purpose: '))
    purpose, facts = lines[start][len('Purpose: '):], {}
    for line in lines[start + 1:]:
        if not line.strip():
            break
        key, _, value = line.partition(': ')
        facts[key] = value
    return purpose, facts


def schema_answer(schema, purpose, facts, judge=oracle):
    props = schema['properties']
    if 'answer' in props:
        value, confidence = judge(purpose, facts, 'judge', None)
        return {'answer': value, 'confidence': confidence}
    if 'choice' in props:
        value, confidence = judge(purpose, facts, 'choose', props['choice']['enum'])
        return {'choice': value, 'confidence': confidence}
    if 'choices' in props:
        value, confidence = judge(purpose, facts, 'choose_many', props['choices']['items']['enum'])
        return {'choices': value, 'confidence': confidence}
    return {'score': props['score']['minimum'], 'confidence': 0.9}


class OpenAITransport:
    def __init__(self, judge=oracle, model='gpt-4o-mini-2024-07-18'):
        self.judge, self.model, self.calls = judge, model, []

    def __call__(self, url, body, headers=None, timeout=60):
        self.calls.append(url)
        if not url.endswith('/chat/completions'):
            raise AssertionError('unexpected call ' + url)
        purpose, facts = parse_prompt(body['messages'][-1]['content'])
        arguments = schema_answer(body['tools'][0]['function']['parameters'], purpose, facts, self.judge)
        reply = {'choices': [{'message': {'role': 'assistant', 'tool_calls': [
            {'id': 'c1', 'type': 'function', 'function': {'name': 'decide', 'arguments': json.dumps(arguments)}}]}}]}
        if self.model:
            reply['model'] = self.model
        return reply


class JevTransport:
    """Replies in the shape of docs.typesafe.ai/api (answers keyed by question id)."""

    def __init__(self, judge=oracle, fail=None):
        self.judge, self.fail, self.calls = judge, fail, []

    def __call__(self, url, body, headers=None, timeout=60):
        self.calls.append({'url': url, 'body': body, 'headers': headers, 'timeout': timeout})
        if self.fail:
            raise self.fail
        state = dict(body['state'])
        purpose = state.pop('purpose')
        (qid, question), = body['questions'].items()
        if question['type'] == 'noul':
            value, confidence = self.judge(purpose, state, 'judge', None)
            answer = {'type': 'noul', 'noul': confidence if value else 1 - confidence}
        elif question['type'] == 'choice':
            options = list(question['criteria'])
            value, confidence = self.judge(purpose, state, 'choose', options)
            answer = {'type': 'choice', 'choice': value, 'confidence': confidence,
                      'probabilities': {option: (confidence if option == value else 0) for option in options}}
        else:
            answer = {'type': 'score', 'score': 2.0, 'confidence': 0.8, 'legend': {}, 'probabilities': {}}
        return {'model': 'jev-1.13.0', 'answers': {qid: answer}, 'usage': {'input_tokens': 10, 'output_tokens': 2}}


CODEX_HELP = ('Usage: codex exec [OPTIONS] [PROMPT]\n -c, --config <key=value>\n --json\n --ignore-user-config\n'
              ' --ignore-rules\n --ephemeral\n --skip-git-repo-check\n --output-schema <FILE>\n -m, --model <MODEL>\n'
              ' --disable <FEATURE>\n --sandbox <MODE>\n')
CLAUDE_HELP = (' -p, --print\n --output-format <format>\n --json-schema <schema>\n --tools <tools...>\n'
               ' --strict-mcp-config\n --setting-sources <sources>\n --restricted\n --no-session-persistence\n'
               ' --system-prompt <prompt>\n --model <model>\n')
#: A `codex features list` shape (name, stage, enabled), as printed by 0.153.4.
CODEX_FEATURES = (('apps', 'stable', True), ('auth_elicitation', 'stable', True), ('browser_use', 'stable', True),
                  ('memories', 'stable', False), ('multi_agent', 'stable', True), ('personality', 'stable', True),
                  ('shell_tool', 'stable', True), ('sqlite', 'removed', True), ('unified_exec', 'stable', True),
                  ('view_image', 'stable', True), ('web_search_request', 'deprecated', False),
                  ('artifact', 'under development', False))


def features_listing(disabled=(), features=CODEX_FEATURES):
    return '\n'.join(f'{name:<40} {stage:<18} {"false" if name in disabled else str(enabled).lower()}'
                     for name, stage, enabled in features)


class CliRunner:
    """A fake `subprocess.run` for the two official CLIs.

    ``judges`` maps a requested model (``None`` = engine default) to an
    oracle, so tests can make one candidate model qualified and another not.
    """

    def __init__(self, judges=None, *, help_text=None, fail=None, logged_in=True, claude_model='claude-fixture-small',
                 features=CODEX_FEATURES, ignore_disable=()):
        self.judges = judges or {None: oracle}
        self.help_text, self.fail, self.logged_in, self.claude_model = help_text or {}, fail, logged_in, claude_model
        self.features, self.ignore_disable = features, ignore_disable
        self.calls = []

    def __call__(self, argv, cwd=None, env=None, stdin=None, capture_output=None, text=None, timeout=None, shell=None,
                 start_new_session=None):
        assert shell is False
        self.calls.append({'argv': list(argv), 'cwd': cwd, 'env': dict(env or {}), 'timeout': timeout,
                           'start_new_session': start_new_session})
        binary = os.path.basename(argv[0])
        engine = 'codex' if binary == 'codex' else 'claude-code'
        done = lambda out='', code=0, err='': types.SimpleNamespace(returncode=code, stdout=out, stderr=err)
        if '--help' in argv:
            return done(self.help_text.get(engine, CODEX_HELP if engine == 'codex' else CLAUDE_HELP))
        if '--version' in argv:
            return done('codex-cli 0.153.4' if engine == 'codex' else '2.1.280 (Claude Code)')
        if argv[1:3] == ['features', 'list']:
            disabled = {argv[i + 1] for i, part in enumerate(argv) if part == '--disable'} - set(self.ignore_disable)
            return done(features_listing(disabled, self.features))
        if argv[1:3] == ['login', 'status']:
            return done('Logged in using ChatGPT' if self.logged_in else 'Not logged in', 0 if self.logged_in else 1)
        if argv[1:3] == ['auth', 'status']:
            return done(json.dumps({'loggedIn': self.logged_in, 'authMethod': 'claude.ai'}))
        if self.fail:
            return self.fail(engine, argv)
        model = argv[argv.index('--model') + 1] if '--model' in argv else None
        judge = self.judges.get(model, careless)
        if engine == 'codex':
            schema = json.loads(Path(argv[argv.index('--output-schema') + 1]).read_text())
            purpose, facts = parse_prompt(argv[-1])
            answer = schema_answer(schema, purpose, facts, judge)
            events = [{'type': 'thread.started', 'thread_id': 't'}, {'type': 'turn.started'},
                      {'type': 'item.completed', 'item': {'id': 'i', 'type': 'agent_message', 'text': json.dumps(answer)}},
                      {'type': 'turn.completed', 'usage': {'input_tokens': 5, 'output_tokens': 1}}]
            return done('\n'.join(json.dumps(e) for e in events))
        schema = json.loads(argv[argv.index('--json-schema') + 1])
        purpose, facts = parse_prompt(argv[argv.index('-p') + 1])
        answer = schema_answer(schema, purpose, facts, judge)
        return done(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': '',
                                'structured_output': answer,
                                'modelUsage': {self.claude_model: {'inputTokens': 5}}}))


PLAN = codex_disable_plan(parse_codex_features(features_listing()))


def cli_adapter(runner, root, finder=None):
    codex_home = Path(root) / 'codex-home'
    codex_home.mkdir(exist_ok=True)
    return BoundedExecutionAdapter(finder=finder or (lambda name: f'/fixture/bin/{name}'), runner=runner,
                                   runtime_root=Path(root) / 'runs', codex_home=codex_home,
                                   credentials=lambda engine: 'cc-fixture-token-000000' if engine == 'claude-code' else '')


class Temp(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name


# --- the same semantic cases through every adapter ------------------------------
class AdapterParityTests(Temp):
    """Equivalent semantic cases across API, Jev and subscription adapters,
    asked by the unchanged production caller (ConversationJudgments)."""

    def engines(self, judge=oracle):
        runner = CliRunner({None: judge})
        execution = cli_adapter(runner, self.root)
        return {
            'direct_api': ModelDecisionEngine(ModelAdapter(OpenAITransport(judge)),
                                              lambda: ({'provider': 'openai', 'endpoint': 'https://api.openai.com/v1',
                                                        'model': 'gpt-4o-mini'}, OPENAI_KEY)),
            'jev': JevDecisionEngine(lambda: JEV_KEY, transport=JevTransport(judge)),
            'codex': SubscriptionCliDecisionEngine(execution, 'codex', codex_disabled_features=PLAN),
            'claude-code': SubscriptionCliDecisionEngine(execution, 'claude-code'),
        }

    def test_every_route_passes_the_same_qualification_suite_through_the_same_contract(self):
        for name, engine in self.engines().items():
            with self.subTest(route=name):
                result = qualify(engine, stop_on_failure=False)
                self.assertEqual(result['suite_version'], SUITE_VERSION)
                if name == 'jev':
                    # Jev's API has no multi-selection type, so it cannot serve
                    # the #605 lookup judgment and does not qualify for it.
                    self.assertEqual([row['case'] for row in result['results'] if not row['passed']],
                                     ['lookup-withholds-the-identifier'])
                    continue
                self.assertTrue(result['qualified'], (name, result['results']))
                self.assertEqual([row['case'] for row in result['results']], list(CASE_IDS))

    def test_the_caller_gets_identical_typed_answers_from_every_route(self):
        answers = set()
        for name, engine in self.engines().items():
            judged = ConversationJudgments(engine).followup_relation('다시 해봐', 'research', 'failed')
            answers.add((judged.outcome, judged.value))
            withdrawn = ConversationJudgments(engine).parked_work_withdrawn('그건 취소해줘', ('google-gmail-read',))
            answers.add(('withdrawn', withdrawn.outcome))
        self.assertEqual(answers, {(JUDGMENT_YES, 'retry'), ('withdrawn', JUDGMENT_YES)})

    def test_a_confident_but_careless_engine_does_not_qualify_on_any_route(self):
        for name, engine in self.engines(careless).items():
            with self.subTest(route=name):
                self.assertFalse(qualify(engine)['qualified'])

    def test_the_suite_is_synthetic_and_bounded(self):
        self.assertGreaterEqual(len(CASE_IDS), 8)
        self.assertEqual(len(set(CASE_IDS)), len(CASE_IDS))
        for required in ('retry-after-failed-work', 'correction-replaces-parameters', 'ambiguous-referent-abstains',
                         'no-invented-candidate', 'failed-stays-failed', 'partial-stays-partial',
                         'unknown-stays-unknown'):
            self.assertIn(required, CASE_IDS)


# --- subscription CLI isolation and failure modes -------------------------------
class SubscriptionCliTests(Temp):
    def engine(self, engine_id='codex', runner=None, **kwargs):
        self.runner = runner or CliRunner()
        self.audit = []
        if engine_id == 'codex':
            kwargs.setdefault('codex_disabled_features', PLAN)
        return SubscriptionCliDecisionEngine(cli_adapter(self.runner, self.root), engine_id, audit=self.audit.append, **kwargs)

    def context(self, **facts):
        return DecisionContext('conversation-followup', facts or {'owner_message': '다시 해봐'})

    def test_codex_runs_isolated_tool_less_and_ignores_owner_configuration(self):
        os.environ['OPENAI_API_KEY_FIXTURE_LEAK'] = 'must-not-travel'
        self.addCleanup(os.environ.pop, 'OPENAI_API_KEY_FIXTURE_LEAK', None)
        decision = self.engine().choose(self.context(), ('retry', 'reference'), 'relation?')
        self.assertEqual((decision.outcome, decision.choice), (OUTCOME_DECIDED, 'retry'))
        call = self.runner.calls[-1]
        argv = call['argv']
        for flag in ('--ignore-user-config', '--ignore-rules', '--ephemeral', '--skip-git-repo-check', '--output-schema',
                     '--json'):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index('--sandbox') + 1], 'read-only')
        disabled = [argv[i + 1] for i, part in enumerate(argv) if part == '--disable']
        self.assertEqual(sorted(disabled), ['apps', 'artifact', 'browser_use', 'memories', 'multi_agent', 'shell_tool',
                                            'unified_exec', 'view_image', 'web_search_request'],
                         'every listed non-removed feature outside the allowlist, whatever its default')
        self.assertIn('artifact', disabled, 'a feature off by default is still disabled (P3-a)')
        self.assertNotIn('personality', disabled)
        self.assertNotIn('sqlite', disabled, 'removed features are no-ops and are not passed')
        overrides = [argv[i + 1] for i, part in enumerate(argv) if part == '-c']
        self.assertEqual(overrides, [f'{key}={value}' for key, value in CODEX_DECISION_CONFIG])
        self.assertIn('web_search="disabled"', overrides)
        self.assertIn('project_doc_max_bytes=0', overrides)
        self.assertTrue(call['start_new_session'], 'the CLI runs in its own process group')
        self.assertFalse(any('mcp_servers' in part for part in argv), 'no AgentOS MCP bridge or tools for a judgment')
        self.assertNotIn('--model', argv, 'engine_default sends no model flag')
        self.assertNotIn('OPENAI_API_KEY_FIXTURE_LEAK', call['env'])
        self.assertEqual(call['env']['HOME'], str(call['cwd']), 'HOME is the fresh per-call directory')
        self.assertNotEqual(call['env']['HOME'], str(Path.home()))
        self.assertTrue(str(call['cwd']).startswith(str(Path(self.root) / 'runs')))
        self.assertFalse(Path(call['cwd']).exists(), 'the per-call directory is removed')

    def test_claude_code_runs_with_no_tools_no_mcp_and_its_own_token_only(self):
        decision = self.engine('claude-code', model='claude-fixture-small', model_policy='explicit').judge(
            DecisionContext('parked-work-withdrawal', {'owner_message': '취소해줘'}), 'withdrawn?')
        self.assertEqual((decision.outcome, decision.answer), (OUTCOME_DECIDED, True))
        call = self.runner.calls[-1]
        argv = call['argv']
        self.assertEqual(argv[argv.index('--tools') + 1], '')
        self.assertIn('--restricted', argv, 'no code-running tools or WebFetch (P3-b)')
        self.assertIn('--strict-mcp-config', argv)
        self.assertNotIn('--mcp-config', argv)
        self.assertIn('--no-session-persistence', argv)
        self.assertEqual(argv[argv.index('--model') + 1], 'claude-fixture-small')
        self.assertEqual(argv[argv.index('--setting-sources') + 1], '', 'no user/project/local settings files')
        self.assertEqual(call['env'].get('CLAUDE_CODE_OAUTH_TOKEN'), 'cc-fixture-token-000000')
        self.assertEqual((call['env'].get('CLAUDE_CODE_DISABLE_CLAUDE_MDS'), call['env'].get('CLAUDE_CODE_DISABLE_AUTO_MEMORY')),
                         ('1', '1'), 'no CLAUDE.md discovery or auto-memory')
        self.assertEqual(set(call['env']) - {'HOME', 'PATH', 'LANG', 'PYTHONPATH', 'CLAUDE_CODE_OAUTH_TOKEN',
                                             'CLAUDE_CODE_DISABLE_CLAUDE_MDS', 'CLAUDE_CODE_DISABLE_AUTO_MEMORY'}, set())

    def test_requested_and_observed_models_stay_separate(self):
        self.engine('claude-code', model='haiku', model_policy='explicit').judge(self.context(), 'p')
        self.assertEqual((self.audit[-1]['requested_model'], self.audit[-1]['observed_model']),
                         ('haiku', 'claude-fixture-small'))
        self.assertEqual((self.audit[-1]['route'], self.audit[-1]['engine'], self.audit[-1]['model_policy']),
                         ('subscription_cli', 'claude-code', 'explicit'))
        self.engine('codex').choose(self.context(), ('retry',), 'q')
        self.assertEqual(self.audit[-1]['observed_model'], 'not reported', 'Codex exec --json reports no model')
        self.assertEqual(self.audit[-1]['requested_model'], '')

    def test_every_failure_is_explicit_and_nothing_retries_elsewhere(self):
        import subprocess

        def timeout(engine, argv):
            raise subprocess.TimeoutExpired(argv, 1)
        cases = (
            (timeout, OUTCOME_TIMEOUT, 'timeout'),
            (lambda e, a: types.SimpleNamespace(returncode=1, stdout=json.dumps(
                {'type': 'turn.failed', 'error': {'message': json.dumps({'status': 401, 'error': {'message': 'bad'}})}}),
                stderr=''), OUTCOME_UNAVAILABLE, 'auth'),
            (lambda e, a: types.SimpleNamespace(returncode=1, stdout='', stderr='Error: not logged in'),
             OUTCOME_UNAVAILABLE, 'auth'),
            (lambda e, a: types.SimpleNamespace(returncode=1, stdout=json.dumps(
                {'type': 'error', 'message': json.dumps({'status': 400, 'error': {'message': 'model not supported'}})}),
                stderr=''), OUTCOME_UNAVAILABLE, 'request-rejected'),
            (lambda e, a: types.SimpleNamespace(returncode=1, stdout=json.dumps(
                {'type': 'result', 'is_error': True, 'result': 'There is an issue with the selected model', 'modelUsage': {}}),
                stderr='[claude-code:unrecognized_model] {"model":"x"}'), OUTCOME_UNAVAILABLE, 'request-rejected'),
            (lambda e, a: types.SimpleNamespace(returncode=0, stdout='{"type":"turn.completed"}', stderr=''),
             OUTCOME_MALFORMED, 'invalid-output'),
            (lambda e, a: types.SimpleNamespace(returncode=0, stdout=json.dumps(
                {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '{"choice":"invented","confidence":0.9}'}}),
                stderr=''), OUTCOME_MALFORMED, 'invalid-output'),
        )
        for fail, outcome, failure in cases:
            with self.subTest(failure=failure, outcome=outcome):
                engine = self.engine(runner=CliRunner(fail=fail))
                decision = engine.choose(self.context(), ('retry',), 'q')
                self.assertEqual(decision.outcome, outcome)
                self.assertIsNone(decision.choice)
                self.assertEqual(self.audit[-1]['failure'], failure)
                self.assertEqual(len(self.runner.calls), 1, 'no retry, no other route')

    def test_cancelled_oversized_and_missing_cli_make_no_call(self):
        engine = self.engine()
        cancelled = DecisionContext('x', {'m': 'a'}, cancelled=lambda: True)
        self.assertEqual(engine.judge(cancelled, 'p').outcome, OUTCOME_CANCELLED)
        self.assertEqual(engine.judge(DecisionContext('x', {'m': 'a' * 7000}), 'p').outcome, OUTCOME_REJECTED)
        self.assertEqual(self.runner.calls, [])
        missing = SubscriptionCliDecisionEngine(cli_adapter(self.runner, self.root, finder=lambda name: None), 'codex',
                                                codex_disabled_features=PLAN)
        self.assertEqual(missing.judge(DecisionContext('x', {'m': 'a'}), 'p').outcome, OUTCOME_UNAVAILABLE)
        self.assertEqual(self.runner.calls, [])

    def test_codex_without_a_checked_tool_surface_makes_no_call(self):
        engine = SubscriptionCliDecisionEngine(cli_adapter(CliRunner(), self.root), 'codex', audit=[].append)
        runner = engine.execution.runner
        self.assertEqual(engine.judge(DecisionContext('x', {'m': 'a'}), 'p').outcome, OUTCOME_UNAVAILABLE)
        self.assertEqual(engine.last_failure, 'capability-unchecked')
        self.assertEqual(runner.calls, [])

    def test_a_timeout_kills_the_whole_process_group(self):
        import subprocess
        import sys
        import time as clock
        marker = Path(self.root) / 'grandchild.pid'
        script = ('import subprocess,sys,time;'
                  f'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]);'
                  f'open({str(marker)!r},"w").write(str(p.pid));time.sleep(60)')
        with self.assertRaises(subprocess.TimeoutExpired):
            bounded_run(subprocess.run, [sys.executable, '-c', script], cwd=self.root, env=dict(os.environ), timeout=2)
        pid = int(marker.read_text())
        for _ in range(50):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            clock.sleep(0.1)
        else:
            os.kill(pid, 9)
            self.fail('the grandchild (the native CLI behind a wrapper) survived the timeout')

    def test_a_model_identifier_is_one_bounded_argument(self):
        for bad in ('--dangerously-bypass-approvals-and-sandbox', 'a b', '', 'x' * 200, 'm;rm'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                SubscriptionCliDecisionEngine(cli_adapter(CliRunner(), self.root), 'codex', model=bad)


# --- Jev ---------------------------------------------------------------------------
class JevTests(Temp):
    def test_requests_follow_the_documented_api_and_keep_jev_vocabulary_inside(self):
        transport, audit = JevTransport(), []
        engine = JevDecisionEngine(lambda: JEV_KEY, transport=transport, audit=audit.append, timeout=5)
        chosen = engine.choose(DecisionContext('conversation-followup', {'owner_message': '다시 해봐'}),
                               ('retry', 'reference'), 'relation?')
        self.assertEqual((chosen.outcome, chosen.choice, chosen.confidence.probability), (OUTCOME_DECIDED, 'retry', 0.9))
        call = transport.calls[0]
        self.assertEqual(call['url'], JEV_ENDPOINT)
        self.assertEqual(call['headers'], {'Authorization': 'Bearer ' + JEV_KEY})
        self.assertEqual(call['body']['model'], 'jev-latest')
        self.assertEqual(call['body']['state'], {'purpose': 'conversation-followup', 'owner_message': '다시 해봐'})
        question = call['body']['questions']['q']
        self.assertEqual((question['type'], list(question['criteria'])), ('choice', ['retry', 'reference', NO_CANDIDATE]))
        self.assertEqual(audit[-1]['observed_model'], 'jev-1.13.0')
        self.assertEqual(audit[-1]['requested_model'], 'jev-latest')
        judged = engine.judge(DecisionContext('parked-work-withdrawal', {'owner_message': '취소해줘'}), 'withdrawn?')
        self.assertEqual((judged.answer, judged.confidence.probability), (True, 0.9))
        self.assertEqual(transport.calls[-1]['body']['questions']['q']['type'], 'noul')
        scored = engine.score(DecisionContext('x', {'m': 'a'}), 'how?', (0, 10))
        self.assertEqual((scored.outcome, scored.score), (OUTCOME_DECIDED, 5.0))
        self.assertEqual(len(transport.calls[-1]['body']['questions']['q']['criteria']), 5)
        for decision in (chosen, judged, scored):
            self.assertNotIn('noul', type(decision).__name__.lower())

    def test_errors_are_explicit_and_no_key_means_no_request(self):
        transport = JevTransport()
        engine = JevDecisionEngine(lambda: '', transport=transport)
        self.assertEqual(engine.judge(DecisionContext('x', {'m': 'a'}), 'p').outcome, OUTCOME_UNAVAILABLE)
        self.assertEqual(transport.calls, [])
        for status, outcome in ((401, OUTCOME_UNAVAILABLE), (422, OUTCOME_REJECTED), (429, OUTCOME_UNAVAILABLE),
                                (529, OUTCOME_UNAVAILABLE), ('timeout', OUTCOME_TIMEOUT), (None, OUTCOME_UNAVAILABLE)):
            with self.subTest(status=status):
                failing = JevDecisionEngine(lambda: JEV_KEY, transport=JevTransport(fail=ProviderError('x', status=status)))
                self.assertEqual(failing.judge(DecisionContext('x', {'m': 'a'}), 'p').outcome, outcome)

    def test_an_answer_outside_the_declared_options_is_malformed(self):
        engine = JevDecisionEngine(lambda: JEV_KEY, transport=lambda url, body, headers, timeout: {
            'model': 'jev-1.13.0', 'answers': {'q': {'type': 'choice', 'choice': 'invented', 'confidence': 0.99}}})
        self.assertEqual(engine.choose(DecisionContext('x', {'m': 'a'}), ('a',), 'q').outcome, OUTCOME_MALFORMED)
        engine = JevDecisionEngine(lambda: JEV_KEY, transport=lambda url, body, headers, timeout: {'model': 'jev'})
        self.assertEqual(engine.judge(DecisionContext('x', {'m': 'a'}), 'p').outcome, OUTCOME_MALFORMED)


# --- service: selection, persistence, independence ----------------------------
class ServiceRouteSelectionTests(Temp):
    def service(self, runner=None, jev=None, openai=None, finder=None):
        self.store = QuickStore(self.root) if not hasattr(self, 'store') else self.store
        self.runner = runner or CliRunner()
        self.openai = openai or OpenAITransport()
        self.jev = jev or JevTransport()
        finder = finder or (lambda name: f'/fixture/bin/{name}')
        service = AgentService(self.store, ModelAdapter(self.openai), self.openai,
                               subscription_engines=SubscriptionEngines(finder=finder),
                               execution_adapter=cli_adapter(self.runner, self.root, finder=finder))
        service.decision_routes.jev_transport = self.jev
        # Fixture only: treat the fixture CLI version as instruction-file
        # qualified so the other activation paths stay testable (#624).
        service.decision_routes.codex_instruction_qualified = frozenset({'0.153.4'})
        return service

    def judge(self, service):
        return service.decision_judge.followup_relation('다시 해봐', 'research', 'failed')

    def test_opening_settings_calls_no_model_and_runs_no_cli(self):
        service = self.service(runner=CliRunner(fail=lambda e, a: self.fail('ran a CLI')))
        self.store.secret('decision_jev_key', JEV_KEY)
        self.store.put('model', {'provider': 'openai', 'endpoint': 'https://api.openai.com/v1', 'model': 'gpt-5'})
        self.store.secret('model_key', OPENAI_KEY)
        status = service.settings()['decision_route']
        self.assertEqual((self.openai.calls, self.jev.calls, self.runner.calls), ([], [], []))
        self.assertEqual(status['active']['transport'], 'direct_api')
        self.assertEqual(status['active']['source'], 'default')
        self.assertEqual(status['direct_api']['model'], 'gpt-4o-mini')
        self.assertEqual(status['jev']['destination'], 'api.typesafe.ai')
        self.assertEqual({e['id']: e['model_selection'] for e in status['subscription_cli']},
                         {'codex': 'unchecked', 'claude-code': 'unchecked'})
        self.assertNotIn(JEV_KEY, json.dumps(status))
        self.assertNotIn(OPENAI_KEY, json.dumps(status))

    def test_saving_a_credential_never_activates_a_route(self):
        service = self.service()
        service.save_decision_route_credential({'transport': 'jev', 'key': JEV_KEY})
        self.assertIsNone(self.store.config('decision_route'))
        self.assertEqual(service.settings()['decision_route']['active']['transport'], 'none')
        self.assertEqual(self.jev.calls, [])
        self.assertEqual(self.judge(service).outcome, 'unavailable', 'a saved Jev key is not an active route')
        self.assertEqual(self.jev.calls, [])

    def test_saving_a_direct_decision_key_starts_no_openai_egress(self):
        service = self.service()
        service.save_decision_route_credential({'transport': 'direct_api', 'key': OPENAI_KEY})
        self.assertIsNone(self.store.config('decision_route'))
        self.assertFalse(self.store.config('decision_model', {}), 'only activation writes decision_model')
        self.assertEqual(self.judge(service).outcome, 'unavailable')
        self.assertEqual(self.openai.calls, [], 'a saved key alone never contacts api.openai.com')
        status = service.settings()['decision_route']
        self.assertEqual(status['active']['transport'], 'none', 'the pre-#580 default is unchanged')
        self.assertTrue(status['direct_api']['configured'], 'the saved key makes the route selectable')
        service.activate_decision_route({'transport': 'direct_api'})
        self.assertEqual(len(self.openai.calls), 1, 'the explicit activation sends one probe')
        self.assertEqual(self.store.config('decision_model')['model'], 'gpt-4o-mini')
        self.assertEqual(self.judge(service).value, 'retry')

    def test_concurrent_activations_are_serialised(self):
        service = self.service()
        service.save_decision_route_credential({'transport': 'jev', 'key': JEV_KEY})
        service.decision_routes._activating.acquire()
        try:
            with self.assertRaises(DecisionRouteError) as raised:
                service.activate_decision_route({'transport': 'jev'})
            self.assertIn('이미', str(raised.exception))
        finally:
            service.decision_routes._activating.release()
        self.assertEqual(self.jev.calls, [])
        self.assertEqual(service.activate_decision_route({'transport': 'jev'})['active']['transport'], 'jev')

    def test_codex_tool_surface_is_an_allowlist_that_fails_closed(self):
        cases = (
            ('a feature that cannot be disabled', CliRunner(ignore_disable=('unified_exec',)), 'tool-features-enabled'),
            ('an unknown stage', CliRunner(features=CODEX_FEATURES + (('mystery_tool', 'beta', True),)), 'unverified'),
        )
        for label, runner, surface in cases:
            with self.subTest(label):
                self.store = QuickStore(tempfile.mkdtemp(dir=self.root))
                service = self.service(runner=runner)
                with self.assertRaises(DecisionRouteError):
                    service.activate_decision_route({'transport': 'subscription_cli', 'engine': 'codex'})
                self.assertIsNone(self.store.config('decision_route'))
                self.assertEqual(self.store.config('decision_cli_capabilities')['codex']['tool_surface'], surface)
                codex = next(e for e in service.settings()['decision_route']['subscription_cli'] if e['id'] == 'codex')
                self.assertEqual(codex['tool_surface'], surface, 'Settings shows why Codex was refused')
                if surface == 'tool-features-enabled':
                    self.assertIn('unified_exec', codex['tool_surface_detail'])
                self.assertEqual(codex['check']['failure'], 'tool-surface-unverified')
                self.assertFalse(any('exec' in call['argv'] and '--help' not in call['argv'] for call in runner.calls),
                                 'no judgment runs on an unverified tool surface')
        self.store = QuickStore(tempfile.mkdtemp(dir=self.root))
        service = self.service()
        route = service.activate_decision_route({'transport': 'subscription_cli', 'engine': 'codex'})['active']
        self.assertEqual(route['codex_disabled_features'], PLAN)
        listing = [call['argv'] for call in self.runner.calls if call['argv'][1:3] == ['features', 'list']]
        self.assertEqual(len(listing), 2, 'listed, then re-listed with the disables to verify')
        self.assertEqual(self.runner.calls[-1]['argv'].count('--disable'), len(PLAN))
        self.assertTrue(all(call['env']['CODEX_HOME'] != str(Path(self.root) / 'codex-home')
                            for call in self.runner.calls if call['argv'][1:3] == ['features', 'list']),
                        'the listing uses an empty CODEX_HOME, i.e. the defaults --ignore-user-config runs with')

    def test_help_flags_match_whole_words_only(self):
        from personal_agent.decision_routes import has_flag
        self.assertTrue(has_flag(' -m, --model <MODEL>', '--model'))
        self.assertFalse(has_flag(' --model-provider <X>', '--model'))
        self.assertFalse(has_flag(' --no-json', '--json'))
        service = self.service(runner=CliRunner(help_text={'codex': CODEX_HELP.replace(' -m, --model <MODEL>\n', ' --model-provider <P>\n')}))
        self.assertFalse(service.check_decision_cli_capabilities({'engine': 'codex'})['model_override'])

    def test_activation_probes_persists_and_survives_restart(self):
        service = self.service()
        service.save_decision_route_credential({'transport': 'jev', 'key': JEV_KEY})
        status = service.activate_decision_route({'transport': 'jev'})
        self.assertEqual((status['active']['transport'], status['active']['source']), ('jev', 'owner'))
        self.assertEqual(status['jev']['check']['observed_model'], 'jev-1.13.0')
        self.assertEqual(len(self.jev.calls), 1, 'exactly one synthetic probe on the explicit action')
        self.assertNotIn('다시 해봐 please', json.dumps(self.jev.calls))
        restarted = self.service()
        self.assertEqual(restarted.settings()['decision_route']['active']['transport'], 'jev')
        self.assertEqual(self.judge(restarted).value, 'retry')
        self.assertEqual(self.openai.calls, [], 'Jev answered; OpenAI was never contacted')

    def test_a_failed_switch_keeps_the_previous_working_route(self):
        service = self.service()
        service.save_decision_route_credential({'transport': 'direct_api', 'key': OPENAI_KEY})
        service.activate_decision_route({'transport': 'direct_api'})
        before = self.store.config('decision_route')
        service.save_decision_route_credential({'transport': 'jev', 'key': JEV_KEY})
        self.jev.fail = ProviderError('bad key', status=401)
        with self.assertRaises(DecisionRouteError) as raised:
            service.activate_decision_route({'transport': 'jev'})
        self.assertIn('그대로 유지', str(raised.exception))
        self.assertEqual(self.store.config('decision_route'), before)
        status = service.settings()['decision_route']
        self.assertEqual(status['active']['transport'], 'direct_api')
        self.assertEqual((status['jev']['check']['state'], status['jev']['check']['failure']), ('failed', 'auth'))

    def test_a_decision_key_can_be_rotated_and_removed_without_switching_routes(self):
        service = self.service()
        service.save_decision_route_credential({'transport': 'direct_api', 'key': OPENAI_KEY})
        service.activate_decision_route({'transport': 'direct_api'})
        route = self.store.config('decision_route')
        service.save_decision_route_credential({'transport': 'direct_api', 'key': 'sk-fixture-rotated-0002'})
        self.assertEqual(self.store.config('decision_route'), route, 'rotating a key does not re-activate or switch')
        self.assertEqual(service.decision_route()[1], 'sk-fixture-rotated-0002')
        service.save_decision_route_credential({'transport': 'direct_api', 'key': ''})
        self.assertIsNone(service.decision_route())
        status = service.settings()['decision_route']
        self.assertEqual((status['active']['transport'], status['active']['available']), ('direct_api', False),
                         'removal leaves the chosen route needing attention, never another route')

    def test_no_silent_cross_route_fallback(self):
        service = self.service()
        self.store.put('model', {'provider': 'openai', 'endpoint': 'https://api.openai.com/v1', 'model': 'gpt-5'})
        self.store.secret('model_key', OPENAI_KEY)
        service.save_decision_route_credential({'transport': 'jev', 'key': JEV_KEY})
        service.activate_decision_route({'transport': 'jev'})
        self.jev.fail = ProviderError('down', status=529)
        self.assertEqual(self.judge(service).outcome, 'unavailable')
        self.assertEqual(self.openai.calls, [], 'an unavailable Jev route never falls back to OpenAI')
        self.store.secret('decision_jev_key', '')
        self.assertEqual(self.judge(service).outcome, 'unavailable')
        self.assertEqual(self.openai.calls, [])

    def test_decision_and_work_routes_change_independently(self):
        service = self.service()
        self.store.put('subscription_engine', {'id': 'codex', 'connected_at': 1, 'authentication': 'owner-confirmed-official-login'})
        self.store.put('model', {'provider': 'openai', 'endpoint': 'https://api.openai.com/v1', 'model': 'gpt-5'})
        self.store.secret('model_key', OPENAI_KEY)
        self.store.put('model_test', None)
        work_before = (self.store.config('subscription_engine'), self.store.config('model'))
        service.activate_decision_route({'transport': 'subscription_cli', 'engine': 'claude-code',
                                         'model_policy': 'engine_default'})
        self.assertEqual((self.store.config('subscription_engine'), self.store.config('model')), work_before,
                         'activating the decision route never touches the Work route')
        self.assertEqual(service.settings()['subscription_engines']['selected'], 'codex')
        decision_before = self.store.config('decision_route')
        service.connect_subscription_engine({'engine': 'claude-code', 'officially_authenticated': True})
        self.assertEqual(self.store.config('subscription_engine')['id'], 'claude-code')
        self.assertEqual(self.store.config('decision_route'), decision_before,
                         'switching the Work route never touches the decision route')

    def test_subscription_model_policies_offer_only_what_the_cli_verified(self):
        no_model_flag = CliRunner(help_text={'codex': CODEX_HELP.replace(' -m, --model <MODEL>\n', '')})
        service = self.service(runner=no_model_flag)
        service.activate_decision_route({'transport': 'subscription_cli', 'engine': 'codex', 'model_policy': 'engine_default'})
        before = self.store.config('decision_route')
        for policy, extra in (('explicit', {'model': 'gpt-5-mini'}), ('lowest_qualified', {'candidates': ['a-model']})):
            with self.subTest(policy=policy):
                with self.assertRaises(DecisionRouteError) as raised:
                    service.activate_decision_route({'transport': 'subscription_cli', 'engine': 'codex',
                                                     'model_policy': policy, **extra})
                self.assertIn('모델 지정을 지원하지 않습니다', str(raised.exception))
                self.assertEqual(self.store.config('decision_route'), before)
        codex = next(e for e in service.settings()['decision_route']['subscription_cli'] if e['id'] == 'codex')
        self.assertEqual(codex['model_selection'], 'unsupported')
        self.assertFalse(any('--model' in call['argv'] for call in no_model_flag.calls),
                         'an unsupported model flag is never emulated')

    def test_claude_code_without_restricted_mode_is_refused(self):
        service = self.service(runner=CliRunner(help_text={'claude-code': CLAUDE_HELP.replace(' --restricted\n', '')}))
        with self.assertRaises(DecisionRouteError):
            service.activate_decision_route({'transport': 'subscription_cli', 'engine': 'claude-code'})
        self.assertIn('--restricted', self.store.config('decision_cli_capabilities')['claude-code']['missing_flags'])
        self.assertFalse(any('-p' in call['argv'] for call in self.runner.calls))

    def test_decision_layer_doc_states_the_codex_home_instruction_limitation(self):
        # #624: the overrides do not keep CODEX_HOME instruction files out.
        doc = (Path(__file__).resolve().parents[1] / 'docs' / 'decision-layer.en.md').read_text(encoding='utf-8')
        self.assertNotIn('(no AGENTS.md/project docs)', doc)
        for phrase in ('$CODEX_HOME/AGENTS.override.md', '$CODEX_HOME/AGENTS.md', 'untracked, untrusted input',
                       'CodexDecisionInstructionFiles', '--ignore-rules'):
            self.assertIn(phrase, doc)

    def test_codex_is_refused_until_its_instruction_files_are_qualified(self):
        # #624: no Codex version is qualified in the product; activation fails
        # closed before any judgment even when the tool surface passes.
        service = self.service()
        service.decision_routes.codex_instruction_qualified = CODEX_INSTRUCTION_FILES_QUALIFIED
        self.assertEqual(CODEX_INSTRUCTION_FILES_QUALIFIED, frozenset())
        with self.assertRaises(DecisionRouteError):
            service.activate_decision_route({'transport': 'subscription_cli', 'engine': 'codex'})
        self.assertIsNone(self.store.config('decision_route'))
        self.assertEqual(self.store.config('decision_cli_capabilities')['codex']['tool_surface'], 'allowlisted-features-only')
        self.assertFalse(any('exec' in call['argv'] and '--json' in call['argv'] for call in self.runner.calls))
        engines = {e['id']: e for e in service.settings()['decision_route']['subscription_cli']}
        self.assertEqual(engines['codex']['check']['failure'], 'instruction-files-unqualified')
        self.assertIn('AGENTS.md', engines['codex']['instruction_files'])
        self.assertEqual(engines['claude-code']['instruction_files'], '')

    def test_codex_without_ignore_rules_is_refused(self):
        # #624: a CODEX_HOME execpolicy rule must not widen a judgment's sandbox.
        service = self.service(runner=CliRunner(help_text={'codex': CODEX_HELP.replace(' --ignore-rules\n', '')}))
        with self.assertRaises(DecisionRouteError):
            service.activate_decision_route({'transport': 'subscription_cli', 'engine': 'codex'})
        self.assertIn('--ignore-rules', self.store.config('decision_cli_capabilities')['codex']['missing_flags'])
        self.assertFalse(any('exec' in call['argv'] and '--json' in call['argv'] for call in self.runner.calls))

    def test_isolation_flags_are_required_before_any_judgment(self):
        service = self.service(runner=CliRunner(help_text={'claude-code': ' --model <model>\n'}))
        with self.assertRaises(DecisionRouteError):
            service.activate_decision_route({'transport': 'subscription_cli', 'engine': 'claude-code'})
        self.assertFalse(any('-p' in call['argv'] for call in self.runner.calls))

    def test_explicit_model_is_verified_by_the_account_or_reported_unsupported(self):
        def rejected(engine, argv):
            return types.SimpleNamespace(returncode=1, stderr='', stdout=json.dumps(
                {'type': 'error', 'message': json.dumps({'status': 400, 'error': {'message': 'model not supported'}})}))
        service = self.service(runner=CliRunner(fail=rejected))
        with self.assertRaises(DecisionRouteError) as raised:
            service.activate_decision_route({'transport': 'subscription_cli', 'engine': 'codex',
                                             'model_policy': 'explicit', 'model': 'gpt-imaginary'})
        self.assertIn('확인하지 못했습니다', str(raised.exception))
        self.assertIsNone(self.store.config('decision_route'))
        check = service.settings()['decision_route']['subscription_cli'][0]['check']
        self.assertEqual((check['failure'], check['requested_model']), ('model-not-verified', 'gpt-imaginary'))
        good = self.service(runner=CliRunner({'gpt-5-mini': oracle}))
        status = good.activate_decision_route({'transport': 'subscription_cli', 'engine': 'codex',
                                               'model_policy': 'explicit', 'model': 'gpt-5-mini'})
        self.assertEqual((status['active']['model_policy'], status['active']['requested_model']), ('explicit', 'gpt-5-mini'))
        codex = next(e for e in status['subscription_cli'] if e['id'] == 'codex')
        self.assertEqual(codex['check']['observed_model'], 'not reported')

    def test_lowest_qualified_picks_the_first_qualified_declared_candidate(self):
        service = self.service(runner=CliRunner({'tiny': careless, 'small': oracle, 'large': oracle}))
        status = service.activate_decision_route({'transport': 'subscription_cli', 'engine': 'codex',
                                                  'model_policy': 'lowest_qualified', 'candidates': 'tiny, small, large'})
        active = status['active']
        self.assertEqual((active['model_policy'], active['requested_model']), ('lowest_qualified', 'small'))
        self.assertEqual(active['qualification']['suite_version'], SUITE_VERSION)
        tried = next(e for e in status['subscription_cli'] if e['id'] == 'codex')['check']['candidates']
        self.assertEqual([(row['model'], row['qualified']) for row in tried], [('tiny', False), ('small', True)])
        models = [call['argv'][call['argv'].index('--model') + 1] for call in self.runner.calls if '--model' in call['argv']]
        self.assertNotIn('large', models, 'a stronger candidate is not tried once a lighter one qualified')
        self.assertEqual(self.judge(service).value, 'retry')
        self.assertEqual(self.runner.calls[-1]['argv'][self.runner.calls[-1]['argv'].index('--model') + 1], 'small')

    def test_no_qualified_candidate_is_needs_attention_not_another_route(self):
        service = self.service(runner=CliRunner({'tiny': careless, 'small': careless}))
        with self.assertRaises(DecisionRouteError) as raised:
            service.activate_decision_route({'transport': 'subscription_cli', 'engine': 'codex',
                                             'model_policy': 'lowest_qualified', 'candidates': ['tiny', 'small']})
        self.assertIn(SUITE_VERSION, str(raised.exception))
        self.assertIsNone(self.store.config('decision_route'))
        codex = next(e for e in service.settings()['decision_route']['subscription_cli'] if e['id'] == 'codex')
        self.assertEqual(codex['check']['failure'], 'no-qualified-candidate')
        self.assertFalse(any('--model' not in call['argv'] and 'exec' in call['argv'] and '--help' not in call['argv']
                             for call in self.runner.calls), 'the engine default is not silently tried')
        self.assertEqual(self.openai.calls + self.jev.calls, [])

    def test_a_changed_cli_binary_requires_requalification(self):
        binary = Path(self.root) / 'bin' / 'codex'
        binary.parent.mkdir()
        binary.write_text('v1')
        finder = lambda name: str(binary) if name == 'codex' else None
        service = self.service(runner=CliRunner({'small': oracle}), finder=finder)
        service.activate_decision_route({'transport': 'subscription_cli', 'engine': 'codex',
                                         'model_policy': 'explicit', 'model': 'small'})
        self.assertEqual(self.judge(service).value, 'retry')
        self.assertTrue(service.settings()['decision_route']['active']['available'])
        binary.write_text('version two, different size')
        active = service.settings()['decision_route']['active']
        self.assertEqual((active['available'], active['requalification_needed']), (False, True),
                         'Settings shows the same requalification state the runtime guard enforces')
        calls = len(self.runner.calls)
        self.assertEqual(self.judge(service).outcome, 'unavailable')
        self.assertEqual(len(self.runner.calls), calls, 'no call against an unverified binary')
        self.assertEqual(self.store.config('decision_audit')[-1]['failure'], 'requalification-needed')

    def test_engine_default_is_also_bound_to_the_checked_binary(self):
        binary = Path(self.root) / 'bin' / 'claude'
        binary.parent.mkdir()
        binary.write_text('v1')
        finder = lambda name: str(binary) if name == 'claude' else None
        service = self.service(finder=finder)
        service.activate_decision_route({'transport': 'subscription_cli', 'engine': 'claude-code'})
        self.assertEqual(self.judge(service).value, 'retry')
        binary.write_text('an updated CLI with a different size')
        calls = len(self.runner.calls)
        self.assertEqual(self.judge(service).outcome, 'unavailable')
        self.assertEqual(len(self.runner.calls), calls)
        self.assertTrue(service.settings()['decision_route']['active']['requalification_needed'])

    def test_a_signed_out_cli_is_refused_and_the_route_is_off_by_choice_only(self):
        service = self.service(runner=CliRunner(logged_in=False))
        with self.assertRaises(DecisionRouteError):
            service.activate_decision_route({'transport': 'subscription_cli', 'engine': 'codex'})
        self.assertIsNone(self.store.config('decision_route'))
        service.activate_decision_route({'transport': 'off'})
        self.assertIsInstance(service.decision_routes.engine(), UnavailableDecisionEngine)

    def test_decision_trace_names_route_policy_and_models_separately(self):
        service = self.service(runner=CliRunner({'small': oracle}))
        service.activate_decision_route({'transport': 'subscription_cli', 'engine': 'claude-code',
                                         'model_policy': 'explicit', 'model': 'small'})
        service.current_work_id = 'work-1'
        self.judge(service)
        row = self.store.config('decision_audit')[-1]
        self.assertEqual({k: row[k] for k in ('route', 'engine', 'model_policy', 'requested_model', 'observed_model', 'work_id')},
                         {'route': 'subscription_cli', 'engine': 'claude-code', 'model_policy': 'explicit',
                          'requested_model': 'small', 'observed_model': 'claude-fixture-small', 'work_id': 'work-1'})
        self.assertNotIn('다시 해봐', json.dumps(row, ensure_ascii=False), 'no owner content in the audit')

    def test_route_payloads_are_validated(self):
        service = self.service()
        for body in (None, {}, {'transport': 'shell'}, {'transport': 'subscription_cli', 'engine': 'other'},
                     {'transport': 'subscription_cli', 'engine': 'codex', 'model_policy': 'strongest'}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                service.activate_decision_route(body)
        for body in ({'transport': 'jev', 'key': 'a b'}, {'transport': 'off', 'key': 'k'},
                     {'transport': 'jev', 'key': 'k', 'model': '--x y'}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                service.save_decision_route_credential(body)
        self.assertIsNone(self.store.config('decision_route'))


if __name__ == '__main__':
    unittest.main()

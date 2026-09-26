"""AGENCY-ISOLATION-01 (#616, AX-15 / AX-S19): the strict-isolated CLI profile.

Two evidence classes, named separately:

* Unit tests (always run): the declaration, the exact argv, the execute-time
  version refusal, the no-model qualification logic and the owner's choice.
  Injected runners; no CLI, model or provider is contacted.
* Process-level qualification (opt-in, ``AGENTOS_CLI_QUALIFICATION=1``): the
  exact argv ``BoundedExecutionAdapter.execute`` builds drives the real
  ``codex exec`` / ``claude -p`` against a scripted local fake model endpoint
  (loopback only; no account, credential or live provider).  The only argv
  additions are the fake provider's endpoint settings.  A fake store and a
  canary file are created and removed; no owner data is read.  Codex runs
  against a synthetic, populated CODEX_HOME (exec rules, AGENTS.md, skills,
  plugins, hooks, a widening config.toml), never the owner's real one.  The bridge's
  public network is stubbed inside the real bridge process through a
  per-turn ``usercustomize`` (the bridge itself is not replaced), as
  ``BoundedProfileHostInvocation`` does in-process.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from personal_agent.bounded_execution import (
    BASELINE_READABLE_ROOTS,
    BOUNDED_PROFILE,
    CLI_PROFILES,
    CODEX_STRICT_PERMISSIONS,
    CODEX_STRICT_TABLE,
    STRICT_PROFILE,
    TRUSTED_LOCAL_LIMITATION,
    AgentOSMcpTools,
    BoundedExecutionAdapter,
    ExecutionError,
    ExecutionResult,
    StrictIsolatedAgentOSMcpTools,
    parse_cli_version,
    strict_allowed_features,
    profile_actions,
    route_unavailable,
)
from personal_agent.decision import OUTCOME_DECIDED, DecisionContext
from personal_agent.decision_adapters import (CODEX_DECISION_CONFIG, SubscriptionCliDecisionEngine, codex_disable_plan,
                                              parse_codex_features)
from personal_agent.quickstart_store import QuickStore

ROOT = Path(__file__).resolve().parents[1]
CODEX_VERSION = CLI_PROFILES[STRICT_PROFILE]['runtimes']['codex']['tested_versions'][0]
CLAUDE_VERSION = CLI_PROFILES[STRICT_PROFILE]['runtimes']['claude-code']['tested_versions'][0]


class _Done:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class _Caps:
    def __init__(self, root):
        self.store = type('S', (), {'root': Path(root)})()
        self.job_id, self.private_provenance = 'job', set()


def _codex_answer():
    return _Done(stdout=json.dumps({'item': {'type': 'agent_message', 'text': 'answer'}}))


class StrictProfileDeclaration(unittest.TestCase):
    def test_strict_profile_is_separate_and_trusted_local_is_unchanged(self):
        strict, trusted = CLI_PROFILES[STRICT_PROFILE], CLI_PROFILES[BOUNDED_PROFILE]
        self.assertEqual((STRICT_PROFILE, strict['trust']), ('strict-isolated', 'strict-isolated'))
        self.assertEqual(trusted['trust'], 'trusted-local')
        self.assertEqual(trusted['limitation'], TRUSTED_LOCAL_LIMITATION)
        self.assertIn('/tmp', strict['limitation'], 'the residual readable paths are stated')
        self.assertEqual(CLI_PROFILES[STRICT_PROFILE]['runtimes']['codex']['tested_versions'], ('0.153.4',))
        self.assertEqual(CLI_PROFILES[STRICT_PROFILE]['runtimes']['claude-code']['tested_versions'], ('2.1.280',))

    def test_strict_offers_what_the_bridge_serves(self):
        """The bridge serves the bounded action set; strict must equal it."""
        self.assertEqual(profile_actions(STRICT_PROFILE), profile_actions(BOUNDED_PROFILE))
        self.assertEqual(route_unavailable(STRICT_PROFILE), route_unavailable(BOUNDED_PROFILE))
        self.assertEqual(StrictIsolatedAgentOSMcpTools.PROFILE, STRICT_PROFILE)

    def test_cli_versions_are_parsed_exactly(self):
        self.assertEqual(parse_cli_version('codex', 'codex-cli 0.153.4\n'), '0.153.4')
        self.assertEqual(parse_cli_version('claude-code', '2.1.280 (Claude Code)\n'), '2.1.280')
        for engine, text in (('codex', 'codex-cli 0.153.4-beta'), ('codex', ''), ('claude-code', '2.1.280'),
                             ('claude-code', 'error'), ('other', '1.0.0')):
            with self.subTest(engine=engine, text=text):
                self.assertIsNone(parse_cli_version(engine, text))


PLAN = ['apps', 'browser_use', 'hooks', 'image_generation', 'multi_agent', 'plugins', 'shell_tool', 'view_image']


class StrictLaunchArguments(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        (self.folder / 'codex-home').mkdir()
        self.config = self.folder / 'agentos-mcp.json'
        self.config.write_text(json.dumps({'mcpServers': {'agentos': {'command': 'python3', 'args': ['-m', 'x']}}}))
        self.adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, codex_home=self.folder / 'codex-home')

    def test_codex_strict_argv_is_pinned(self):
        trusted = self.adapter.command('codex', '/runtime/codex', 'prompt', self.config)
        strict = self.adapter.command('codex', '/runtime/codex', 'prompt', self.config, profile=STRICT_PROFILE,
                                      disabled_features=PLAN)
        # With --sandbox read-only also present Codex applies it, which can read the store.
        self.assertNotIn('--sandbox', strict)
        overrides = [item for key, value in CODEX_DECISION_CONFIG for item in ('-c', f'{key}={value}')]
        expected = ['--ignore-rules', '-c', f'default_permissions="{CODEX_STRICT_PERMISSIONS}"', '-c', CODEX_STRICT_TABLE,
                    *overrides, *[item for feature in PLAN for item in ('--disable', feature)]]
        self.assertEqual(strict[3:3 + len(expected)], expected)
        self.assertEqual(strict[3], '--ignore-rules', 'review P1: exec rules cannot run a command outside Seatbelt')
        self.assertIn('web_search="disabled"', strict, 'provider-hosted search stays off')
        self.assertEqual(CODEX_STRICT_TABLE, 'permissions.agentos-strict-isolated={filesystem={":minimal"="read", '
                                             '":workspace_roots"={"."="read"}}, network={enabled=false}}')
        self.assertEqual(strict[:3] + strict[3 + len(expected):], trusted[:3] + trusted[5:],
                         'everything else is the trusted-local argv')
        self.assertEqual(trusted[3:5], ['--sandbox', 'read-only'], 'trusted-local is unchanged')
        self.assertNotIn('--ignore-rules', trusted)

    def test_codex_strict_without_a_verified_feature_plan_is_refused(self):
        for plan in ((), None, ['apps', 'unified_exec'], ['personality']):
            with self.subTest(plan=plan), self.assertRaises(ExecutionError):
                self.adapter.command('codex', '/runtime/codex', 'prompt', self.config, profile=STRICT_PROFILE,
                                     disabled_features=plan)

    def test_claude_strict_has_no_built_in_tools_and_allows_only_the_offered_bridge_tools(self):
        trusted = self.adapter.command('claude-code', '/runtime/claude', 'prompt', self.config, 'instructions')
        strict = self.adapter.command('claude-code', '/runtime/claude', 'prompt', self.config, 'instructions', profile=STRICT_PROFILE)
        self.assertEqual(strict[:len(trusted)], trusted)
        self.assertEqual(strict[len(trusted):], ['--tools', '', '--restricted', '--allowedTools',
                                                 'mcp__agentos__bounded_public_research,mcp__agentos__list_notes,'
                                                 'mcp__agentos__save_note,mcp__agentos__weather,mcp__agentos__web_search'])
        self.assertNotIn('--tools', trusted)

    def test_no_widening_for_parity_and_unknown_profiles_are_refused(self):
        for engine in ('codex', 'claude-code'):
            argv = self.adapter.command(engine, '/runtime/cli', 'prompt', self.config, profile=STRICT_PROFILE,
                                        disabled_features=PLAN)
            joined = ' '.join(argv)
            for forbidden in ('danger-full-access', 'workspace-write', '--full-auto', 'dangerously', '--add-dir',
                              'bypass', '"write"', 'enabled=true', ':root', '--enable'):
                with self.subTest(engine=engine, forbidden=forbidden):
                    self.assertNotIn(forbidden, joined)
            for profile in ('isolated-agentos-mcp', 'unknown', None):
                with self.subTest(engine=engine, profile=profile), self.assertRaises(ExecutionError):
                    self.adapter.command(engine, '/runtime/cli', 'prompt', self.config, profile=profile)
        env = self.adapter.environment('codex', '/runtime/codex', self.folder)
        self.assertEqual(set(env), {'HOME', 'PATH', 'LANG', 'PYTHONPATH', 'CODEX_HOME'}, 'environment unchanged')

    def test_the_work_allowlist_is_the_decision_allowlist_plus_unified_exec(self):
        from personal_agent.decision_adapters import CODEX_ALLOWED_ENABLED_FEATURES
        self.assertEqual(strict_allowed_features(), CODEX_ALLOWED_ENABLED_FEATURES | {'unified_exec'})
        self.assertNotIn('shell_tool', strict_allowed_features())


#: A fake native CLI: the ELF magic the strict profile requires of the executable.
FAKE_NATIVE = b'\x7fELF fake native cli\n'


def _pinned_platform(case):
    """The qualification logic is platform-independent; CI runs on Linux."""
    from unittest import mock
    patcher = mock.patch.object(sys, 'platform', 'darwin')
    patcher.start()
    case.addCleanup(patcher.stop)


class StrictExecuteRefusesStaleQualifications(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        (self.folder / 'codex-home').mkdir()
        (self.folder / 'bin').mkdir()
        self.binary = self.folder / 'bin' / 'codex'
        self.binary.write_bytes(FAKE_NATIVE)
        self.calls = []
        _pinned_platform(self)

    def _adapter(self, version_output=None, runtime_root=None):
        version_output = version_output or f'codex-cli {CODEX_VERSION}'

        def runner(argv, **kwargs):
            self.calls.append(list(argv))
            return _Done(stdout=version_output) if argv[1:] == ['--version'] else _codex_answer()
        return BoundedExecutionAdapter(finder=lambda name: str(self.binary), runner=runner,
                                       runtime_root=runtime_root or self.folder / 'turns', codex_home=self.folder / 'codex-home')

    def _record(self, adapter, **changes):
        record = {'version': CODEX_VERSION, 'platform': sys.platform, 'disabled_features': PLAN,
                  'binding': adapter.strict_binding('codex', str(self.binary), self.folder),
                  **adapter.strict_digests('codex', str(self.binary))}
        record.update(changes)
        return record

    def _facade(self, record):
        return StrictIsolatedAgentOSMcpTools(_Caps(self.folder), qualification=record)

    def test_a_current_qualification_runs_with_its_verified_plan(self):
        adapter = self._adapter()
        result = adapter.execute('codex', 'hello', self._facade(self._record(adapter)))
        self.assertEqual(result.content, 'answer')
        self.assertEqual(self.calls[0], [str(self.binary), '--version'])
        self.assertIn('--ignore-rules', self.calls[1])
        self.assertEqual([self.calls[1][i + 1] for i, part in enumerate(self.calls[1]) if part == '--disable'], PLAN)
        self.assertNotIn('--sandbox', self.calls[1])

    def _refused(self, adapter, record, expected_calls):
        self.calls.clear()
        with self.assertRaises(ExecutionError) as caught:
            adapter.execute('codex', 'hello', self._facade(record))
        self.assertEqual(caught.exception.failure_class, 'isolation-unqualified')
        self.assertEqual(self.calls, expected_calls, 'no CLI turn is started at all')
        return caught.exception

    def test_an_upgraded_unqualified_or_unknown_version_is_refused_without_fallback(self):
        version_call = [[str(self.binary), '--version']]
        for output, qualified in ((f'codex-cli {CODEX_VERSION}', None), (f'codex-cli {CODEX_VERSION}', '0.1.0'),
                                  ('codex-cli 9.9.9', '9.9.9'), ('garbled', CODEX_VERSION)):
            adapter = self._adapter(output)
            with self.subTest(output=output, qualified=qualified):
                self._refused(adapter, self._record(adapter, version=qualified), version_call)

    def test_changed_paths_binary_or_plan_are_refused_before_any_process(self):
        """Review P2/P3: the qualification is bound to the resolved paths and binary."""
        adapter = self._adapter()
        good = self._record(adapter)
        for field, value in (('store', '/elsewhere/store'), ('home', '/Users/other'), ('runtime_root', '/elsewhere/turns'),
                             ('codex_home', '/elsewhere/.codex'), ('binary', '/other/codex'), ('fingerprint', 'x|1|2'),
                             ('platform', 'linux')):
            with self.subTest(field=field):
                error = self._refused(adapter, {**good, 'binding': {**good['binding'], field: value}}, [])
                self.assertIn(field, error.reason)
        for broken in ({**good, 'disabled_features': None}, {**good, 'binding': None}, {}, None):
            with self.subTest(record=broken):
                self._refused(adapter, broken, [])

    def test_changed_bytes_with_the_same_path_size_and_mtime_are_refused(self):
        """Review N2: the sha256 is enforced, not only path/size/mtime."""
        adapter = self._adapter()
        record = self._record(adapter)
        stat = self.binary.stat()
        self.binary.write_bytes(FAKE_NATIVE.replace(b'fake', b'fak3'))
        os.utime(self.binary, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertEqual(adapter.strict_binding('codex', str(self.binary), self.folder), record['binding'])
        error = self._refused(adapter, record, [])
        self.assertIn('binary_sha256', error.reason)
        for missing in ('binary_sha256', 'native_sha256'):
            with self.subTest(missing=missing):
                self._refused(adapter, {**self._record(adapter), missing: None}, [])

    def test_an_untested_platform_is_refused_even_with_a_matching_record(self):
        """A data folder moved from the qualified Mac to another OS (review P1)."""
        from unittest import mock
        adapter = self._adapter()
        record = self._record(adapter)
        with mock.patch.object(sys, 'platform', 'linux'):
            record['binding']['platform'] = 'linux'
            self._refused(adapter, record, [])

    def test_trusted_local_does_not_check_versions(self):
        result = self._adapter('garbled').execute('codex', 'hello', AgentOSMcpTools(_Caps(self.folder)))
        self.assertEqual(result.content, 'answer')
        self.assertEqual(len(self.calls), 1)
        self.assertIn('--sandbox', self.calls[0])


FEATURES = ('apps                 stable             true\n'
            'personality          stable             true\n'
            'shell_tool           stable             true\n'
            'unified_exec         stable             true\n'
            'memories             stable             false\n'
            'steer                removed            true\n')


class StrictQualificationLogic(unittest.TestCase):
    """``qualify_strict`` with a scripted runner in place of the CLI."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.store = self.folder / 'store'
        self.store.mkdir()
        (self.folder / 'codex-home').mkdir()
        (self.folder / 'bin').mkdir()
        for name in ('codex', 'claude'):
            (self.folder / 'bin' / name).write_bytes(FAKE_NATIVE)
        self.finder = lambda name: str(self.folder / 'bin' / name)
        self.calls = []
        _pinned_platform(self)
        # tempfile lives under /tmp on Linux CI; the baseline-readable
        # refusal has its own test with the real list.
        from unittest import mock
        from personal_agent import bounded_execution
        patcher = mock.patch.object(bounded_execution, 'BASELINE_READABLE_ROOTS', ('/nonexistent-baseline-root',))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _runner(self, version, readable=(), stuck=()):
        def runner(argv, **kwargs):
            self.calls.append((list(argv), dict(kwargs['env'])))
            if argv[1:] == ['--version']:
                return _Done(stdout=version)
            if argv[1:3] == ['features', 'list']:
                disabled = {argv[i + 1] for i, part in enumerate(argv) if part == '--disable'}
                lines = [line for line in FEATURES.splitlines()
                         if line.split()[0] not in disabled or line.split()[0] in stuck]
                return _Done(stdout='\n'.join(lines))
            target, turn = Path(argv[-1]), Path(kwargs['cwd'])
            return _Done(returncode=0 if target == turn or target in readable else 1)
        return runner

    def _qualify(self, engine='codex', version=None, readable=(), stuck=(), runtime_root=None):
        version = version or (f'codex-cli {CODEX_VERSION}' if engine == 'codex' else f'{CLAUDE_VERSION} (Claude Code)')
        adapter = BoundedExecutionAdapter(finder=self.finder, runner=self._runner(version, readable, stuck),
                                          runtime_root=runtime_root or self.folder / 'turns',
                                          codex_home=self.folder / 'codex-home')
        return adapter.qualify_strict(engine, store_root=self.store)

    def test_codex_qualifies_and_binds_its_plan_binary_and_paths(self):
        result = self._qualify()
        self.assertTrue(result['qualified'], result)
        self.assertEqual(result['version'], CODEX_VERSION)
        self.assertEqual([check['check'] for check in result['checks']],
                         ['tested-platform', 'runtime-root-not-baseline-readable', 'tested-version',
                          'turn-directory-readable', 'sibling-turn-denied', 'protected-directory-denied',
                          'protected-directory-denied', 'protected-directory-denied', 'tool-features-allowlisted',
                          'native-binary-identified'])
        self.assertEqual(result['binary_sha256'], result['native_sha256'], 'a plain executable is its own native binary')
        self.assertEqual(len(result['binary_sha256']), 64)
        self.assertEqual(result['disabled_features'], ['apps', 'memories', 'shell_tool'],
                         'every non-removed feature outside the allowlist, whatever its default')
        binding = result['binding']
        self.assertEqual(binding['store'], str(self.store.resolve()))
        self.assertEqual(binding['codex_home'], str((self.folder / 'codex-home').resolve()))
        self.assertEqual(binding['runtime_root'], str((self.folder / 'turns').resolve()))
        self.assertEqual(binding['home'], str(Path.home().resolve()))
        self.assertIn('fingerprint', binding)
        sandbox = [argv for argv, _ in self.calls if 'sandbox' in argv]
        self.assertTrue(Path(sandbox[1][-1]).name.startswith('qualify-sibling-'))
        self.assertEqual([argv[-1] for argv in sandbox[2:]],
                         [str(Path.home()), str(self.folder / 'codex-home'), str(self.store)])
        for argv, env in ((argv, env) for argv, env in self.calls if argv[1] in ('sandbox', 'features')):
            self.assertNotEqual(env['CODEX_HOME'], str(self.folder / 'codex-home'), "the owner's Codex config is not loaded")
        for argv in sandbox:
            self.assertEqual(argv[2:9], ['-C', argv[3], '-c', CODEX_STRICT_TABLE, '-P', CODEX_STRICT_PERMISSIONS, '--'])
            self.assertEqual(argv[9], '/bin/ls', 'a listing only; output is discarded')
        self.assertNotIn('content', json.dumps(result))

    def test_any_readable_protected_or_sibling_directory_fails_qualification(self):
        for readable in ((self.store,), (Path.home(),), (self.folder / 'codex-home',)):
            with self.subTest(readable=readable):
                result = self._qualify(readable=readable)
                self.assertFalse(result['qualified'])
                self.assertEqual(result['reason'], 'protected-directory-denied')

    def test_a_feature_that_stays_enabled_fails_closed(self):
        result = self._qualify(stuck=('shell_tool',))
        self.assertFalse(result['qualified'])
        self.assertEqual(result['reason'], 'tool-features-allowlisted')
        self.assertIsNone(result['disabled_features'])

    def test_a_runtime_root_the_baseline_keeps_readable_fails_before_any_process(self):
        from unittest import mock
        from personal_agent import bounded_execution
        self.assertEqual(BASELINE_READABLE_ROOTS, ('/tmp', '/private/tmp', '/var/tmp', '/private/var/tmp'))
        patcher = mock.patch.object(bounded_execution, 'BASELINE_READABLE_ROOTS', BASELINE_READABLE_ROOTS)
        patcher.start()
        self.addCleanup(patcher.stop)
        for root in ('/tmp/agentos-runs', '/private/var/tmp/agentos-runs', '/var/tmp'):
            with self.subTest(root=root):
                self.calls.clear()
                result = self._qualify(runtime_root=Path(root))
                self.assertFalse(result['qualified'])
                self.assertEqual(result['reason'], 'runtime-root-not-baseline-readable')
                self.assertEqual(self.calls, [])

    def test_an_untested_version_fails_before_any_sandbox_probe(self):
        self.calls.clear()
        result = self._qualify(version='codex-cli 9.9.9')
        self.assertFalse(result['qualified'])
        self.assertEqual(result['reason'], 'tested-version')
        self.assertFalse([argv for argv, _ in self.calls if 'sandbox' in argv])

    def test_a_broken_runner_is_not_mistaken_for_denial(self):
        """Every probe failing (for example no sandbox) fails the turn-dir control."""
        def runner(argv, **kwargs):
            return _Done(stdout=f'codex-cli {CODEX_VERSION}') if argv[1:] == ['--version'] else _Done(returncode=1)
        adapter = BoundedExecutionAdapter(finder=self.finder, runner=runner,
                                          runtime_root=self.folder / 'turns', codex_home=self.folder / 'codex-home')
        result = adapter.qualify_strict('codex', store_root=self.store)
        self.assertFalse(result['qualified'])
        self.assertIn('turn-directory-readable', result['reason'])

    def test_an_untested_platform_fails_closed_before_running_anything(self):
        from unittest import mock
        with mock.patch.object(sys, 'platform', 'linux'):
            result = self._qualify()
        self.assertFalse(result['qualified'])
        self.assertEqual(result['reason'], 'tested-platform')
        self.assertEqual(self.calls, [])

    def test_claude_code_qualification_is_version_platform_and_paths(self):
        result = self._qualify('claude-code')
        self.assertTrue(result['qualified'])
        self.assertNotIn('codex_home', result['binding'])
        self.assertFalse(self._qualify('claude-code', version='2.2.0 (Claude Code)')['qualified'])
        self.assertFalse(BoundedExecutionAdapter(finder=lambda name: None).qualify_strict('codex')['qualified'])
        # A launcher whose native executable cannot be identified fails closed.
        missing = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=self._runner(f'codex-cli {CODEX_VERSION}'),
                                          runtime_root=self.folder / 'turns', codex_home=self.folder / 'codex-home')
        self.assertIn('native-binary-identified', missing.qualify_strict('codex', store_root=self.store)['reason'])

    def test_the_codex_js_shim_resolves_to_the_native_binary_it_spawns(self):
        """Review N2: mirror codex.js's findCodexExecutable; anything else fails closed."""
        from unittest import mock
        native_of = BoundedExecutionAdapter.native_cli_binary
        modules = self.folder / 'lib' / 'node_modules'
        root = modules / '@openai' / 'codex'
        (root / 'bin').mkdir(parents=True)
        shim = root / 'bin' / 'codex.js'
        shim.write_text('#!/usr/bin/env node\n// shim\n')
        link = self.folder / 'codex-link'
        link.symlink_to(shim)

        def platform_package(base):
            (base / 'package.json').parent.mkdir(parents=True, exist_ok=True)
            (base / 'package.json').write_text('{}')
            native = base / 'vendor' / 'aarch64-apple-darwin' / 'bin' / 'codex'
            native.parent.mkdir(parents=True)
            native.write_bytes(FAKE_NATIVE)
            return native.resolve()

        with mock.patch('platform.machine', return_value='arm64'):
            self.assertEqual(native_of('codex', str(link)), '', 'no native binary: fail closed')
            fallback = platform_package(root)  # the package's own vendor/
            (root / 'package.json').unlink()
            self.assertEqual(native_of('codex', str(link)), str(fallback))
            hoisted = platform_package(modules / '@openai' / 'codex-darwin-arm64')
            self.assertEqual(native_of('codex', str(link)), str(hoisted), 'a hoisted platform package wins over vendor/')
            nested = platform_package(root / 'node_modules' / '@openai' / 'codex-darwin-arm64')
            self.assertEqual(native_of('codex', str(link)), str(nested), 'the nearest node_modules wins')
            nested.write_text('#!/bin/sh\nexec /somewhere/else "$@"\n')
            self.assertEqual(native_of('codex', str(link)), '', 'a resolved non-native file fails closed')
            nested.write_bytes(FAKE_NATIVE)
            digests = BoundedExecutionAdapter().strict_digests('codex', str(link))
        self.assertNotEqual(digests['binary_sha256'], digests['native_sha256'])
        with mock.patch('platform.machine', return_value='riscv64'):
            self.assertEqual(native_of('codex', str(link)), '', 'an unknown target triple fails closed')
        wrapper = self.folder / 'wrapper'
        wrapper.write_text('#!/bin/sh\nexec codex "$@"\n')
        for engine in ('codex', 'claude-code'):
            with self.subTest(engine=engine):
                self.assertEqual(native_of(engine, str(wrapper)), '', 'a shell wrapper fails closed')
                self.assertEqual(native_of(engine, str(self.folder / 'bin' / 'codex')),
                                 str((self.folder / 'bin' / 'codex').resolve()))
        self.assertFalse(BoundedExecutionAdapter().qualify_strict('other')['qualified'])


class _Engine:
    """A scripted subscription adapter recording what the service asks of it."""

    def __init__(self, qualification, stale=()):
        self.qualification, self.facades, self.qualified, self.stale = qualification, [], [], list(stale)
        self.during_qualification = None

    def login_status(self, engine_id, binary=None):
        return {'state': 'signed-in'}

    def qualify_strict(self, engine_id, binary=None, store_root=None):
        self.qualified.append((engine_id, str(store_root)))
        if self.during_qualification:
            self.during_qualification()
        return dict(self.qualification)

    def strict_binding_mismatch(self, engine_id, qualification, store_root, binary=None):
        return list(self.stale)

    def execute(self, engine, prompt, tools, **kwargs):
        self.facades.append(tools)
        if getattr(tools, 'PROFILE', None) == STRICT_PROFILE and tools.qualified_version != CODEX_VERSION:
            raise ExecutionError('refused', failure_class='isolation-unqualified')
        return ExecutionResult('answer', engine, 0, {})


PASS = {'qualified': True, 'version': CODEX_VERSION, 'reason': '', 'profile': STRICT_PROFILE,
        'checks': [{'check': 'tested-version', 'passed': True}], 'binding': {'store': '/s'}, 'binary_sha256': 'ab',
        'disabled_features': PLAN}
FAIL = {'qualified': False, 'version': CODEX_VERSION, 'reason': 'protected-directory-denied', 'checks': []}


class OwnerChoosesTheProfile(unittest.TestCase):
    def _service(self, qualification, stale=()):
        from personal_agent.quickstart_service import AgentService
        from personal_agent.subscription_engines import SubscriptionEngines
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.engine = _Engine(qualification, stale)
        service = AgentService(self.store, subscription_engines=SubscriptionEngines(finder=lambda c: '/runtime/' + c, clock=lambda: 1),
                               execution_adapter=self.engine)
        service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        return service

    def _turn(self, service):
        self.store.enqueue('hello', f'k{len(self.store.jobs())}')
        self.assertTrue(service.run_one())
        job_id = service.task_progress()['tasks'][0]['id']
        return self.store.turn_provenance(job_id)

    def test_default_is_trusted_local_and_labelled(self):
        service = self._service(PASS)
        status = service.settings()['subscription_execution']
        self.assertEqual((status['profile'], status['trust'], status['limitation']),
                         ('trusted-local', 'trusted-local', TRUSTED_LOCAL_LIMITATION))
        record = self._turn(service)
        self.assertEqual((record['capability_profile'], record['capability_trust']), ('trusted-local', 'trusted-local'))
        self.assertIs(type(self.engine.facades[-1]), AgentOSMcpTools)
        self.assertEqual(self.engine.qualified, [], 'nothing is qualified or switched automatically')

    def test_a_passing_qualification_selects_strict_and_every_surface_says_so(self):
        service = self._service(PASS)
        result = service.select_subscription_isolation({'profile': 'strict-isolated'})
        self.assertEqual(result['profile'], 'strict-isolated')
        self.assertEqual(self.engine.qualified, [('codex', str(self.store.root))], 'the real store path is probed')
        stored = self.store.config('subscription_isolation')['qualified']['codex']
        self.assertEqual((stored['binding'], stored['binary_sha256'], stored['disabled_features']), ({'store': '/s'}, 'ab', PLAN))
        status = service.settings()['subscription_execution']
        self.assertEqual((status['profile'], status['trust'], status['requalify_needed']),
                         ('strict-isolated', 'strict-isolated', False))
        self.assertEqual(status['qualified']['codex']['version'], CODEX_VERSION)
        self.assertNotIn('binding', status['qualified']['codex'], 'resolved paths stay out of Settings')
        record = self._turn(service)
        self.assertEqual((record['capability_profile'], record['capability_trust'], record['status']),
                         ('strict-isolated', 'strict-isolated', 'answered'))
        self.assertEqual(record['capability_limitation'], CLI_PROFILES[STRICT_PROFILE]['limitation'])
        facade = self.engine.facades[-1]
        self.assertIsInstance(facade, StrictIsolatedAgentOSMcpTools)
        self.assertEqual(facade.qualification['disabled_features'], PLAN)

    def test_settings_say_requalify_when_the_binding_no_longer_matches(self):
        service = self._service(PASS)
        service.select_subscription_isolation({'profile': 'strict-isolated'})
        self.engine.stale = ['store']
        status = service.settings()['subscription_execution']
        self.assertEqual((status['trust'], status['requalify_needed']), ('strict-isolated', True))

    def test_a_failed_qualification_keeps_the_previous_profile(self):
        service = self._service(FAIL)
        with self.assertRaisesRegex(ValueError, 'trusted-local'):
            service.select_subscription_isolation({'profile': 'strict-isolated'})
        self.assertEqual(service.settings()['subscription_execution']['trust'], 'trusted-local')
        # Previously strict: a failed requalification keeps strict and its record.
        self.engine.qualification = PASS
        service.select_subscription_isolation({'profile': 'strict-isolated'})
        self.engine.qualification = FAIL
        with self.assertRaisesRegex(ValueError, 'strict-isolated'):
            service.select_subscription_isolation({'profile': 'strict-isolated'})
        status = service.settings()['subscription_execution']
        self.assertEqual((status['trust'], status['qualified']['codex']['version']), ('strict-isolated', CODEX_VERSION))

    def test_a_concurrent_owner_choice_is_not_overwritten_by_a_finishing_qualification(self):
        service = self._service(PASS)
        service.select_subscription_isolation({'profile': 'strict-isolated'})
        # While a requalification runs, the owner explicitly picks trusted-local.
        self.engine.during_qualification = lambda: service.select_subscription_isolation({'profile': 'trusted-local'})
        with self.assertRaisesRegex(ValueError, '바뀌어'):
            service.select_subscription_isolation({'profile': 'strict-isolated'})
        self.assertEqual(service.settings()['subscription_execution']['trust'], 'trusted-local')

    def test_an_unrecognised_or_malformed_stored_profile_fails_closed(self):
        service = self._service(PASS)
        for row in (None, 'strict-isolated', [], {}, {'qualified': {}}, {'profile': None}, {'profile': 'strict-isolated-v2'}):
            with self.subTest(row=row):
                self.store.put('subscription_isolation', row)
                self.assertEqual(service.subscription_isolation()['profile'], 'unrecognised')
        self.store.put('subscription_isolation', {'profile': 'strict-isolated-v2', 'qualified': {}})
        status = service.settings()['subscription_execution']
        self.assertEqual((status['profile'], status['trust'], status['requalify_needed']), ('unrecognised', 'unknown', True))
        record = self._turn(service)
        self.assertEqual((record['status'], record['failure_class']), ('failed', 'isolation-unqualified'))
        self.assertIsInstance(self.engine.facades[-1], StrictIsolatedAgentOSMcpTools, 'never read as trusted-local')
        self.assertIsNone(self.engine.facades[-1].qualification)

    def test_no_silent_downgrade_when_the_cli_no_longer_qualifies(self):
        service = self._service(PASS)
        service.select_subscription_isolation({'profile': 'strict-isolated'})
        # The owner switches to another CLI that was never qualified.
        service.connect_subscription_engine({'engine': 'claude-code', 'officially_authenticated': True})
        self.assertTrue(service.settings()['subscription_execution']['requalify_needed'])
        record = self._turn(service)
        self.assertEqual((record['capability_trust'], record['status'], record['failure_class']),
                         ('strict-isolated', 'failed', 'isolation-unqualified'))
        self.assertTrue(all(isinstance(facade, StrictIsolatedAgentOSMcpTools) for facade in self.engine.facades),
                        'no trusted-local facade was ever used instead')

    def test_a_record_from_another_platform_qualifies_nothing(self):
        service = self._service(PASS)
        service.select_subscription_isolation({'profile': 'strict-isolated'})
        row = self.store.config('subscription_isolation')
        self.assertEqual(row['qualified']['codex']['platform'], sys.platform)
        row['qualified']['codex']['platform'] = 'another-os'
        self.store.put('subscription_isolation', row)
        record = self._turn(service)
        self.assertEqual((record['capability_trust'], record['status'], record['failure_class']),
                         ('strict-isolated', 'failed', 'isolation-unqualified'))
        self.assertIsNone(self.engine.facades[-1].qualified_version)

    def test_trusted_local_is_an_explicit_owner_choice_and_input_is_checked(self):
        service = self._service(PASS)
        service.select_subscription_isolation({'profile': 'strict-isolated'})
        service.select_subscription_isolation({'profile': 'trusted-local'})
        self.assertEqual(service.settings()['subscription_execution']['trust'], 'trusted-local')
        for body in (None, {}, {'profile': 'isolated-agentos-mcp'}, {'profile': 'full-access'}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                service.select_subscription_isolation(body)


class DoctorReportsTheSelectedProfile(unittest.TestCase):
    def test_selected_profile_and_recorded_trust_are_read_only(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        self.addCleanup(sys.path.remove, str(ROOT / 'scripts'))
        import agentos_doctor
        with tempfile.TemporaryDirectory() as folder:
            store = QuickStore(Path(folder) / 'data')
            self.assertEqual(agentos_doctor._selected_host_profile(store.root),
                             {'profile': 'trusted-local', 'qualified_versions': {}})
            for row in ({'profile': 'strict-isolated-v2'}, {}, None, ['strict-isolated'], 'trusted-local'):
                store.put('subscription_isolation', row)
                self.assertEqual(agentos_doctor._selected_host_profile(store.root)['profile'], 'unrecognised', row)
            store.put('subscription_isolation', {'profile': 'strict-isolated', 'qualified': {'codex': {'version': CODEX_VERSION}}})
            with store.db() as db:
                db.execute('INSERT INTO turn_provenance VALUES (?,?,?)',
                           ('j', json.dumps({'route': 'subscription', 'capability_profile': 'strict-isolated',
                                             'capability_trust': 'strict-isolated'}), 1))
            self.assertEqual(agentos_doctor._selected_host_profile(store.root),
                             {'profile': 'strict-isolated', 'qualified_versions': {'codex': CODEX_VERSION}})
            turn = agentos_doctor._recent_turns(store.root)[0]
            self.assertEqual((turn['capability_profile'], turn['capability_trust']), ('strict-isolated', 'strict-isolated'))


# -- Process-level qualification (opt-in) ------------------------------------

class _ScriptedModel:
    """A loopback fake model endpoint that plays a fixed tool-call script.

    ``responses`` speaks the OpenAI Responses SSE shape Codex reads;
    ``anthropic`` speaks the Messages SSE shape Claude Code reads.  It records
    every request so a test can read the tool results the CLI sent back.
    """

    def __init__(self, dialect, script):
        self.dialect, self.script, self.requests, self.turn = dialect, list(script), [], 0
        model = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(404)
                self.end_headers()

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get('content-length') or 0)) or b'{}')
                model.requests.append({'path': self.path, 'body': body,
                                       'authorization': 'authorization' in {k.lower() for k in self.headers.keys()}})
                events = model.events(self.path, body)
                if events is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header('content-type', 'text/event-stream')
                self.end_headers()
                for name, data in events:
                    self.wfile.write(f'event: {name}\ndata: {json.dumps(data)}\n\n'.encode())
                self.wfile.flush()

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def _next(self):
        step = self.script[self.turn] if self.turn < len(self.script) else {'message': 'done'}
        self.turn += 1
        return step

    def events(self, path, body):
        if self.dialect == 'responses':
            if not path.endswith('/responses'):
                return None
            step = self._next()
            if 'message' in step:
                item = {'type': 'message', 'role': 'assistant', 'id': f'm{self.turn}',
                        'content': [{'type': 'output_text', 'text': step['message']}]}
            else:
                item = {'type': 'function_call', 'id': f'f{self.turn}', 'call_id': f'c{self.turn}',
                        'name': step['name'], 'arguments': json.dumps(step['arguments'])}
                if step.get('namespace'):
                    item['namespace'] = step['namespace']
            usage = {'input_tokens': 1, 'input_tokens_details': None, 'output_tokens': 1,
                     'output_tokens_details': None, 'total_tokens': 2}
            return [('response.created', {'type': 'response.created', 'response': {'id': f'r{self.turn}'}}),
                    ('response.output_item.done', {'type': 'response.output_item.done', 'output_index': 0, 'item': item}),
                    ('response.completed', {'type': 'response.completed', 'response': {'id': f'r{self.turn}', 'usage': usage}})]
        if '/v1/messages' not in path or 'count_tokens' in path:
            return None
        # Side requests (for example a title) carry no tools: answer plainly.
        step = self._next() if body.get('tools') else {'message': 'ok'}
        if 'message' in step:
            block, delta, stop = {'type': 'text', 'text': ''}, {'type': 'text_delta', 'text': step['message']}, 'end_turn'
        else:
            block = {'type': 'tool_use', 'id': f'toolu_{self.turn}', 'name': step['tool'], 'input': {}}
            delta, stop = {'type': 'input_json_delta', 'partial_json': json.dumps(step['input'])}, 'tool_use'
        usage = {'input_tokens': 1, 'output_tokens': 1}
        return [('message_start', {'type': 'message_start', 'message': {
                    'id': f'msg_{self.turn}', 'type': 'message', 'role': 'assistant', 'model': body.get('model', 'fake'),
                    'content': [], 'stop_reason': None, 'stop_sequence': None, 'usage': usage}}),
                ('content_block_start', {'type': 'content_block_start', 'index': 0, 'content_block': block}),
                ('content_block_delta', {'type': 'content_block_delta', 'index': 0, 'delta': delta}),
                ('content_block_stop', {'type': 'content_block_stop', 'index': 0}),
                ('message_delta', {'type': 'message_delta', 'delta': {'stop_reason': stop, 'stop_sequence': None},
                                   'usage': {'output_tokens': 1}}),
                ('message_stop', {'type': 'message_stop'})]

    def tool_results(self):
        """Tool results the CLI returned to the model, in call order."""
        last = self.requests[-1]['body'] if self.requests else {}
        if self.dialect == 'responses':
            results = []
            for request in self.requests:
                for item in request['body'].get('input', []):
                    if item.get('type') == 'function_call_output':
                        results.append(json.dumps(item.get('output')))
            return list(dict.fromkeys(results))
        return [json.dumps(part.get('content')) for message in last.get('messages', [])
                for part in (message.get('content') if isinstance(message.get('content'), list) else [])
                if part.get('type') == 'tool_result']

    def offered_tools(self):
        for request in self.requests:
            if request['body'].get('tools'):
                return request['body']['tools']
        return []


_BRIDGE_STUB = '''
# Test-only (#616): stub the public network of the real AgentOS bridge process.
import sys
sys.path.insert(0, {src!r})
try:
    from personal_agent import local_tools as _lt
    _lt.LocalTools.search = lambda self, query: {{"tool": "web_search", "query": query, "retrieved_at": 1,
        "results": [{{"url": "https://example.com/stub", "title": "stub-search-616", "snippet": "s"}}],
        "sources": ["https://example.com/stub"]}}
    _lt.LocalTools.weather = lambda self, city, country="": {{"tool": "weather", "location": {{"name": "stub-weather-616"}},
        "retrieved_at": 1, "forecast": {{}}, "sources": ["https://open-meteo.com/"]}}
except Exception:
    pass
'''


def _installed(engine):
    binary = shutil.which({'codex': 'codex', 'claude-code': 'claude'}[engine])
    if not binary:
        return None, None
    done = subprocess.run([binary, '--version'], capture_output=True, text=True, timeout=30)
    return binary, parse_cli_version(engine, done.stdout)


def populate_codex_home(home, store_root):
    """A synthetic, populated CODEX_HOME (review): never the owner's real one.

    An "always allow" exec rule, a global AGENTS.md, a skill, a plugin
    folder, a hooks file and a config.toml that would widen the sandbox.
    """
    home = Path(home)
    (home / 'rules').mkdir(parents=True)
    (home / 'rules' / 'default.rules').write_text(
        'prefix_rule(pattern=["cat"], decision="allow")\nprefix_rule(pattern=["ls"], decision="allow")\n')
    (home / 'AGENTS.md').write_text('AGENTS-MD-CANARY-616 global owner instructions\n')
    (home / 'AGENTS.override.md').write_text('AGENTS-OVERRIDE-CANARY-616 global owner override\n')
    skill = home / 'skills' / 'canary-skill'
    skill.mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: canary-skill-616\ndescription: SKILL-CANARY-616\n---\nSKILL-BODY-CANARY-616\n')
    plugin = home / 'plugins' / 'canary-plugin'
    plugin.mkdir(parents=True)
    (plugin / 'plugin.json').write_text(json.dumps({'name': 'canary-plugin-616', 'description': 'PLUGIN-CANARY-616'}))
    (home / 'hooks.json').write_text(json.dumps({'hooks': {'PreToolUse': [{'hooks': [
        {'type': 'command', 'command': f'cat {store_root}/FAKE-STORE-CANARY.txt'}]}]}}))
    (home / 'config.toml').write_text('sandbox_mode = "danger-full-access"\napproval_policy = "never"\n')


#: Tools Codex may still offer under strict: the AgentOS bridge namespace,
#: the MCP resource helpers (the bridge serves no resources) and the
#: non-interactive user-input request.  No shell, file, image or web tool.
STRICT_CODEX_TOOLS = {'mcp__agentos', 'list_mcp_resources', 'list_mcp_resource_templates', 'read_mcp_resource',
                      'request_user_input'}


@unittest.skipUnless(os.environ.get('AGENTOS_CLI_QUALIFICATION') == '1',
                     'opt-in process-level CLI qualification (set AGENTOS_CLI_QUALIFICATION=1)')
class ProcessLevelQualification(unittest.TestCase):
    """AX-S19 under the exact argv AgentOS uses; no live model or account."""

    def setUp(self):
        # Fake owner layout under the real home, like a default install
        # (store and engine turns under ~/), never inside the owner's data.
        tmp = tempfile.TemporaryDirectory(dir=Path.home(), prefix='.agentos-616-qualification-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = QuickStore(self.root / 'data')
        (self.store.root / 'FAKE-STORE-CANARY.txt').write_text('fake-store-canary-616\n')
        with self.store.db() as db:
            db.execute("INSERT INTO notes VALUES ('n1','fake-note-616',1)")
        self.job = self.store.enqueue('qualification', 'q-' + uuid.uuid4().hex)
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (self.job,))
        self.home_canary = Path.home() / f'.agentos-616-home-canary-{uuid.uuid4().hex}.txt'
        self.home_canary.write_text('fake-home-canary-616\n')
        self.addCleanup(self.home_canary.unlink)
        populate_codex_home(self.root / 'codex-home', self.store.root)
        self.argv = None

    def _stub_bridge_network(self, run_dir):
        site = subprocess.run([sys.executable, '-c', 'import site; print(site.getusersitepackages())'],
                              env={'HOME': str(run_dir), 'PATH': '/usr/bin:/bin'}, capture_output=True, text=True,
                              check=True).stdout.strip()
        Path(site).mkdir(parents=True, exist_ok=True)
        (Path(site) / 'usercustomize.py').write_text(_BRIDGE_STUB.format(src=str(ROOT / 'src')))

    def _adapter(self, engine, binary, model=None, argv_edit=None):
        def runner(argv, **kwargs):
            argv, env = list(argv), dict(kwargs['env'])
            if model is None or 'exec' not in argv and '-p' not in argv:
                return subprocess.run(argv, **kwargs)   # --version, sandbox, features list
            self._stub_bridge_network(Path(kwargs['cwd']))
            if argv_edit:
                argv = argv_edit(argv)
            if engine == 'codex':
                # Only the fake model endpoint is added; the AgentOS argv is otherwise untouched.
                at = argv.index('exec') + 1
                argv[at:at] = ['-c', 'model_provider="fake"', '-c', 'model="fake-model"', '-c',
                               f'model_providers.fake={{name="fake", base_url="http://127.0.0.1:{model.port}/v1", '
                               'wire_api="responses", env_key="AGENTOS_FAKE_MODEL_KEY", request_max_retries=0, stream_max_retries=0}']
                env['AGENTOS_FAKE_MODEL_KEY'] = 'fake'
            else:
                env.update(ANTHROPIC_BASE_URL=f'http://127.0.0.1:{model.port}', ANTHROPIC_API_KEY='fake-key',
                           CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1')
            self.argv = argv
            kwargs['env'] = env
            return subprocess.run(argv, **kwargs)
        return BoundedExecutionAdapter(finder=lambda name: binary, runner=runner, runtime_root=self.root / 'engine-runs',
                                       codex_home=self.root / 'codex-home')

    def _qualification(self, engine, binary):
        result = self._adapter(engine, binary).qualify_strict(engine, store_root=self.store.root)
        self.assertTrue(result['qualified'], result)
        # The record the service stores (quickstart_service.select_subscription_isolation).
        return {'version': result['version'], 'platform': sys.platform, 'binding': result['binding'],
                'binary_sha256': result['binary_sha256'], 'native_sha256': result['native_sha256'],
                'disabled_features': result['disabled_features']}

    def _run(self, engine, binary, model, profile, qualification=None, argv_edit=None):
        adapter = self._adapter(engine, binary, model, argv_edit)
        caps = type('Caps', (), {'store': self.store, 'job_id': self.job, 'private_provenance': set()})()
        facade = StrictIsolatedAgentOSMcpTools(caps, qualification=qualification) if profile == STRICT_PROFILE \
            else AgentOSMcpTools(caps)
        try:
            adapter.execute(engine, 'AgentOS isolation qualification probe', facade)
        finally:
            model.close()
        with self.store.db() as db:
            events = db.execute('SELECT tool, status FROM tool_events WHERE job_id=?', (self.job,)).fetchall()
        return model.tool_results(), [tuple(row) for row in events]

    def _codex(self, tested=True):
        binary, version = _installed('codex')
        if version != '0.153.4' or (tested and version not in CLI_PROFILES[STRICT_PROFILE]['runtimes']['codex']['tested_versions']):
            self.skipTest(f'codex {version} is not the tested version')
        return binary

    def _shell_script(self):
        shell = lambda cmd: {'name': 'exec_command', 'arguments': {'cmd': cmd, 'login': False}}
        return [shell(f'cat {self.store.root / "FAKE-STORE-CANARY.txt"}'),
                shell(f'cat {self.home_canary}'),
                shell('cat agentos-mcp.json'),
                {'message': 'qualification finished'}]

    @staticmethod
    def _without(argv, *pairs):
        argv = list(argv)
        for pair in pairs:
            for at in range(len(argv) - len(pair) + 1):
                if argv[at:at + len(pair)] == list(pair):
                    del argv[at:at + len(pair)]
                    break
        return argv

    def test_codex_strict_offers_no_host_tool_and_keeps_the_bridge(self):
        binary = self._codex()
        qualification = self._qualification('codex', binary)
        model = _ScriptedModel('responses', [
            {'name': 'exec_command', 'arguments': {'cmd': f'cat {self.store.root / "FAKE-STORE-CANARY.txt"}', 'login': False}},
            {'name': 'view_image', 'arguments': {'path': str(self.store.root / 'FAKE-STORE-CANARY.txt')}},
            {'name': 'web_search', 'namespace': 'mcp__agentos', 'arguments': {'query': 'public query'}},
            {'name': 'weather', 'namespace': 'mcp__agentos', 'arguments': {'city': 'Daejeon'}},
            {'name': 'list_notes', 'namespace': 'mcp__agentos', 'arguments': {}},
            {'message': 'qualification finished'}])
        results, events = self._run('codex', binary, model, STRICT_PROFILE, qualification)
        shell, image, search, weather, notes = results[:5]
        self.assertIn('unsupported call', shell)
        self.assertIn('unsupported call', image)
        self.assertIn('stub-search-616', search)
        self.assertIn('stub-weather-616', weather)
        self.assertIn('fake-note-616', notes)
        self.assertEqual(events, [('web_search', 'succeeded'), ('weather', 'succeeded'), ('list_notes', 'succeeded')])
        offered = {tool.get('name') or tool.get('type') for tool in model.offered_tools()}
        self.assertLessEqual(offered, STRICT_CODEX_TOOLS, offered)
        context = json.dumps([request['body'] for request in model.requests])
        for canary in ('fake-store-canary-616', 'fake-home-canary-616', 'SKILL-CANARY-616', 'canary-skill-616',
                       'PLUGIN-CANARY-616'):
            self.assertNotIn(canary, context)
        # Declared limitation: no official override stops the global
        # AGENTS.override.md (it takes precedence over AGENTS.md).
        self.assertIn('AGENTS-OVERRIDE-CANARY-616', context)
        for name in ('AGENTS.override.md', 'AGENTS.md'):
            self.assertIn(name, CLI_PROFILES[STRICT_PROFILE]['limitation'])
        self.assertIn('--ignore-rules', self.argv)
        self.assertNotIn('--sandbox', self.argv)

    def test_codex_strict_sandbox_holds_even_if_a_shell_were_offered_with_an_allow_rule(self):
        """Test-only: re-offer the shell to exercise --ignore-rules and Seatbelt."""
        binary = self._codex()
        qualification = self._qualification('codex', binary)
        model = _ScriptedModel('responses', self._shell_script())
        results, _ = self._run('codex', binary, model, STRICT_PROFILE, qualification,
                               argv_edit=lambda argv: self._without(argv, ('--disable', 'shell_tool')))
        store_read, home_read, turn_read = results[:3]
        for denied in (store_read, home_read):
            self.assertIn('Operation not permitted', denied)
            self.assertNotIn('canary-616', denied)
        self.assertIn('personal_agent.mcp_bridge', turn_read, 'the turn directory is readable')

    def test_codex_exec_rules_escape_the_sandbox_without_ignore_rules(self):
        """Review P1 reproduction: why --ignore-rules is pinned."""
        binary = self._codex()
        qualification = self._qualification('codex', binary)
        model = _ScriptedModel('responses', self._shell_script())
        results, _ = self._run('codex', binary, model, STRICT_PROFILE, qualification,
                               argv_edit=lambda argv: self._without(argv, ('--disable', 'shell_tool'), ('--ignore-rules',)))
        self.assertIn('fake-store-canary-616', results[0], 'the "always allow" rule ran cat outside Seatbelt')

    def test_codex_trusted_local_reads_the_store_as_its_label_says(self):
        binary = self._codex(tested=False)
        model = _ScriptedModel('responses', self._shell_script())
        results, _ = self._run('codex', binary, model, BOUNDED_PROFILE)
        self.assertIn('--sandbox', self.argv)
        self.assertIn('fake-store-canary-616', results[0])
        self.assertIn('fake-home-canary-616', results[1])
        self.assertIn('outside AgentOS provenance', CLI_PROFILES[BOUNDED_PROFILE]['limitation'])

    def test_codex_in_product_qualification_uses_the_real_cli(self):
        binary = self._codex()
        result = self._adapter('codex', binary).qualify_strict('codex', store_root=self.store.root)
        self.assertTrue(result['qualified'], result)
        self.assertIn('shell_tool', result['disabled_features'])
        self.assertNotIn('unified_exec', result['disabled_features'])
        self.assertEqual(result['binding']['codex_home'], str((self.root / 'codex-home').resolve()))
        # A store the platform baseline keeps readable (/tmp) fails closed.
        with tempfile.TemporaryDirectory(dir='/tmp', prefix='agentos-616-') as readable:
            self.assertFalse(self._adapter('codex', binary).qualify_strict('codex', store_root=Path(readable))['qualified'])
        adapter = BoundedExecutionAdapter(finder=lambda name: binary, runtime_root=Path('/private/var/tmp/agentos-616-runs'),
                                          codex_home=self.root / 'codex-home')
        self.assertEqual(adapter.qualify_strict('codex', store_root=self.store.root)['reason'],
                         'runtime-root-not-baseline-readable')

    def _claude_script(self):
        return [{'tool': 'Read', 'input': {'file_path': str(self.store.root / 'FAKE-STORE-CANARY.txt')}},
                {'tool': 'Bash', 'input': {'command': f'cat {self.home_canary}'}},
                {'tool': 'mcp__agentos__web_search', 'input': {'query': 'public query'}},
                {'tool': 'mcp__agentos__weather', 'input': {'city': 'Daejeon'}},
                {'tool': 'mcp__agentos__list_notes', 'input': {}},
                {'message': 'qualification finished'}]

    def _claude(self):
        binary, version = _installed('claude-code')
        if version not in CLI_PROFILES[STRICT_PROFILE]['runtimes']['claude-code']['tested_versions']:
            self.skipTest(f'claude {version} is not a tested version')
        return binary

    def test_claude_strict_has_no_file_tools_and_keeps_the_bridge(self):
        binary = self._claude()
        qualification = self._qualification('claude-code', binary)
        model = _ScriptedModel('anthropic', self._claude_script())
        results, events = self._run('claude-code', binary, model, STRICT_PROFILE, qualification)
        read, shell, search, weather, notes = results[:5]
        for denied in (read, shell):
            self.assertIn('No such tool available', denied)
            self.assertNotIn('canary-616', denied)
        self.assertIn('stub-search-616', search)
        self.assertIn('stub-weather-616', weather)
        self.assertIn('fake-note-616', notes)
        self.assertEqual(events, [('web_search', 'succeeded'), ('weather', 'succeeded'), ('list_notes', 'succeeded')])
        self.assertEqual(sorted(tool['name'] for tool in model.offered_tools()),
                         sorted(f'mcp__agentos__{action}' for action in profile_actions(STRICT_PROFILE)),
                         'no built-in tool is offered at all')
        self.assertFalse(any(request['authorization'] for request in model.requests), 'no owner credential was sent')

    def test_claude_trusted_local_documents_its_permission_layer(self):
        """Observed, not endorsed: under -p the trusted-local argv denies the
        out-of-directory read by permission, and also every bridge call."""
        binary = self._claude()
        model = _ScriptedModel('anthropic', self._claude_script())
        results, events = self._run('claude-code', binary, model, BOUNDED_PROFILE)
        self.assertNotIn('canary-616', results[0] + results[1])
        self.assertIn("haven't granted", results[2], 'bridge tools are not pre-approved on trusted-local')
        self.assertEqual(events, [])


@unittest.skipUnless(os.environ.get('AGENTOS_CLI_QUALIFICATION') == '1',
                     'opt-in process-level CLI qualification (set AGENTOS_CLI_QUALIFICATION=1)')
class CodexDecisionInstructionFiles(unittest.TestCase):
    """#624: what a synthetic CODEX_HOME puts into a Codex *decision* prompt.

    The exact ``SubscriptionCliDecisionEngine`` argv against the real
    ``codex exec`` and the loopback scripted model; the only argv additions are
    the fake provider's endpoint settings.  Activation is bypassed on purpose
    (on 0.153.4 it is refused because ``unified_exec`` cannot be disabled):
    this pins the instruction-file behaviour a future qualification must
    re-check, it does not qualify the route.  No owner profile or model.
    """

    def setUp(self):
        binary, version = _installed('codex')
        if version != '0.153.4':
            self.skipTest(f'codex {version} is not the observed version')
        self.binary = binary
        tmp = tempfile.TemporaryDirectory(dir=Path.home(), prefix='.agentos-624-decision-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / 'store').mkdir()
        populate_codex_home(self.root / 'codex-home', self.root / 'store')
        with tempfile.TemporaryDirectory(dir=self.root) as empty:
            listing = subprocess.run([binary, 'features', 'list'], cwd=empty, capture_output=True, text=True, timeout=30,
                                     env={'HOME': empty, 'CODEX_HOME': empty, 'PATH': f'{Path(binary).parent}:/usr/bin:/bin'})
        self.plan = codex_disable_plan(parse_codex_features(listing.stdout))
        self.argv = None

    def _decide(self):
        model = _ScriptedModel('responses', [{'message': json.dumps({'choice': 'retry', 'confidence': 0.9})}])

        def runner(argv, **kwargs):
            argv, env = list(argv), dict(kwargs['env'])
            at = argv.index('exec') + 1
            argv[at:at] = ['-c', 'model_provider="fake"', '-c', 'model="fake-model"', '-c',
                           f'model_providers.fake={{name="fake", base_url="http://127.0.0.1:{model.port}/v1", '
                           'wire_api="responses", env_key="AGENTOS_FAKE_MODEL_KEY", request_max_retries=0, stream_max_retries=0}']
            env['AGENTOS_FAKE_MODEL_KEY'] = 'fake'
            self.argv = argv
            kwargs['env'] = env
            return subprocess.run(argv, **kwargs)

        adapter = BoundedExecutionAdapter(finder=lambda name: self.binary, runner=runner,
                                          runtime_root=self.root / 'engine-runs', codex_home=self.root / 'codex-home')
        engine = SubscriptionCliDecisionEngine(adapter, 'codex', codex_disabled_features=self.plan)
        try:
            decision = engine.choose(DecisionContext('decision-route-probe', {'owner_message': 'retry please'}),
                                     ('retry', 'reference'), 'How does the owner message relate to the previous Work?')
        finally:
            model.close()
        self.failure = engine.last_failure
        return decision, json.dumps([request['body'] for request in model.requests])

    def test_global_instruction_files_reach_the_decision_prompt(self):
        decision, context = self._decide()
        self.assertEqual((decision.outcome, decision.choice), (OUTCOME_DECIDED, 'retry'), self.failure)
        for flag in ('--ignore-user-config', '--ignore-rules'):
            self.assertIn(flag, self.argv)
        self.assertIn('project_doc_max_bytes=0', self.argv)
        for canary in ('SKILL-CANARY-616', 'canary-skill-616', 'PLUGIN-CANARY-616'):
            self.assertNotIn(canary, context)
        # Observed limitation (documented in docs/decision-layer.en.md): the
        # overrides do not stop the global file; the override file wins.
        self.assertIn('AGENTS-OVERRIDE-CANARY-616', context)
        self.assertNotIn('AGENTS-MD-CANARY-616', context)
        (self.root / 'codex-home' / 'AGENTS.override.md').unlink()
        _decision, context = self._decide()
        self.assertIn('AGENTS-MD-CANARY-616', context)
        # With neither file present no instruction-file content reaches the prompt.
        (self.root / 'codex-home' / 'AGENTS.md').unlink()
        _decision, context = self._decide()
        for canary in ('AGENTS-MD-CANARY-616', 'AGENTS-OVERRIDE-CANARY-616', 'SKILL-CANARY-616', 'canary-skill-616',
                       'PLUGIN-CANARY-616'):
            self.assertNotIn(canary, context)
        self.assertNotIn('# AGENTS.md instructions', context)
        self.assertNotIn('<INSTRUCTIONS>', context)


if __name__ == '__main__':
    unittest.main()

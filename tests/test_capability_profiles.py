"""AGENCY-CAP-01 (#604, AX-02/AX-03): one action source, qualified route profiles.

Evidence class: focused unit tests with fake transports and a temporary store;
no model, CLI or provider is contacted.  The real-bridge wire and host
invocation checks are in tests/test_mcp_bridge_protocol.py.
"""
import json
import re
import tempfile
import unittest
from pathlib import Path

from personal_agent import isolated_engine_mcp_bridge
from personal_agent.agent_runtime import DEFINITIONS, Capabilities, check_arguments
from personal_agent.bounded_execution import (
    BOUNDED_PROFILE,
    CLI_PROFILES,
    ISOLATED_PROFILE,
    AgentOSMcpTools,
    BoundedExecutionAdapter,
    ExecutionError,
    ReadOnlyAgentOSMcpTools,
    profile_actions,
    profile_mcp_tools,
    route_unavailable,
)
from personal_agent.isolated_mcp_proxy import IsolatedMcpProxy, TaskCapabilityRegistry
from personal_agent.manifests import HOST_ACTIONS
from personal_agent.plugins import PluginRegistry
from personal_agent.quickstart_store import QuickStore

ROOT = Path(__file__).resolve().parents[1]
NATIVE = {definition['function']['name']: definition['function'] for definition in DEFINITIONS}
FACADES = {BOUNDED_PROFILE: AgentOSMcpTools, ISOLATED_PROFILE: ReadOnlyAgentOSMcpTools}


class _Network:
    def __init__(self):
        self.plans = []

    def execute(self, plan):
        self.plans.append(plan)
        if plan['tool'] == 'public_page_read':
            return {'tool': 'public_page_read', 'url': plan['url'], 'content': 'public page', 'retrieved_at': 2}
        return {'tool': plan['tool'], 'retrieved_at': 1, 'sources': ['https://example.com/a'],
                'results': [{'url': 'https://example.com/a', 'title': 'a', 'snippet': 's'}],
                'location': {'name': plan.get('city')}}


class _Store(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.network = _Network()

    def caps(self, allowed=None, **kwargs):
        return Capabilities(self.store, None, {}, '', 'job', lambda *a: None, network=self.network,
                            document_access=False, allowed_tools=allowed, **kwargs)

    def install(self, manifest):
        path = Path(self.store.root) / (manifest['id'] + '.manifest.json')
        path.write_text(json.dumps(manifest))
        return PluginRegistry(self.store.root).install(path)


class OneActionSource(_Store):
    """Native schemas and MCP tools/list derive from the same definitions."""

    def test_every_profile_tool_is_the_native_definition_on_the_mcp_wire(self):
        for profile, facade in FACADES.items():
            listed = facade(self.caps()).definitions()
            with self.subTest(profile=profile):
                self.assertEqual([tool['name'] for tool in listed], sorted(profile_actions(profile)))
                for tool in listed:
                    native = NATIVE[tool['name']]
                    self.assertEqual(tool['inputSchema'], native['parameters'])
                    self.assertEqual(tool['description'], native['description'])
                    self.assertNotIn('input_schema', tool)
                self.assertEqual(listed, profile_mcp_tools(profile), 'live Capabilities and static projection agree')

    def test_the_isolated_bridge_lists_the_same_projection_as_its_facade(self):
        self.assertEqual(isolated_engine_mcp_bridge.ISOLATED_TOOLS, ReadOnlyAgentOSMcpTools(self.caps()).definitions())

    def test_read_only_hint_comes_from_the_manifest_mode(self):
        hints = {tool['name']: tool['annotations']['readOnlyHint'] for tool in AgentOSMcpTools(self.caps()).definitions()}
        self.assertEqual(hints, {'bounded_public_research': True, 'list_notes': True, 'save_note': False,
                                 'weather': True, 'web_search': True})

    def test_no_route_keeps_its_own_schema_list(self):
        """The removed three-tool fork and the two list_notes copies stay gone."""
        for module in ('bounded_execution', 'mcp_bridge', 'isolated_engine_mcp_bridge', 'isolated_mcp_proxy'):
            source = (ROOT / 'src' / 'personal_agent' / f'{module}.py').read_text()
            with self.subTest(module=module):
                self.assertNotIn('MCP_TOOLS', source)
                self.assertNotIn('LIST_NOTES_TOOL', source)
                self.assertNotRegex(source, r"['\"](?:input_schema|inputSchema)['\"]\s*:\s*\{")


class DeclaredProfileLimits(unittest.TestCase):
    def test_every_host_action_is_offered_or_has_a_declared_reason(self):
        for profile in CLI_PROFILES:
            actions, unavailable = set(profile_actions(profile)), route_unavailable(profile)
            with self.subTest(profile=profile):
                self.assertEqual(actions | set(unavailable), HOST_ACTIONS)
                self.assertFalse(actions & set(unavailable))
                self.assertTrue(all(isinstance(reason, str) and reason for reason in unavailable.values()))

    def test_profile_trust_level_limitation_and_runtime_versions_are_explicit(self):
        """Owner decision on #604: the subscription route is a named trusted-local profile."""
        self.assertEqual(BOUNDED_PROFILE, 'trusted-local')
        self.assertEqual(CLI_PROFILES[BOUNDED_PROFILE]['trust'], 'trusted-local')
        self.assertEqual(CLI_PROFILES[BOUNDED_PROFILE]['limitation'],
                         'the CLI may read host files outside AgentOS provenance '
                         '(verified: codex sandbox -P :read-only, codex-cli 0.153.4)')
        self.assertEqual(CLI_PROFILES[ISOLATED_PROFILE]['trust'], 'isolated-restricted')
        for profile in CLI_PROFILES.values():
            self.assertNotIn('gate_qualified', profile, 'no dead qualification flag')
        for profile in CLI_PROFILES.values():
            for runtime in profile['runtimes'].values():
                self.assertIsNone(runtime['live_tested_version'], 'no live AgentOS-mediated run is claimed')
        pinned = re.search(r'@openai/codex@([0-9.]+)', (ROOT / 'Dockerfile.engine').read_text()).group(1)
        self.assertEqual(CLI_PROFILES[ISOLATED_PROFILE]['runtimes']['codex']['pinned_version'], pinned)

    def test_the_isolated_profile_stays_restricted_to_the_argumentless_read(self):
        """The proxy forwards only ``arguments == {}``; a wider profile must revisit it."""
        self.assertEqual(profile_actions(ISOLATED_PROFILE), ('list_notes',))
        for tool in profile_mcp_tools(ISOLATED_PROFILE):
            self.assertEqual(tool['inputSchema']['properties'], {})


ARGUMENT_CASES = (
    # (tool, arguments, accepted)
    ('weather', {'city': 'Daejeon', 'country': 'KR'}, True),
    ('weather', {'city': 'Daejeon'}, True),
    ('weather', {'country': 'KR'}, False),                      # missing required
    ('weather', {'city': 'Daejeon', 'lat': '1'}, False),        # unknown field
    ('weather', {'city': 7}, False),                            # non-string
    ('web_search', {'query': 'today news'}, True),
    ('web_search', {'q': 'today news'}, False),
    ('bounded_public_research', {'mode': 'travel_plan', 'query': 'q'}, True),
    ('bounded_public_research', {'mode': 'travel_plan', 'query': 'q', 'approved_urls': 'x'}, False),
    ('list_notes', {}, True),
    ('list_notes', {'filter': 'x'}, False),
    ('save_note', {'content': 'remember this'}, True),
    ('save_note', {'content': ['x']}, False),
)


class ArgumentConversion(_Store):
    def test_native_and_mcp_accept_and_refuse_the_same_arguments(self):
        tools = AgentOSMcpTools(self.caps())
        for name, arguments, accepted in ARGUMENT_CASES:
            with self.subTest(tool=name, arguments=arguments):
                try:
                    check_arguments(NATIVE[name]['parameters'], arguments)
                    native = True
                except ValueError:
                    native = False
                self.assertEqual(native, accepted, 'native loop decision')
                before = len(self.network.plans)
                if accepted:
                    tools.call(name, dict(arguments))
                else:
                    with self.assertRaises(ExecutionError):
                        tools.call(name, dict(arguments))
                    self.assertEqual(len(self.network.plans), before, 'a refused call reaches no host')

    def test_mcp_arguments_reach_the_host_unchanged(self):
        AgentOSMcpTools(self.caps()).call('weather', {'city': 'Daejeon', 'country': 'KR'})
        self.assertEqual(self.network.plans, [{'tool': 'weather', 'city': 'Daejeon', 'country': 'KR'}])

    def test_blank_required_strings_and_non_objects_are_refused(self):
        tools = AgentOSMcpTools(self.caps())
        for name, arguments in (('web_search', {'query': '  '}), ('save_note', {'content': ''}),
                                ('weather', None), ('weather', ['Daejeon'])):
            with self.subTest(tool=name, arguments=arguments), self.assertRaises(ExecutionError):
                tools.call(name, arguments)
        self.assertEqual(self.network.plans, [])


class EffectiveAvailability(_Store):
    """What each route offers, and that discovery or installation grants nothing."""

    NEWS = {'version': 1, 'id': 'news', 'tools': [{'id': 'news_search', 'host_action': 'web_search', 'mode': 'read_only'}],
            'roles': []}

    def test_routes_offer_their_profile_and_the_native_route_keeps_its_default(self):
        native = [definition['function']['name'] for definition in self.caps().definitions()]
        self.assertIn('public_page_read', native)
        self.assertIn('weather', native)
        self.assertEqual([t['name'] for t in AgentOSMcpTools(self.caps()).definitions()],
                         sorted(profile_actions(BOUNDED_PROFILE)))
        self.assertEqual([t['name'] for t in ReadOnlyAgentOSMcpTools(self.caps()).definitions()], ['list_notes'])

    def test_a_profile_never_widens_a_work_that_did_not_allow_the_action(self):
        tools = AgentOSMcpTools(self.caps(allowed={'list_notes'}))
        self.assertEqual([t['name'] for t in tools.definitions()], ['list_notes'])
        with self.assertRaises(ExecutionError):
            tools.call('weather', {'city': 'Daejeon'})
        self.assertEqual(self.network.plans, [])

    def test_an_installed_package_alias_is_not_exposed_on_a_cli_route(self):
        self.install(self.NEWS)
        caps = self.caps(packages=PluginRegistry(self.store.root).runtime_packages())
        self.assertIn('news_search', [d['function']['name'] for d in caps.definitions()], 'native route: enabled package')
        tools = AgentOSMcpTools(caps)
        self.assertNotIn('news_search', [t['name'] for t in tools.definitions()])
        with self.assertRaises(ExecutionError):
            tools.call('news_search', {'query': 'q'})
        self.assertEqual(self.network.plans, [])

    def test_a_package_disabled_or_redeclared_after_discovery_is_refused(self):
        registry = PluginRegistry(self.store.root)
        self.install(self.NEWS)
        caps = self.caps(packages=registry.runtime_packages(), current_packages=registry.runtime_packages)
        self.assertIn('news_search', [d['function']['name'] for d in caps.definitions()])
        caps.execute('news_search', {'query': 'q'})
        registry.set_enabled('news', False)
        with self.assertRaisesRegex(ValueError, '비활성화'):
            caps.execute('news_search', {'query': 'q'})
        registry.set_enabled('news', True)
        self.install({**self.NEWS, 'tools': [{'id': 'news_search', 'host_action': 'weather', 'mode': 'read_only'}]})
        with self.assertRaisesRegex(ValueError, '비활성화'):
            caps.execute('news_search', {'query': 'q'})
        caps.execute('web_search', {'query': 'q'})  # allowed control: the built-in action still works
        self.assertEqual([plan['tool'] for plan in self.network.plans], ['web_search', 'web_search'])

    def test_package_revocation_reaches_delegated_specialists(self):
        """Review of #615: a delegated child rechecks the same live package state."""
        from personal_agent.providers import ModelAdapter
        registry = PluginRegistry(self.store.root)
        role = {'id': 'scout', 'name': 'Scout', 'instructions': 'search', 'permissions': ['read_only'], 'tools': ['news_search']}
        self.install({**self.NEWS, 'roles': [role]})
        calls = []

        def transport(url, body, headers):
            calls.append(body)
            if body['messages'][-1]['role'] == 'tool':
                return {'choices': [{'message': {'content': 'report'}}]}
            # Revoke mid-delegation, then the child asks for the package tool.
            registry.set_enabled('news', False)
            return {'choices': [{'message': {'content': None, 'tool_calls': [{'id': 'c1', 'type': 'function',
                     'function': {'name': 'news_search', 'arguments': json.dumps({'query': 'q'})}}]}}]}

        config = {'provider': 'compatible', 'endpoint': 'http://127.0.0.1:9', 'model': 'm'}
        caps = Capabilities(self.store, ModelAdapter(transport), config, '', 'job', lambda *a: None, network=self.network,
                            packages=registry.runtime_packages(), current_packages=registry.runtime_packages)
        caps.execute('delegate_agent', {'agent_id': 'scout', 'task': 'find news'})
        self.assertEqual(self.network.plans, [], 'the child could not use the revoked package tool')
        with self.assertRaisesRegex(ValueError, '비활성화'):
            caps.execute('delegate_agent', {'agent_id': 'scout', 'task': 'again'})
        caps.execute('delegate_agent', {'agent_id': 'researcher', 'task': 'built-in control'})

    def test_an_owner_page_approval_for_the_api_model_is_not_carried_to_a_cli(self):
        """No silent destination change: the approval names the direct-API model."""
        caps = self.caps(public_page_scope=['https://example.com/a'])
        native = [definition['function']['name'] for definition in caps.definitions()]
        self.assertIn('public_page_read', native)
        tools = AgentOSMcpTools(caps)
        self.assertNotIn('public_page_read', [t['name'] for t in tools.definitions()])
        with self.assertRaises(ExecutionError):
            tools.call('public_page_read', {'url': 'https://example.com/a'})
        self.assertEqual(route_unavailable(BOUNDED_PROFILE)['public_page_read'],
                         'owner-page-approval-bound-to-direct-api-model')
        self.assertEqual(self.network.plans, [])


class SettingsProjection(_Store):
    def test_settings_describe_the_same_profile_the_route_serves(self):
        from personal_agent.quickstart_service import AgentService
        profile = AgentService(self.store).settings()['subscription_execution']
        self.assertEqual(profile, {'profile': 'trusted-local', 'mode': 'bounded-agentos-mcp', 'trust': 'trusted-local',
                                   'limitation': CLI_PROFILES[BOUNDED_PROFILE]['limitation'],
                                   'tools': ['bounded_public_research', 'list_notes', 'save_note', 'weather', 'web_search'],
                                   'unavailable': route_unavailable(BOUNDED_PROFILE),
                                   # #616: the owner can choose; nothing is qualified by default.
                                   'selectable': ['trusted-local', 'strict-isolated'], 'qualified': {}})


class PackageAuthorityRechecks(_Store):
    def test_an_invalid_plugin_registry_refuses_package_tools_but_not_built_ins(self):
        """Review P3: a broken manifest must not make every call raise."""
        def broken():
            raise ValueError('invalid manifest')
        caps = self.caps(packages=[{'id': 'builtin', 'enabled': True, 'tools': [
            {'id': 'web_search', 'host_action': 'web_search', 'mode': 'read_only'},
            {'id': 'news_search', 'host_action': 'web_search', 'mode': 'read_only'}], 'roles': []}],
            current_packages=broken)
        caps.execute('web_search', {'query': 'q'})
        with self.assertRaisesRegex(ValueError, '비활성화'):
            caps.execute('news_search', {'query': 'q'})
        self.assertEqual(len(self.network.plans), 1)

    def test_the_builtin_package_id_is_reserved_for_agentos(self):
        """Re-review P2: a third-party manifest cannot claim id 'builtin'."""
        from personal_agent.manifests import runtime_packages
        spoof = {'version': 1, 'id': 'builtin', 'enabled': True, 'tools': [], 'roles': [
            {'id': 'scout', 'name': 'Scout', 'instructions': 'x', 'permissions': ['read_only'], 'tools': []}]}
        with self.assertRaisesRegex(ValueError, 'builtin'):
            self.install(spoof)
        with self.assertRaisesRegex(ValueError, 'builtin'):
            runtime_packages([spoof])

    def test_a_role_claiming_the_builtin_package_is_still_rechecked_after_disable(self):
        """Re-review P2: built-in roles are decided by the built-in declaration, not package_id."""
        from personal_agent.manifests import runtime_packages
        spoofed = runtime_packages([])
        spoofed[0] = {**spoofed[0], 'roles': [*spoofed[0]['roles'], {'id': 'scout', 'name': 'Scout', 'instructions': 'x',
                                                                     'permissions': ['read_only'], 'tools': ['web_search']}]}
        caps = self.caps(packages=spoofed, current_packages=lambda: runtime_packages([]))
        with self.assertRaisesRegex(ValueError, '비활성화'):
            caps.execute('delegate_agent', {'agent_id': 'scout', 'task': 'find news'})

    def test_a_package_role_disabled_after_discovery_is_refused(self):
        registry = PluginRegistry(self.store.root)
        role = {'id': 'scout', 'name': 'Scout', 'instructions': 'x', 'permissions': ['read_only'], 'tools': ['news_search']}
        self.install({**EffectiveAvailability.NEWS, 'roles': [role]})
        caps = self.caps(packages=registry.runtime_packages(), current_packages=registry.runtime_packages)
        self.assertIn('scout', caps.roles, 'discovered')
        registry.set_enabled('news', False)
        with self.assertRaisesRegex(ValueError, '비활성화'):
            caps.execute('delegate_agent', {'agent_id': 'scout', 'task': 'find news'})
        self.assertEqual(self.network.plans, [])


class IsolatedRejectionsAfterDiscovery(_Store):
    """Revoked, replayed, expired, wrong-task and out-of-scope isolated calls."""

    CALL = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'list_notes', 'arguments': {}}})

    def setUp(self):
        super().setUp()
        self.now = [0.0]
        self.registry = TaskCapabilityRegistry(clock=lambda: self.now[0])
        self.proxy = IsolatedMcpProxy(self.registry)
        self.tools = ReadOnlyAgentOSMcpTools(self.caps(allowed={'list_notes', 'web_search'}))

    def test_allowed_control_then_each_rejection(self):
        token = self.registry.register('task', self.tools)
        self.assertIn('result', self.proxy.handle(self.CALL, token=token, task_id='task'))
        self.assertIn('error', self.proxy.handle(self.CALL, token=token, task_id='task'), 'replayed')
        revoked = self.registry.register('task', self.tools)
        self.registry.revoke(revoked)
        self.assertIn('error', self.proxy.handle(self.CALL, token=revoked, task_id='task'), 'revoked')
        wrong = self.registry.register('task', self.tools)
        self.assertIn('error', self.proxy.handle(self.CALL, token=wrong, task_id='another-task'), 'wrong task')
        stale = self.registry.register('task', self.tools, ttl_seconds=1)
        self.now[0] = 5
        self.assertIn('error', self.proxy.handle(self.CALL, token=stale, task_id='task'), 'expired')
        for name, arguments in (('web_search', {'query': 'q'}), ('weather', {'city': 'x'}), ('list_notes', {'x': '1'})):
            with self.subTest(tool=name), self.assertRaises(ExecutionError):
                self.tools.call(name, arguments)
        self.assertEqual(self.network.plans, [])


class IsolationIsNotUnlockedForParity(unittest.TestCase):
    """The profile change adds AgentOS-hosted actions only; the CLI's own
    sandbox, argv and environment are what they were."""

    def _argv(self, engine, folder):
        profile = Path(folder) / 'codex-home'
        profile.mkdir(exist_ok=True)
        adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, codex_home=profile)
        config = Path(folder) / 'agentos-mcp.json'
        config.write_text(json.dumps({'mcpServers': {'agentos': {'command': 'python3', 'args': []}}}))
        return adapter.command(engine, '/runtime/cli', 'prompt', config), adapter.environment(engine, '/runtime/cli', Path(folder))

    def test_cli_argv_and_environment_keep_their_restrictions(self):
        with tempfile.TemporaryDirectory() as folder:
            codex, codex_env = self._argv('codex', folder)
            claude, claude_env = self._argv('claude-code', folder)
        self.assertEqual(codex[codex.index('--sandbox') + 1], 'read-only')
        self.assertIn('--ignore-user-config', codex)
        self.assertIn('--strict-mcp-config', claude)
        for argv in (codex, claude):
            joined = ' '.join(argv)
            for forbidden in ('danger-full-access', 'workspace-write', '--full-auto', 'dangerously', '--add-dir', 'bypass'):
                self.assertNotIn(forbidden, joined)
        self.assertEqual(set(codex_env), {'HOME', 'PATH', 'LANG', 'PYTHONPATH', 'CODEX_HOME'})
        self.assertEqual(set(claude_env), {'HOME', 'PATH', 'LANG', 'PYTHONPATH'})
        for env in (codex_env, claude_env):
            self.assertTrue(env['PATH'].endswith('/usr/bin:/bin'))
            self.assertNotEqual(env['HOME'], str(Path.home()), 'HOME is the per-turn directory')


if __name__ == '__main__':
    unittest.main()

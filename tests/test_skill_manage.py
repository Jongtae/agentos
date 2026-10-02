"""SKILL-MANAGE-01 (#962): AgentOS management know-how as a bundled skill over the existing settings services.

Evidence class: focused unit tests and a scripted-model run (no network, model,
family instance or owner data).  The skill is content over #961's contract.
These tests check:

* the content is a supported bundled skill;
* management works with skills off;
* a repeated "create" never makes a second paired assistant of the same name;
* a scripted run that follows the skill ends on the settings service's own result.

Reused evidence, not repeated here:

* a Main AI switch never redirects a running Work:
  ``test_ai_route_selection.test_switch_during_running_work_does_not_redirect_it``;
* duplicate display names are resolved by instance id when sharing:
  ``test_family_share`` / ``test_owner_settings_conversation``;
* settings drafts, confirmation and the family setup states: ``test_owner_settings_conversation``,
  ``test_family_setup``;
* revocation, routes and loading: ``test_skill_supply``.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from personal_agent.agent_runtime import SETTINGS_ACTIONS, SKILL_ACTIONS, Capabilities, run_agent
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_store import QuickStore
from personal_agent.settings_orchestrator import SettingsError, SettingsOrchestrator
from personal_agent.skills import BUNDLED_ROOT, SkillLibrary, inspect_skill
from test_agency_loop import CFG, Script, call, finish, judgments

SKILL = 'agentos/agentos-management'
FOLDER = BUNDLED_ROOT / 'agentos-management'
ASSISTANTS = {'@main': {'name': '내 비서', 'state': 'paired', 'main': True},
              'family-1': {'name': '아내 비서', 'state': 'paired', 'main': False},
              'family-2': {'name': '둘째 비서', 'state': 'setting_up', 'main': False}}


class _Service(unittest.TestCase):
    def setUp(self):
        from personal_agent.quickstart_service import AgentService
        self.folder = tempfile.TemporaryDirectory()
        self.store = QuickStore(Path(self.folder.name) / 'data')
        self.service = AgentService(self.store)
        self.started = []
        self.service.start_family_setup = lambda display_name, name=None, notify=None: self.started.append(display_name) or {'state': 'requested'}
        patcher = mock.patch('personal_agent.family_share.instances', return_value=dict(ASSISTANTS))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.settings = SettingsOrchestrator(self.store, service=self.service)

    def tearDown(self):
        self.folder.cleanup()


class TheSkillIsBundledContent(_Service):
    def test_it_is_a_supported_bundled_skill_with_its_references(self):
        record = inspect_skill(FOLDER)
        self.assertEqual(record['status'], ['supported_as_is'])
        self.assertEqual(sorted(record['files']), ['SKILL.md', 'references/family.md', 'references/main-ai.md',
                                                   'references/sharing.md'])
        library = SkillLibrary(self.store)
        library.set_enabled(True)
        binding = library.binding()
        self.assertIn(SKILL, binding.entries)
        loaded = binding.load(SKILL)
        self.assertEqual(loaded['resources'], ['references/family.md', 'references/main-ai.md', 'references/sharing.md'])
        for reference in loaded['resources']:
            self.assertTrue(binding.resource(SKILL, reference)['content'])

    def test_it_points_only_at_the_existing_settings_tools(self):
        text = '\n'.join(path.read_text() for path in sorted(FOLDER.rglob('*.md')))
        for tool in ('settings_read', 'settings_change'):
            self.assertIn(tool, text)
        for setting in ('main_ai', 'family', 'share_site', 'unshare_site', 'add', 'route', 'model'):
            self.assertIn(setting, text)
        # Know-how, not authority: no credential handling, shell or file editing instructions.
        for forbidden in ('launchctl', 'sqlite', '.json', 'password:', 'token='):
            self.assertNotIn(forbidden, text)


class ManagementWorksWithoutTheSkill(_Service):
    def test_skills_off_keep_the_settings_tools(self):
        caps = Capabilities(self.store, None, CFG, '', 'job', lambda *a: None, settings=lambda *a: {'state': 'read'})
        offered = {d['function']['name'] for d in caps.definitions()}
        self.assertTrue(SETTINGS_ACTIONS <= offered)
        self.assertFalse(SKILL_ACTIONS & offered)
        draft = self.settings.propose('owner', 'web', 'family', 'add', '셋째 비서')
        self.assertEqual(draft['state'], 'awaiting-confirmation')


class RepeatedCreationMakesNoDuplicate(_Service):
    def test_a_paired_assistant_of_the_same_name_is_not_created_again(self):
        for value in ('아내 비서', ' 아내   비서 ', '아내 비서'.upper()):
            with self.subTest(value=value), self.assertRaisesRegex(SettingsError, '이미 있어요'):
                self.settings.propose('owner', 'web', 'family', 'add', value)
        with self.assertRaisesRegex(SettingsError, 'family-1'):
            self.settings.propose('owner', 'web', 'family', 'add', '아내 비서')
        self.assertEqual(self.started, [])

    def test_an_unfinished_setup_may_be_asked_for_again(self):
        draft = self.settings.propose('owner', 'web', 'family', 'add', '둘째 비서')
        result = self.settings.confirm('owner', 'web', draft['draft_id'], draft['digest'])
        self.assertEqual((result['state'], self.started), ('requested', ['둘째 비서']))

    def test_the_owners_own_assistant_name_is_not_reused(self):
        with self.assertRaisesRegex(SettingsError, '이미 있어요'):
            self.settings.propose('owner', 'web', 'family', 'add', '내 비서')


class ScriptedRunFollowsTheService(_Service):
    def test_completion_rests_on_the_settings_result_not_the_skill(self):
        """Load the skill, read, propose: the report says the change waits for the owner; nothing was created."""
        library = SkillLibrary(self.store)
        library.set_enabled(True)
        binding = library.binding()
        script = Script({'tool_calls': [call('s1', 'skill_load', skill=SKILL)]},
                        {'tool_calls': [call('r1', 'settings_read', category='family')]},
                        {'tool_calls': [call('c1', 'settings_change', category='family', setting='add', value='셋째 비서',
                                             reason='가족 비서를 만들어 달라고 하셨어요.')]},
                        finish('f', 'c1', summary='셋째 비서 만들기를 확인해 주세요.'))
        adapter = ModelAdapter(script)
        events = []
        handler = self.settings.work_tools('owner', 'web', 'job')
        caps = Capabilities(self.store, adapter, CFG, '', 'job', lambda *a: events.append(a), skills=binding,
                            settings=handler, judgments=judgments(True))
        result = run_agent(adapter, CFG, '', [{'role': 'user', 'content': '셋째 비서 만들어줘'}], '', caps,
                           lambda *a: events.append(a))
        # The existing #814 contract, unchanged by the skill: the Work delivered a draft, and its report
        # lists the change itself as waiting for the owner, from the settings service's own result.
        waiting = dict(result.report['failed'])
        self.assertIn('settings_change', waiting)
        self.assertIn('확인을 기다립니다', waiting['settings_change'])
        self.assertEqual(self.started, [], 'nothing was created without the owner confirming')
        drafted = [json.loads(detail) for tool, status, detail in events if tool == 'settings_change']
        self.assertTrue(drafted)
        self.assertEqual(self.settings.pending_for_work('job')[0]['after'], '셋째 비서')


if __name__ == '__main__':
    unittest.main()

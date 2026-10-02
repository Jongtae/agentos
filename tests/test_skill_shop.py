"""SKILL-SHOP-01 (#963): shopping and site know-how as skill content over the unchanged browser port.

Evidence classes: content checks, and model-free scripted runs on the
deterministic fixture shop of ``test_browser_session`` (its FakeDriver records
every form post). A fake GitHub transport serves this repository's own
``skills/`` folders. No live site, account, model or network is used, and
fixtures prove contracts, not Emart success rates.

Reused, not repeated here:

* browser mediation, payment guard, login continuation, budget: ``test_browser_session``;
* skill revocation, routes, containment, off path: ``test_skill_supply``;
* no core branch on a site or skill: ``test_no_scenario_code``.
"""
import io
import json
import re
import tarfile
import tempfile
import unittest
from pathlib import Path

from personal_agent.agent_runtime import BROWSER_ACTIONS, SKILL_ACTIONS, Capabilities, ToolError, run_agent, turn_context
from personal_agent.plugins import PluginRegistry
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_store import QuickStore
from personal_agent.skills import SkillLibrary, inspect_skill
from test_agency_loop import judgments
from test_browser_session import CFG, ORIGIN, FakeDriver, Script, call

ROOT = Path(__file__).resolve().parents[1]
REPO, COMMIT = 'Jongtae/agentos', 'a' * 40
SHOPPING, SITE = 'shopping-cart', 'emart-ssg'
FIXTURE_SITE = Path(__file__).resolve().parent / 'fixtures' / 'skills' / 'fixture-mart'


def archive(folders):
    """A codeload-shaped tarball of ``{repo path: local folder}``."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        for prefix, folder in folders.items():
            for path in sorted(Path(folder).rglob('*')):
                if path.is_file():
                    data = path.read_bytes()
                    info = tarfile.TarInfo(f"agentos-{COMMIT}/{prefix}/{path.relative_to(folder).as_posix()}")
                    info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class GitHub:
    def __init__(self):
        self.data = archive({f'skills/{SHOPPING}': ROOT / 'skills' / SHOPPING, f'skills/{SITE}': ROOT / 'skills' / SITE,
                             'tests/fixtures/skills/fixture-mart': FIXTURE_SITE})

    def __call__(self, url, limit=None, timeout=None):
        if url.startswith('https://api.github.com/'):
            return COMMIT.encode()
        return self.data


def address(path):
    return f'https://github.com/{REPO}/tree/main/{path}'


class ReferencePackages(unittest.TestCase):
    def test_both_packages_are_supported_instruction_only_content(self):
        for name in (SHOPPING, SITE):
            with self.subTest(skill=name):
                record = inspect_skill(ROOT / 'skills' / name)
                self.assertEqual(record['status'], ['supported_as_is'])
                self.assertEqual(record['licence'], 'AGPL-3.0-only')

    def test_the_method_carries_the_contract_and_the_site_carries_only_site_facts(self):
        method = '\n'.join(path.read_text() for path in sorted((ROOT / 'skills' / SHOPPING).rglob('*.md')))
        for phrase in ('Read the cart back', 'click once per unit, and read the quantity after each click', 'read the cart before doing anything else', '**Add** N',
                       '**Set** the total to N', '**Ensure** at least N', 'do not pick a substitute silently',
                       'Do not send a cart link as proof', 'AgentOS refuses it'):
            self.assertIn(phrase, method)
        self.assertNotRegex(method.lower(), r'emart|ssg|coupang|kurly', 'the method names no site')
        site = (ROOT / 'skills' / SITE / 'SKILL.md').read_text()
        self.assertIn('Follow the `shopping-cart` skill for the method', site)
        self.assertIn('**Provenance:**', site)
        for text in (method, site):
            self.assertNotRegex(text, r'(?i)password\s*[:=]|cookie\s*[:=]|card number|cvc\s*[:=]')

    def test_the_bundled_guide_points_at_the_reference_skills(self):
        guide = (ROOT / 'src' / 'personal_agent' / 'bundled_skills' / 'agentos-skills' / 'SKILL.md').read_text()
        for name in (SHOPPING, SITE):
            self.assertIn(address(f'skills/{name}'), guide)


class _Shop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = QuickStore(Path(self.tmp.name) / 'data')
        PluginRegistry(self.store.root)
        self.library = SkillLibrary(self.store, transport=GitHub())
        self.events = []

    def record(self, tool, status, detail):
        self.events.append((tool, status, detail))

    def install(self, *paths):
        for path in paths:
            self.library.install(address(path))
        self.library.set_enabled(True)
        return self.library.binding()

    def caps(self, script, driver, **kwargs):
        return Capabilities(self.store, ModelAdapter(script), CFG, '', 'job', self.record, browser=lambda: driver, **kwargs)


class FirstUseOnAFreshStore(_Shop):
    def flow(self, site_skill):
        return [{'tool_calls': [call('s1', 'skill_load', skill=f'{SHOPPING}/{SHOPPING}')]},
                {'tool_calls': [call('s2', 'skill_load', skill=site_skill)]},
                {'tool_calls': [call('1', 'browser_open', url=ORIGIN + '/cart', effect='read')]},
                {'tool_calls': [call('2', 'browser_open', url=ORIGIN + '/product', effect='navigate')]},
                {'tool_calls': [call('3', 'browser_find', text='세탁세제')]},
                {'tool_calls': [call('4', 'browser_click', target='장바구니', effect='mutate')]},
                {'tool_calls': [call('5', 'browser_open', url=ORIGIN + '/cart', effect='read')]},
                {'tool_calls': [call('6', 'finish', status='done', evidence_refs=['5'],
                                     summary='장바구니에 세탁세제 3L × 1이 있습니다.')]}]

    def test_supplied_knowledge_is_used_on_the_first_request_with_one_change_and_a_readback(self):
        binding = self.install(f'skills/{SHOPPING}', 'tests/fixtures/skills/fixture-mart')
        script, driver = Script(*self.flow('fixture-mart/fixture-mart')), FakeDriver()
        caps = self.caps(script, driver, skills=binding, judgments=judgments(True))
        context = turn_context([{'role': 'user', 'content': '세탁세제 장바구니에 담아줘'}], 'api', skills=binding.catalogue_text())
        result = run_agent(caps.adapter, CFG, '', [{'role': 'user', 'content': context['request']}], context['skills'], caps,
                           self.record)
        self.assertEqual(result.outcome, 'succeeded')
        self.assertEqual(driver.posts, [('post', '/cart')], 'exactly one change')
        loads = [json.loads(d)['evidence'] for t, s, d in self.events if t == 'skill_load' and s == 'succeeded']
        self.assertEqual([row['skill'] for row in loads], [f'{SHOPPING}/{SHOPPING}', 'fixture-mart/fixture-mart'])
        self.assertTrue(all(row['revision'] == COMMIT for row in loads), 'pinned, attributable identity')
        reads = [json.loads(d)['evidence'] for t, s, d in self.events if t == 'browser_open' and s == 'succeeded']
        self.assertEqual(reads[-1]['url'], ORIGIN + '/cart', 'the claim rests on the cart read after the change')
        self.assertEqual([e for e in self.events if e[1] == 'failed'], [])
        # #964 item 10: supplied knowledge adds no planner, translator or verifier model call.
        self.assertEqual(len(script.bodies), 8, 'one model call per scripted step, nothing more')
        caps.close_browser()

    def test_the_same_method_works_with_the_published_site_package_without_core_edits(self):
        binding = self.install(f'skills/{SHOPPING}', f'skills/{SITE}')
        self.assertEqual(sorted(binding.entries), ['agentos/agentos-management', 'agentos/agentos-skills',
                                                   f'{SITE}/{SITE}', f'{SHOPPING}/{SHOPPING}'])
        loaded = self.caps(Script(), FakeDriver(), skills=binding).execute('skill_load', {'skill': f'{SITE}/{SITE}'})
        self.assertIn('pay.ssg.com/cart/dmsShpp.ssg', loaded['instructions'])


class RepeatUsesTheInstalledRevision(_Shop):
    def test_a_later_request_reuses_the_pinned_revision_without_fetching(self):
        """#964 item 3: a repeat reuses the method; the next Work's facts are read again from the page."""
        first = self.install(f'skills/{SHOPPING}')
        fetches = []
        self.library.transport = lambda url, **kwargs: fetches.append(url) or b''
        second = self.library.binding()
        self.assertEqual(second.entries[f'{SHOPPING}/{SHOPPING}']['digest'], first.entries[f'{SHOPPING}/{SHOPPING}']['digest'])
        self.assertTrue(second.load(f'{SHOPPING}/{SHOPPING}')['instructions'])
        self.assertEqual(fetches, [], 'no supplier call on repeat')


class BrowserPortIsPreserved(_Shop):
    def test_without_skills_the_browser_tools_are_unchanged(self):
        caps = self.caps(Script(), FakeDriver())
        offered = {d['function']['name'] for d in caps.definitions()}
        self.assertTrue(BROWSER_ACTIONS <= offered)
        self.assertFalse(SKILL_ACTIONS & offered)

    def test_each_reference_package_is_removable_on_its_own(self):
        self.install(f'skills/{SHOPPING}', f'skills/{SITE}')
        self.library.remove(SITE)
        self.assertEqual(sorted(self.library.binding().entries),
                         ['agentos/agentos-management', 'agentos/agentos-skills', f'{SHOPPING}/{SHOPPING}'])

    def test_withdrawing_the_method_mid_flow_stops_the_next_click_before_it_reaches_the_shop(self):
        binding = self.install(f'skills/{SHOPPING}')
        driver = FakeDriver()
        caps = self.caps(Script(), driver, skills=binding)
        caps.execute('skill_load', {'skill': f'{SHOPPING}/{SHOPPING}'})
        caps.execute('browser_open', {'url': ORIGIN + '/product', 'effect': 'navigate'})
        self.library.remove(SHOPPING)
        with self.assertRaises(ToolError) as raised:
            caps.execute('browser_click', {'target': '장바구니', 'effect': 'mutate'})
        self.assertEqual(raised.exception.code, 'skill_revoked')
        self.assertEqual(driver.posts, [], 'no change reached the shop')
        caps.close_browser()

    def test_skill_text_never_carries_session_material(self):
        binding = self.install(f'skills/{SHOPPING}', f'skills/{SITE}')
        caps = self.caps(Script(), FakeDriver(), skills=binding)
        for skill in (f'{SHOPPING}/{SHOPPING}', f'{SITE}/{SITE}'):
            text = json.dumps(caps.execute('skill_load', {'skill': skill}), ensure_ascii=False)
            self.assertIsNone(re.search(r'(?i)set-cookie|sessionid|bearer ', text))



class OwnerAddsAReferenceSkillByName(_Shop):
    """#976 review P1: on a fresh install (skills off) the owner can still say "장보기 스킬 추가해줘"."""

    def setUp(self):
        super().setUp()
        from personal_agent.quickstart_service import AgentService
        from personal_agent.settings_orchestrator import SettingsOrchestrator
        self.service = AgentService(self.store)
        self.service.skill_transport = GitHub()
        self.settings = SettingsOrchestrator(self.store, service=self.service)

    def test_the_reference_skills_are_listed_while_skills_are_off(self):
        self.assertIsNone(self.service.skill_binding(), 'fresh install: skills off')
        read = self.settings.read('owner', 'skills')
        available = read['settings']['skills']['add']['available']
        self.assertEqual([(row['name'], row['installed']) for row in available], [(SHOPPING, False), (SITE, False)])
        self.assertNotIn('https://', json.dumps(read, ensure_ascii=False), 'no endpoint is reported')

    def test_adding_by_name_pins_the_commit_and_switches_skills_on_once_confirmed(self):
        draft = self.settings.propose('owner', 'web', 'skills', 'add', SHOPPING)
        self.assertEqual(draft['after'], f'https://github.com/{REPO}/tree/{COMMIT}/skills/{SHOPPING}')
        self.assertIn('함께 켭니다', draft['summary'])
        self.assertIsNone(self.service.skill_binding(), 'nothing changes before the owner confirms')
        applied = self.settings.confirm('owner', 'web', draft['draft_id'], draft['digest'])
        self.assertIn('스킬 사용도 켰어요', applied['response'])
        self.assertIn(f'{SHOPPING}/{SHOPPING}', self.service.skill_binding().entries)
        listed = self.settings.read('owner', 'skills')['settings']['skills']['add']['available']
        self.assertEqual([(row['name'], row['installed']) for row in listed], [(SHOPPING, True), (SITE, False)])

    def test_an_unknown_name_is_not_guessed(self):
        from personal_agent.settings_orchestrator import SettingsError
        with self.assertRaises(SettingsError):
            self.settings.propose('owner', 'web', 'skills', 'add', 'groceries')


if __name__ == '__main__':
    unittest.main()

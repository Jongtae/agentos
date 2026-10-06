"""UPSTREAM-KNOWLEDGE-01 (#1026): immutable content through the existing skill consumer.

The older fixture and active development copy are genuine upstream bytes. Only
the GitHub wire and worker provider are injected; production installation,
binding, capability dispatch and MCP tool delivery execute unchanged. This is
model-free compatibility evidence, not a claim of live model/design quality.
Generic withdrawal, tamper, restart and rollback coverage stays in
test_skill_supply; the rejected same-package update is the additional boundary.
"""
import hashlib
import json
from pathlib import Path

from personal_agent.agent_runtime import run_agent, turn_context
from personal_agent.bounded_execution import AgentOSMcpTools
from personal_agent.providers import ModelAdapter
from personal_agent.skills import SkillBinding, SkillError, inspect_skill
from test_skill_supply import CFG, FakeGitHub, Script, _Store, call, finish, judgments, tarball


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = 'anthropics/skills'
OLD = '2235be7c60b551f5de82ade908fd3816455afcda'
CANDIDATE = '41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f'
OLD_FOLDER = ROOT / 'tests' / 'fixtures' / 'skills' / 'frontend-design' / OLD / 'frontend-design'
CURRENT_FOLDER = ROOT / '.claude' / 'skills' / 'frontend-design'
SKILL = 'frontend-design/frontend-design'
LICENSE_HASH = '0d542e0c8804e39aa7f37eb00da5a762149dc682d7829451287e11b938e94594'
HASHES = {
    OLD: {'SKILL.md': '1608ea77fbb6fc30d13a97d12cfa8ebf31358d40f0dd97beed24829d6b3f45dd',
          'LICENSE.txt': LICENSE_HASH},
    CANDIDATE: {'SKILL.md': 'd91970639e9f5c37682ac7ab60094d35f1c7c1f38d731bd56396563aee10c1d3',
                'LICENSE.txt': LICENSE_HASH},
}
FOLDERS = {OLD: OLD_FOLDER, CANDIDATE: CURRENT_FOLDER}


def source(revision):
    return f'https://github.com/{UPSTREAM}/tree/{revision}/skills/frontend-design'


def files(folder):
    return {path.relative_to(folder).as_posix(): path.read_bytes()
            for path in folder.rglob('*') if path.is_file()}


def instructions(folder):
    # Independently delimit the known upstream frontmatter; compare the entire
    # delivered body, so a short sentinel cannot hide truncation or substitution.
    return (folder / 'SKILL.md').read_text().split('\n---\n', 1)[1].strip()


class ImmutableKnowledgeConsumer(_Store):
    def setUp(self):
        super().setUp()
        archives = {revision: tarball(UPSTREAM, revision,
                                     {f'skills/frontend-design/{name}': data
                                      for name, data in files(folder).items()})
                    for revision, folder in FOLDERS.items()}
        self.github = FakeGitHub(archives)
        self.library.transport = self.github
        self.library.set_enabled(True)

    def assert_delivered(self, revision):
        folder = FOLDERS[revision]
        binding = self.library.binding()
        entry = binding.entries[SKILL]
        self.assertEqual(files(self.library.folder(entry)), files(folder))
        caps = self.caps(skills=binding)
        loaded = caps.execute('skill_load', {'skill': SKILL})
        resource = caps.execute('skill_resource', {'skill': SKILL, 'path': 'LICENSE.txt'})
        self.assertEqual(loaded['revision'], revision)
        self.assertEqual(loaded['instructions'], instructions(folder))
        self.assertEqual(loaded['resources'], ['LICENSE.txt'])
        self.assertEqual(loaded['licence'], 'Apache-2.0 (LICENSE.txt)')
        self.assertEqual(resource['content'].encode(), (folder / 'LICENSE.txt').read_bytes())
        self.assertFalse(resource['truncated'])
        self.assertEqual(resource['digest'], loaded['digest'])
        # Reconstruct the real CLI binding from its references and compare the
        # actual MCP boundary's full payload with direct capability delivery.
        bridge = SkillBinding.from_refs(self.library, binding.refs())
        tools = AgentOSMcpTools(self.caps(skills=bridge))
        self.assertTrue({'skill_load', 'skill_resource'} <= {tool['name'] for tool in tools.definitions()})
        self.assertEqual(tools.call('skill_load', {'skill': SKILL}), loaded)
        self.assertEqual(tools.call('skill_resource', {'skill': SKILL, 'path': 'LICENSE.txt'}), resource)
        return loaded

    def test_exact_external_bytes_and_licence_are_preserved(self):
        for revision, folder in FOLDERS.items():
            with self.subTest(revision=revision):
                content = files(folder)
                self.assertEqual({name: hashlib.sha256(data).hexdigest() for name, data in content.items()},
                                 HASHES[revision])
                record = inspect_skill(folder)
                self.assertEqual(record['status'], ['supported_as_is'])
                self.assertEqual(record['licence'], 'Apache-2.0 (LICENSE.txt)')
                self.assertEqual(record['files'], HASHES[revision])
        self.assertNotEqual(instructions(OLD_FOLDER), instructions(CURRENT_FOLDER))
        self.assertEqual((OLD_FOLDER / 'LICENSE.txt').read_bytes(),
                         (CURRENT_FOLDER / 'LICENSE.txt').read_bytes())

    def test_genuine_old_to_candidate_update_delivers_complete_content(self):
        prior_digest = None
        for revision in (OLD, CANDIDATE):
            with self.subTest(revision=revision):
                manifest = self.library.install(source(revision))
                self.assertEqual(manifest['source']['revision'], revision)
                self.assertEqual(manifest['skills'][0]['files'], HASHES[revision])
                self.assertEqual((manifest['tools'], manifest['roles']), ([], []))
                delivered = self.assert_delivered(revision)
                if prior_digest is not None:
                    self.assertNotEqual(prior_digest, delivered['digest'])
                    retained = self.library.content / prior_digest / 'frontend-design'
                    self.assertEqual(files(retained), files(OLD_FOLDER))
                prior_digest = delivered['digest']
        self.assertEqual(self.github.urls, [f'https://codeload.github.com/{UPSTREAM}/tar.gz/{revision}'
                                           for revision in (OLD, CANDIDATE)])

    def test_scripted_worker_receives_selected_instructions_and_resource(self):
        for revision in (OLD, CANDIDATE):
            with self.subTest(revision=revision):
                self.library.install(source(revision))
                binding = self.library.binding()
                script = Script({'tool_calls': [call('load', 'skill_load', skill=SKILL)]},
                                {'tool_calls': [call('license', 'skill_resource', skill=SKILL, path='LICENSE.txt')]},
                                finish('done', 'load', 'license', summary='Read the selected design guidance and licence.'))
                adapter = ModelAdapter(script)
                caps = self.caps(skills=binding, judgments=judgments(True))
                caps.adapter = adapter
                context = turn_context([{'role': 'user', 'content': 'Read the selected frontend design guidance and licence.'}],
                                       'api', skills=binding.catalogue_text())
                result = run_agent(adapter, CFG, '', [{'role': 'user', 'content': context['request']}],
                                   context['skills'], caps, lambda *args: None)
                self.assertEqual(result.outcome, 'succeeded')
                self.assertIn(SKILL, script.bodies[0]['messages'][0]['content'])
                self.assertNotIn(instructions(FOLDERS[revision]), json.dumps(script.bodies[0]))
                self.assertTrue({'skill_load', 'skill_resource'} <=
                                {tool['function']['name'] for tool in script.bodies[0]['tools']})
                observations = {message['tool_call_id']: json.loads(message['content'])
                                for message in script.bodies[-1]['messages'] if message['role'] == 'tool'}
                self.assertEqual(observations['load']['instructions'], instructions(FOLDERS[revision]))
                self.assertEqual(observations['load']['revision'], revision)
                self.assertEqual(observations['license']['content'].encode(),
                                 (FOLDERS[revision] / 'LICENSE.txt').read_bytes())

    def test_installed_candidate_remains_usable_when_source_is_offline(self):
        self.library.install(source(CANDIDATE))
        urls = list(self.github.urls)
        self.github.offline = True
        self.assert_delivered(CANDIDATE)
        self.assertEqual(self.github.urls, urls)

    def test_unsupported_same_package_update_preserves_known_good_versions(self):
        old = self.library.install(source(OLD))
        current = self.library.install(source(CANDIDATE))
        manifest_path = self.library.root / 'frontend-design.json'
        manifest_bytes = manifest_path.read_bytes()
        retained = {revision: self.library.content / manifest['skills'][0]['digest'] / 'frontend-design'
                    for revision, manifest in ((OLD, old), (CANDIDATE, current))}
        before = {revision: files(folder) for revision, folder in retained.items()}
        active = self.caps(skills=self.library.binding())
        active.execute('skill_load', {'skill': SKILL})
        for index, unsupported in enumerate(('scripts/run.py', 'hooks/pre.sh')):
            with self.subTest(content=unsupported):
                # Explicitly synthetic adverse revisions, never upstream update evidence.
                synthetic = str(index + 7) * 40
                candidate = {f'skills/frontend-design/{name}': data
                             for name, data in files(CURRENT_FOLDER).items()}
                candidate[f'skills/frontend-design/{unsupported}'] = b'# executable fixture; never executed\n'
                self.github.archives[synthetic] = tarball(UPSTREAM, synthetic, candidate)
                with self.assertRaises(SkillError) as raised:
                    self.library.install(source(synthetic))
                self.assertEqual(raised.exception.code, 'unsupported')
                self.assertIn('스크립트나 훅', str(raised.exception))
                self.assertEqual(manifest_path.read_bytes(), manifest_bytes)
                self.assertEqual(self.library.installed(), [current])
                for revision, folder in retained.items():
                    self.assertEqual(files(folder), before[revision])
                self.assertEqual(active.execute('skill_load', {'skill': SKILL})['revision'], CANDIDATE)
                self.assertEqual(self.assert_delivered(CANDIDATE)['digest'], current['skills'][0]['digest'])
                self.assertFalse(any(self.library.root.glob('*.json.tmp')))

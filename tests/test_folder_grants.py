import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from personal_agent import folder_grants
from personal_agent.agent_runtime import Capabilities
from personal_agent.file_workspace import FileWorkspace
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore


class FolderGrantTests(unittest.TestCase):
    """Both grant entry points refuse the same folders with distinct reasons."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        self.home = base / 'home' / 'owner'
        self.home.mkdir(parents=True)
        self.patches = [mock.patch.object(Path, 'home', return_value=self.home),
                        mock.patch.dict(os.environ, {'HOME': str(self.home)})]
        for patch in self.patches:
            patch.start()
        self.store = QuickStore(base / 'data')
        self.service = AgentService(self.store)
        self.docs = self.home / 'Documents' / 'Research'
        self.docs.mkdir(parents=True)
        self.out = self.home / 'Documents' / 'Results'
        self.out.mkdir()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.tmp.cleanup()

    def refuse_both(self, value, message):
        with self.assertRaisesRegex(ValueError, message):
            self.service.save_roots({'paths': [value]})
        with self.assertRaisesRegex(ValueError, message):
            FileWorkspace(self.store).configure([value], str(self.out))
        with self.assertRaisesRegex(ValueError, message):
            FileWorkspace(self.store).configure([str(self.docs)], value)

    def test_sensitive_credential_folders_are_refused_itself_inside_and_as_ancestor(self):
        (self.home / '.ssh' / 'keys').mkdir(parents=True)
        (self.home / 'Library' / 'Keychains').mkdir(parents=True)
        for value in (self.home / '.ssh', self.home / '.ssh' / 'keys', self.home / 'Library'):
            with self.subTest(value=value):
                self.refuse_both(str(value), folder_grants.SENSITIVE)

    def test_system_configuration_folder_is_refused(self):
        etc = Path('/etc').resolve()
        if not etc.is_dir():
            self.skipTest('no /etc on this platform')
        self.refuse_both(str(etc), folder_grants.SENSITIVE)

    def test_broad_folders_are_refused(self):
        for value in ('/', str(self.home), str(self.home.parent), str(self.store.private)):
            with self.subTest(value=value):
                self.refuse_both(value, folder_grants.BROAD)

    def test_each_refusal_class_has_its_own_message(self):
        (self.docs / 'note.txt').write_text('x')
        link = self.home / 'Documents' / 'link'
        link.symlink_to(self.docs, target_is_directory=True)
        cases = {str(self.home / 'missing'): '폴더를 찾을 수 없습니다',
                 str(self.docs / 'note.txt'): '폴더가 아닙니다',
                 'Documents/Research': '전체 경로',
                 str(link): '심볼릭 링크',
                 '   ': '폴더 경로를 입력하세요'}
        for value, message in cases.items():
            with self.subTest(value=value):
                self.refuse_both(value, message)

    def test_tilde_expands_the_same_way_for_both_entry_points(self):
        roots = self.service.save_roots({'paths': ['~/Documents/Research']})['roots']
        self.assertEqual([root['path'] for root in roots], [str(self.docs)])
        status = FileWorkspace(self.store).configure(['~/Documents/Research'], '~/Documents/Results')
        self.assertEqual([ref['path'] for ref in status['references']], [str(self.docs)])
        self.assertEqual(status['workspace'], str(self.out))

    def test_duplicate_paths_are_stored_once(self):
        roots = self.service.save_roots({'paths': [str(self.docs), str(self.docs) + '/', '~/Documents/Research']})['roots']
        self.assertEqual(len(roots), 1)
        status = FileWorkspace(self.store).configure([str(self.docs), str(self.docs) + '/'], str(self.out))
        self.assertEqual(len(status['references']), 1)

    def test_stored_grants_now_forbidden_are_blocked_at_use_and_disclosed(self):
        ssh = self.home / '.ssh'
        ssh.mkdir()
        (ssh / 'id.txt').write_text('secret')
        self.service.save_roots({'paths': [str(self.docs)]})
        self.store.put('file_roots', self.store.config('file_roots') + [{'id': 'legacy', 'path': str(ssh)}])
        self.store.put('file_workspace', {'references': [{'id': 'legacy-ref', 'path': str(ssh)}],
                                          'workspace': str(ssh), 'workspace_id': 'legacy-out'})

        caps = Capabilities(self.store, None, {}, '', 'job', lambda *args: None)
        self.assertEqual([root['path'] for root in caps.roots()], [str(self.docs)])
        with self.assertRaisesRegex(ValueError, '먼저 연결 설정'):
            caps.resolve_file('legacy', 'id.txt')

        workspace = FileWorkspace(self.store)
        self.assertEqual(workspace.active()['references'], [])
        self.assertIsNone(workspace.active()['workspace'])
        with self.assertRaises(ValueError):
            workspace.read('legacy-ref', 'id.txt')
        with self.assertRaisesRegex(ValueError, '관리 작업공간을 먼저'):
            workspace._workspace_id()

        settings = self.service.settings()
        blocked = {root['path']: root['blocked'] for root in settings['file_roots']}
        self.assertIsNone(blocked[str(self.docs)])
        self.assertEqual(blocked[str(ssh)], folder_grants.SENSITIVE)
        self.assertEqual(settings['file_workspace']['references'][0]['blocked'], folder_grants.SENSITIVE)
        self.assertEqual(settings['file_workspace']['workspace_blocked'], folder_grants.SENSITIVE)
        self.assertEqual([root['path'] for root in self.store.config('file_roots')], [str(self.docs), str(ssh)],
                         'stored grants are not silently rewritten')

    def test_ordinary_owner_and_temporary_folders_stay_allowed(self):
        other = Path(self.tmp.name).resolve() / 'scratch'
        other.mkdir()
        roots = self.service.save_roots({'paths': [str(self.docs), str(other)]})['roots']
        self.assertEqual(len(roots), 2)
        self.assertEqual(FileWorkspace(self.store).configure([str(self.docs)], str(self.out))['workspace'], str(self.out))


if __name__ == '__main__':
    unittest.main()

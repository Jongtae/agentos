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


    def case_insensitive(self):
        probe = self.home / 'CaseProbe'
        probe.mkdir()
        try:
            return (self.home / 'caseprobe').exists()
        finally:
            probe.rmdir()

    def test_mixed_case_spellings_cannot_reach_a_sensitive_folder(self):
        if not self.case_insensitive():
            self.skipTest('case-sensitive filesystem')
        (self.home / '.ssh').mkdir()
        (self.home / 'Library' / 'Keychains').mkdir(parents=True)
        for value in ('~/.SSH', '~/library/keychains', '~/Library/KEYCHAINS', '~/LIBRARY'):
            with self.subTest(value=value):
                self.refuse_both(value, folder_grants.SENSITIVE)
        self.assertEqual(folder_grants.blocked(str(self.home / '.SSH'), self.store), folder_grants.SENSITIVE)
        self.refuse_both(str(self.home).upper() if str(self.home).upper() != str(self.home) else str(self.home), folder_grants.BROAD)

    def test_case_sensitive_volume_keeps_distinct_case_spelling_allowed(self):
        if self.case_insensitive():
            self.skipTest('case-insensitive filesystem')
        alternate=self.home/'.AWS'
        alternate.mkdir()
        self.assertIsNone(folder_grants.blocked(str(alternate),self.store))
        self.assertEqual(self.service.save_roots({'paths':[str(alternate)]})['roots'][0]['path'],str(alternate))

    def test_case_sensitive_volume_allows_directory_with_home_case_variant(self):
        if self.case_insensitive():
            self.skipTest('case-insensitive filesystem')
        alternate=self.home.with_name(self.home.name.swapcase())
        alternate.mkdir()
        self.assertIsNone(folder_grants.blocked(str(alternate),self.store))
        self.assertEqual(self.service.save_roots({'paths':[str(alternate)]})['roots'][0]['path'],str(alternate))

    def test_case_sensitivity_is_probed_once_per_validation(self):
        with mock.patch.object(folder_grants,'_case_insensitive',wraps=folder_grants._case_insensitive) as probe:
            folder_grants.validate(str(self.docs),self.store)
        self.assertEqual(probe.call_count,1)

    def test_blocked_stored_roots_do_not_prevent_other_changes(self):
        ssh, aws = self.home / '.ssh', self.home / '.aws'
        ssh.mkdir(); aws.mkdir()
        self.store.put('file_roots', [{'id': 'a', 'path': str(ssh)}, {'id': 'b', 'path': str(aws)}, {'id': 'c', 'path': str(self.docs)}])
        roots = self.service.save_roots({'paths': [str(ssh), str(aws)]})['roots']
        self.assertEqual([root['path'] for root in roots], [str(ssh), str(aws)], 'an ordinary folder can be removed while blocked roots remain')
        roots = self.service.save_roots({'paths': [str(aws)]})['roots']
        self.assertEqual([root['path'] for root in roots], [str(aws)], 'one blocked folder can be removed while another remains')
        roots = self.service.save_roots({'paths': [str(aws), str(self.docs)]})['roots']
        self.assertEqual([root['path'] for root in roots], [str(aws), str(self.docs)], 'the remaining blocked folder and an ordinary folder can be saved')
        self.assertEqual({root['path']: root['blocked'] for root in roots}[str(aws)], folder_grants.SENSITIVE, 'response discloses the block')
        roots = self.service.save_roots({'paths': [str(aws), str(self.docs), str(self.out)]})['roots']
        self.assertEqual(len(roots), 3, 'adding a folder works while a blocked one is still stored')
        with self.assertRaisesRegex(ValueError, folder_grants.SENSITIVE):
            self.service.save_roots({'paths': [str(ssh)]})

    def test_file_workspace_can_remove_blocked_references_incrementally(self):
        ssh, aws = self.home / '.ssh', self.home / '.aws'
        ssh.mkdir(); aws.mkdir()
        files=FileWorkspace(self.store)
        files.configure([str(self.docs)], str(self.out))
        original=files.status()
        blocked=[{'id':'ssh-ref','path':str(ssh)},{'id':'aws-ref','path':str(aws)}]
        self.store.put('file_workspace',{**original,'references':original['references']+blocked})
        other=self.home/'Documents'/'OtherResults'; other.mkdir()

        state=files.configure([str(self.docs),str(aws)],str(other))
        self.assertEqual([ref['path'] for ref in state['references']],[str(self.docs),str(aws)])
        state=files.configure([str(self.docs)],str(other))
        self.assertEqual([ref['path'] for ref in state['references']],[str(self.docs)])
        self.assertEqual(state['workspace'],str(other))

    def test_retained_unavailable_reference_still_prevents_workspace_overlap(self):
        reference=self.home/'Documents'/'OwnerFiles'/'Research'
        reference.parent.mkdir(); reference.mkdir()
        initial=FileWorkspace(self.store)
        initial.configure([str(reference)],str(self.out))
        reference.rmdir()
        parent=reference.parent
        with self.assertRaisesRegex(ValueError,'겹치지 않게 연결'):
            initial.configure([str(reference)],str(parent))

    def test_capabilities_rechecks_filesystem_after_roots_was_read(self):
        moved=self.home/'Documents'/'Moved'; target=self.home/'Documents'/'Other'
        moved.mkdir(); target.mkdir()
        self.service.save_roots({'paths':[str(moved)]})
        caps=Capabilities(self.store,None,{},'','job',lambda *args:None)
        self.assertEqual([root['path'] for root in caps.roots()],[str(moved)])
        moved.rmdir(); moved.symlink_to(target,target_is_directory=True)
        self.assertEqual(caps.roots(),[])
        with self.assertRaisesRegex(ValueError,'먼저 연결 설정'):
            caps.resolve_file(self.store.config('file_roots')[0]['id'],'anything.txt')

    def test_searches_skip_blocked_folders_and_blocked_output_refuses_saves(self):
        ssh = self.home / '.ssh'
        ssh.mkdir()
        (ssh / 'aurora.txt').write_text('Aurora secret')
        (self.docs / 'aurora.txt').write_text('Aurora launch plan')
        self.service.save_roots({'paths': [str(self.docs)]})
        self.store.put('file_roots', self.store.config('file_roots') + [{'id': 'legacy', 'path': str(ssh)}])
        hits = Capabilities(self.store, None, {}, '', 'job', lambda *args: None).find_files('Aurora')['files']
        self.assertEqual({hit['root_id'] for hit in hits}, {self.store.config('file_roots')[0]['id']})
        workspace = FileWorkspace(self.store)
        workspace.configure([str(self.docs)], str(self.out))
        status = workspace.status()
        self.store.put('file_workspace', {**status, 'references': status['references'] + [{'id': 'legacy-ref', 'path': str(ssh)}]})
        sources = workspace.find_references('Aurora')
        self.assertEqual([source['reference_id'] for source in sources], [status['references'][0]['id']])
        self.store.put('file_workspace', {**status, 'workspace': str(ssh)})
        with self.assertRaisesRegex(ValueError, '관리 작업공간을 먼저'):
            workspace.save('job-1', 'Notes', 'body', sources)
        self.assertEqual(list(ssh.iterdir()), [ssh / 'aurora.txt'], 'nothing written into the blocked folder')

    def test_stored_folder_later_replaced_by_symlink_into_a_sensitive_folder_is_blocked(self):
        (self.home / '.ssh').mkdir()
        moved = self.home / 'Documents' / 'Moved'
        moved.mkdir()
        self.service.save_roots({'paths': [str(moved)]})
        moved.rmdir()
        moved.symlink_to(self.home / '.ssh', target_is_directory=True)
        self.assertEqual(Capabilities(self.store, None, {}, '', 'job', lambda *args: None).roots(), [])

    def test_stored_folder_later_replaced_by_symlink_to_an_ordinary_folder_is_blocked(self):
        moved = self.home / 'Documents' / 'Moved'
        target = self.home / 'Documents' / 'Other'
        moved.mkdir()
        target.mkdir()
        self.service.save_roots({'paths': [str(moved)]})
        FileWorkspace(self.store).configure([str(moved)], str(self.out))
        moved.rmdir()
        moved.symlink_to(target, target_is_directory=True)

        self.assertEqual(folder_grants.blocked(str(moved), self.store), folder_grants.SYMLINK_CHANGED)
        self.assertEqual(Capabilities(self.store, None, {}, '', 'job', lambda *args: None).roots(), [])
        self.assertEqual(FileWorkspace(self.store).active()['references'], [])

    def test_store_subfolder_and_icloud_drive_stay_allowed(self):
        acceptance = self.store.root / 'acceptance-documents'
        acceptance.mkdir()
        icloud = self.home / 'Library' / 'Mobile Documents' / 'com~apple~CloudDocs'
        icloud.mkdir(parents=True)
        (self.home / 'Library' / 'Keychains').mkdir()
        roots = self.service.save_roots({'paths': [str(acceptance), str(icloud)]})['roots']
        self.assertEqual([root['blocked'] for root in roots], [None, None])


if __name__ == '__main__':
    unittest.main()

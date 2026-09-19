import tempfile
import unittest
from pathlib import Path

from personal_agent.file_workspace import FileWorkspace
from personal_agent.quickstart_store import QuickStore


class FileWorkspaceLanguageTests(unittest.TestCase):
    def test_bilingual_topic_alternatives_match_single_language_documents_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            refs=root/'references'; out=root/'workspace'; refs.mkdir(); out.mkdir()
            (refs/'english.md').write_text('Project launch decision and budget.',encoding='utf-8')
            (refs/'korean.md').write_text('프로젝트 출시 결정과 예산.',encoding='utf-8')
            (refs/'unrelated.md').write_text('Meeting room maintenance only.',encoding='utf-8')
            store=QuickStore(root/'state'); workspace=FileWorkspace(store)
            state=workspace.configure([str(refs)],str(out))
            hits=workspace.find_references('project||프로젝트')
            self.assertEqual({item['path'] for item in hits},{'english.md','korean.md'})
            self.assertEqual(state['references'][0]['path'],str(refs.resolve()))


if __name__ == '__main__': unittest.main()
